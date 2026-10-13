#!/usr/bin/env python3
"""
逐步调试数据处理流程 —— 打印每一步的输入和输出

用法：
    # 从某个项目开始，走完 1~10 步（含自动关联的模拟与报告）
    python scripts/debug_pipeline.py <project_id>

    # 只看某一步喂给大模型的提示词（不消耗 token）
    python scripts/debug_pipeline.py <project_id> --prompt ontology

    # 跳过所有需要联网的步骤（Zep 拉取 / 图谱数据）
    python scripts/debug_pipeline.py <project_id> --offline

    # 已知模拟 ID，直接从第 6 步开始看
    python scripts/debug_pipeline.py --sim <simulation_id>

步骤一览：
    1  原始文件          2  提取的文本        3  项目配置(本体)
    4  文本分块          5  Zep 图谱数据      6  智能体人设
    7  模拟配置          8  模拟动作          9  回写图谱的文本
    10 报告
"""

import os
import sys
import csv
import json
import sqlite3
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

UPLOADS = backend_dir / "uploads"

from app.config import Config
from app.services.text_processor import TextProcessor
from app.services.ontology_generator import OntologyGenerator
from app.services.graph_builder import GraphBuilderService

# 预览长度（可用环境变量覆盖）
PREVIEW = int(os.environ.get("DEBUG_PREVIEW", "400"))


def print_section(title):
    """打印分段标题"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def preview(text, n=PREVIEW):
    """截断预览"""
    text = str(text)
    return text if len(text) <= n else text[:n] + f"... (共 {len(text)} 字符)"


# ---------------------------------------------------------------------------
# 关联查找：project_id / graph_id → simulation_id → report_id
# ---------------------------------------------------------------------------

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_simulations(project_id=None, graph_id=None):
    """找出属于该项目的所有模拟"""
    sims = []
    sim_root = UPLOADS / "simulations"
    if not sim_root.exists():
        return sims
    for d in sorted(sim_root.iterdir()):
        state = _read_json(d / "state.json")
        if not state:
            continue
        if project_id and state.get("project_id") == project_id:
            sims.append((d.name, state))
        elif graph_id and state.get("graph_id") == graph_id:
            sims.append((d.name, state))
    return sims


def find_reports(simulation_id=None, graph_id=None):
    """找出属于该模拟的所有报告"""
    reports = []
    rep_root = UPLOADS / "reports"
    if not rep_root.exists():
        return reports
    for d in sorted(rep_root.iterdir()):
        meta = _read_json(d / "meta.json")
        if not meta:
            continue
        if simulation_id and meta.get("simulation_id") == simulation_id:
            reports.append((d.name, meta))
        elif graph_id and meta.get("graph_id") == graph_id:
            reports.append((d.name, meta))
    return reports


# ---------------------------------------------------------------------------
# 步骤 1~5：项目侧（原有逻辑）
# ---------------------------------------------------------------------------

def debug_project(project_id: str, offline: bool = False):
    """逐步调试项目"""

    print_section(f"开始调试项目: {project_id}")

    project_dir = UPLOADS / "projects" / project_id
    if not project_dir.exists():
        print(f"[x] 项目不存在: {project_id}")
        print("可用项目: python scripts/preview_project.py")
        return

    # ========== 步骤1: 查看原始文件 ==========
    print_section("步骤1: 原始文件  (输入)")
    files_dir = project_dir / "files"
    if files_dir.exists():
        any_file = False
        for f in sorted(files_dir.iterdir()):
            if f.is_file():
                any_file = True
                print(f"\n文件: {f.name}  ({f.stat().st_size} 字节)")
                if f.suffix.lower() in (".md", ".txt", ".markdown"):
                    print(preview(f.read_text(encoding="utf-8", errors="ignore"), 300))
        if not any_file:
            print("(空目录)")
    else:
        print("[!] 没有 files 目录")

    # ========== 步骤2: 查看提取的文本 ==========
    print_section("步骤2: 提取的文本 extracted_text.txt  (步骤1 的输出 = 步骤4 的输入)")
    text_file = project_dir / "extracted_text.txt"
    if not text_file.exists():
        print("[!] 文件不存在，解析阶段没跑完")
        return
    text = text_file.read_text(encoding="utf-8")
    print(f"文本长度: {len(text)} 字符")
    print(preview(text))

    # ========== 步骤3: 查看项目配置 ==========
    print_section("步骤3: 项目配置 project.json (本体)")
    config = _read_json(project_dir / "project.json")
    if not config:
        print("[!] project.json 不存在")
        return

    print(f"项目ID: {config.get('project_id')}")
    print(f"图谱ID: {config.get('graph_id')}")
    print(f"模拟需求: {config.get('simulation_requirement')}")
    print(f"分块参数: chunk_size={config.get('chunk_size')}, overlap={config.get('chunk_overlap')}")

    ontology = config.get("ontology", {})
    print(f"\n本体 - 实体类型 ({len(ontology.get('entity_types', []))}):")
    for e in ontology.get("entity_types", []):
        print(f"  - {e['name']}: {preview(e.get('description', ''), 60)}")
    print(f"\n本体 - 关系类型 ({len(ontology.get('edge_types', []))}):")
    for e in ontology.get("edge_types", []):
        st = e.get("source_targets") or []
        pairs = ", ".join(f"{s.get('source')}->{s.get('target')}" for s in st)
        print(f"  - {e['name']}: {pairs if pairs else preview(e.get('description', ''), 60)}")

    # ========== 步骤4: 文本分块 ==========
    print_section("步骤4: 文本分块 (真正发给 Zep 的内容)")
    chunk_size = config.get("chunk_size", 500)
    chunk_overlap = config.get("chunk_overlap", 50)
    chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
    print(f"分块参数: chunk_size={chunk_size}, overlap={chunk_overlap}")
    print(f"分块数量: {len(chunks)}")
    print(f"\n前 2 块示例:  <-- Zep 只能看到这些，来源和时间全靠块里的文字")
    for i, chunk in enumerate(chunks[:2]):
        print(f"\n  Chunk {i} (长度 {len(chunk)}):")
        print("  " + preview(chunk, 250).replace("\n", "\n  "))

    # ========== 步骤5: 从 Zep 获取图谱数据 ==========
    graph_id = config.get("graph_id")
    if offline:
        print_section("步骤5: Zep 图谱数据")
        print("[跳过] --offline 模式")
    elif not graph_id:
        print_section("步骤5: Zep 图谱数据")
        print("[!] 无 graph_id，图谱还没建")
    else:
        print_section(f"步骤5: Zep 图谱数据  graph_id={graph_id}")
        print("正在从 Zep 云端获取...")
        try:
            builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
            graph_data = builder.get_graph_data(graph_id)
            print(f"\n[ok] 节点数 {graph_data['node_count']} / 边数 {graph_data['edge_count']}")

            entity_types = {}
            for node in graph_data.get("nodes", []):
                for label in node.get("labels", []):
                    if label not in ("Entity", "Node"):
                        entity_types[label] = entity_types.get(label, 0) + 1
            print("\n实体类型分布:")
            for t, c in sorted(entity_types.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {t}: {c}")

            print("\n前 5 个节点:")
            for i, node in enumerate(graph_data.get("nodes", [])[:5]):
                etype = [l for l in node.get("labels", []) if l not in ("Entity", "Node")]
                print(f"\n  [{i+1}] {node['name']}  类型: {', '.join(etype) or 'Unknown'}")
                print(f"      摘要: {preview(node.get('summary', ''), 120)}")
        except Exception as e:
            print(f"[x] 获取失败: {e}")

    # ========== 步骤 6~10：往下追模拟与报告 ==========
    sims = find_simulations(project_id=project_id, graph_id=graph_id)
    if not sims:
        print_section("后续步骤")
        print("[!] 这个项目还没有对应的模拟（prepare 阶段没跑）")
        return

    print_section(f"找到 {len(sims)} 个关联模拟")
    for name, state in sims:
        print(f"  - {name}  status={state.get('status')}  "
              f"entities={state.get('entities_count')}  profiles={state.get('profiles_count')}")

    # 取最新的一个继续往下走
    sim_id, sim_state = sims[-1]
    debug_simulation(sim_id, sim_state)


# ---------------------------------------------------------------------------
# 步骤 6~9：模拟侧
# ---------------------------------------------------------------------------

def debug_simulation(sim_id, state=None):
    sim_dir = UPLOADS / "simulations" / sim_id
    if not sim_dir.exists():
        print(f"[x] 模拟目录不存在: {sim_dir}")
        return
    if state is None:
        state = _read_json(sim_dir / "state.json") or {}

    # ========== 步骤6: 人设 ==========
    print_section(f"步骤6: 智能体人设  ({sim_id})")
    tw = sim_dir / "twitter_profiles.csv"
    rd = sim_dir / "reddit_profiles.json"
    if tw.exists():
        with open(tw, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        print(f"\n[twitter] twitter_profiles.csv  {len(rows)} 条   字段: {list(rows[0].keys()) if rows else '-'}")
        for r in rows[:2]:
            print(f"\n  - {r.get('name')} (@{r.get('username')})")
            print(f"    user_char: {preview(r.get('user_char', ''), 120)}")
            print(f"    description: {preview(r.get('description', ''), 300)}")
    if rd.exists():
        data = _read_json(rd)
        if isinstance(data, list):
            print(f"\n[reddit] reddit_profiles.json  {len(data)} 条")
            for r in data[:1]:
                print(preview(json.dumps(r, ensure_ascii=False), 400))
    if not tw.exists() and not rd.exists():
        print("[!] 没有人设文件（prepare 没跑完）")
        return

    # ========== 步骤7: 模拟配置 ==========
    print_section("步骤7: 模拟配置 simulation_config.json")
    cfg = _read_json(sim_dir / "simulation_config.json")
    if not cfg:
        print("[!] 没有配置文件")
        return
    tc = cfg.get("time_config", {})
    print(f"总时长: {tc.get('total_simulation_hours')} 小时, "
          f"每轮 {tc.get('minutes_per_round')} 分钟 "
          f"→ 共 {tc.get('total_simulation_hours', 0) * 60 // max(tc.get('minutes_per_round', 1), 1)} 轮")
    print(f"每轮上线人数: {tc.get('agents_per_hour_min')} ~ {tc.get('agents_per_hour_max')}")
    print(f"高峰时段: {tc.get('peak_hours')} (x{tc.get('peak_activity_multiplier')})")

    agents = cfg.get("agent_configs", [])
    print(f"\nagent_configs: {len(agents)} 个")
    for a in agents[:3]:
        print(f"  - {a.get('entity_name')} ({a.get('entity_type')}) "
              f"activity={a.get('activity_level')} 活跃时段={a.get('active_hours')}")

    ev = cfg.get("event_config", {}) or {}
    posts = ev.get("initial_posts", []) or []
    print(f"\n初始帖: {len(posts)} 条  <-- 第 0 轮的导火索")
    for p in posts[:3]:
        print(f"  - {preview(p.get('content') if isinstance(p, dict) else p, 120)}")

    # ========== 步骤8: 模拟动作 ==========
    print_section("步骤8: 模拟动作 (模拟真正跑出来的东西)")
    real_actions = []
    for platform in ("twitter", "reddit"):
        jf = sim_dir / platform / "actions.jsonl"
        if not jf.exists():
            print(f"\n[{platform}] 没有 actions.jsonl（模拟没启动或没产出）")
            continue
        lines = [l for l in jf.read_text(encoding="utf-8").splitlines() if l.strip()]
        events, kinds, actions = {}, {}, []
        for l in lines:
            try:
                d = json.loads(l)
            except Exception:
                continue
            et = d.get("event_type") or ("action" if d.get("action_type") else "unknown")
            events[et] = events.get(et, 0) + 1
            if d.get("action_type"):
                kinds[d["action_type"]] = kinds.get(d["action_type"], 0) + 1
                actions.append(d)
        print(f"\n[{platform}] actions.jsonl  {len(lines)} 条")
        print(f"  记录类型分布: {sorted(events.items(), key=lambda x: x[1], reverse=True)}")
        print(f"  真实动作 {len(actions)} 条, 分布: {sorted(kinds.items(), key=lambda x: x[1], reverse=True)}")
        for a in actions[:3]:
            print(f"  样例: round{a.get('round')} {a.get('agent_name')} "
                  f"{a.get('action_type')} -> {preview(json.dumps(a.get('action_args', {}), ensure_ascii=False), 160)}")
        for a in actions:
            real_actions.append(dict(platform=platform, **a))

    db = sim_dir / "twitter_simulation.db"
    if not db.exists():
        db = sim_dir / "reddit_simulation.db"
    if db.exists():
        print(f"\n[世界数据库] {db.name}")
        try:
            conn = sqlite3.connect(str(db))
            cur = conn.cursor()
            for table in ("user", "post", "comment", "like", "follow", "trace"):
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    print(f"  {table}: {cur.fetchone()[0]} 行")
                except Exception:
                    print(f"  {table}: (无此表)")
            conn.close()
        except Exception as e:
            print(f"  [x] 读取失败: {e}")

    # ========== 步骤9: 回写图谱的文本 ==========
    print_section("步骤9: 回写图谱的文本 (Zep 收到的模拟活动)")
    print("下面是系统把动作翻译后、塞回知识图谱的原文。")
    try:
        from app.services.zep_graph_memory_updater import AgentActivity

        picked, seen = [], set()
        for a in real_actions:
            if a.get("action_type") not in seen:
                seen.add(a["action_type"])
                picked.append(a)
            if len(picked) >= 3:
                break

        if picked:
            print("（取自本项目的真实动作）\n")
            for a in picked:
                act = AgentActivity(
                    platform=a.get("platform", "twitter"),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a["action_type"],
                    action_args=a.get("action_args", {}),
                    round_num=a.get("round", 0),
                    timestamp=a.get("timestamp", ""),
                )
                print(f"  [{a['action_type']}] {act.to_episode_text()}")
        else:
            print("（本模拟还没有真实动作，以下是格式示例）\n")
            demo = [
                dict(platform="twitter", agent_id=3, agent_name="罗永浩", action_type="CREATE_POST",
                     action_args={"content": "西贝的菜价贵得离谱，还说是预制菜，这不是糊弄人吗"},
                     round_num=12, timestamp="2026-09-20T20:15:00"),
                dict(platform="twitter", agent_id=7, agent_name="贾国龙", action_type="CREATE_COMMENT",
                     action_args={"post_id": 41, "content": "我们从来没有使用预制菜，欢迎随时来后厨参观"},
                     round_num=13, timestamp="2026-09-20T20:40:00"),
            ]
            for s in demo:
                print(f"  [{s['action_type']}] {AgentActivity(**s).to_episode_text()}")
    except Exception as e:
        print(f"  [x] 无法生成: {e}")

    # ========== 步骤10: 报告 ==========
    reports = find_reports(simulation_id=sim_id) or find_reports(graph_id=state.get("graph_id"))
    print_section("步骤10: 报告")
    if not reports:
        print("[!] 还没有报告")
        return
    for rid, meta in reports:
        print(f"\n报告 {rid}  status={meta.get('status')}")
        outline = meta.get("outline") or _read_json(UPLOADS / "reports" / rid / "outline.json")
        if outline:
            titles = outline.get("sections") or outline.get("outline") or []
            print(f"  章节数: {len(titles)}")
            for s in (titles[:8] if isinstance(titles, list) else []):
                title = s.get("title") if isinstance(s, dict) else s
                print(f"    - {title}")
        rep_dir = UPLOADS / "reports" / rid
        secs = sorted(rep_dir.glob("section_*.md"))
        print(f"  已落盘章节: {len(secs)} 个 -> {[s.name for s in secs][:10]}")
        prog = _read_json(rep_dir / "progress.json")
        if prog:
            print(f"  进度: {preview(json.dumps(prog, ensure_ascii=False), 200)}")
        full = rep_dir / "full_report.md"
        if full.exists():
            print(f"  最终报告: {full.stat().st_size} 字节")
            print("  开头: " + preview(full.read_text(encoding="utf-8"), 300).replace("\n", "\n  "))

    print_section("调试完成")


# ---------------------------------------------------------------------------
# 只看提示词（不调用大模型，不花钱）
# ---------------------------------------------------------------------------

def show_prompt(stage, target_id):
    if stage == "ontology":
        project_dir = UPLOADS / "projects" / target_id
        cfg = _read_json(project_dir / "project.json") or {}
        text_file = project_dir / "extracted_text.txt"
        texts = [text_file.read_text(encoding="utf-8")] if text_file.exists() else ["（示例文本）"]
        g = OntologyGenerator.__new__(OntologyGenerator)  # 绕过 __init__，不创建 LLMClient
        msg = g._build_user_message(texts, cfg.get("simulation_requirement", ""), None)
        print_section("步骤3 提示词：本体生成（真实文本，截断显示）")
        print(preview(msg, int(os.environ.get("DEBUG_PREVIEW", "3000"))))
    else:
        print(f"暂不支持的阶段: {stage}（目前只有 ontology）")


# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        print("\n可用项目:")
        pdir = UPLOADS / "projects"
        for d in sorted(pdir.iterdir()) if pdir.exists() else []:
            if d.is_dir():
                print(f"  - {d.name}")
        print("\n可用模拟:")
        sdir = UPLOADS / "simulations"
        for d in sorted(sdir.iterdir()) if sdir.exists() else []:
            if d.is_dir() and (d / "state.json").exists():
                print(f"  - {d.name}")
        sys.exit(1)

    offline = "--offline" in args
    args = [a for a in args if a != "--offline"]

    if args[0] == "--sim":
        if len(args) < 2:
            print("用法: --sim <simulation_id>")
            sys.exit(1)
        state = _read_json(UPLOADS / "simulations" / args[1] / "state.json") or {}
        debug_simulation(args[1], state)
        return

    if args[0] == "--prompt":
        if len(args) < 3:
            print("用法: --prompt ontology <project_id>")
            sys.exit(1)
        show_prompt(args[1], args[2])
        return

    debug_project(args[0], offline=offline)


if __name__ == "__main__":
    main()
