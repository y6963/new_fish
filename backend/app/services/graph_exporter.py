"""
知识图谱导出与恢复模块
实现图谱数据的独立导出、持久化和恢复功能
"""

import os
import json
import sqlite3
import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from ..utils.zep import get_zep_client
from .graph_builder import GraphBuilderService

logger = get_logger('mirofish.graph_exporter')


class ExportFormat(str, Enum):
    """导出格式"""
    JSON = "json"
    SQLITE = "sqlite"
    CYPHER = "cypher"


@dataclass
class ExportedNode:
    """导出的节点"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    created_at: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportedNode':
        return cls(
            uuid=data['uuid'],
            name=data.get('name', ''),
            labels=data.get('labels', []),
            summary=data.get('summary', ''),
            attributes=data.get('attributes', {}),
            created_at=data.get('created_at')
        )


@dataclass
class ExportedEdge:
    """导出的边"""
    uuid: str
    name: str
    fact: str
    fact_type: str
    source_node_uuid: str
    target_node_uuid: str
    attributes: Dict[str, Any]
    created_at: Optional[str]
    valid_at: Optional[str]
    invalid_at: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportedEdge':
        return cls(
            uuid=data['uuid'],
            name=data.get('name', ''),
            fact=data.get('fact', ''),
            fact_type=data.get('fact_type', ''),
            source_node_uuid=data['source_node_uuid'],
            target_node_uuid=data['target_node_uuid'],
            attributes=data.get('attributes', {}),
            created_at=data.get('created_at'),
            valid_at=data.get('valid_at'),
            invalid_at=data.get('invalid_at')
        )


@dataclass
class ExportedGraph:
    """导出的图谱"""
    graph_id: str
    original_zep_graph_id: str
    name: str
    exported_at: str
    export_version: str = "1.0"
    nodes: List[ExportedNode] = field(default_factory=list)
    edges: List[ExportedEdge] = field(default_factory=list)
    
    @property
    def node_count(self) -> int:
        return len(self.nodes)
    
    @property
    def edge_count(self) -> int:
        return len(self.edges)
    
    @property
    def checksum(self) -> str:
        """计算图谱数据的校验和"""
        data = {
            'nodes': [n.to_dict() for n in self.nodes],
            'edges': [e.to_dict() for e in self.edges]
        }
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'graph_id': self.graph_id,
            'original_zep_graph_id': self.original_zep_graph_id,
            'name': self.name,
            'exported_at': self.exported_at,
            'export_version': self.export_version,
            'node_count': self.node_count,
            'edge_count': self.edge_count,
            'checksum': self.checksum,
            'nodes': [n.to_dict() for n in self.nodes],
            'edges': [e.to_dict() for e in self.edges]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportedGraph':
        return cls(
            graph_id=data['graph_id'],
            original_zep_graph_id=data['original_zep_graph_id'],
            name=data['name'],
            exported_at=data['exported_at'],
            export_version=data.get('export_version', '1.0'),
            nodes=[ExportedNode.from_dict(n) for n in data.get('nodes', [])],
            edges=[ExportedEdge.from_dict(e) for e in data.get('edges', [])]
        )


class GraphExporter:
    """
    图谱导出器
    负责将 Zep Cloud 图谱导出为独立可用的格式
    """
    
    EXPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'exports')
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        self.client = get_zep_client(self.api_key)
        self.builder = GraphBuilderService(api_key=self.api_key)
        os.makedirs(self.EXPORTS_DIR, exist_ok=True)
    
    def fetch_graph_from_zep(self, graph_id: str) -> ExportedGraph:
        """
        从 Zep Cloud 获取图谱数据
        
        Args:
            graph_id: Zep 图谱 ID
            
        Returns:
            ExportedGraph 对象
        """
        logger.info(f"从 Zep 获取图谱数据: {graph_id}")
        
        # 获取图谱信息
        try:
            zep_graph = self.client.graph.get(graph_id)
            graph_name = getattr(zep_graph, 'name', 'Unknown Graph')
        except Exception as e:
            logger.warning(f"无法获取图谱名称: {e}")
            graph_name = f"Graph {graph_id[:8]}"
        
        # 获取所有节点
        nodes_raw = fetch_all_nodes(self.client, graph_id)
        nodes = []
        for node in nodes_raw:
            created_at = getattr(node, 'created_at', None)
            nodes.append(ExportedNode(
                uuid=node.uuid_,
                name=node.name or '',
                labels=node.labels or [],
                summary=node.summary or '',
                attributes=node.attributes or {},
                created_at=str(created_at) if created_at else None
            ))
        
        # 获取所有边
        edges_raw = fetch_all_edges(self.client, graph_id)
        edges = []
        for edge in edges_raw:
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            
            edges.append(ExportedEdge(
                uuid=edge.uuid_,
                name=edge.name or '',
                fact=edge.fact or '',
                fact_type=getattr(edge, 'fact_type', None) or edge.name or '',
                source_node_uuid=edge.source_node_uuid,
                target_node_uuid=edge.target_node_uuid,
                attributes=edge.attributes or {},
                created_at=str(created_at) if created_at else None,
                valid_at=str(valid_at) if valid_at else None,
                invalid_at=str(invalid_at) if invalid_at else None
            ))
        
        return ExportedGraph(
            graph_id=f"exported_{uuid.uuid4().hex[:12]}",
            original_zep_graph_id=graph_id,
            name=graph_name,
            exported_at=datetime.now().isoformat(),
            nodes=nodes,
            edges=edges
        )
    
    def export_to_json(self, graph_id: str, output_filename: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        导出图谱为 JSON 格式
        
        Args:
            graph_id: Zep 图谱 ID
            output_filename: 输出文件名（可选，默认自动生成）
            
        Returns:
            (文件路径, 图谱数据字典)
        """
        exported_graph = self.fetch_graph_from_zep(graph_id)
        
        if output_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = "".join(c if c.isalnum() else '_' for c in exported_graph.name[:20])
            output_filename = f"{safe_name}_{timestamp}.json"
        
        output_path = os.path.join(self.EXPORTS_DIR, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(exported_graph.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"图谱已导出到 JSON: {output_path}, 节点={exported_graph.node_count}, 边={exported_graph.edge_count}")
        
        return output_path, exported_graph.to_dict()
    
    def export_to_sqlite(self, graph_id: str, output_filename: Optional[str] = None) -> str:
        """
        导出图谱为 SQLite 数据库
        
        Args:
            graph_id: Zep 图谱 ID
            output_filename: 输出文件名（可选，默认自动生成）
            
        Returns:
            数据库文件路径
        """
        exported_graph = self.fetch_graph_from_zep(graph_id)
        
        if output_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = "".join(c if c.isalnum() else '_' for c in exported_graph.name[:20])
            output_filename = f"{safe_name}_{timestamp}.db"
        
        output_path = os.path.join(self.EXPORTS_DIR, output_filename)
        
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()
        
        # 创建表结构
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS graph_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                uuid TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                labels TEXT NOT NULL,
                summary TEXT,
                attributes TEXT,
                created_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS edges (
                uuid TEXT PRIMARY KEY,
                name TEXT,
                fact TEXT,
                fact_type TEXT,
                source_node_uuid TEXT NOT NULL,
                target_node_uuid TEXT NOT NULL,
                attributes TEXT,
                created_at TEXT,
                valid_at TEXT,
                invalid_at TEXT,
                FOREIGN KEY (source_node_uuid) REFERENCES nodes(uuid),
                FOREIGN KEY (target_node_uuid) REFERENCES nodes(uuid)
            )
        ''')
        
        # 插入元数据
        meta_data = [
            ('graph_id', exported_graph.graph_id),
            ('original_zep_graph_id', exported_graph.original_zep_graph_id),
            ('name', exported_graph.name),
            ('exported_at', exported_graph.exported_at),
            ('export_version', exported_graph.export_version),
            ('checksum', exported_graph.checksum),
            ('node_count', str(exported_graph.node_count)),
            ('edge_count', str(exported_graph.edge_count))
        ]
        cursor.executemany('INSERT OR REPLACE INTO graph_meta VALUES (?, ?)', meta_data)
        
        # 插入节点
        for node in exported_graph.nodes:
            cursor.execute('''
                INSERT OR REPLACE INTO nodes VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                node.uuid,
                node.name,
                json.dumps(node.labels, ensure_ascii=False),
                node.summary,
                json.dumps(node.attributes, ensure_ascii=False),
                node.created_at
            ))
        
        # 插入边
        for edge in exported_graph.edges:
            cursor.execute('''
                INSERT OR REPLACE INTO edges VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                edge.uuid,
                edge.name,
                edge.fact,
                edge.fact_type,
                edge.source_node_uuid,
                edge.target_node_uuid,
                json.dumps(edge.attributes, ensure_ascii=False),
                edge.created_at,
                edge.valid_at,
                edge.invalid_at
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"图谱已导出到 SQLite: {output_path}, 节点={exported_graph.node_count}, 边={exported_graph.edge_count}")
        
        return output_path
    
    def export_to_cypher(self, graph_id: str, output_filename: Optional[str] = None) -> str:
        """
        导出图谱为 Cypher 格式（Neo4j 兼容）
        
        Args:
            graph_id: Zep 图谱 ID
            output_filename: 输出文件名（可选，默认自动生成）
            
        Returns:
            Cypher 文件路径
        """
        exported_graph = self.fetch_graph_from_zep(graph_id)
        
        if output_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = "".join(c if c.isalnum() else '_' for c in exported_graph.name[:20])
            output_filename = f"{safe_name}_{timestamp}.cypher"
        
        output_path = os.path.join(self.EXPORTS_DIR, output_filename)
        
        cypher_lines = []
        cypher_lines.append("// Graph Export - Neo4j Cypher Format")
        cypher_lines.append(f"// Original Graph: {exported_graph.name}")
        cypher_lines.append(f"// Exported at: {exported_graph.exported_at}")
        cypher_lines.append(f"// Export ID: {exported_graph.graph_id}")
        cypher_lines.append("")
        
        # 创建节点
        cypher_lines.append("// Create Nodes")
        for node in exported_graph.nodes:
            labels = ':'.join(l for l in node.labels if l not in ['Entity', 'Node']) or 'Entity'
            
            props = {
                'uuid': node.uuid,
                'name': node.name,
                'summary': node.summary
            }
            props.update(node.attributes)
            
            props_str = ', '.join(f"{k}: {json.dumps(str(v), ensure_ascii=False)}" 
                                  for k, v in props.items() if v)
            
            cypher_lines.append(f"CREATE (n:{labels} {{{props_str}}});")
        
        cypher_lines.append("")
        cypher_lines.append("// Create Relationships")
        
        # 创建关系
        for edge in exported_graph.edges:
            rel_type = edge.fact_type or edge.name or 'RELATED_TO'
            rel_type = ''.join(c if c.isalnum() else '_' for c in rel_type)
            
            props = {}
            if edge.fact:
                props['fact'] = edge.fact
            props.update(edge.attributes)
            
            props_str = ', '.join(f"{k}: {json.dumps(str(v), ensure_ascii=False)}" 
                                  for k, v in props.items() if v)
            
            if props_str:
                cypher_lines.append(
                    f"MATCH (s {{uuid: '{edge.source_node_uuid}'}}), "
                    f"(t {{uuid: '{edge.target_node_uuid}'}}) "
                    f"CREATE (s)-[r:{rel_type} {{{props_str}}}]->(t);"
                )
            else:
                cypher_lines.append(
                    f"MATCH (s {{uuid: '{edge.source_node_uuid}'}}), "
                    f"(t {{uuid: '{edge.target_node_uuid}'}}) "
                    f"CREATE (s)-[r:{rel_type}]->(t);"
                )
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(cypher_lines))
        
        logger.info(f"图谱已导出为 Cypher: {output_path}")
        
        return output_path
    
    def export_graph(self, graph_id: str, format: ExportFormat = ExportFormat.JSON) -> str:
        """
        统一导出接口
        
        Args:
            graph_id: Zep 图谱 ID
            format: 导出格式
            
        Returns:
            导出文件路径
        """
        if format == ExportFormat.JSON:
            path, _ = self.export_to_json(graph_id)
            return path
        elif format == ExportFormat.SQLITE:
            return self.export_to_sqlite(graph_id)
        elif format == ExportFormat.CYPHER:
            return self.export_to_cypher(graph_id)
        else:
            raise ValueError(f"不支持的导出格式: {format}")
    
    def list_exports(self) -> List[Dict[str, Any]]:
        """列出所有导出文件"""
        exports = []
        for filename in os.listdir(self.EXPORTS_DIR):
            filepath = os.path.join(self.EXPORTS_DIR, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                exports.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'format': os.path.splitext(filename)[1].lstrip('.')
                })
        return sorted(exports, key=lambda x: x['created_at'], reverse=True)


class GraphRestore:
    """
    图谱恢复器
    负责从导出的文件恢复图谱数据
    """
    
    EXPORTS_DIR = GraphExporter.EXPORTS_DIR
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        self.client = get_zep_client(self.api_key)
        self.builder = GraphBuilderService(api_key=self.api_key)
    
    def load_from_json(self, filepath: str) -> ExportedGraph:
        """从 JSON 文件加载图谱"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return ExportedGraph.from_dict(data)
    
    def load_from_sqlite(self, filepath: str) -> ExportedGraph:
        """从 SQLite 数据库加载图谱"""
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        
        # 读取元数据
        cursor.execute('SELECT key, value FROM graph_meta')
        meta = dict(cursor.fetchall())
        
        # 读取节点
        cursor.execute('SELECT uuid, name, labels, summary, attributes, created_at FROM nodes')
        nodes = []
        for row in cursor.fetchall():
            nodes.append(ExportedNode(
                uuid=row[0],
                name=row[1],
                labels=json.loads(row[2]),
                summary=row[3] or '',
                attributes=json.loads(row[4]) if row[4] else {},
                created_at=row[5]
            ))
        
        # 读取边
        cursor.execute('''
            SELECT uuid, name, fact, fact_type, source_node_uuid, target_node_uuid, 
                   attributes, created_at, valid_at, invalid_at 
            FROM edges
        ''')
        edges = []
        for row in cursor.fetchall():
            edges.append(ExportedEdge(
                uuid=row[0],
                name=row[1] or '',
                fact=row[2] or '',
                fact_type=row[3] or '',
                source_node_uuid=row[4],
                target_node_uuid=row[5],
                attributes=json.loads(row[6]) if row[6] else {},
                created_at=row[7],
                valid_at=row[8],
                invalid_at=row[9]
            ))
        
        conn.close()
        
        return ExportedGraph(
            graph_id=meta.get('graph_id', ''),
            original_zep_graph_id=meta.get('original_zep_graph_id', ''),
            name=meta.get('name', ''),
            exported_at=meta.get('exported_at', ''),
            export_version=meta.get('export_version', '1.0'),
            nodes=nodes,
            edges=edges
        )
    
    def load_exported_graph(self, filepath: str) -> ExportedGraph:
        """自动识别格式并加载图谱"""
        ext = os.path.splitext(filepath)[1].lower()
        
        if ext == '.json':
            return self.load_from_json(filepath)
        elif ext in ['.db', '.sqlite', '.sqlite3']:
            return self.load_from_sqlite(filepath)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
    
    def get_local_graph_data(self, filepath: str) -> Dict[str, Any]:
        """
        获取本地图谱数据（用于前端显示）
        
        Args:
            filepath: 导出文件路径
            
        Returns:
            前端所需的图谱数据格式
        """
        graph = self.load_exported_graph(filepath)
        
        # 构建前端需要的格式
        nodes_data = []
        for node in graph.nodes:
            nodes_data.append({
                "uuid": node.uuid,
                "name": node.name,
                "labels": node.labels,
                "summary": node.summary,
                "attributes": node.attributes,
                "created_at": node.created_at,
            })
        
        # 构建节点映射
        node_map = {node.uuid: node.name for node in graph.nodes}
        
        edges_data = []
        for edge in graph.edges:
            edges_data.append({
                "uuid": edge.uuid,
                "name": edge.name,
                "fact": edge.fact,
                "fact_type": edge.fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes,
                "created_at": edge.created_at,
                "valid_at": edge.valid_at,
                "invalid_at": edge.invalid_at,
            })
        
        return {
            "graph_id": graph.graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
            "is_local": True,
            "original_zep_graph_id": graph.original_zep_graph_id,
            "source_file": os.path.basename(filepath)
        }


class GraphValidator:
    """
    图谱验证器
    负责验证恢复前后数据的一致性
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        self.client = get_zep_client(self.api_key)
        self.exporter = GraphExporter(api_key=self.api_key)
        self.restorer = GraphRestore(api_key=self.api_key)
    
    def validate_export(self, graph_id: str, export_filepath: str) -> Dict[str, Any]:
        """
        验证导出的图谱数据
        
        Args:
            graph_id: Zep 图谱 ID
            export_filepath: 导出文件路径
            
        Returns:
            验证报告
        """
        # 重新从 Zep 获取原始数据
        original_graph = self.exporter.fetch_graph_from_zep(graph_id)
        
        # 加载导出文件
        exported_graph = self.restorer.load_exported_graph(export_filepath)
        
        return self._compare_graphs(original_graph, exported_graph)
    
    def _compare_graphs(self, original: ExportedGraph, exported: ExportedGraph) -> Dict[str, Any]:
        """比较两个图谱的一致性"""
        report = {
            'is_valid': True,
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'original_nodes': original.node_count,
                'exported_nodes': exported.node_count,
                'original_edges': original.edge_count,
                'exported_edges': exported.edge_count,
            },
            'checksum': {
                'original': original.checksum,
                'exported': exported.checksum,
                'match': original.checksum == exported.checksum
            },
            'nodes': {
                'missing': [],
                'extra': [],
                'mismatch': []
            },
            'edges': {
                'missing': [],
                'extra': [],
                'mismatch': []
            }
        }
        
        # 创建节点映射
        original_nodes = {n.uuid: n for n in original.nodes}
        exported_nodes = {n.uuid: n for n in exported.nodes}
        
        # 检查节点
        for uuid, node in original_nodes.items():
            if uuid not in exported_nodes:
                report['nodes']['missing'].append(uuid)
            else:
                exported_node = exported_nodes[uuid]
                diff = self._compare_nodes(node, exported_node)
                if diff:
                    report['nodes']['mismatch'].append({
                        'uuid': uuid,
                        'differences': diff
                    })
        
        for uuid in exported_nodes:
            if uuid not in original_nodes:
                report['nodes']['extra'].append(uuid)
        
        # 创建边映射
        original_edges = {e.uuid: e for e in original.edges}
        exported_edges = {e.uuid: e for e in exported.edges}
        
        # 检查边
        for uuid, edge in original_edges.items():
            if uuid not in exported_edges:
                report['edges']['missing'].append(uuid)
            else:
                exported_edge = exported_edges[uuid]
                diff = self._compare_edges(edge, exported_edge)
                if diff:
                    report['edges']['mismatch'].append({
                        'uuid': uuid,
                        'differences': diff
                    })
        
        for uuid in exported_edges:
            if uuid not in original_edges:
                report['edges']['extra'].append(uuid)
        
        # 判断是否通过验证
        report['is_valid'] = (
            len(report['nodes']['missing']) == 0 and
            len(report['nodes']['extra']) == 0 and
            len(report['nodes']['mismatch']) == 0 and
            len(report['edges']['missing']) == 0 and
            len(report['edges']['extra']) == 0 and
            len(report['edges']['mismatch']) == 0 and
            report['checksum']['match']
        )
        
        return report
    
    def _compare_nodes(self, original: ExportedNode, exported: ExportedNode) -> List[str]:
        """比较两个节点的差异"""
        differences = []
        
        if original.name != exported.name:
            differences.append(f"name: '{original.name}' != '{exported.name}'")
        
        if set(original.labels) != set(exported.labels):
            differences.append(f"labels: {original.labels} != {exported.labels}")
        
        if original.summary != exported.summary:
            differences.append(f"summary mismatch")
        
        if original.attributes != exported.attributes:
            differences.append(f"attributes mismatch")
        
        return differences
    
    def _compare_edges(self, original: ExportedEdge, exported: ExportedEdge) -> List[str]:
        """比较两条边的差异"""
        differences = []
        
        if original.name != exported.name:
            differences.append(f"name: '{original.name}' != '{exported.name}'")
        
        if original.source_node_uuid != exported.source_node_uuid:
            differences.append("source_node_uuid mismatch")
        
        if original.target_node_uuid != exported.target_node_uuid:
            differences.append("target_node_uuid mismatch")
        
        if original.fact != exported.fact:
            differences.append(f"fact mismatch")
        
        if original.attributes != exported.attributes:
            differences.append(f"attributes mismatch")
        
        return differences
    
    def verify_local_graph(self, filepath: str) -> Dict[str, Any]:
        """
        验证本地导出的图谱文件
        
        Args:
            filepath: 导出文件路径
            
        Returns:
            验证报告
        """
        try:
            graph = self.restorer.load_exported_graph(filepath)
            
            return {
                'is_valid': True,
                'timestamp': datetime.now().isoformat(),
                'graph_id': graph.graph_id,
                'original_zep_graph_id': graph.original_zep_graph_id,
                'name': graph.name,
                'exported_at': graph.exported_at,
                'export_version': graph.export_version,
                'checksum': graph.checksum,
                'node_count': graph.node_count,
                'edge_count': graph.edge_count,
                'file_path': filepath,
                'message': '图谱文件完整且可读'
            }
        except Exception as e:
            return {
                'is_valid': False,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'file_path': filepath,
                'message': f'图谱文件验证失败: {str(e)}'
            }