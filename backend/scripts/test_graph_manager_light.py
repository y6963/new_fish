# -*- coding: utf-8 -*-
"""
ZepGraphManager 轻量级测试（不实际获取大量数据）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.graph_manager import ZepGraphManager, get_graph_manager

def main():
    print("\n" + "=" * 70)
    print(" " * 20 + "ZepGraphManager 功能测试")
    print("=" * 70)

    # 获取管理器实例
    manager = get_graph_manager()

    # 1. 列出云端图谱
    print("\n📡 [步骤 1] 获取云端图谱列表...")
    try:
        cloud_graphs = manager.list_cloud_graphs()
        print(f"\n✅ 找到 {len(cloud_graphs)} 个云端图谱:\n")
        for i, g in enumerate(cloud_graphs, 1):
            print(f"   {i:2d}. {g.graph_id}")

    except Exception as e:
        print(f"\n❌ 获取云端图谱失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 获取第一个图谱的统计信息
    if cloud_graphs:
        test_graph_id = cloud_graphs[0].graph_id
        print(f"\n📊 [步骤 2] 获取图谱统计: {test_graph_id}")

        try:
            # 尝试获取统计信息（使用 limit=1 来快速检查）
            from app.utils.zep import call_zep_read_with_retry

            nodes_result = call_zep_read_with_retry(
                lambda: manager.client.graph.get_nodes(graph_id=test_graph_id, limit=1),
                operation_name="get_nodes"
            )

            edges_result = call_zep_read_with_retry(
                lambda: manager.client.graph.get_edges(graph_id=test_graph_id, limit=1),
                operation_name="get_edges"
            )

            # 检查是否有下一页来判断总量
            # 注意：这里只是演示，实际需要通过分页来准确计数
            print(f"\n   图谱信息:")
            print(f"   ├─ graph_id: {test_graph_id}")
            print(f"   └─ 状态: API 访问正常")

        except Exception as e:
            print(f"\n   ⚠️ API 访问受限: {e}")
            print(f"   ├─ graph_id: {test_graph_id}")
            print(f"   └─ 状态: 需要等待限流恢复")

    # 3. 列出本地已存储的图谱
    print("\n💾 [步骤 3] 检查本地存储...")
    stored_graphs = manager.list_stored_graphs()
    if stored_graphs:
        print(f"\n已存储 {len(stored_graphs)} 个图谱:")
        for g in stored_graphs:
            print(f"   • {g.graph_id} ({g.node_count} 节点)")
    else:
        print("\n本地暂无存储的图谱")
        print("   提示: 等待 Zep API 限流恢复后，可使用 store_graph() 存储图谱")

    # 4. 演示如何调用存储功能
    print("\n📝 [步骤 4] 存储功能使用示例:")
    print("\n   # 同步存储（完整数据）")
    print("   stored = manager.store_graph(")
    print("       graph_id='mirofish_a2b57893b31644d1',")
    print("       name='我的测试图谱',")
    print("       include_data=True")
    print("   )")

    print("\n   # 异步存储（推荐用于大型图谱）")
    print("   task_id = manager.store_graph_async(")
    print("       graph_id='mirofish_a2b57893b31644d1',")
    print("       name='我的测试图谱'")
    print("   )")

    print("\n   # 读取已存储的图谱")
    print("   data = manager.get_stored_graph_data('mirofish_a2b57893b31644d1')")
    print("   # data 包含: nodes, edges, graph_id, is_local 等")

    print("\n   # 批量存储多个图谱")
    print("   results = manager.store_multiple_graphs(")
    print("       graph_ids=['id1', 'id2', 'id3'],")
    print("       names={'id1': '图谱1', 'id2': '图谱2'}")
    print("   )")

    # 5. 检查存储目录
    print(f"\n📁 [步骤 5] 存储目录检查...")
    graphs_dir = manager.GRAPHS_DIR
    print(f"\n   存储根目录: {graphs_dir}")
    print(f"   目录存在: {os.path.exists(graphs_dir)}")

    if os.path.exists(graphs_dir):
        subdirs = os.listdir(graphs_dir)
        print(f"   已存储图谱数: {len(subdirs)}")
        for subdir in subdirs[:5]:
            full_path = os.path.join(graphs_dir, subdir)
            if os.path.isdir(full_path):
                files = os.listdir(full_path)
                print(f"   • {subdir}: {files}")

    print("\n" + "=" * 70)
    print(" " * 25 + "测试完成 ✨")
    print("=" * 70)
    print("\n💡 提示: Zep API 有频率限制，如遇到限流请等待后重试。")
    print("   存储的图谱数据会保存在: uploads/stored_graphs/")
    print()

if __name__ == "__main__":
    main()