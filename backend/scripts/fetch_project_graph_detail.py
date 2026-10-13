#!/usr/bin/env python3
"""
获取指定项目的完整图谱数据（包括节点、边、原始文本、分块等）
使用方法: python fetch_project_graph_detail.py <project_id> [output_dir]
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

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


def main():
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python fetch_project_graph_detail.py <project_id> [output_dir]")
        print("\n示例:")
        print("  python fetch_project_graph_detail.py proj_584f702adfdd")
        print("  python fetch_project_graph_detail.py proj_584f702adfdd ./my_output")
        sys.exit(1)
    
    project_id = sys.argv[1]
    output_base = Path(sys.argv[2]) if len(sys.argv) > 2 else backend_dir / "outputs"
    
    # 目录设置
    projects_dir = backend_dir / "uploads" / "projects"
    project_dir = projects_dir / project_id
    
    if not project_dir.exists():
        print(f"❌ 项目不存在: {project_id}")
        sys.exit(1)
    
    print("=" * 80)
    print(f"📥 获取项目图谱数据: {project_id}")
    print("=" * 80)
    
    # 检查 ZEP_API_KEY
    if not Config.ZEP_API_KEY:
        print("❌ 错误: ZEP_API_KEY 未配置")
        sys.exit(1)
    
    # 1. 加载项目配置
    print("\n📋 步骤1: 加载项目配置...")
    project_config = load_project_config(project_dir)
    if not project_config:
        print("❌ 无法加载项目配置")
        sys.exit(1)
    
    graph_id = project_config.get('graph_id')
    if not graph_id:
        print("❌ 项目没有关联的图谱ID")
        sys.exit(1)
    
    print(f"  ✅ 图谱ID: {graph_id}")
    print(f"  ✅ 模拟需求: {project_config.get('simulation_requirement', '未设置')}")
    print(f"  ✅ 实体类型数: {len(project_config.get('ontology', {}).get('entity_types', []))}")
    print(f"  ✅ 关系类型数: {len(project_config.get('ontology', {}).get('edge_types', []))}")
    
    # 2. 加载原始文本
    print("\n📝 步骤2: 加载原始文本...")
    text = load_extracted_text(project_dir)
    print(f"  ✅ 文本长度: {len(text)} 字符")
    
    # 3. 文本分块
    print("\n✂️ 步骤3: 文本分块...")
    chunk_size = project_config.get('chunk_size', 500)
    chunk_overlap = project_config.get('chunk_overlap', 50)
    chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
    print(f"  ✅ 分块数量: {len(chunks)}")
    print(f"  ✅ 块大小: {chunk_size}, 重叠: {chunk_overlap}")
    
    # 4. 获取图谱数据
    print("\n⏳ 步骤4: 从Zep云端获取图谱数据...")
    try:
        graph_data = get_graph_data(graph_id)
        print(f"  ✅ 节点数: {graph_data['node_count']}")
        print(f"  ✅ 边数: {graph_data['edge_count']}")
    except Exception as e:
        print(f"  ❌ 获取图谱数据失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 5. 创建输出目录
    print("\n💾 步骤5: 保存数据...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_base / f"{project_id}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存项目配置
    with open(output_dir / "project_config.json", 'w', encoding='utf-8') as f:
        json.dump(project_config, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: project_config.json")
    
    # 保存原始文本
    with open(output_dir / "extracted_text.txt", 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"  ✅ 保存: extracted_text.txt ({len(text)} 字符)")
    
    # 保存分块数据
    chunks_data = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "index": i,
                "text": chunk,
                "length": len(chunk)
            }
            for i, chunk in enumerate(chunks)
        ]
    }
    with open(output_dir / "text_chunks.json", 'w', encoding='utf-8') as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: text_chunks.json ({len(chunks)} 个块)")
    
    # 保存图谱数据
    with open(output_dir / "graph_data.json", 'w', encoding='utf-8') as f:
        json.dump(graph_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: graph_data.json ({graph_data['node_count']} 节点, {graph_data['edge_count']} 边)")
    
    # 6. 生成分析报告
    print("\n📊 步骤6: 生成分析报告...")
    
    # 统计实体类型
    entity_types_count = {}
    for node in graph_data.get('nodes', []):
        for label in node.get('labels', []):
            if label not in ['Entity', 'Node']:
                entity_types_count[label] = entity_types_count.get(label, 0) + 1
    
    # 统计关系类型
    edge_types_count = {}
    for edge in graph_data.get('edges', []):
        name = edge.get('name', 'UNKNOWN')
        edge_types_count[name] = edge_types_count.get(name, 0) + 1
    
    # 生成报告
    report = {
        "project_id": project_id,
        "graph_id": graph_id,
        "timestamp": timestamp,
        "statistics": {
            "text_length": len(text),
            "chunks_count": len(chunks),
            "nodes_count": graph_data['node_count'],
            "edges_count": graph_data['edge_count']
        },
        "entity_types": entity_types_count,
        "edge_types": edge_types_count,
        "top_entities": [
            {
                "name": node['name'],
                "type": node.get('labels', ['Unknown'])[0] if node.get('labels') else 'Unknown',
                "summary": node.get('summary', '')[:100]
            }
            for node in sorted(graph_data.get('nodes', []), 
                             key=lambda x: len(x.get('labels', [])), 
                             reverse=True)[:10]
        ]
    }
    
    with open(output_dir / "analysis_report.json", 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 保存: analysis_report.json")
    
    # 打印摘要
    print("\n" + "=" * 80)
    print("📋 数据摘要")
    print("=" * 80)
    print(f"项目ID: {project_id}")
    print(f"图谱ID: {graph_id}")
    print(f"模拟需求: {project_config.get('simulation_requirement', '未设置')[:60]}...")
    print(f"\n数据统计:")
    print(f"  文本长度: {len(text)} 字符")
    print(f"  分块数量: {len(chunks)} 个")
    print(f"  图谱节点: {graph_data['node_count']} 个")
    print(f"  图谱边数: {graph_data['edge_count']} 条")
    print(f"\n实体类型分布:")
    for entity_type, count in sorted(entity_types_count.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {entity_type}: {count}")
    print(f"\n关系类型分布:")
    for edge_type, count in sorted(edge_types_count.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {edge_type}: {count}")
    
    print(f"\n输出目录: {output_dir}")
    print("=" * 80)
    print("✅ 完成!")


if __name__ == "__main__":
    main()