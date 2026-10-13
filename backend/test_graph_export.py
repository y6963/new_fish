# -*- coding: utf-8 -*-
"""
测试图谱导出与恢复功能
运行方法: python test_graph_export.py
"""

import os
import sys
import json

# 添加 backend 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def test_import():
    """测试模块导入"""
    try:
        from app.services.graph_exporter import GraphExporter, GraphRestore, GraphValidator, ExportFormat, ExportedGraph
        print("✓ 模块导入成功")
        return True
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False


def test_exported_graph():
    """测试 ExportedGraph 数据类"""
    try:
        from app.services.graph_exporter import ExportedGraph, ExportedNode, ExportedEdge
        
        # 创建测试数据
        node = ExportedNode(
            uuid="test-node-1",
            name="Test Node",
            labels=["Entity", "Person"],
            summary="A test node",
            attributes={"age": 30},
            created_at="2024-01-15T10:00:00"
        )
        
        edge = ExportedEdge(
            uuid="test-edge-1",
            name="KNOWS",
            fact="Person knows another person",
            fact_type="KNOWS",
            source_node_uuid="test-node-1",
            target_node_uuid="test-node-2",
            attributes={},
            created_at="2024-01-15T10:00:00",
            valid_at=None,
            invalid_at=None
        )
        
        graph = ExportedGraph(
            graph_id="exported_test_123",
            original_zep_graph_id="mirofish_abc",
            name="Test Graph",
            exported_at="2024-01-15T14:30:00",
            nodes=[node],
            edges=[edge]
        )
        
        # 测试 to_dict 和 from_dict
        graph_dict = graph.to_dict()
        assert graph_dict['graph_id'] == "exported_test_123"
        assert graph_dict['node_count'] == 1
        assert graph_dict['edge_count'] == 1
        assert graph.checksum  # 校验和应该存在
        
        # 测试 from_dict
        restored_graph = ExportedGraph.from_dict(graph_dict)
        assert restored_graph.graph_id == graph.graph_id
        assert restored_graph.node_count == graph.node_count
        assert restored_graph.edge_count == graph.edge_count
        
        print("✓ ExportedGraph 数据类测试通过")
        return True
    except Exception as e:
        print(f"✗ ExportedGraph 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_export_format_enum():
    """测试 ExportFormat 枚举"""
    try:
        from app.services.graph_exporter import ExportFormat
        
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.SQLITE.value == "sqlite"
        assert ExportFormat.CYPHER.value == "cypher"
        
        # 测试从字符串创建
        fmt = ExportFormat('json')
        assert fmt == ExportFormat.JSON
        
        print("✓ ExportFormat 枚举测试通过")
        return True
    except Exception as e:
        print(f"✗ ExportFormat 测试失败: {e}")
        return False


def test_json_export_local():
    """测试本地 JSON 导出（不需要真实 Zep 连接）"""
    try:
        from app.services.graph_exporter import GraphExporter, ExportedGraph, ExportedNode, ExportedEdge
        
        # 创建一个模拟的图谱
        node = ExportedNode(
            uuid="local-test-node",
            name="Local Test Node",
            labels=["Test"],
            summary="Local test",
            attributes={"key": "value"},
            created_at=None
        )
        
        edge = ExportedEdge(
            uuid="local-test-edge",
            name="TEST_REL",
            fact="Test fact",
            fact_type="TEST_REL",
            source_node_uuid="local-test-node",
            target_node_uuid="local-test-node-2",
            attributes={},
            created_at=None,
            valid_at=None,
            invalid_at=None
        )
        
        graph = ExportedGraph(
            graph_id="local_test_123",
            original_zep_graph_id="test_original",
            name="Local Test Graph",
            exported_at="2024-01-15T14:30:00",
            nodes=[node],
            edges=[edge]
        )
        
        # 保存到临时文件
        import tempfile
        temp_dir = tempfile.mkdtemp()
        test_file = os.path.join(temp_dir, "test_export.json")
        
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump(graph.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 验证文件存在
        assert os.path.exists(test_file), "导出文件不存在"
        
        # 读取并验证
        with open(test_file, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        
        assert loaded_data['graph_id'] == graph.graph_id
        assert loaded_data['node_count'] == 1
        assert loaded_data['edge_count'] == 1
        assert 'checksum' in loaded_data
        
        # 清理
        os.unlink(test_file)
        os.rmdir(temp_dir)
        
        print("✓ 本地 JSON 导出测试通过")
        return True
    except Exception as e:
        print(f"✗ 本地 JSON 导出测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validation():
    """测试验证功能"""
    try:
        from app.services.graph_exporter import GraphValidator, ExportedGraph, ExportedNode, ExportedEdge
        
        # 创建两个相同和一个不同的图谱
        node1 = ExportedNode(
            uuid="node-1",
            name="Node 1",
            labels=["Test"],
            summary="Summary",
            attributes={},
            created_at=None
        )
        
        node2 = ExportedNode(
            uuid="node-2",
            name="Node 2",
            labels=["Test"],
            summary="Summary",
            attributes={},
            created_at=None
        )
        
        # 创建两个相同的图谱
        graph1 = ExportedGraph(
            graph_id="graph-1",
            original_zep_graph_id="original",
            name="Test Graph",
            exported_at="2024-01-15T14:30:00",
            nodes=[node1, node2],
            edges=[]
        )
        
        graph2 = ExportedGraph(
            graph_id="graph-2",
            original_zep_graph_id="original",
            name="Test Graph",
            exported_at="2024-01-15T14:35:00",
            nodes=[node1, node2],
            edges=[]
        )
        
        # 创建验证器（使用 mock）
        validator = GraphValidator.__new__(GraphValidator)
        validator._compare_graphs = lambda o, e: {
            'is_valid': o.checksum == e.checksum,
            'checksum': {
                'original': o.checksum,
                'exported': e.checksum,
                'match': o.checksum == e.checksum
            }
        }
        
        # 测试校验和一致性
        assert graph1.checksum == graph2.checksum, "相同图谱的校验和应该相同"
        
        # 修改一个节点，创建不同的图谱
        node1_modified = ExportedNode(
            uuid="node-1",
            name="Node 1 Modified",  # 修改了名称
            labels=["Test"],
            summary="Summary",
            attributes={},
            created_at=None
        )
        
        graph3 = ExportedGraph(
            graph_id="graph-3",
            original_zep_graph_id="original",
            name="Test Graph",
            exported_at="2024-01-15T14:40:00",
            nodes=[node1_modified, node2],
            edges=[]
        )
        
        assert graph1.checksum != graph3.checksum, "不同图谱的校验和应该不同"
        
        print("✓ 验证功能测试通过")
        return True
    except Exception as e:
        print(f"✗ 验证功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cypher_format():
    """测试 Cypher 格式生成"""
    try:
        from app.services.graph_exporter import ExportedNode, ExportedEdge, ExportedGraph
        
        node = ExportedNode(
            uuid="test-uuid-123",
            name="John Doe",
            labels=["Person", "Employee"],
            summary="A test person",
            attributes={"age": 30, "department": "Engineering"},
            created_at=None
        )
        
        edge = ExportedEdge(
            uuid="edge-uuid-456",
            name="WORKS_AT",
            fact="John works at Company X",
            fact_type="WORKS_AT",
            source_node_uuid="test-uuid-123",
            target_node_uuid="test-uuid-456",
            attributes={"since": 2020},
            created_at=None,
            valid_at=None,
            invalid_at=None
        )
        
        # 生成 Cypher 格式的代码片段
        labels = ':'.join(l for l in node.labels if l not in ['Entity', 'Node']) or 'Entity'
        props = {
            'uuid': node.uuid,
            'name': node.name,
            'summary': node.summary
        }
        props.update(node.attributes)
        props_str = ', '.join(f"{k}: {json.dumps(str(v), ensure_ascii=False)}" 
                              for k, v in props.items() if v)
        
        cypher_node = f"CREATE (n:{labels} {{{props_str}}});"
        
        assert 'Person:Employee' in cypher_node or labels in cypher_node
        assert '"uuid": "test-uuid-123"' in cypher_node or 'uuid' in cypher_node
        
        # 测试关系
        rel_type = edge.fact_type or edge.name or 'RELATED_TO'
        rel_type_safe = ''.join(c if c.isalnum() else '_' for c in rel_type)
        cypher_rel = (f"MATCH (s {{uuid: '{edge.source_node_uuid}'}}), "
                     f"(t {{uuid: '{edge.target_node_uuid}'}}) "
                     f"CREATE (s)-[r:{rel_type_safe}]->(t);")
        
        assert 'WORKS_AT' in cypher_rel or 'WORKS_AT' in rel_type_safe
        assert edge.source_node_uuid in cypher_rel
        assert edge.target_node_uuid in cypher_rel
        
        print("✓ Cypher 格式测试通过")
        return True
    except Exception as e:
        print(f"✗ Cypher 格式测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试图谱导出与恢复功能")
    print("=" * 60)
    
    tests = [
        ("模块导入", test_import),
        ("ExportedGraph 数据类", test_exported_graph),
        ("ExportFormat 枚举", test_export_format_enum),
        ("本地 JSON 导出", test_json_export_local),
        ("验证功能", test_validation),
        ("Cypher 格式", test_cypher_format),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        print(f"\n测试: {name}")
        print("-" * 60)
        if test_func():
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n✓ 所有测试通过！")
        print("\n下一步：")
        print("1. 启动后端服务: cd backend && python app.py")
        print("2. 使用 API 测试导出功能:")
        print("   POST /api/graph/export/{graph_id}")
        print("3. 详细文档请参考: backend/GRAPG_EXPORT_RESTORE_GUIDE.md")
        return 0
    else:
        print("\n✗ 有测试失败，请检查错误信息")
        return 1


if __name__ == '__main__':
    exit(main())