#!/usr/bin/env python3
"""
获取所有项目的完整图谱数据
使用方法: python fetch_graph_data.py [project_id]

如果不指定 project_id，则获取所有项目的图谱数据
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
from app.services.text_processor import TextProcessor


def load_project_config(project_dir: Path) -> dict:
    """加载项目配置"""
    project_json = project_dir / "project.json"
    if not project_json.exists():
        return None
    
    with open(project_json, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_extracted_text(project_dir: Path) -> str:
    """加载提取的文本"""
    text_file = project_dir / "extracted_text.txt"
    if not text_file.exists():
        return ""
    
    with open(text_file, 'r', encoding='utf-8') as f:
        return f.read()


def get_graph_data(graph_id: str) -> dict:
    """获取图谱数据"""
    builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
    return builder.get_graph_data(graph_id)


def save_graph_data(project_id: str, graph_data: dict, output_dir: Path):
    """保存图谱数据"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"{project_id}_graph_data.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✅ 保存到: {output_file}")
    return output_file


def analyze_graph_data(graph_data: dict) -> dict:
    """分析图谱数据"""
    nodes = graph_data.get('nodes', [])
    edges = graph_data.get('edges', [])
    
    # 统计实体类型
    entity_types = {}
    for node in nodes:
        labels = node.get('labels', [])
        for label in labels:
            if label not in ['Entity', 'Node']:
                entity_types[label] = entity_types.get(label, 0) + 1
    
    # 统计关系类型
    edge_types = {}
    for edge in edges:
        name = edge.get('name', 'UNKNOWN')
        edge_types[name] = edge_types.get(name, 0) + 1
    
    return {
        'node_count': len(nodes),
        'edge_count': len(edges),
        'entity_types': entity_types,
        'edge_types': edge_types,
    }


def process_project(project_dir: Path, output_dir: Path):
    """处理单个项目"""
    project_config = load_project_config(project_dir)
    if not project_config:
        print(f"  ⚠️ 跳过: {project_dir.name} (无 project.json)")
        return None
    
    project_id = project_config.get('project_id', project_dir.name)
    graph_id = project_config.get('graph_id')
    simulation_requirement = project_config.get('simulation_requirement', '未设置')
    
    print(f"\n📄 项目: {project_id}")
    print(f"  模拟需求: {simulation_requirement[:50]}...")
    
    # 检查是否有图谱ID
    if not graph_id:
        print(f"  ⚠️ 跳过: 无 graph_id")
        return None
    
    print(f"  图谱ID: {graph_id}")
    
    try:
        # 获取图谱数据
        print(f"  ⏳ 正在从 Zep 云端获取图谱数据...")
        graph_data = get_graph_data(graph_id)
        
        # 保存图谱数据
        output_file = save_graph_data(project_id, graph_data, output_dir)
        
        # 分析图谱
        analysis = analyze_graph_data(graph_data)
        print(f"  📊 节点数: {analysis['node_count']}")
        print(f"  📊 边数: {analysis['edge_count']}")
        print(f"  📊 实体类型: {analysis['entity_types']}")
        print(f"  📊 关系类型: {analysis['edge_types']}")
        
        return {
            'project_id': project_id,
            'graph_id': graph_id,
            'analysis': analysis
        }
        
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_text_chunks(text: str, chunk_size: int = 500, overlap: int = 50):
    """获取文本分块"""
    return TextProcessor.split_text(text, chunk_size, overlap)


def main():
    # 项目目录
    projects_dir = backend_dir / "uploads" / "projects"
    output_dir = backend_dir / "outputs" / "graph_data"
    
    print("=" * 80)
    print("📥 获取所有项目的完整图谱数据")
    print("=" * 80)
    
    # 检查 ZEP_API_KEY
    if not Config.ZEP_API_KEY:
        print("❌ 错误: ZEP_API_KEY 未配置")
        print("   请在环境变量或配置文件中设置 ZEP_API_KEY")
        sys.exit(1)
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        # 处理指定的项目
        project_id = sys.argv[1]
        project_dir = projects_dir / project_id
        
        if not project_dir.exists():
            print(f"❌ 项目不存在: {project_id}")
            sys.exit(1)
        
        result = process_project(project_dir, output_dir)
        if result:
            print(f"\n✅ 完成!")
        else:
            print(f"\n⚠️ 处理失败")
        
        return
    
    # 处理所有项目
    project_dirs = [d for d in projects_dir.iterdir() if d.is_dir()]
    project_dirs.sort(key=lambda x: x.name)
    
    print(f"\n找到 {len(project_dirs)} 个项目")
    
    results = []
    for project_dir in project_dirs:
        result = process_project(project_dir, output_dir)
        if result:
            results.append(result)
    
    # 汇总统计
    print("\n" + "=" * 80)
    print("📊 汇总统计")
    print("=" * 80)
    print(f"成功处理: {len(results)}/{len(project_dirs)} 个项目")
    
    if results:
        total_nodes = sum(r['analysis']['node_count'] for r in results)
        total_edges = sum(r['analysis']['edge_count'] for r in results)
        print(f"总节点数: {total_nodes}")
        print(f"总边数: {total_edges}")
        
        # 列出所有项目
        print("\n项目列表:")
        for r in results:
            print(f"  - {r['project_id']}: {r['analysis']['node_count']} 节点, {r['analysis']['edge_count']} 边")
        
        print(f"\n📁 输出目录: {output_dir}")
    
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()