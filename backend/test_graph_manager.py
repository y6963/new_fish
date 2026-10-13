# -*- coding: utf-8 -*-
"""
测试 ZepGraphManager 功能
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.graph_manager import ZepGraphManager, get_graph_manager

def main():
    print("=" * 60)
    print("ZepGraphManager 测试")
    print("=" * 60)

    # 获取管理器实例
    manager = get_graph_manager()

    # 1. 列出云端图谱
    print("\n[1] 获取云端图谱列表...")
    try:
        cloud_graphs = manager.list_cloud_graphs()
        print(f"    找到 {len(cloud_graphs)} 个云端图谱:")
        for i, g in enumerate(cloud_graphs[:5], 1):
            print(f"    {i}. {g.graph_id} ({g.name})")
        if len(cloud_graphs) > 5:
            print(f"    ... 还有 {len(cloud_graphs) - 5} 个")
    except Exception as e:
        print(f"    获取云端图谱失败: {e}")

    # 2. 列出本地已存储的图谱
    print("\n[2] 列出本地存储的图谱...")
    stored_graphs = manager.list_stored_graphs()
    print(f"    本地存储 {len(stored_graphs)} 个图谱:")
    for g in stored_graphs[:5]:
        print(f"    - {g.graph_id}: {g.node_count} 节点, {g.edge_count} 边")
    if len(stored_graphs) > 5:
        print(f"    ... 还有 {len(stored_graphs) - 5} 个")

    # 3. 如果有云端图谱，测试存储功能
    if cloud_graphs:
        test_graph_id = cloud_graphs[0].graph_id
        print(f"\n[3] 测试存储图谱: {test_graph_id}")

        try:
            stored = manager.store_graph(test_graph_id, include_data=True)
            print(f"    存储成功!")
            print(f"    - 节点数: {stored.node_count}")
            print(f"    - 边数: {stored.edge_count}")
            print(f"    - 实体类型: {stored.entity_types}")
            print(f"    - 校验和: {stored.checksum[:16]}...")
            print(f"    - 存储时间: {stored.stored_at}")
        except Exception as e:
            print(f"    存储失败: {e}")

        # 4. 测试读取存储的图谱
        print(f"\n[4] 测试读取存储的图谱: {test_graph_id}")
        try:
            data = manager.get_stored_graph_data(test_graph_id)
            if data:
                print(f"    读取成功!")
                print(f"    - is_local: {data['is_local']}")
                print(f"    - 节点数: {data['node_count']}")
                print(f"    - 边数: {data['edge_count']}")
                print(f"    - 节点数据: {len(data['nodes'])} 条")
                print(f"    - 边数据: {len(data['edges'])} 条")
            else:
                print(f"    读取失败: 返回 None")
        except Exception as e:
            print(f"    读取失败: {e}")

        # 5. 测试验证功能
        print(f"\n[5] 测试验证图谱完整性: {test_graph_id}")
        try:
            verify_result = manager.verify_stored_graph(test_graph_id)
            print(f"    验证结果: {'通过' if verify_result['valid'] else '失败'}")
            print(f"    - stored_checksum: {verify_result.get('stored_checksum', 'N/A')[:16]}...")
            print(f"    - current_checksum: {verify_result.get('current_checksum', 'N/A')[:16]}...")
        except Exception as e:
            print(f"    验证失败: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()