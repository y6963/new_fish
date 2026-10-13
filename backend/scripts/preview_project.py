#!/usr/bin/env python3
"""
快速预览项目的图谱数据
使用方法: python preview_project.py <project_id>
"""

import os
import sys
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import Config
from app.services.graph_builder import GraphBuilderService


def main():
    if len(sys.argv) < 2:
        print("用法: python preview_project.py <project_id>")
        print("\n可用项目:")
        projects_dir = backend_dir / "uploads" / "projects"
        for d in sorted(projects_dir.iterdir()):
            if d.is_dir():
                config_file = d / "project.json"
                if config_file.exists():
                    with open(config_file) as f:
                        config = json.load(f)
                    name = config.get('name', 'Unnamed')
                    status = config.get('status', 'unknown')
                    graph_id = config.get('graph_id', '无')
                    print(f"  {d.name} - {name} (状态: {status}, 图谱: {graph_id[:20]}...)")
        sys.exit(1)
    
    project_id = sys.argv[1]
    projects_dir = backend_dir / "uploads" / "projects"
    project_dir = projects_dir / project_id
    
    if not project_dir.exists():
        print(f"❌ 项目不存在: {project_id}")
        sys.exit(1)
    
    # 加载配置
    with open(project_dir / "project.json") as f:
        config = json.load(f)
    
    graph_id = config.get('graph_id')
    if not graph_id:
        print(f"❌ 项目没有图谱ID")
        sys.exit(1)
    
    print("=" * 80)
    print(f"📊 项目: {project_id}")
    print("=" * 80)
    print(f"\n📋 基本信息:")
    print(f"  名称: {config.get('name', 'Unnamed')}")
    print(f"  状态: {config.get('status', 'unknown')}")
    print(f"  图谱ID: {graph_id}")
    print(f"  模拟需求: {config.get('simulation_requirement', '未设置')}")
    
    # 本体信息
    ontology = config.get('ontology', {})
    print(f"\n📦 本体定义:")
    print(f"  实体类型 ({len(ontology.get('entity_types', []))}):")
    for entity in ontology.get('entity_types', [])[:5]:
        print(f"    - {entity['name']}: {entity.get('description', '')[:50]}...")
    if len(ontology.get('entity_types', [])) > 5:
        print(f"    ... 还有 {len(ontology.get('entity_types', [])) - 5} 个")
    
    print(f"\n  关系类型 ({len(ontology.get('edge_types', []))}):")
    for edge in ontology.get('edge_types', [])[:5]:
        print(f"    - {edge['name']}: {edge.get('description', '')[:50]}...")
    if len(ontology.get('edge_types', [])) > 5:
        print(f"    ... 还有 {len(ontology.get('edge_types', [])) - 5} 个")
    
    # 获取图谱数据
    print(f"\n⏳ 正在从 Zep 云端获取图谱数据...")
    builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
    graph_data = builder.get_graph_data(graph_id)
    
    print(f"\n🕸️ 图谱统计:")
    print(f"  节点数: {graph_data['node_count']}")
    print(f"  边数: {graph_data['edge_count']}")
    
    # 实体类型分布
    entity_types = {}
    for node in graph_data.get('nodes', []):
        for label in node.get('labels', []):
            if label not in ['Entity', 'Node']:
                entity_types[label] = entity_types.get(label, 0) + 1
    
    print(f"\n📈 实体类型分布:")
    for entity_type, count in sorted(entity_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {entity_type}: {count}")
    
    # 关系类型分布
    edge_types = {}
    for edge in graph_data.get('edges', []):
        name = edge.get('name', 'UNKNOWN')
        edge_types[name] = edge_types.get(name, 0) + 1
    
    print(f"\n🔗 关系类型分布:")
    for edge_type, count in sorted(edge_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {edge_type}: {count}")
    
    # 显示部分节点
    print(f"\n📝 部分节点示例:")
    for i, node in enumerate(graph_data.get('nodes', [])[:5]):
        labels = node.get('labels', [])
        entity_type = [l for l in labels if l not in ['Entity', 'Node']]
        print(f"\n  [{i+1}] {node['name']}")
        print(f"      类型: {', '.join(entity_type) if entity_type else 'Unknown'}")
        print(f"      摘要: {node.get('summary', '')[:100]}...")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()