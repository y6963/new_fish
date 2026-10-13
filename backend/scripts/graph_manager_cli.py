#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ZepGraphManager 统一测试入口
提供交互式菜单，支持所有图谱管理功能
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from app.services.graph_manager import (
    get_graph_manager,
    StoreProgress,
    StoreConfig
)
from app.models.task import TaskManager


class GraphManagerCLI:
    """图谱管理器命令行工具"""

    def __init__(self):
        self.manager = get_graph_manager()
        self.task_manager = TaskManager()
        self.current_graphs = []

    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self):
        """打印标题"""
        print("\n" + "=" * 70)
        print(" " * 20 + "ZepGraphManager 统一测试工具")
        print("=" * 70)

    def print_menu(self):
        """打印菜单"""
        print("\n📋 功能菜单:")
        print("-" * 70)
        print("  1. 📡  列出云端图谱")
        print("  2. 💾  同步存储图谱（显示进度）")
        print("  3. 🔄  异步存储图谱")
        print("  4. 📤  读取本地图谱")
        print("  5. 📋  列出所有已存储图谱")
        print("  6. 🔍  验证图谱完整性")
        print("  7. 🗑️   删除本地图谱")
        print("  8. 📊  批量存储图谱")
        print("  9. ⚙️   查看/修改配置")
        print("  0. 🚪  退出")
        print("-" * 70)

    def wait_enter(self):
        """等待回车"""
        input("\n按 Enter 继续...")

    def select_graph(self, graphs: list, title: str = "选择图谱") -> str:
        """选择图谱"""
        if not graphs:
            print("❌ 没有可用的图谱")
            return None

        print(f"\n{title}:")
        print("-" * 70)
        for i, g in enumerate(graphs, 1):
            print(f"  {i:2d}. {g.graph_id}")
        print(f"  0.  返回")
        print("-" * 70)

        while True:
            try:
                choice = input("\n请输入编号: ").strip()
                if choice == '0':
                    return None
                idx = int(choice) - 1
                if 0 <= idx < len(graphs):
                    return graphs[idx].graph_id if hasattr(graphs[idx], 'graph_id') else graphs[idx]
                print("❌ 无效选择，请重试")
            except ValueError:
                print("❌ 请输入有效数字")

    # ==================== 功能实现 ====================

    def list_cloud_graphs(self):
        """列出云端图谱"""
        self.clear_screen()
        self.print_header()
        print("\n📡 正在获取云端图谱列表...\n")

        try:
            graphs = self.manager.list_cloud_graphs()
            self.current_graphs = graphs

            print(f"✅ 成功获取 {len(graphs)} 个云端图谱:\n")
            print("-" * 70)
            print(f"{'序号':<6}{'Graph ID':<35}{'名称'}")
            print("-" * 70)

            for i, g in enumerate(graphs, 1):
                name = g.name[:20] if len(g.name) > 20 else g.name
                print(f"{i:<6}{g.graph_id:<35}{name}")

            print("-" * 70)
            print(f"总计: {len(graphs)} 个图谱")

        except Exception as e:
            print(f"❌ 获取失败: {e}")

        self.wait_enter()

    def store_graph_sync(self):
        """同步存储图谱"""
        self.clear_screen()
        self.print_header()

        if not self.current_graphs:
            print("\n⚠️  请先获取云端图谱列表（选项 1）")
            self.wait_enter()
            return

        graph_id = self.select_graph(self.current_graphs, "选择要存储的图谱")
        if not graph_id:
            return

        self.clear_screen()
        self.print_header()
        print(f"\n🚀 开始同步存储图谱: {graph_id}")
        print("\n⚠️  注意: 存储过程可能需要几分钟，请耐心等待...")
        print("    按 Ctrl+C 可中断，下次运行会从断点继续\n")

        def progress_handler(progress: StoreProgress):
            status_icons = {
                "starting": "⏳",
                "storing_nodes": "📦",
                "storing_edges": "🔗",
                "completed": "✅",
                "failed": "❌"
            }
            icon = status_icons.get(progress.status, "❓")

            print(f"\r{icon} {progress.status:<15} | "
                  f"节点: {progress.nodes_stored:>4}/{progress.total_nodes:<4} | "
                  f"边: {progress.edges_stored:>4}/{progress.total_edges:<4} | "
                  f"进度: {progress.progress_percent:>5.1f}%   ", end="", flush=True)

        try:
            stored = self.manager.store_graph(
                graph_id=graph_id,
                name=f"存储_{graph_id[:12]}",
                include_data=True,
                progress_callback=progress_handler,
                force_refresh=False
            )

            print(f"\n\n✅ 存储完成!")
            print("\n📊 存储结果:")
            print("-" * 70)
            print(f"  Graph ID:     {stored.graph_id}")
            print(f"  节点数:       {stored.node_count}")
            print(f"  边数:         {stored.edge_count}")
            print(f"  实体类型:     {len(stored.entity_types)} 种")
            print(f"  存储时间:     {stored.stored_at}")
            print(f"  存储耗时:     {stored.metadata.get('stored_duration', 0):.1f}s")
            print("-" * 70)

            if stored.entity_types:
                print(f"\n  实体类型: {', '.join(stored.entity_types[:10])}")
                if len(stored.entity_types) > 10:
                    print(f"            ... 等 {len(stored.entity_types)} 种类型")

        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断，数据已保存")
            print("    重新运行会从断点继续")

        except Exception as e:
            print(f"\n\n❌ 存储失败: {e}")

        self.wait_enter()

    def store_graph_async(self):
        """异步存储图谱"""
        self.clear_screen()
        self.print_header()

        if not self.current_graphs:
            print("\n⚠️  请先获取云端图谱列表（选项 1）")
            self.wait_enter()
            return

        graph_id = self.select_graph(self.current_graphs, "选择要异步存储的图谱")
        if not graph_id:
            return

        self.clear_screen()
        self.print_header()
        print(f"\n🚀 启动异步存储: {graph_id}\n")

        try:
            task_id = self.manager.store_graph_async(
                graph_id=graph_id,
                name=f"异步存储_{graph_id[:12]}",
                include_data=True
            )

            print(f"✅ 已启动异步任务")
            print(f"\n  Task ID: {task_id}")
            print("\n  监控任务状态...")
            print("  (任务在后台运行，可按 Ctrl+C 退出监控)\n")

            try:
                while True:
                    task = self.task_manager.get_task(task_id)

                    if not task:
                        print("\n❌ 任务不存在")
                        break

                    status_icons = {
                        "pending": "⏳",
                        "processing": "🔄",
                        "completed": "✅",
                        "failed": "❌"
                    }
                    icon = status_icons.get(task.status.value, "❓")

                    print(f"\r{icon} 状态: {task.status.value:<12} | "
                          f"进度: {task.progress:>3}% | "
                          f"{task.message}", end="", flush=True)

                    if task.status.value == "completed":
                        print("\n\n✅ 异步存储完成!")
                        if task.result:
                            print(f"\n📊 结果:")
                            print(f"  节点数: {task.result.get('node_count', 0)}")
                            print(f"  边数: {task.result.get('edge_count', 0)}")
                        break

                    if task.status.value == "failed":
                        print(f"\n\n❌ 异步存储失败: {task.error}")
                        break

                    time.sleep(2)

            except KeyboardInterrupt:
                print("\n\n⚠️  已退出监控，任务仍在后台运行")
                print(f"   Task ID: {task_id}")

        except Exception as e:
            print(f"❌ 启动失败: {e}")

        self.wait_enter()

    def read_stored_graph(self):
        """读取本地图谱"""
        self.clear_screen()
        self.print_header()

        stored = self.manager.list_stored_graphs()

        if not stored:
            print("\n❌ 没有已存储的图谱")
            self.wait_enter()
            return

        print(f"\n📁 本地存储 {len(stored)} 个图谱:")
        graph_ids = [g.graph_id for g in stored]

        graph_id = self.select_graph(stored, "选择要读取的图谱")
        if not graph_id:
            return

        data = self.manager.get_stored_graph_data(graph_id)

        if not data:
            print(f"\n❌ 读取图谱 {graph_id} 失败")
            self.wait_enter()
            return

        print(f"\n📊 图谱详情: {graph_id}")
        print("-" * 70)
        print(f"  名称:       {data['name']}")
        print(f"  节点数:     {data['node_count']}")
        print(f"  边数:       {data['edge_count']}")
        print(f"  实体类型:   {len(data['entity_types'])} 种")
        print(f"  存储时间:   {data['stored_at']}")
        print(f"  数据来源:   {'本地存储' if data.get('is_local') else '云端'}")
        print("-" * 70)

        # 显示节点示例
        if data['nodes']:
            print(f"\n📌 节点示例 (前 5 个):")
            for i, node in enumerate(data['nodes'][:5], 1):
                name = node.get('name', 'N/A')[:40]
                labels = ','.join(node.get('labels', [])[:2])
                print(f"  {i}. {name}")
                if labels:
                    print(f"     └─ 类型: {labels}")

        # 显示边示例
        if data['edges']:
            print(f"\n🔗 边示例 (前 5 条):")
            for i, edge in enumerate(data['edges'][:5], 1):
                source = edge.get('source_node_name', 'N/A')[:20]
                target = edge.get('target_node_name', 'N/A')[:20]
                rel = edge.get('name', 'N/A')
                print(f"  {i}. {source} --[{rel}]--> {target}")

        self.wait_enter()

    def list_stored_graphs(self):
        """列出所有已存储图谱"""
        self.clear_screen()
        self.print_header()
        print("\n💾 本地存储图谱列表\n")

        stored = self.manager.list_stored_graphs()

        if not stored:
            print("❌ 没有已存储的图谱")
            self.wait_enter()
            return

        print(f"✅ 找到 {len(stored)} 个已存储图谱:\n")
        print("-" * 70)
        print(f"{'Graph ID':<35}{'节点':<8}{'边':<8}{'类型数':<8}{'存储时间'}")
        print("-" * 70)

        for g in stored:
            stored_time = g.stored_at[:19] if len(g.stored_at) > 19 else g.stored_at
            print(f"{g.graph_id:<35}{g.node_count:<8}{g.edge_count:<8}"
                  f"{len(g.entity_types):<8}{stored_time}")

        print("-" * 70)

        # 统计
        total_nodes = sum(g.node_count for g in stored)
        total_edges = sum(g.edge_count for g in stored)
        print(f"\n📊 总计:")
        print(f"  图谱数: {len(stored)}")
        print(f"  节点总数: {total_nodes}")
        print(f"  边总数: {total_edges}")

        self.wait_enter()

    def verify_graph(self):
        """验证图谱完整性"""
        self.clear_screen()
        self.print_header()

        stored = self.manager.list_stored_graphs()

        if not stored:
            print("\n❌ 没有已存储的图谱")
            self.wait_enter()
            return

        graph_id = self.select_graph(stored, "选择要验证的图谱")
        if not graph_id:
            return

        print(f"\n🔍 正在验证图谱: {graph_id}\n")

        result = self.manager.verify_stored_graph(graph_id)

        print("-" * 70)
        if result['valid']:
            print("  ✅ 验证通过 - 图谱数据完整")
        else:
            print("  ❌ 验证失败 - 数据可能被篡改或损坏")
        print("-" * 70)
        print(f"  Graph ID:          {result['graph_id']}")
        print(f"  存储校验和:        {result.get('stored_checksum', 'N/A')[:32]}...")
        print(f"  当前校验和:        {result.get('current_checksum', 'N/A')[:32]}...")
        print(f"  节点数:            {result.get('node_count', 0)}")
        print(f"  边数:              {result.get('edge_count', 0)}")
        print(f"  存储时间:          {result.get('stored_at', 'N/A')}")
        print("-" * 70)

        if result.get('entity_types'):
            print(f"\n  实体类型: {', '.join(result['entity_types'][:10])}")
            if len(result['entity_types']) > 10:
                print(f"            ... 等 {len(result['entity_types'])} 种")

        self.wait_enter()

    def delete_graph(self):
        """删除图谱"""
        self.clear_screen()
        self.print_header()

        stored = self.manager.list_stored_graphs()

        if not stored:
            print("\n❌ 没有已存储的图谱")
            self.wait_enter()
            return

        graph_id = self.select_graph(stored, "选择要删除的图谱")
        if not graph_id:
            return

        print(f"\n⚠️  确认删除图谱: {graph_id}?")
        print("   此操作不可恢复！")

        confirm = input("\n请输入 'yes' 确认: ").strip().lower()
        if confirm != 'yes':
            print("取消删除")
            self.wait_enter()
            return

        if self.manager.delete_stored_graph(graph_id):
            print(f"\n✅ 图谱 {graph_id} 已删除")
        else:
            print(f"\n❌ 删除失败")

        self.wait_enter()

    def batch_store_graphs(self):
        """批量存储图谱"""
        self.clear_screen()
        self.print_header()

        if not self.current_graphs:
            print("\n⚠️  请先获取云端图谱列表（选项 1）")
            self.wait_enter()
            return

        stored = self.manager.list_stored_graphs()
        stored_ids = {g.graph_id for g in stored}

        # 过滤未存储的图谱
        unstored = [g for g in self.current_graphs if g.graph_id not in stored_ids]

        if not unstored:
            print("\n⚠️  所有云端图谱都已存储")
            self.wait_enter()
            return

        print(f"\n📋 可存储图谱 ({len(unstored)} 个):")
        print("-" * 70)
        for i, g in enumerate(unstored[:20], 1):
            print(f"  {i:2d}. {g.graph_id}")
        if len(unstored) > 20:
            print(f"  ... 还有 {len(unstored) - 20} 个")
        print("-" * 70)

        # 选择要存储的图谱
        print("\n输入要存储的图谱编号（用逗号分隔，如: 1,3,5）:")
        print("输入 'all' 存储所有, 'q' 取消")

        choice = input("\n选择: ").strip().lower()

        if choice == 'q':
            return

        if choice == 'all':
            selected = unstored
        else:
            try:
                indices = [int(i.strip()) - 1 for i in choice.split(',')]
                selected = [unstored[i] for i in indices if 0 <= i < len(unstored)]
            except (ValueError, IndexError):
                print("❌ 无效选择")
                self.wait_enter()
                return

        if not selected:
            print("❌ 没有选择图谱")
            self.wait_enter()
            return

        graph_ids = [g.graph_id for g in selected]
        print(f"\n🚀 开始批量存储 {len(graph_ids)} 个图谱...")

        def batch_progress(graph_id: str, progress: StoreProgress):
            print(f"\r  [{graph_id[:16]}] {progress.progress_percent:>5.1f}%", end="", flush=True)

        try:
            results = self.manager.store_multiple_graphs(
                graph_ids=graph_ids,
                progress_callback=batch_progress
            )

            print("\n\n📊 批量存储结果:")
            print("-" * 70)
            print(f"  总数: {results['total']}")
            print(f"  成功: ✅ {results['success']}")
            print(f"  失败: ❌ {results['failed']}")

            if results['details']:
                print("\n  详情:")
                for d in results['details']:
                    status = "✅" if d['status'] == 'success' else "❌"
                    if d['status'] == 'success':
                        print(f"    {status} {d['graph_id']}: "
                              f"{d.get('node_count', 0)} 节点, {d.get('edge_count', 0)} 边")
                    else:
                        print(f"    {status} {d['graph_id']}: {d.get('error', 'Unknown error')}")

        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断")

        except Exception as e:
            print(f"\n\n❌ 批量存储失败: {e}")

        self.wait_enter()

    def show_config(self):
        """显示/修改配置"""
        self.clear_screen()
        self.print_header()
        print("\n⚙️  当前配置:")
        print("-" * 70)
        print(f"  REQUEST_DELAY:  {StoreConfig.REQUEST_DELAY}s   (每次请求间隔)")
        print(f"  PAGE_DELAY:     {StoreConfig.PAGE_DELAY}s    (每页获取后延迟)")
        print(f"  RETRY_DELAY:    {StoreConfig.RETRY_DELAY}s   (重试延迟基础值)")
        print(f"  MAX_RETRIES:    {StoreConfig.MAX_RETRIES}        (最大重试次数)")
        print(f"  PAGE_SIZE:      {StoreConfig.PAGE_SIZE}        (每页大小)")
        print("-" * 70)

        print("\n修改配置:")
        print("  1. REQUEST_DELAY")
        print("  2. PAGE_DELAY")
        print("  3. RETRY_DELAY")
        print("  4. MAX_RETRIES")
        print("  0. 返回")

        choice = input("\n选择: ").strip()

        configs = {
            '1': ('REQUEST_DELAY', 0.1, 10.0),
            '2': ('PAGE_DELAY', 0.5, 10.0),
            '3': ('RETRY_DELAY', 1.0, 60.0),
            '4': ('MAX_RETRIES', 1, 20)
        }

        if choice in configs:
            name, min_val, max_val = configs[choice]
            current = getattr(StoreConfig, name)
            print(f"\n当前值: {current}")
            print(f"有效范围: {min_val} - {max_val}")

            try:
                new_val = float(input("输入新值: ").strip())
                new_val = max(min_val, min(max_val, new_val))
                setattr(StoreConfig, name, new_val)
                print(f"✅ 已修改 {name} = {new_val}")
            except ValueError:
                print("❌ 无效值")

        self.wait_enter()

    def run(self):
        """运行主循环"""
        while True:
            try:
                self.clear_screen()
                self.print_header()
                self.print_menu()

                choice = input("\n请选择功能 (0-9): ").strip()

                if choice == '0':
                    print("\n👋 再见!")
                    break
                elif choice == '1':
                    self.list_cloud_graphs()
                elif choice == '2':
                    self.store_graph_sync()
                elif choice == '3':
                    self.store_graph_async()
                elif choice == '4':
                    self.read_stored_graph()
                elif choice == '5':
                    self.list_stored_graphs()
                elif choice == '6':
                    self.verify_graph()
                elif choice == '7':
                    self.delete_graph()
                elif choice == '8':
                    self.batch_store_graphs()
                elif choice == '9':
                    self.show_config()
                else:
                    print("\n❌ 无效选择，请输入 0-9")
                    time.sleep(1)

            except KeyboardInterrupt:
                print("\n\n👋 再见!")
                break
            except Exception as e:
                print(f"\n❌ 发生错误: {e}")
                import traceback
                traceback.print_exc()
                self.wait_enter()


def main():
    """主入口"""
    cli = GraphManagerCLI()
    cli.run()


if __name__ == "__main__":
    main()