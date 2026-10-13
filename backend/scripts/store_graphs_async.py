# -*- coding: utf-8 -*-
"""
ZepGraphManager 异步存储演示
使用异步方式存储图谱，避免长时间阻塞
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from app.services.graph_manager import get_graph_manager
from app.models.task import TaskManager

def store_with_progress(task_id: str, graph_id: str):
    """监控存储进度"""
    task_manager = TaskManager()

    print("\n⏳ 异步存储进行中...")
    print("   (此脚本不会阻塞，可以同时进行其他操作)")

    max_wait = 300  # 最多等待 5 分钟
    start_time = time.time()

    while True:
        task = task_manager.get_task(task_id)

        if not task:
            print(f"\n❌ 任务 {task_id} 不存在")
            return False

        elapsed = time.time() - start_time

        # 显示进度
        status_icon = {
            "pending": "⏳",
            "processing": "🔄",
            "completed": "✅",
            "failed": "❌"
        }.get(task.status.value, "❓")

        print(f"\r{status_icon} 状态: {task.status.value} | 进度: {task.progress}% | "
              f"已用时: {int(elapsed)}s | {task.message}", end="")

        if task.status.value == "completed":
            print(f"\n\n✅ 图谱 {graph_id} 存储完成!")
            print(f"\n📊 存储结果:")
            print(f"   ├─ node_count: {task.result.get('node_count', 0)}")
            print(f"   ├─ edge_count: {task.result.get('edge_count', 0)}")
            print(f"   └─ checksum: {task.result.get('checksum', 'N/A')[:32]}...")
            return True

        if task.status.value == "failed":
            print(f"\n\n❌ 图谱 {graph_id} 存储失败!")
            print(f"   错误: {task.error}")
            return False

        if elapsed > max_wait:
            print(f"\n\n⏰ 等待超时（{max_wait}s）")
            return False

        time.sleep(2)

def main():
    print("\n" + "=" * 70)
    print(" " * 18 + "ZepGraphManager 异步存储演示")
    print("=" * 70)

    # 获取管理器实例
    manager = get_graph_manager()

    # 1. 获取云端图谱列表
    print("\n📡 [步骤 1] 获取云端图谱列表...")
    cloud_graphs = manager.list_cloud_graphs()
    print(f"\n✅ 找到 {len(cloud_graphs)} 个云端图谱")

    if not cloud_graphs:
        print("\n❌ 没有找到云端图谱")
        return

    # 2. 选择图谱进行异步存储
    print("\n🚀 [步骤 2] 启动异步存储...")
    test_graph_id = cloud_graphs[0].graph_id

    print(f"\n   准备存储图谱: {test_graph_id}")
    print("   (使用异步方式，不阻塞主线程)")

    try:
        task_id = manager.store_graph_async(
            graph_id=test_graph_id,
            name=f"测试图谱 - {test_graph_id[:12]}",
            include_data=True
        )

        print(f"   ✓ 已启动异步任务")
        print(f"   └─ task_id: {task_id}")

        # 3. 监控进度
        success = store_with_progress(task_id, test_graph_id)

        if success:
            # 4. 读取存储的图谱
            print("\n📤 [步骤 3] 读取存储的图谱...")
            data = manager.get_stored_graph_data(test_graph_id)

            if data:
                print(f"\n   ✅ 读取成功!")
                print(f"\n   📊 图谱统计:")
                print(f"   ├─ graph_id: {data['graph_id']}")
                print(f"   ├─ 节点数: {data['node_count']}")
                print(f"   ├─ 边数: {data['edge_count']}")
                print(f"   ├─ 实体类型: {len(data['entity_types'])} 种")
                print(f"   └─ 数据来源: {'本地存储' if data.get('is_local') else '云端'}")

                if data['nodes']:
                    print(f"\n   📌 节点示例 (前 3 个):")
                    for i, node in enumerate(data['nodes'][:3], 1):
                        name = node.get('name', 'N/A')[:40]
                        labels = ','.join(node.get('labels', [])[:2])
                        print(f"   {i}. {name}")
                        if labels:
                            print(f"      └─ 类型: {labels}")

                if data['edges']:
                    print(f"\n   🔗 边示例 (前 3 条):")
                    for i, edge in enumerate(data['edges'][:3], 1):
                        source = edge.get('source_node_name', 'N/A')[:20]
                        target = edge.get('target_node_name', 'N/A')[:20]
                        name = edge.get('name', 'N/A')
                        print(f"   {i}. {source} --[{name}]--> {target}")

    except Exception as e:
        print(f"\n❌ 启动异步存储失败: {e}")
        import traceback
        traceback.print_exc()

    # 5. 列出所有已存储的图谱
    print("\n📁 [步骤 4] 本地图谱列表...")
    stored_graphs = manager.list_stored_graphs()
    print(f"\n   共 {len(stored_graphs)} 个本地图谱:")

    for g in stored_graphs:
        entity_types_str = ', '.join(g.entity_types[:3])
        if len(g.entity_types) > 3:
            entity_types_str += f" ... (+{len(g.entity_types)-3})"

        print(f"\n   📊 {g.graph_id}")
        print(f"   ├─ 名称: {g.name}")
        print(f"   ├─ 节点: {g.node_count}")
        print(f"   ├─ 边数: {g.edge_count}")
        print(f"   ├─ 类型: {entity_types_str}")
        print(f"   ├─ 存储时间: {g.stored_at}")
        print(f"   └─ 校验和: {g.checksum[:32]}...")

    print("\n" + "=" * 70)
    print(" " * 25 + "异步存储完成 ✨")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()