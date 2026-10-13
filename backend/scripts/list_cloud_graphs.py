# -*- coding: utf-8 -*-
"""
列出 Zep Cloud 上所有图谱
"""
import sys
import os

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.zep import get_zep_client
from app.config import Config

def main():
    if not Config.ZEP_API_KEY:
        print("错误: ZEP_API_KEY 未配置")
        return

    print("正在连接 Zep Cloud...")
    client = get_zep_client()

    try:
        # 尝试获取图谱列表
        # Zep Cloud API 可能使用不同的方法名
        print("\n尝试获取图谱列表...\n")

        # 方法1: list()
        try:
            graphs = client.graph.list()
            print(f"找到 {len(graphs)} 个图谱:")
            for i, g in enumerate(graphs, 1):
                name = getattr(g, 'name', 'Unknown')
                graph_id = getattr(g, 'graph_id', getattr(g, 'uuid', 'N/A'))
                print(f"  {i}. {name} (ID: {graph_id})")
            return
        except AttributeError:
            print("client.graph.list() 方法不存在，尝试其他方法...")

        # 方法2: list_graphs()
        try:
            graphs = client.graph.list_graphs()
            print(f"找到 {len(graphs)} 个图谱:")
            for i, g in enumerate(graphs, 1):
                print(f"  {i}. {getattr(g, 'name', 'Unknown')} (ID: {getattr(g, 'graph_id', 'N/A')})")
            return
        except AttributeError:
            print("client.graph.list_graphs() 方法不存在")

        # 方法3: 直接用 REST API
        import httpx
        response = httpx.get(
            "https://api.getzep.com/api/v2/graphs",
            headers={"Authorization": f"Bearer {Config.ZEP_API_KEY}"},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            graphs = data.get('graphs', data) if isinstance(data, dict) else data
            print(f"找到 {len(graphs)} 个图谱:")
            for i, g in enumerate(graphs, 1):
                if isinstance(g, dict):
                    print(f"  {i}. {g.get('name', 'Unknown')} (ID: {g.get('graph_id', g.get('uuid', 'N/A'))})")
                else:
                    print(f"  {i}. {getattr(g, 'name', 'Unknown')} (ID: {getattr(g, 'graph_id', 'N/A')})")
            return
        else:
            print(f"REST API 返回状态码: {response.status_code}")
            print(response.text[:500])

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()