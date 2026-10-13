# -*- coding: utf-8 -*-
"""
ZepGraphManager 完整功能演示
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.services.graph_manager import ZepGraphManager, get_graph_manager

def main():
    print("\n" + "=" * 70)
    print(" " * 20 + "ZepGraphManager 功能演示")
    print("=" * 70)

    # 获取管理器实例
    manager = get_graph_manager()

    # 1. 列出云端图谱
    print("\n📡 [步骤 1] 获取云端图谱列表...")
    try:
        cloud_graphs = manager.list_cloud_graphs()
        print(f"\n✅ 找到 {len(cloud_graphs)} 个云端图谱:\n")
        print("   " + "-" * 60)
        for i, g in enumerate(cloud_graphs, 1):
            print(f"   {i:2d}. {g.graph_id}")
        print("   " + "-" * 60)
    except Exception as e:
        print(f"\n❌ 获取云端图谱失败: {e}")
        return

    # 2. 列出本地已存储的图谱
    print("\n💾 [步骤 2] 检查本地存储...")
    stored_graphs = manager.list_stored_graphs()
    if stored_graphs:
        print(f"\n已存储 {len(stored_graphs)} 个图谱:")
        for g in stored_graphs:
            print(f"   ✓ {g.graph_id} ({g.node_count} 节点, {g.edge_count} 边)")
    else:
        print("\n本地暂无存储的图谱")

    # 3. 选择一个图谱进行存储
    print("\n📥 [步骤 3] 存储第一个图谱...")
    if cloud_graphs:
        test_graph_id = cloud_graphs[0].graph_id
        print(f"\n   准备存储: {test_graph_id}")

        try:
            stored = manager.store_graph(
                graph_id=test_graph_id,
                name=f"测试图谱",
                include_data=True
            )

            print("\n   ✅ 存储成功！")
            print("\n   图谱信息:")
            print(f"   ├─ graph_id: {stored.graph_id}")
            print(f"   ├─ 节点数: {stored.node_count}")
            print(f"   ├─ 边数: {stored.edge_count}")
            print(f"   ├─ 实体类型: {', '.join(stored.entity_types[:5])}")
            if len(stored.entity_types) > 5:
                print(f"   │           ... 等 {len(stored.entity_types)} 种类型")
            print(f"   ├─ 校验和: {stored.checksum[:32]}...")
            print(f"   └─ 存储时间: {stored.stored_at}")

        except Exception as e:
            print(f"\n   ❌ 存储失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 4. 读取存储的图谱
        print("\n📤 [步骤 4] 读取存储的图谱...")
        try:
            data = manager.get_stored_graph_data(test_graph_id)

            if data:
                print("\n   ✅ 读取成功！")
                print("\n   数据摘要:")
                print(f"   ├─ is_local: {data['is_local']}")
                print(f"   ├─ 节点数: {data['node_count']}")
                print(f"   ├─ 边数: {data['edge_count']}")
                print(f"   ├─ 节点数据: {len(data['nodes'])} 条记录")
                print(f"   ├─ 边数据: {len(data['edges'])} 条记录")

                if data['nodes']:
                    print("\n   📌 前3个节点示例:")
                    for i, node in enumerate(data['nodes'][:3], 1):
                        name = node.get('name', 'N/A')[:30]
                        labels = ','.join(node.get('labels', [])[:2])
                        print(f"   {i}. {name}")
                        if labels:
                            print(f"      类型: {labels}")

                if data['edges']:
                    print("\n   🔗 前3条边示例:")
                    for i, edge in enumerate(data['edges'][:3], 1):
                        source = edge.get('source_node_name', 'N/A')[:15]
                        target = edge.get('target_node_name', 'N/A')[:15]
                        name = edge.get('name', 'N/A')
                        print(f"   {i}. {source} --[{name}]--> {target}")

            else:
                print("\n   ❌ 读取失败: 返回 None")

        except Exception as e:
            print(f"\n   ❌ 读取失败: {e}")
            import traceback
            traceback.print_exc()

        # 5. 验证完整性
        print("\n🔍 [步骤 5] 验证图谱完整性...")
        try:
            verify_result = manager.verify_stored_graph(test_graph_id)

            if verify_result['valid']:
                print("\n   ✅ 验证通过！图谱数据完整。")
            else:
                print("\n   ⚠️ 验证失败！数据可能被篡改或损坏。")

            print(f"\n   验证详情:")
            print(f"   ├─ 存储校验和: {verify_result['stored_checksum'][:32]}...")
            print(f"   └─ 当前校验和: {verify_result['current_checksum'][:32]}...")

        except Exception as e:
            print(f"\n   ❌ 验证失败: {e}")

    # 6. 列出所有本地图谱
    print("\n📁 [步骤 6] 本地图谱列表...")
    final_stored = manager.list_stored_graphs()
    print(f"\n   共 {len(final_stored)} 个本地图谱:")
    for g in final_stored:
        print(f"   • {g.graph_id} ({g.node_count} 节点)")

    print("\n" + "=" * 70)
    print(" " * 25 + "演示完成 ✨")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()