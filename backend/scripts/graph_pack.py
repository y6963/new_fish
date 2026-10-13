"""MiroFish 知识图谱「独立导出 / 恢复 / 校验」工具（图谱包 v1）。

设计目标：让一份图谱脱离 MiroFish 系统也能保存、展示、重建、验证、被别的系统直接查询。

一份「图谱包」是一个目录，内容自描述：

    manifest.json     格式版本、来源、计数、各文件 sha256
    nodes.jsonl       一行一个节点（含 uuid / 类型 / 摘要 / 属性 / 时间）
    edges.jsonl       一行一条关系（含 uuid / fact / 两端 / 时序字段 / 来源 episode）
    episodes.jsonl    一行一段原始文本（建图文档块 + 模拟活动记录）
    ontology.json     本体快照（Zep 上的实体类型 / 关系类型定义）
    checksums.sha256  各数据文件的校验和
    viewer.html       独立查看器（内联 d3 与全部数据，双击即可看，不联网不依赖系统）
    graph.db          可选：同一份数据的 SQLite 副本，任何语言可直接 SQL 查询

五个子命令：

    # 1) 导出
    ./.venv/bin/python scripts/graph_pack.py export --sim sim_xxxx
    ./.venv/bin/python scripts/graph_pack.py export --graph-id mirofish_xxxx --out-dir /tmp/pack

    # 2) 恢复到一张新的 Zep 图谱（结构级复制，不重跑大模型抽取）
    ./.venv/bin/python scripts/graph_pack.py restore --pack uploads/graph_packs/xxx \
        --graph-id mirofish_restored_1

    # 3) 校验恢复前后一致性
    ./.venv/bin/python scripts/graph_pack.py verify --pack uploads/graph_packs/xxx \
        --graph-id mirofish_restored_1

    # 4) 转成 SQLite（给别的系统直接查，不联网）
    ./.venv/bin/python scripts/graph_pack.py sqlite --pack uploads/graph_packs/xxx

    # 5) 离线重建查看器（改了数据后不用再拉云端）
    ./.venv/bin/python scripts/graph_pack.py viewer --pack uploads/graph_packs/xxx

说明：底层用的是 Zep 的 graph.add_nodes（直接建节点）
与 graph.add_fact_triple（直接建关系，可带 valid_at/invalid_at/expired_at），
因此恢复是「结构级复制」，不是重新让大模型从文本里抽一遍，一致性可量化验证。
注意 Zep 不允许自带节点 uuid，所以一致性以「名称 + 类型 + 事实文本」为口径。
"""

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)
load_dotenv(override=True)

from app.utils.zep import get_zep_client  # noqa: E402
from app.utils.zep_paging import fetch_all_nodes, fetch_all_edges  # noqa: E402

UPLOADS = os.path.join(BACKEND_DIR, "uploads")
PACK_ROOT = os.path.join(UPLOADS, "graph_packs")
FORMAT_NAME = "mirofish-graph-pack"
FORMAT_VERSION = 1
D3_PATH = os.path.join(ROOT_DIR, "frontend", "node_modules", "d3", "dist", "d3.min.js")


# ----------------------------- 通用工具 -----------------------------

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: str, rows) -> int:
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: str):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def resolve_source(args):
    """返回 (graph_id, project_id, simulation_id)"""
    if getattr(args, "graph_id", None):
        return args.graph_id, None, None
    if getattr(args, "project", None):
        p = os.path.join(UPLOADS, "projects", args.project, "project.json")
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("graph_id"), args.project, None
    if getattr(args, "sim", None):
        p = os.path.join(UPLOADS, "simulations", args.sim, "state.json")
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("graph_id"), data.get("project_id"), args.sim
    raise SystemExit("必须给 --graph-id，或用 --project / --sim 指定")


def find_ontology(project_id: str, graph_id: str):
    """从项目文件里找本体快照；找不到就返回空结构"""
    empty = {"entity_types": [], "edge_types": [], "source": None}
    if project_id:
        p = os.path.join(UPLOADS, "projects", project_id, "project.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            onto = data.get("ontology") or {}
            if onto:
                return {
                    "entity_types": onto.get("entity_types", []),
                    "edge_types": onto.get("edge_types", []),
                    "source": f"project:{project_id}",
                }
        return empty
    # 没给项目时，反查持有该 graph_id 的项目
    proj_root = os.path.join(UPLOADS, "projects")
    if os.path.isdir(proj_root):
        for pid in sorted(os.listdir(proj_root)):
            p = os.path.join(proj_root, pid, "project.json")
            if not os.path.exists(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if data.get("graph_id") == graph_id and data.get("ontology"):
                onto = data["ontology"]
                return {
                    "entity_types": onto.get("entity_types", []),
                    "edge_types": onto.get("edge_types", []),
                    "source": f"project:{pid}",
                }
    return empty


def main_label(labels):
    """取第一个非 Entity 的标签作为主类型"""
    for l in labels or []:
        if l and l != "Entity":
            return l
    return None


def _s(v):
    return str(v) if v else None


# ----------------------------- 1) 导出 -----------------------------

def cmd_export(args):
    graph_id, project_id, sim_id = resolve_source(args)
    print(f"graph_id = {graph_id}")
    client = get_zep_client()

    print("  拉取节点 ...", flush=True)
    nodes_raw = fetch_all_nodes(client, graph_id)
    print("  拉取关系 ...", flush=True)
    edges_raw = fetch_all_edges(client, graph_id)
    name_map = {n.uuid_: (n.name or "") for n in nodes_raw}

    nodes = [{
        "uuid": n.uuid_,
        "name": n.name or "",
        "labels": list(n.labels or []),
        "label": main_label(n.labels),
        "summary": n.summary or "",
        "attributes": dict(n.attributes or {}),
        "created_at": _s(getattr(n, "created_at", None)),
    } for n in nodes_raw]

    edges = []
    for e in edges_raw:
        eps = getattr(e, "episodes", None) or getattr(e, "episode_ids", None) or []
        if eps and not isinstance(eps, list):
            eps = [str(eps)]
        else:
            eps = [str(x) for x in eps]
        edges.append({
            "uuid": e.uuid_,
            "name": e.name or "",
            "fact": e.fact or "",
            "source_node_uuid": e.source_node_uuid,
            "target_node_uuid": e.target_node_uuid,
            "source_node_name": name_map.get(e.source_node_uuid, ""),
            "target_node_name": name_map.get(e.target_node_uuid, ""),
            "attributes": dict(e.attributes or {}),
            "created_at": _s(getattr(e, "created_at", None)),
            "valid_at": _s(getattr(e, "valid_at", None)),
            "invalid_at": _s(getattr(e, "invalid_at", None)),
            "expired_at": _s(getattr(e, "expired_at", None)),
            "episodes": eps,
        })
    print(f"  节点 {len(nodes)} | 关系 {len(edges)}", flush=True)

    episodes = []
    if not args.no_episodes:
        print("  拉取原始文本 episode ...", flush=True)
        resp = client.graph.episode.get_by_graph_id(graph_id=graph_id, lastn=args.lastn)
        for ep in getattr(resp, "episodes", None) or []:
            episodes.append({
                "uuid": getattr(ep, "uuid_", None),
                "content": getattr(ep, "content", "") or "",
                "source_description": getattr(ep, "source_description", None) or "",
                "created_at": _s(getattr(ep, "created_at", None)),
                "source": getattr(ep, "source", None),
            })
        print(f"  episode {len(episodes)}", flush=True)

    out_dir = args.out_dir or os.path.join(
        PACK_ROOT, f"{graph_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)

    ontology = find_ontology(project_id, graph_id)
    files = {
        "nodes.jsonl": write_jsonl(os.path.join(out_dir, "nodes.jsonl"), nodes),
        "edges.jsonl": write_jsonl(os.path.join(out_dir, "edges.jsonl"), edges),
        "episodes.jsonl": write_jsonl(os.path.join(out_dir, "episodes.jsonl"), episodes),
    }
    with open(os.path.join(out_dir, "ontology.json"), "w", encoding="utf-8") as f:
        json.dump(ontology, f, ensure_ascii=False, indent=2)

    checksums = {name: sha256_file(os.path.join(out_dir, name)) for name in files}
    with open(os.path.join(out_dir, "checksums.sha256"), "w", encoding="utf-8") as f:
        for name, digest in checksums.items():
            f.write(f"{digest}  {name}\n")

    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "graph_id": graph_id,
            "project_id": project_id,
            "simulation_id": sim_id,
        },
        "counts": {"nodes": len(nodes), "edges": len(edges), "episodes": len(episodes)},
        "files": {
            name: {"sha256": checksums[name], "rows": files[name]} for name in files
        },
        "ontology_included": bool(ontology.get("entity_types")),
        "ontology": {
            "entity_types": [t.get("name") for t in ontology.get("entity_types", [])],
            "edge_types": [t.get("name") for t in ontology.get("edge_types", [])],
        },
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if not args.no_viewer:
        build_viewer(out_dir, manifest, nodes, edges, episodes)

    print(f"\n图谱包已生成: {out_dir}")
    print(f"  节点 {len(nodes)} | 关系 {len(edges)} | episode {len(episodes)}")
    print("  双击 viewer.html 即可脱离系统查看（不联网、不需要启动 MiroFish）")
    return out_dir


# ----------------------------- 2) 独立查看器 -----------------------------

VIEWER_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>知识图谱包 · __GRAPH_ID__</title>
<style>
  * { box-sizing: border-box; }
  body { margin:0; font-family:'Space Grotesk','Noto Sans SC',system-ui,sans-serif;
         background:#fff; color:#1a1a1a; }
  header { height:52px; border-bottom:1px solid #eaeaea; display:flex; align-items:center;
           gap:16px; padding:0 18px; }
  .title { font-weight:600; font-size:14px; }
  .stat { font-size:12px; color:#666; }
  input[type=search] { margin-left:auto; width:220px; padding:6px 10px; border:1px solid #ddd;
                       border-radius:6px; font-size:12px; }
  .wrap { display:flex; height:calc(100vh - 52px); }
  aside { width:190px; border-right:1px solid #eaeaea; padding:14px; overflow:auto; font-size:12px; }
  .legend-item { display:flex; align-items:center; gap:8px; padding:4px 0; cursor:pointer; }
  .legend-dot { width:10px; height:10px; border-radius:50%; }
  .legend-item.off { opacity:.35; }
  main { flex:1; position:relative; }
  svg { width:100%; height:100%; }
  .detail { position:absolute; top:12px; right:12px; width:300px; max-height:calc(100% - 24px);
            overflow:auto; background:#fff; border:1px solid #e5e5e5; border-radius:10px;
            padding:14px; font-size:12px; line-height:1.6; }
  .detail h3 { margin:0 0 8px; font-size:13px; }
  .kv { color:#666; }
  .badge { display:inline-block; padding:1px 8px; border-radius:10px; color:#fff; font-size:11px; }
  .node-label { font-size:10px; fill:#333; pointer-events:none; }
  .link { fill:none; stroke:#bbb; stroke-width:1; }
  footer { position:absolute; left:12px; bottom:12px; font-size:11px; color:#999; }
</style>
</head>
<body>
<header>
  <span class="title">知识图谱包 · __GRAPH_ID__</span>
  <span class="stat">节点 <b id="nc"></b> · 关系 <b id="ec"></b> · 原文 <b id="pc"></b></span>
  <input type="search" id="q" placeholder="搜索节点名，回车定位">
</header>
<div class="wrap">
  <aside><div style="font-weight:600;margin-bottom:8px">实体类型（点击隐藏/显示）</div><div id="legend"></div></aside>
  <main>
    <svg id="svg"></svg>
    <div class="detail" id="detail" style="display:none"></div>
    <footer>本文件自包含：数据已内联，离线可用。导出时间 __EXPORTED_AT__</footer>
  </main>
</div>
<script>__D3__</script>
<script>
const DATA = __PAYLOAD__;
const nodes = DATA.nodes, edges = DATA.edges, episodes = DATA.episodes;
document.getElementById('nc').textContent = nodes.length;
document.getElementById('ec').textContent = edges.length;
document.getElementById('pc').textContent = episodes.length;

const types = [];
nodes.forEach(n => { const t = n.label || 'Entity'; if (!types.includes(t)) types.push(t); });
const palette = ['#FF6B35','#004E89','#7B2D8E','#1A936F','#C5283D','#E9724C','#3498db','#9b59b6','#27ae60','#f39c12','#888780'];
const color = {}; types.forEach((t,i) => color[t] = palette[i % palette.length]);
const hidden = new Set();

const legend = document.getElementById('legend');
types.forEach(t => {
  const div = document.createElement('div');
  div.className = 'legend-item';
  div.innerHTML = '<span class="legend-dot" style="background:' + color[t] + '"></span>' +
                  '<span>' + t + '</span>';
  div.onclick = () => { hidden.has(t) ? hidden.delete(t) : hidden.add(t);
                        div.classList.toggle('off'); render(); };
  legend.appendChild(div);
});

const svg = d3.select('#svg');
let W = svg.node().clientWidth, H = svg.node().clientHeight;
const g = svg.append('g');
svg.call(d3.zoom().scaleExtent([0.1,6]).on('zoom', e => g.attr('transform', e.transform)));

let sim;
function render() {
  const keep = nodes.filter(n => !hidden.has(n.label || 'Entity'));
  const keepIds = new Set(keep.map(n => n.uuid));
  const links = edges.filter(e => keepIds.has(e.source_node_uuid) && keepIds.has(e.target_node_uuid))
                     .map(e => Object.assign({}, e));
  g.selectAll('*').remove();
  const link = g.append('g').selectAll('line').data(links).join('line')
    .attr('class','link').attr('stroke','#c9c9c9').attr('stroke-width',0.8)
    .on('click', (ev,d) => showEdge(d));
  const node = g.append('g').selectAll('circle').data(keep).join('circle')
    .attr('r', d => 4 + Math.min(6, (d.summary||'').length / 220))
    .attr('fill', d => color[d.label || 'Entity'])
    .attr('stroke','#fff').attr('stroke-width',1.2)
    .on('click', (ev,d) => showNode(d))
    .call(d3.drag().on('start',(ev,d)=>{if(!ev.active)sim.alphaTarget(0.2).restart();d.fx=d.x;d.fy=d.y;})
                   .on('drag',(ev,d)=>{d.fx=ev.x;d.fy=ev.y;})
                   .on('end',(ev,d)=>{if(!ev.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));
  const label = g.append('g').selectAll('text').data(keep).join('text')
    .attr('class','node-label').text(d => d.name).attr('dx',9).attr('dy',3);
  sim = d3.forceSimulation(keep)
    .force('link', d3.forceLink(links).id(d=>d.uuid).distance(80))
    .force('charge', d3.forceManyBody().strength(-160))
    .force('center', d3.forceCenter(W/2, H/2))
    .force('collide', d3.forceCollide(14))
    .on('tick', () => {
      link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
          .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
      node.attr('cx',d=>d.x).attr('cy',d=>d.y);
      label.attr('x',d=>d.x).attr('y',d=>d.y);
    });
}

function esc(s){ return (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function rows(obj){ return Object.keys(obj||{}).map(k =>
  '<div><span class="kv">'+esc(k)+':</span> '+esc(String(obj[k]))+'</div>').join(''); }

function showNode(d){
  const el = document.getElementById('detail');
  el.style.display='block';
  el.innerHTML = '<h3>'+esc(d.name)+'</h3>' +
    '<div><span class="badge" style="background:'+color[d.label||'Entity']+'">'+esc(d.label||'Entity')+'</span></div>' +
    '<div style="margin-top:8px">'+esc(d.summary)+'</div>' +
    (d.attributes && Object.keys(d.attributes).length ? '<hr>'+rows(d.attributes) : '') +
    '<hr><div class="kv">uuid: '+esc(d.uuid)+'</div>' +
    '<div class="kv">created_at: '+esc(d.created_at||'-')+'</div>';
}
function showEdge(d){
  const el = document.getElementById('detail');
  el.style.display='block';
  const eps = (d.episodes||[]).map(id => {
    const hit = episodes.find(e => e.uuid === id);
    return hit ? '<li>'+esc(hit.content.slice(0,180))+'</li>' : null;
  }).filter(Boolean).join('');
  el.innerHTML = '<h3>关系 · '+esc(d.name||'')+'</h3>' +
    '<div>'+esc(d.source_node_name)+' → '+esc(d.target_node_name)+'</div>' +
    '<div style="margin-top:8px">'+esc(d.fact)+'</div>' +
    '<hr><div class="kv">valid_at: '+esc(d.valid_at||'-')+'</div>' +
    '<div class="kv">invalid_at: '+esc(d.invalid_at||'-')+'</div>' +
    '<div class="kv">expired_at: '+esc(d.expired_at||'-')+'</div>' +
    (eps ? '<hr><div class="kv">来源原文：</div><ul style="padding-left:16px">'+eps+'</ul>' : '');
}
document.getElementById('q').addEventListener('change', e => {
  const kw = e.target.value.trim();
  if (!kw) return;
  const hit = nodes.find(n => (n.name||'').includes(kw));
  if (hit) showNode(hit);
});
render();
</script>
</body>
</html>
"""


def build_viewer(out_dir, manifest, nodes, edges, episodes):
    payload = json.dumps(
        {"nodes": nodes, "edges": edges, "episodes": episodes},
        ensure_ascii=False,
    ).replace("</script>", "<\\/script>")
    try:
        with open(D3_PATH, encoding="utf-8") as f:
            d3_src = f.read().replace("</script>", "<\\/script>")
    except OSError:
        d3_src = "/* d3 未找到，图无法渲染（数据仍可用 JSON 查看）*/"
    html = (VIEWER_TEMPLATE
            .replace("__GRAPH_ID__", manifest["source"]["graph_id"] or "")
            .replace("__EXPORTED_AT__", manifest["exported_at"])
            .replace("__D3__", d3_src)
            .replace("__PAYLOAD__", payload))
    path = os.path.join(out_dir, "viewer.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ----------------------------- 3) 恢复 -----------------------------

def _retry(fn, what, attempts=3, delay=2.0):
    last = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts:
                time.sleep(delay * i)
    raise RuntimeError(f"{what} 失败（重试 {attempts} 次）: {last}")


def load_pack(pack: str):
    """读一个图谱包：(manifest, nodes, edges, episodes)"""
    with open(os.path.join(pack, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    if manifest.get("format") != FORMAT_NAME:
        raise SystemExit(f"不是 MiroFish 图谱包: {pack}")
    return (
        manifest,
        read_jsonl(os.path.join(pack, "nodes.jsonl")),
        read_jsonl(os.path.join(pack, "edges.jsonl")),
        read_jsonl(os.path.join(pack, "episodes.jsonl")),
    )


def cmd_viewer(args):
    """离线重建 viewer.html：不访问云端，只把包里的数据重新内联进去"""
    pack = os.path.abspath(args.pack)
    manifest, nodes, edges, episodes = load_pack(pack)
    path = build_viewer(pack, manifest, nodes, edges, episodes)
    print(f"查看器已重建: {path}  "
          f"（节点 {len(nodes)} / 关系 {len(edges)} / 原文 {len(episodes)}，"
          f"{os.path.getsize(path) / 1024:.0f} KB）")


SQLITE_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE nodes (
  uuid TEXT PRIMARY KEY, name TEXT, label TEXT, labels TEXT,
  summary TEXT, attributes TEXT, created_at TEXT);
CREATE TABLE edges (
  uuid TEXT PRIMARY KEY, name TEXT, fact TEXT,
  source_uuid TEXT, source_name TEXT, target_uuid TEXT, target_name TEXT,
  attributes TEXT, created_at TEXT, valid_at TEXT, invalid_at TEXT, expired_at TEXT,
  episodes TEXT);
CREATE TABLE episodes (
  uuid TEXT PRIMARY KEY, source TEXT, source_description TEXT,
  content TEXT, created_at TEXT);
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_nodes_label ON nodes(label);
CREATE INDEX idx_edges_name ON edges(name);
CREATE INDEX idx_edges_src ON edges(source_name);
CREATE INDEX idx_edges_tgt ON edges(target_name);
CREATE VIEW v_relations AS
  SELECT e.name AS relation, e.fact, s.name AS source_name, s.label AS source_type,
         t.name AS target_name, t.label AS target_type,
         e.valid_at, e.invalid_at, e.expired_at, e.uuid AS edge_uuid
  FROM edges e
  LEFT JOIN nodes s ON s.uuid = e.source_uuid
  LEFT JOIN nodes t ON t.uuid = e.target_uuid;
"""


def cmd_sqlite(args):
    """把图谱包转成 SQLite：别的系统不用装 Zep、不用起服务，直接 SQL 查"""
    import sqlite3

    pack = os.path.abspath(args.pack)
    manifest, nodes, edges, episodes = load_pack(pack)
    out = args.out or os.path.join(pack, "graph.db")
    if os.path.exists(out):
        os.remove(out)

    conn = sqlite3.connect(out)
    conn.executescript(SQLITE_SCHEMA)

    def dumps(v):
        return json.dumps(v, ensure_ascii=False) if v else None

    conn.executemany(
        "INSERT INTO nodes VALUES (?,?,?,?,?,?,?)",
        [(n.get("uuid"), n.get("name"), n.get("label"), dumps(n.get("labels")),
          n.get("summary"), dumps(n.get("attributes")), n.get("created_at")) for n in nodes])
    conn.executemany(
        "INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(e.get("uuid"), e.get("name"), e.get("fact"), e.get("source_node_uuid"),
          e.get("source_node_name"), e.get("target_node_uuid"), e.get("target_node_name"),
          dumps(e.get("attributes")), e.get("created_at"), e.get("valid_at"),
          e.get("invalid_at"), e.get("expired_at"), dumps(e.get("episodes"))) for e in edges])
    conn.executemany(
        "INSERT INTO episodes VALUES (?,?,?,?,?)",
        [(p.get("uuid"), p.get("source"), p.get("source_description"),
          p.get("content"), p.get("created_at")) for p in episodes])

    meta = {
        "format": FORMAT_NAME,
        "format_version": str(FORMAT_VERSION),
        "source_graph_id": manifest["source"].get("graph_id") or "",
        "exported_at": manifest.get("exported_at", ""),
        "node_count": str(len(nodes)),
        "edge_count": str(len(edges)),
        "episode_count": str(len(episodes)),
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
    conn.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    conn.commit()

    print(f"SQLite 已生成: {out}  ({os.path.getsize(out) / 1024:.0f} KB)")
    for table in ("nodes", "edges", "episodes"):
        print(f"  {table}: {conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]}")
    print("\n可以直接查，例如：")
    print('  SELECT source_name, relation, target_name, fact FROM v_relations')
    print("  WHERE source_name LIKE '%特朗普%' LIMIT 20;")
    conn.close()


def wait_until_stable(client, graph_id, total=60, interval=20):
    """add_fact_triple 是异步任务，等边数稳定再校验"""
    last, waited = -1, 0
    while waited <= total:
        try:
            n = len(fetch_all_edges(client, graph_id))
        except Exception:  # noqa: BLE001
            n = -1
        print(f"    边数 {n}（已等 {waited}s）", flush=True)
        if n > 0 and n == last:
            return n
        last = n
        time.sleep(interval)
        waited += interval
    return last


def cmd_restore(args):
    pack = os.path.abspath(args.pack)
    manifest = json.load(open(os.path.join(pack, "manifest.json"), encoding="utf-8"))
    if manifest.get("format") != FORMAT_NAME:
        raise SystemExit(f"不是 MiroFish 图谱包: {pack}")

    if not args.skip_checksum:
        for name, meta in manifest["files"].items():
            p = os.path.join(pack, name)
            if not os.path.exists(p):
                raise SystemExit(f"缺少文件 {name}")
            if sha256_file(p) != meta["sha256"]:
                raise SystemExit(f"{name} 校验和不符，包可能已损坏（可用 --skip-checksum 跳过）")
        print("  校验和通过", flush=True)

    nodes_all = read_jsonl(os.path.join(pack, "nodes.jsonl"))
    edges = read_jsonl(os.path.join(pack, "edges.jsonl"))
    nodes = nodes_all
    if args.limit_nodes:
        nodes = nodes[:args.limit_nodes]
    if args.limit_edges:
        edges = edges[:args.limit_edges]

    if args.retry_failed:
        rep = os.path.join(pack, f"restore_report_{args.graph_id or ''}.json")
        if not os.path.exists(rep):
            raise SystemExit(f"找不到上一轮报告 {rep}，无法重试")
        prev = json.load(open(rep, encoding="utf-8"))
        failed = {x.get("uuid") for x in prev.get("edge_errors", []) if x.get("uuid")}
        edges = [e for e in edges if e.get("uuid") in failed]
        nodes = []
        print(f"  重试上一轮失败的关系 {len(edges)} 条（节点已存在，跳过节点写入）", flush=True)

    target = args.graph_id or f"{manifest['source']['graph_id']}_restored_{int(time.time())}"
    client = get_zep_client()

    existing = None
    try:
        existing = client.graph.get(graph_id=target)
    except Exception:  # noqa: BLE001
        existing = None
    if existing is not None and not args.force and not args.retry_failed:
        raise SystemExit(f"目标图谱 {target} 已存在。换一个 --graph-id，或加 --force 追加写入。")

    if existing is None:
        print(f"  创建图谱 {target} ...", flush=True)
        _retry(lambda: client.graph.create(graph_id=target), "创建图谱")

    ontology_path = os.path.join(pack, "ontology.json")
    if not args.no_ontology and os.path.exists(ontology_path):
        with open(ontology_path, encoding="utf-8") as f:
            onto = json.load(f)
        if onto.get("entity_types"):
            try:
                from app.services.graph_builder import GraphBuilderService
                from app.config import Config
                GraphBuilderService(api_key=Config.ZEP_API_KEY).set_ontology(target, onto)
                print(f"  本体已恢复（{len(onto['entity_types'])} 类实体 / "
                      f"{len(onto.get('edge_types', []))} 类关系）", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  本体恢复失败（继续恢复数据）: {e}", flush=True)

    from zep_cloud import AddNodeItem

    # Zep 的三条硬限制（实测）：节点 uuid 由服务端分配；summary ≤ 500；fact ≤ 250。
    MAX_SUMMARY = 500
    MAX_FACT = 250
    node_index = {n["uuid"]: n for n in nodes_all}
    truncated = 0
    fact_truncated = 0

    def clip(text):
        nonlocal truncated
        if text and len(text) > MAX_SUMMARY:
            truncated += 1
            return text[:MAX_SUMMARY]
        return text or None

    def clip_fact(text):
        nonlocal fact_truncated
        if text and len(text) > MAX_FACT:
            fact_truncated += 1
            return text[:MAX_FACT]
        return text or ""

    def scalar_attrs(attrs):
        if not attrs:
            return None
        out = {k: v for k, v in attrs.items() if isinstance(v, (str, int, float, bool))}
        return out or None

    print(f"  写入节点 {len(nodes)} 个（每批 100）...", flush=True)
    node_errors = []

    def put_batch(batch):
        # 属性默认不写：设了本体后，Zep 会校验属性必须在本体里定义过，源图的属性大多不在其中
        items = [AddNodeItem(
            name=n["name"],
            label=n.get("label"),
            summary=clip(n.get("summary")),
            attributes=scalar_attrs(n.get("attributes")) if args.with_attributes else None,
            created_at=n.get("created_at"),
        ) for n in batch]
        _retry(lambda: client.graph.add_nodes(nodes=items, graph_id=target), "写入节点")

    batches = [nodes[i:i + 100] for i in range(0, len(nodes), 100)]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(put_batch, b): i for i, b in enumerate(batches)}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                node_errors.append({"batch": futures[fut], "error": str(e)})
            if done % 5 == 0 or done == len(batches):
                print(f"    节点批次 {done}/{len(batches)}", flush=True)

    if args.nodes_only:
        edges = []
    print(f"  写入关系 {len(edges)} 条 ...", flush=True)
    edge_errors = []

    def put_edge(e):
        # 原图的节点 uuid 属于另一张图，不能跨图引用；只给名字，让服务端按名字解析/新建。
        src = node_index.get(e.get("source_node_uuid"), {})
        tgt = node_index.get(e.get("target_node_uuid"), {})
        if not (e.get("source_node_name") and e.get("target_node_name")):
            return
        kwargs = dict(
            graph_id=target,
            fact=clip_fact(e.get("fact") or ""),
            fact_name=(e.get("name") or "RELATES_TO"),
            source_node_name=e["source_node_name"],
            target_node_name=e["target_node_name"],
        )
        if src.get("label"):
            kwargs["source_node_labels"] = [src["label"]]
        if src.get("summary"):
            kwargs["source_node_summary"] = clip(src["summary"])
        if args.with_attributes and scalar_attrs(src.get("attributes")):
            kwargs["source_node_attributes"] = scalar_attrs(src["attributes"])
        if tgt.get("label"):
            kwargs["target_node_labels"] = [tgt["label"]]
        if tgt.get("summary"):
            kwargs["target_node_summary"] = clip(tgt["summary"])
        if args.with_attributes and scalar_attrs(tgt.get("attributes")):
            kwargs["target_node_attributes"] = scalar_attrs(tgt["attributes"])
        if e.get("uuid"):
            kwargs["fact_uuid"] = e["uuid"]
        for key in ("created_at", "valid_at", "invalid_at", "expired_at"):
            if e.get(key):
                kwargs[key] = e[key]
        if args.with_attributes and scalar_attrs(e.get("attributes")):
            kwargs["edge_attributes"] = scalar_attrs(e["attributes"])
        _retry(lambda: client.graph.add_fact_triple(**kwargs), "写入关系", attempts=3, delay=1.5)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(put_edge, e): e for e in edges}
        done = 0
        for fut in as_completed(futures):
            done += 1
            try:
                fut.result()
            except Exception as ex:  # noqa: BLE001
                edge_errors.append({"uuid": futures[fut].get("uuid"), "error": str(ex)})
            if done % 200 == 0 or done == len(edges):
                print(f"    关系 {done}/{len(edges)}，失败 {len(edge_errors)}", flush=True)

    if args.with_episodes:
        eps = read_jsonl(os.path.join(pack, "episodes.jsonl"))
        print(f"  回放原文 episode {len(eps)} 条（会触发云端再次抽取，可能新增节点）...", flush=True)
        for ep in eps:
            try:
                _retry(lambda: client.graph.add(
                    graph_id=target, type="text", data=ep.get("content") or ""), "写入 episode")
            except Exception as ex:  # noqa: BLE001
                print(f"    episode {ep.get('uuid')} 失败: {ex}", flush=True)

    settled = None
    if args.wait_seconds > 0:
        print("  等待云端异步落库 ...", flush=True)
        settled = wait_until_stable(client, target, total=args.wait_seconds, interval=20)

    report = {
        "restored_at": datetime.now().isoformat(timespec="seconds"),
        "source_graph_id": manifest["source"]["graph_id"],
        "target_graph_id": target,
        "requested": {"nodes": len(nodes), "edges": len(edges)},
        "settled_edges": settled,
        "summary_truncated": truncated,
        "fact_truncated": fact_truncated,
        "node_batch_errors": node_errors,
        "edge_errors": edge_errors,
        "notes": [
            "Zep 不允许自带节点 uuid（服务端分配），因此节点 uuid 无法保留，校验按名称/内容比对",
            "summary 超过 500 字符的会被截断",
        ],
    }
    out = os.path.join(pack, f"restore_report_{target}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n恢复完成 -> {target}")
    print(f"  节点批次失败 {len(node_errors)} | 关系失败 {len(edge_errors)}")
    print(f"  报告: {out}")
    print(f"  下一步: ./scripts/graph_pack.py verify --pack {pack} --graph-id {target}")


# ----------------------------- 4) 校验 -----------------------------

def pct(a, b):
    return round(100.0 * a / b, 2) if b else 0.0


def cmd_verify(args):
    pack = os.path.abspath(args.pack)
    manifest = json.load(open(os.path.join(pack, "manifest.json"), encoding="utf-8"))
    target = args.graph_id or manifest["source"]["graph_id"]
    client = get_zep_client()

    src_nodes = read_jsonl(os.path.join(pack, "nodes.jsonl"))
    src_edges = read_jsonl(os.path.join(pack, "edges.jsonl"))
    if args.limit_nodes:
        src_nodes = src_nodes[:args.limit_nodes]
    if args.limit_edges:
        src_edges = src_edges[:args.limit_edges]

    print(f"  拉取目标图谱 {target} ...", flush=True)
    tgt_nodes_raw = fetch_all_nodes(client, target)
    tgt_edges_raw = fetch_all_edges(client, target)

    tgt_by_uuid = {n.uuid_: n for n in tgt_nodes_raw}
    tgt_by_name = {}
    for n in tgt_nodes_raw:
        tgt_by_name.setdefault((n.name or "").strip(), n)
    tgt_by_edge_uuid = {e.uuid_: e for e in tgt_edges_raw}
    # 事实文本 -> 边（用于在没有 uuid 的情况下也能比对时序字段）
    tgt_by_fact = {}
    for e in tgt_edges_raw:
        tgt_by_fact.setdefault((getattr(e, "fact", "") or "").strip(), e)

    def norm(v):
        return (v or "").strip()

    def clip500(v):
        return norm(v)[:500]

    # 参考项：Zep 不允许自带节点 uuid，所以节点 uuid 命中率预期为 0
    node_uuid_hit = sum(1 for n in src_nodes if n["uuid"] in tgt_by_uuid)
    node_name_hit = sum(1 for n in src_nodes if norm(n["name"]) in tgt_by_name)
    label_ok = label_cmp = 0
    summary_ok = summary_cmp = 0
    for n in src_nodes:
        t = tgt_by_name.get(norm(n["name"]))
        if not t:
            continue
        src_label = n.get("label")
        tgt_label = main_label(list(t.labels or []))
        if src_label or tgt_label:
            label_cmp += 1
            if src_label == tgt_label:
                label_ok += 1
        if norm(n.get("summary")):
            summary_cmp += 1
            if clip500(n.get("summary")) == clip500(t.summary):
                summary_ok += 1

    edge_uuid_hit = sum(1 for e in src_edges if e["uuid"] in tgt_by_edge_uuid)
    fact_hit = 0
    triple_hit = 0
    time_fields = ("valid_at", "invalid_at", "expired_at")
    time_cmp = {k: 0 for k in time_fields}
    time_ok = {k: 0 for k in time_fields}
    for e in src_edges:
        fact = norm(e.get("fact"))
        # 恢复时超过 250 字符的 fact 会被截断，比对时按同样规则取前 250 字
        match = (tgt_by_edge_uuid.get(e["uuid"])
                 or tgt_by_fact.get(fact[:250])
                 or tgt_by_fact.get(fact))
        if match is not None:
            fact_hit += 1
            m_src = tgt_by_uuid.get(getattr(match, "source_node_uuid", None))
            m_tgt = tgt_by_uuid.get(getattr(match, "target_node_uuid", None))
            src_ok = norm(getattr(m_src, "name", "")) == norm(e.get("source_node_name"))
            tgt_ok = norm(getattr(m_tgt, "name", "")) == norm(e.get("target_node_name"))
            if src_ok and tgt_ok:
                triple_hit += 1
            for k in time_fields:
                if e.get(k):
                    time_cmp[k] += 1
                    if norm(e[k])[:19] == norm(_s(getattr(match, k, None)))[:19]:
                        time_ok[k] += 1

    report = {
        "verified_at": datetime.now().isoformat(timespec="seconds"),
        "pack": pack,
        "source_graph_id": manifest["source"]["graph_id"],
        "target_graph_id": target,
        "nodes": {
            "source": len(src_nodes),
            "target": len(tgt_nodes_raw),
            "name_hit": node_name_hit,
            "name_hit_rate": pct(node_name_hit, len(src_nodes)),
            "label_consistent": label_ok,
            "label_compared": label_cmp,
            "label_rate": pct(label_ok, label_cmp),
            "summary_consistent": summary_ok,
            "summary_compared": summary_cmp,
            "summary_rate": pct(summary_ok, summary_cmp),
            "uuid_hit": node_uuid_hit,
            "uuid_hit_rate": pct(node_uuid_hit, len(src_nodes)),
        },
        "edges": {
            "source": len(src_edges),
            "target": len(tgt_edges_raw),
            "fact_hit": fact_hit,
            "fact_hit_rate": pct(fact_hit, len(src_edges)),
            "structure_hit": triple_hit,
            "structure_hit_rate": pct(triple_hit, len(src_edges)),
            "uuid_hit": edge_uuid_hit,
            "uuid_hit_rate": pct(edge_uuid_hit, len(src_edges)),
            "time_field_rates": {
                k: {"compared": time_cmp[k], "ok": time_ok[k], "rate": pct(time_ok[k], time_cmp[k])}
                for k in time_fields
            },
        },
        "notes": [
            "节点 uuid 由 Zep 服务端分配，无法保留，故以「名称 + 类型 + 摘要」为一致性口径",
            "关系优先按 fact_uuid 匹配，匹配不到时按事实文本匹配",
            "summary 超过 500 字符的部分在恢复时被截断，比对时按前 500 字符比较",
        ],
    }

    print("\n=== 一致性校验 ===")
    n, e = report["nodes"], report["edges"]
    print(f"节点  源 {n['source']} -> 目标 {n['target']}")
    print(f"      名称命中 {n['name_hit']} ({n['name_hit_rate']}%)")
    print(f"      类型一致 {n['label_rate']}% ({n['label_consistent']}/{n['label_compared']}) | "
          f"摘要一致 {n['summary_rate']}% ({n['summary_consistent']}/{n['summary_compared']})")
    print(f"      （uuid 不可保留，命中 {n['uuid_hit']}，{n['uuid_hit_rate']}%）")
    print(f"关系  源 {e['source']} -> 目标 {e['target']}")
    print(f"      事实文本命中 {e['fact_hit']} ({e['fact_hit_rate']}%) | "
          f"两端实体也对上 {e['structure_hit']} ({e['structure_hit_rate']}%)")
    print(f"      uuid 命中 {e['uuid_hit']} ({e['uuid_hit_rate']}%)")
    for k, v in e["time_field_rates"].items():
        print(f"      {k}: {v['rate']}% ({v['ok']}/{v['compared']})")

    out_json = os.path.join(pack, f"verify_report_{target}.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    md = [
        "# 图谱恢复一致性校验",
        "",
        f"- 图谱包：`{pack}`",
        f"- 源图谱：`{manifest['source']['graph_id']}` → 目标图谱：`{target}`",
        f"- 校验时间：{report['verified_at']}",
        "",
        "## 节点",
        "",
        "| 指标 | 结果 |",
        "|---|---|",
        f"| 数量（源→目标） | {n['source']} → {n['target']} |",
        f"| 名称命中率 | {n['name_hit_rate']}% ({n['name_hit']}/{n['source']}) |",
        f"| 实体类型一致率 | {n['label_rate']}% ({n['label_consistent']}/{n['label_compared']}) |",
        f"| 摘要一致率 | {n['summary_rate']}% ({n['summary_consistent']}/{n['summary_compared']}) |",
        f"| UUID 命中率（不可保留，仅参考） | {n['uuid_hit_rate']}% |",
        "",
        "## 关系",
        "",
        "| 指标 | 结果 |",
        "|---|---|",
        f"| 数量（源→目标） | {e['source']} → {e['target']} |",
        f"| 事实文本命中率 | {e['fact_hit_rate']}% ({e['fact_hit']}/{e['source']}) |",
        f"| 两端实体一致率 | {e['structure_hit_rate']}% |",
        f"| UUID 命中率（仅参考） | {e['uuid_hit_rate']}% |",
    ]
    for k, v in e["time_field_rates"].items():
        md.append(f"| {k} 一致率 | {v['rate']}% ({v['ok']}/{v['compared']}) |")
    out_md = os.path.join(pack, f"verify_report_{target}.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"\n报告: {out_json}\n      {out_md}")
    return report


# ----------------------------- CLI -----------------------------

def main():
    ap = argparse.ArgumentParser(description="MiroFish 知识图谱独立导出 / 恢复 / 校验")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="导出图谱包")
    ex.add_argument("--graph-id")
    ex.add_argument("--project")
    ex.add_argument("--sim")
    ex.add_argument("--out-dir")
    ex.add_argument("--lastn", type=int, default=1000, help="episode 取最近 N 条（默认 1000）")
    ex.add_argument("--no-episodes", action="store_true")
    ex.add_argument("--no-viewer", action="store_true")
    ex.set_defaults(func=cmd_export)

    rs = sub.add_parser("restore", help="把图谱包恢复成一张新的 Zep 图谱")
    rs.add_argument("--pack", required=True)
    rs.add_argument("--graph-id", help="目标图谱 ID，默认 <源id>_restored_<时间戳>")
    rs.add_argument("--limit-nodes", type=int)
    rs.add_argument("--limit-edges", type=int)
    rs.add_argument("--workers", type=int, default=4)
    rs.add_argument("--force", action="store_true", help="目标图谱已存在时仍继续写入")
    rs.add_argument("--no-ontology", action="store_true")
    rs.add_argument("--with-episodes", action="store_true",
                    help="同时回放原文（会触发云端再次抽取，可能新增节点，默认关闭）")
    rs.add_argument("--wait-seconds", type=int, default=60,
                    help="写完后等待异步任务落库的最大秒数（0 表示不等待）")
    rs.add_argument("--with-attributes", action="store_true",
                    help="同时写入属性（设了本体时多数属性会被拒绝，默认关闭）")
    rs.add_argument("--retry-failed", action="store_true",
                    help="只重跑上一轮 restore_report 里失败的关系（需带 --graph-id）")
    rs.add_argument("--nodes-only", action="store_true",
                    help="只写节点不写关系（用于把被云端改写过的摘要覆盖回原文）")
    rs.add_argument("--skip-checksum", action="store_true")
    rs.set_defaults(func=cmd_restore)

    vf = sub.add_parser("verify", help="校验图谱包与目标图谱的一致性")
    vf.add_argument("--pack", required=True)
    vf.add_argument("--graph-id", help="要校验的图谱，默认用包里的源图谱（自检）")
    vf.add_argument("--limit-nodes", type=int)
    vf.add_argument("--limit-edges", type=int)
    vf.set_defaults(func=cmd_verify)

    sq = sub.add_parser("sqlite", help="把图谱包转成 SQLite，供其他系统直接查询")
    sq.add_argument("--pack", required=True)
    sq.add_argument("--out", help="输出 .db 路径，默认包内 graph.db")
    sq.set_defaults(func=cmd_sqlite)

    vw = sub.add_parser("viewer", help="离线重建 viewer.html（不访问云端）")
    vw.add_argument("--pack", required=True)
    vw.set_defaults(func=cmd_viewer)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
