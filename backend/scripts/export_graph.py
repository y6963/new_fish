"""把某个 graph_id 在 Zep 里的全部节点 / 关系 / 原始文本导出成本地 JSON。

用法（在 backend 目录下）：
    ./.venv/bin/python scripts/export_graph.py <graph_id>
    ./.venv/bin/python scripts/export_graph.py --project proj_cbbcf8b78580   # 从项目读 graph_id
    ./.venv/bin/python scripts/export_graph.py --sim sim_e65a8f86393d        # 从模拟读 graph_id
    ./.venv/bin/python scripts/export_graph.py <graph_id> --out /tmp/g.json --lastn 200

产出字段说明见 README_debug.md 的「导出图谱数据」一节。
"""

import argparse
import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)
load_dotenv(override=True)

from app.utils.zep import get_zep_client  # noqa: E402
from app.utils.zep_paging import fetch_all_nodes, fetch_all_edges  # noqa: E402

UPLOADS = os.path.join(BACKEND_DIR, "uploads")


def resolve_graph_id(args) -> str:
    if args.graph_id:
        return args.graph_id
    if args.project:
        p = os.path.join(UPLOADS, "projects", args.project, "project.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("graph_id")
    if args.sim:
        p = os.path.join(UPLOADS, "simulations", args.sim, "state.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("graph_id")
    raise SystemExit("必须给 graph_id，或用 --project / --sim 指定")


def node_to_dict(n) -> dict:
    created_at = getattr(n, "created_at", None)
    return {
        "uuid": n.uuid_,
        "name": n.name,
        "labels": list(n.labels or []),
        "summary": n.summary or "",
        "attributes": dict(n.attributes or {}),
        "created_at": str(created_at) if created_at else None,
    }


def edge_to_dict(e, node_map: dict) -> dict:
    def s(v):
        return str(v) if v else None

    episodes = getattr(e, "episodes", None) or getattr(e, "episode_ids", None) or []
    if episodes and not isinstance(episodes, list):
        episodes = [str(episodes)]
    else:
        episodes = [str(x) for x in episodes]
    return {
        "uuid": e.uuid_,
        "name": e.name or "",
        "fact": e.fact or "",
        "source_node_name": node_map.get(e.source_node_uuid, ""),
        "target_node_name": node_map.get(e.target_node_uuid, ""),
        "source_node_uuid": e.source_node_uuid,
        "target_node_uuid": e.target_node_uuid,
        "attributes": dict(e.attributes or {}),
        "created_at": s(getattr(e, "created_at", None)),
        "valid_at": s(getattr(e, "valid_at", None)),
        "invalid_at": s(getattr(e, "invalid_at", None)),
        "expired_at": s(getattr(e, "expired_at", None)),
        "episodes": episodes,
    }


def main():
    ap = argparse.ArgumentParser(description="导出 Zep 图谱的 nodes / edges / episodes")
    ap.add_argument("graph_id", nargs="?", help="图谱 ID")
    ap.add_argument("--project", help="项目 ID，自动取它的 graph_id")
    ap.add_argument("--sim", help="模拟 ID，自动取它的 graph_id")
    ap.add_argument("--out", help="输出文件路径，默认 uploads/graph_export_<id>.json")
    ap.add_argument("--lastn", type=int, default=1000,
                    help="取最近 N 条 episode。注意：不传时 Zep 默认只给 4 条，必须显式给大值")
    ap.add_argument("--no-episodes", action="store_true", help="跳过 episode，只出节点和边")
    args = ap.parse_args()

    graph_id = resolve_graph_id(args)
    print(f"graph_id = {graph_id}")

    client = get_zep_client()

    print("  拉取节点 ...", flush=True)
    nodes_raw = fetch_all_nodes(client, graph_id)
    print("  拉取关系 ...", flush=True)
    edges_raw = fetch_all_edges(client, graph_id)

    node_map = {n.uuid_: (n.name or "") for n in nodes_raw}
    nodes = [node_to_dict(n) for n in nodes_raw]
    edges = [edge_to_dict(e, node_map) for e in edges_raw]
    print(f"  节点 {len(nodes)} | 关系 {len(edges)}", flush=True)

    episodes = []
    if not args.no_episodes:
        print("  拉取原始文本 episode ...", flush=True)
        kwargs = {"graph_id": graph_id}
        if args.lastn:
            kwargs["lastn"] = args.lastn
        resp = client.graph.episode.get_by_graph_id(**kwargs)
        for ep in getattr(resp, "episodes", None) or []:
            created_at = getattr(ep, "created_at", None)
            episodes.append({
                "uuid": getattr(ep, "uuid_", None),
                "content": getattr(ep, "content", "") or "",
                "source_description": getattr(ep, "source_description", None) or "",
                "created_at": str(created_at) if created_at else None,
                "source": getattr(ep, "source", None),
            })
        print(f"  episode {len(episodes)}", flush=True)

    result = {
        "graph_id": graph_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "episode_count": len(episodes),
        "nodes": nodes,
        "edges": edges,
        "episodes": episodes,
    }

    out = args.out or os.path.join(UPLOADS, f"graph_export_{graph_id}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n已写出: {out}  ({os.path.getsize(out) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
