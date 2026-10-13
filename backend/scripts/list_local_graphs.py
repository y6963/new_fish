# -*- coding: utf-8 -*-
"""
从本地项目数据库中列出所有已关联的 Zep Cloud 图谱 ID
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.project import ProjectManager

def main():
    print("正在读取本地项目数据...\n")

    # 获取所有项目
    projects = ProjectManager.list_projects(limit=100)

    # 收集所有图谱 ID
    graph_map = {}  # graph_id -> list of projects

    for project in projects:
        graph_id = project.graph_id
        if graph_id:
            if graph_id not in graph_map:
                graph_map[graph_id] = []
            graph_map[graph_id].append({
                'project_id': project.project_id,
                'name': project.name,
                'status': project.status.value if hasattr(project.status, 'value') else project.status
            })

    if not graph_map:
        print("未找到任何已关联云端图谱的项目")
        return

    print(f"找到 {len(graph_map)} 个云端图谱:\n")
    print("=" * 80)

    for i, (graph_id, projects_list) in enumerate(graph_map.items(), 1):
        print(f"\n图谱 #{i}")
        print(f"  Zep Graph ID: {graph_id}")
        print(f"  关联项目数: {len(projects_list)}")
        print("  关联项目列表:")
        for p in projects_list:
            status_icon = "✅" if "COMPLETED" in str(p['status']) else "🔄" if "BUILDING" in str(p['status']) else "❌"
            print(f"    {status_icon} [{p['project_id']}] {p['name']} ({p['status']})")

    print("\n" + "=" * 80)

    # 统计
    completed = sum(1 for g in graph_map.values() for p in g if "COMPLETED" in str(p['status']))
    building = sum(1 for g in graph_map.values() for p in g if "BUILDING" in str(p['status']))

    print(f"\n总计:")
    print(f"  图谱数量: {len(graph_map)}")
    print(f"  已完成项目: {completed}")
    print(f"  构建中项目: {building}")

if __name__ == "__main__":
    main()