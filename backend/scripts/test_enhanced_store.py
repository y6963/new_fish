# -*- coding: utf-8 -*-
"""
测试增强版图谱管理器
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.graph_manager import (
    get_graph_manager,
    StoreProgress,
    StoreConfig
)

def progress_handler(progress: StoreProgress):
    """实时显示存储进度"""
    status_icon = {
        "starting": "⏳",
        "storing_nodes": "📦",
        "storing_edges": "🔗",
        "completed": "✅",
        "failed": "❌"
    }.get(progress.status, "❓")

    print(f"\r{status_icon} {progress.status}: "
          f"节点 {progress.nodes_stored}/{progress.total_nodes}, "
          f"边 {progress.edges_stored}/{progress.total_edges}, "
          f"总体 {progress.progress_percent:.1f}%", end="", flush=True)

def main():
    print("=" * 70)
    print(" " * 18 + "增强版图谱管理器测试")
    print("=" * 70)

    # 显示配置
    print("\n📋 当前配置:")
    print(f"   • REQUEST_DELAY: {StoreConfig.REQUEST_DELAY}s")
    print(f"   • PAGE_DELAY: {StoreConfig.PAGE_DELAY}s")
    print(f"   • RETRY_DELAY: {StoreConfig.RETRY_DELAY}s")
    print(f"   • MAX_RETRIES: {StoreConfig.MAX_RETRIES}")

    manager = get_graph_manager()

    # 1. 列出云端图谱
    print("\n📡 [1] 获取云端图谱列表...")
    cloud_graphs = manager.list_cloud_graphs()
    print(f"   ✅ 找到 {len(cloud_graphs)} 个云端图谱")

    if not cloud_graphs:
        print("   ❌ 没有云端图谱")
        return

    # 2. 查看已存储的图谱
    print("\n💾 [2] 检查本地存储...")
    stored = manager.list_stored_graphs()
    print(f"   本地已存储 {len(stored)} 个图谱")

    # 3. 存储一个图谱
    test_graph_id = cloud_graphs[0].graph_id
    print(f"\n🚀 [3] 开始存储图谱: {test_graph_id}")
    print("   (使用新的速率限制和重试机制)")

    try:
        stored_graph = manager.store_graph(
            graph_id=test_graph_id,
            name=f"测试图谱",
            include_data=True,
            progress_callback=progress_handler,
            force_refresh=False  # 增量存储
        )

        print(f"\n\n✅ 存储完成!")
        print(f"\n   📊 统计:")
        print(f"   ├─ graph_id: {stored_graph.graph_id}")
        print(f"   ├─ 节点数: {stored_graph.node_count}")
        print(f"   ├─ 边数: {stored_graph.edge_count}")
        print(f"   ├─ 实体类型: {len(stored_graph.entity_types)} 种")
        print(f"   └─ 存储耗时: {stored_graph.metadata.get('stored_duration', 0):.1f}s")

        # 4. 读取数据
        print("\n📤 [4] 读取存储的图谱数据...")
        data = manager.get_stored_graph_data(test_graph_id)

        if data and data['nodes']:
            print(f"\n   📌 节点示例 (前 3 个):")
            for i, node in enumerate(data['nodes'][:3], 1):
                name = node.get('name', 'N/A')[:40]
                print(f"   {i}. {name}")

        if data and data['edges']:
            print(f"\n   🔗 边示例 (前 3 条):")
            for i, edge in enumerate(data['edges'][:3], 1):
                source = edge.get('source_node_name', 'N/A')[:15]
                target = edge.get('target_node_name', 'N/A')[:15]
                rel = edge.get('name', 'N/A')
                print(f"   {i}. {source} --[{rel}]--> {target}")

        # 5. 验证完整性
        print("\n🔍 [5] 验证图谱完整性...")
        verify = manager.verify_stored_graph(test_graph_id)
        if verify['valid']:
            print("   ✅ 验证通过，数据完整!")
        else:
            print("   ❌ 验证失败，数据可能损坏")

    except Exception as e:
        print(f"\n\n❌ 存储失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print(" " * 25 + "测试完成 ✨")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()