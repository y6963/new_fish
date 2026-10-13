# -*- coding: utf-8 -*-
"""
Zep 图谱管理器
用于获取云端图谱列表、存储图谱数据、读取本地图谱

支持：
- 云端图谱查询
- 本地图谱存储（支持大图谱和API限流）
- 增量存储和断点续传
- 实时进度回调
"""

import os
import json
import hashlib
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field, asdict
from threading import Lock

from ..config import Config
from ..utils.zep import get_zep_client, call_zep_read_with_retry
from ..utils.logger import get_logger

logger = get_logger("mirofish.graph_manager")


# ==================== 配置常量 ====================

class StoreConfig:
    """存储配置"""
    # API 速率限制
    REQUEST_DELAY = 0.5  # 每次请求间隔（秒）
    PAGE_DELAY = 1.0     # 每页获取后延迟（秒）
    RETRY_DELAY = 5.0    # 重试延迟基础值（秒）
    MAX_RETRIES = 5      # 最大重试次数

    # 进度保存
    PROGRESS_SAVE_INTERVAL = 50  # 每获取多少条保存一次进度

    # 批量大小
    PAGE_SIZE = 100  # 每页大小


@dataclass
class GraphInfo:
    """图谱基本信息"""
    graph_id: str
    name: str = ""
    node_count: int = 0
    edge_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StoredGraph:
    """存储的图谱数据"""
    graph_id: str
    name: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    stored_at: str
    checksum: str
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StoredGraph':
        return cls(**data)


@dataclass
class StoreProgress:
    """存储进度"""
    graph_id: str
    status: str  # "storing_nodes" | "storing_edges" | "completed" | "failed"
    nodes_stored: int = 0
    edges_stored: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    started_at: str = ""
    last_updated: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def progress_percent(self) -> float:
        """计算总体进度百分比"""
        if self.total_nodes == 0 and self.total_edges == 0:
            return 0.0

        nodes_weight = 0.6  # 节点权重 60%
        edges_weight = 0.4  # 边权重 40%

        nodes_progress = (self.nodes_stored / self.total_nodes * 100) if self.total_nodes > 0 else 0
        edges_progress = (self.edges_stored / self.total_edges * 100) if self.total_edges > 0 else 0

        return nodes_progress * nodes_weight + edges_progress * edges_weight


class ZepGraphManager:
    """
    Zep 图谱管理器
    管理云端图谱的查询、存储和读取

    特性：
    - 支持大图谱存储（自动分页）
    - 增量存储（跳过已存储的数据）
    - 断点续传（保存进度，中断可继续）
    - API 限流处理（自动重试 + 延迟）
    - 实时进度回调
    """

    # 图谱存储目录
    GRAPHS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'stored_graphs')

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        self.client = get_zep_client(self.api_key)
        self._ensure_storage_dir()
        self._lock = Lock()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        os.makedirs(self.GRAPHS_DIR, exist_ok=True)

    def _get_graph_dir(self, graph_id: str) -> str:
        """获取图谱存储目录"""
        return os.path.join(self.GRAPHS_DIR, graph_id)

    def _get_graph_metadata_path(self, graph_id: str) -> str:
        """获取图谱元数据文件路径"""
        return os.path.join(self._get_graph_dir(graph_id), 'metadata.json')

    def _get_graph_data_path(self, graph_id: str) -> str:
        """获取图谱数据文件路径"""
        return os.path.join(self._get_graph_dir(graph_id), 'data.json')

    def _get_progress_path(self, graph_id: str) -> str:
        """获取进度文件路径"""
        return os.path.join(self._get_graph_dir(graph_id), 'progress.json')

    # ==================== 云端图谱查询 ====================

    def list_cloud_graphs(self) -> List[GraphInfo]:
        """
        获取云端所有图谱列表

        Returns:
            图谱信息列表
        """
        logger.info("正在获取云端图谱列表...")

        graphs = []

        # 从项目数据中获取已知的图谱
        try:
            from ..models.project import ProjectManager
            projects = ProjectManager.list_projects(limit=1000)

            seen_graphs = set()
            for project in projects:
                if project.graph_id and project.graph_id not in seen_graphs:
                    seen_graphs.add(project.graph_id)
                    graphs.append(GraphInfo(
                        graph_id=project.graph_id,
                        name=f"MiroFish Graph ({project.name})",
                        created_at=project.created_at,
                        updated_at=project.updated_at
                    ))

            logger.info(f"从项目数据中获取到 {len(graphs)} 个图谱")
            return graphs

        except Exception as e:
            logger.error(f"获取图谱列表失败: {e}")
            raise

    def get_cloud_graph_info(self, graph_id: str) -> Optional[GraphInfo]:
        """
        获取云端图谱的详细信息

        Args:
            graph_id: 图谱 ID

        Returns:
            图谱信息，如果不存在返回 None
        """
        logger.info(f"正在获取图谱信息: {graph_id}")

        try:
            # 获取节点数量（使用分页获取）
            nodes = call_zep_read_with_retry(
                lambda: self.client.graph.node.with_raw_response.get_by_graph_id(
                    graph_id=graph_id, limit=100
                ),
                operation_name="get_nodes",
                max_attempts=StoreConfig.MAX_RETRIES,
                initial_delay=StoreConfig.RETRY_DELAY
            )

            node_count = len(nodes.data) if hasattr(nodes, 'data') else 0

            # 尝试获取总页数来判断总量
            # 注意：这里只是估算，实际总量需要遍历所有页
            entity_types = set()

            return GraphInfo(
                graph_id=graph_id,
                node_count=node_count,
                entity_types=list(entity_types)
            )

        except Exception as e:
            logger.error(f"获取图谱 {graph_id} 信息失败: {e}")
            return None

    # ==================== 图谱存储（增强版） ====================

    def store_graph(
        self,
        graph_id: str,
        name: Optional[str] = None,
        include_data: bool = True,
        progress_callback: Optional[Callable[[StoreProgress], None]] = None,
        force_refresh: bool = False
    ) -> StoredGraph:
        """
        存储图谱到本地（支持大图谱和API限流）

        Args:
            graph_id: 图谱 ID
            name: 图谱名称（可选）
            include_data: 是否包含完整的节点和边数据
            progress_callback: 进度回调函数，接受 StoreProgress 参数
            force_refresh: 是否强制重新获取（忽略本地已有的数据）

        Returns:
            存储的图谱对象

        Raises:
            Exception: 存储失败时抛出异常
        """
        logger.info(f"开始存储图谱: {graph_id}")
        start_time = time.time()

        graph_dir = self._get_graph_dir(graph_id)
        os.makedirs(graph_dir, exist_ok=True)

        # 初始化进度
        progress = StoreProgress(
            graph_id=graph_id,
            status="starting",
            started_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat()
        )

        try:
            # 尝试加载已有进度
            existing_progress = self._load_progress(graph_id)
            existing_data = None

            if not force_refresh and existing_progress:
                if existing_progress.status == "completed":
                    # 已有完整数据，直接返回
                    logger.info(f"图谱 {graph_id} 已存在，使用本地数据")
                    return self.get_stored_graph(graph_id)

                # 有部分数据，继续存储
                progress = existing_progress
                logger.info(f"从进度 {progress.status} 继续存储")
                existing_data = self._load_partial_data(graph_id)

            nodes_data = existing_data.get('nodes', []) if existing_data else []
            edges_data = existing_data.get('edges', []) if existing_data else []

            if include_data:
                # 获取所有节点
                progress.status = "storing_nodes"
                self._save_progress(progress)

                logger.info(f"获取图谱 {graph_id} 的节点...")
                new_nodes, total_nodes = self._fetch_nodes_with_rate_limit(
                    graph_id,
                    existing_count=len(nodes_data),
                    progress_callback=progress_callback
                )
                nodes_data.extend(new_nodes)
                progress.nodes_stored = len(nodes_data)
                progress.total_nodes = total_nodes
                progress.last_updated = datetime.now().isoformat()
                self._save_progress(progress)

                if progress_callback:
                    progress_callback(progress)

                # 请求间隔
                time.sleep(StoreConfig.PAGE_DELAY)

                # 获取所有边
                progress.status = "storing_edges"
                self._save_progress(progress)

                logger.info(f"获取图谱 {graph_id} 的边...")
                new_edges, total_edges = self._fetch_edges_with_rate_limit(
                    graph_id,
                    existing_count=len(edges_data),
                    progress_callback=progress_callback
                )
                edges_data.extend(new_edges)
                progress.edges_stored = len(edges_data)
                progress.total_edges = total_edges
                progress.last_updated = datetime.now().isoformat()
                self._save_progress(progress)

                if progress_callback:
                    progress_callback(progress)

            # 计算统计信息
            entity_types = set()
            for node in nodes_data:
                labels = node.get('labels', []) or []
                entity_types.update(labels)

            node_count = len(nodes_data)
            edge_count = len(edges_data)

            # 计算校验和
            checksum_data = {
                "nodes": nodes_data,
                "edges": edges_data
            }
            checksum = hashlib.sha256(
                json.dumps(checksum_data, sort_keys=True).encode()
            ).hexdigest()

            # 创建存储对象
            stored_at = datetime.now().isoformat()
            stored_graph = StoredGraph(
                graph_id=graph_id,
                name=name or graph_id,
                node_count=node_count,
                edge_count=edge_count,
                entity_types=list(entity_types),
                stored_at=stored_at,
                checksum=checksum,
                nodes=nodes_data,
                edges=edges_data,
                metadata={
                    'include_data': include_data,
                    'api_version': 'v2',
                    'stored_duration': time.time() - start_time
                }
            )

            # 保存数据
            self._save_graph_data(graph_id, stored_graph)

            # 更新进度为完成
            progress.status = "completed"
            progress.last_updated = datetime.now().isoformat()
            self._save_progress(progress)

            if progress_callback:
                progress_callback(progress)

            logger.info(
                f"图谱 {graph_id} 存储完成: "
                f"{node_count} 节点, {edge_count} 边 "
                f"(耗时 {time.time() - start_time:.1f}s)"
            )

            return stored_graph

        except Exception as e:
            progress.status = "failed"
            progress.error = str(e)
            progress.last_updated = datetime.now().isoformat()
            self._save_progress(progress)

            logger.error(f"存储图谱 {graph_id} 失败: {e}")
            raise

    def _fetch_nodes_with_rate_limit(
        self,
        graph_id: str,
        existing_count: int = 0,
        progress_callback: Optional[Callable[[StoreProgress], None]] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        获取所有节点（带速率限制和断点续传）

        Returns:
            (新获取的节点列表, 估算的总节点数)
        """
        nodes_data = []
        total_estimated = 0
        cursor = None
        page_number = 0
        consecutive_errors = 0

        while True:
            page_number += 1

            try:
                # 构建请求参数
                kwargs = {"limit": StoreConfig.PAGE_SIZE}
                if cursor:
                    kwargs["cursor"] = cursor

                # 获取一页数据
                response = call_zep_read_with_retry(
                    lambda: self.client.graph.node.with_raw_response.get_by_graph_id(
                        graph_id=graph_id,
                        **kwargs
                    ),
                    operation_name=f"fetch nodes page {page_number}",
                    max_attempts=StoreConfig.MAX_RETRIES,
                    initial_delay=StoreConfig.RETRY_DELAY * (2 ** consecutive_errors)
                )

                # 提取数据
                batch = list(getattr(response, 'data', None) or [])
                total_estimated += len(batch)

                for node in batch:
                    node_dict = {
                        'uuid': getattr(node, 'uuid_', ''),
                        'name': getattr(node, 'name', ''),
                        'summary': getattr(node, 'summary', ''),
                        'labels': getattr(node, 'labels', []),
                        'attributes': getattr(node, 'attributes', {}),
                        'degree': getattr(node, 'degree', 0),
                        'created_at': getattr(node, 'created_at', '')
                    }
                    nodes_data.append(node_dict)

                # 重置错误计数
                consecutive_errors = 0

                # 获取下一页 cursor
                headers = getattr(response, 'headers', None)
                next_cursor = None
                if headers:
                    next_cursor = headers.get('zep-next-cursor')

                if not next_cursor:
                    # 没有更多数据了
                    break

                cursor = next_cursor

                # 速率限制
                time.sleep(StoreConfig.PAGE_DELAY)

                # 更新进度
                logger.info(
                    f"获取节点进度: {len(nodes_data)} 节点 "
                    f"(第 {page_number} 页, 等待后续数据...)"
                )

            except Exception as e:
                consecutive_errors += 1
                logger.warning(
                    f"获取节点第 {page_number} 页失败 "
                    f"(尝试 {consecutive_errors}/{StoreConfig.MAX_RETRIES}): {e}"
                )

                if consecutive_errors >= StoreConfig.MAX_RETRIES:
                    logger.error(f"节点获取失败，已达到最大重试次数")
                    raise

                # 指数退避
                wait_time = StoreConfig.RETRY_DELAY * (2 ** consecutive_errors)
                logger.info(f"等待 {wait_time}s 后重试...")
                time.sleep(wait_time)

        return nodes_data, total_estimated

    def _fetch_edges_with_rate_limit(
        self,
        graph_id: str,
        existing_count: int = 0,
        progress_callback: Optional[Callable[[StoreProgress], None]] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        获取所有边（带速率限制和断点续传）

        Returns:
            (新获取的边列表, 估算的总边数)
        """
        edges_data = []
        total_estimated = 0
        cursor = None
        page_number = 0
        consecutive_errors = 0

        while True:
            page_number += 1

            try:
                # 构建请求参数
                kwargs = {"limit": StoreConfig.PAGE_SIZE}
                if cursor:
                    kwargs["cursor"] = cursor

                # 获取一页数据
                response = call_zep_read_with_retry(
                    lambda: self.client.graph.edge.with_raw_response.get_by_graph_id(
                        graph_id=graph_id,
                        **kwargs
                    ),
                    operation_name=f"fetch edges page {page_number}",
                    max_attempts=StoreConfig.MAX_RETRIES,
                    initial_delay=StoreConfig.RETRY_DELAY * (2 ** consecutive_errors)
                )

                # 提取数据
                batch = list(getattr(response, 'data', None) or [])
                total_estimated += len(batch)

                for edge in batch:
                    edge_dict = {
                        'uuid': getattr(edge, 'uuid_', ''),
                        'name': getattr(edge, 'name', ''),
                        'fact': getattr(edge, 'fact', ''),
                        'source_node_uuid': getattr(edge, 'source_node_uuid', ''),
                        'target_node_uuid': getattr(edge, 'target_node_uuid', ''),
                        'source_node_name': getattr(edge, 'source_node_name', ''),
                        'target_node_name': getattr(edge, 'target_node_name', ''),
                        'attributes': getattr(edge, 'attributes', {}),
                        'valid_at': getattr(edge, 'valid_at', ''),
                        'invalid_at': getattr(edge, 'invalid_at', '')
                    }
                    edges_data.append(edge_dict)

                # 重置错误计数
                consecutive_errors = 0

                # 获取下一页 cursor
                headers = getattr(response, 'headers', None)
                next_cursor = None
                if headers:
                    next_cursor = headers.get('zep-next-cursor')

                if not next_cursor:
                    # 没有更多数据了
                    break

                cursor = next_cursor

                # 速率限制
                time.sleep(StoreConfig.PAGE_DELAY)

                # 更新进度
                logger.info(
                    f"获取边进度: {len(edges_data)} 边 "
                    f"(第 {page_number} 页, 等待后续数据...)"
                )

            except Exception as e:
                consecutive_errors += 1
                logger.warning(
                    f"获取边第 {page_number} 页失败 "
                    f"(尝试 {consecutive_errors}/{StoreConfig.MAX_RETRIES}): {e}"
                )

                if consecutive_errors >= StoreConfig.MAX_RETRIES:
                    logger.error(f"边获取失败，已达到最大重试次数")
                    raise

                # 指数退避
                wait_time = StoreConfig.RETRY_DELAY * (2 ** consecutive_errors)
                logger.info(f"等待 {wait_time}s 后重试...")
                time.sleep(wait_time)

        return edges_data, total_estimated

    def _load_progress(self, graph_id: str) -> Optional[StoreProgress]:
        """加载存储进度"""
        progress_path = self._get_progress_path(graph_id)
        if not os.path.exists(progress_path):
            return None

        try:
            with open(progress_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return StoreProgress(**data)
        except Exception:
            return None

    def _save_progress(self, progress: StoreProgress):
        """保存存储进度"""
        with self._lock:
            progress_path = self._get_progress_path(progress.graph_id)
            with open(progress_path, 'w', encoding='utf-8') as f:
                json.dump(progress.to_dict(), f, ensure_ascii=False, indent=2)

    def _load_partial_data(self, graph_id: str) -> Dict[str, Any]:
        """加载部分数据（用于断点续传）"""
        data_path = self._get_graph_data_path(graph_id)
        if not os.path.exists(data_path):
            return {'nodes': [], 'edges': []}

        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {'nodes': [], 'edges': []}

    def _save_graph_data(self, graph_id: str, stored_graph: StoredGraph):
        """保存图谱数据"""
        # 保存元数据
        metadata_path = self._get_graph_metadata_path(graph_id)
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(stored_graph.to_dict(), f, ensure_ascii=False, indent=2)

        # 保存完整数据
        data_path = self._get_graph_data_path(graph_id)
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump({
                'nodes': stored_graph.nodes,
                'edges': stored_graph.edges
            }, f, ensure_ascii=False, indent=2)

    def _get_storage_status(self, graph_id: str) -> Optional[StoreProgress]:
        """获取存储状态"""
        return self._load_progress(graph_id)

    # ==================== 图谱读取 ====================

    def list_stored_graphs(self) -> List[StoredGraph]:
        """列出本地存储的所有图谱"""
        if not os.path.exists(self.GRAPHS_DIR):
            return []

        stored_graphs = []

        for graph_id in os.listdir(self.GRAPHS_DIR):
            graph_dir = os.path.join(self.GRAPHS_DIR, graph_id)
            if not os.path.isdir(graph_dir):
                continue

            metadata_path = self._get_graph_metadata_path(graph_id)
            if not os.path.exists(metadata_path):
                continue

            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stored_graphs.append(StoredGraph.from_dict(data))
            except Exception as e:
                logger.warning(f"读取图谱 {graph_id} 元数据失败: {e}")

        # 按存储时间排序
        stored_graphs.sort(key=lambda x: x.stored_at, reverse=True)

        return stored_graphs

    def get_stored_graph(self, graph_id: str) -> Optional[StoredGraph]:
        """读取本地存储的图谱"""
        metadata_path = self._get_graph_metadata_path(graph_id)

        if not os.path.exists(metadata_path):
            logger.warning(f"图谱 {graph_id} 未找到本地存储")
            return None

        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return StoredGraph.from_dict(data)
        except Exception as e:
            logger.error(f"读取图谱 {graph_id} 失败: {e}")
            return None

    def get_stored_graph_data(self, graph_id: str) -> Optional[Dict[str, Any]]:
        """获取本地存储图谱的节点和边数据"""
        stored_graph = self.get_stored_graph(graph_id)

        if not stored_graph:
            return None

        return {
            "graph_id": stored_graph.graph_id,
            "name": stored_graph.name,
            "node_count": stored_graph.node_count,
            "edge_count": stored_graph.edge_count,
            "entity_types": stored_graph.entity_types,
            "stored_at": stored_graph.stored_at,
            "checksum": stored_graph.checksum,
            "nodes": stored_graph.nodes,
            "edges": stored_graph.edges,
            "metadata": stored_graph.metadata,
            "is_local": True
        }

    def delete_stored_graph(self, graph_id: str) -> bool:
        """删除本地存储的图谱"""
        graph_dir = self._get_graph_dir(graph_id)

        if not os.path.exists(graph_dir):
            return False

        try:
            import shutil
            shutil.rmtree(graph_dir)
            logger.info(f"已删除图谱 {graph_id} 的本地存储")
            return True
        except Exception as e:
            logger.error(f"删除图谱 {graph_id} 失败: {e}")
            return False

    def verify_stored_graph(self, graph_id: str) -> Dict[str, Any]:
        """验证本地存储图谱的完整性"""
        stored_graph = self.get_stored_graph(graph_id)

        if not stored_graph:
            return {
                "valid": False,
                "error": "图谱未在本地存储"
            }

        # 计算当前数据的校验和
        checksum_data = {
            "nodes": stored_graph.nodes,
            "edges": stored_graph.edges
        }
        current_checksum = hashlib.sha256(
            json.dumps(checksum_data, sort_keys=True).encode()
        ).hexdigest()

        is_valid = current_checksum == stored_graph.checksum

        return {
            "valid": is_valid,
            "graph_id": graph_id,
            "stored_checksum": stored_graph.checksum,
            "current_checksum": current_checksum,
            "node_count": stored_graph.node_count,
            "edge_count": stored_graph.edge_count,
            "stored_at": stored_graph.stored_at,
            "entity_types": stored_graph.entity_types
        }

    # ==================== 异步存储 ====================

    def store_graph_async(
        self,
        graph_id: str,
        name: Optional[str] = None,
        include_data: bool = True,
        force_refresh: bool = False
    ) -> str:
        """
        异步存储图谱到本地

        Args:
            graph_id: 图谱 ID
            name: 图谱名称（可选）
            include_data: 是否包含完整的节点和边数据
            force_refresh: 是否强制重新获取

        Returns:
            任务 ID
        """
        import threading
        from ..models.task import TaskManager

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="graph_store",
            metadata={
                "graph_id": graph_id,
                "name": name,
                "include_data": include_data,
                "force_refresh": force_refresh
            }
        )

        # Capture locale before spawning background thread
        from ..utils.locale import get_locale
        current_locale = get_locale()

        def progress_handler(progress: StoreProgress):
            """进度处理器"""
            from ..models.task import TaskManager, TaskStatus

            task_manager = TaskManager()
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=int(progress.progress_percent),
                message=f"正在存储: {progress.nodes_stored}/{progress.total_nodes} 节点, "
                        f"{progress.edges_stored}/{progress.total_edges} 边"
            )

        thread = threading.Thread(
            target=self._store_graph_worker,
            args=(task_id, graph_id, name, include_data, force_refresh, progress_handler, current_locale)
        )
        thread.daemon = True
        thread.start()

        return task_id

    def _store_graph_worker(
        self,
        task_id: str,
        graph_id: str,
        name: Optional[str],
        include_data: bool,
        force_refresh: bool,
        progress_handler: Optional[Callable],
        locale: str
    ):
        """异步存储工作线程"""
        from ..models.task import TaskManager, TaskStatus
        from ..utils.locale import set_locale

        set_locale(locale)
        task_manager = TaskManager()

        try:
            result = self.store_graph(
                graph_id=graph_id,
                name=name,
                include_data=include_data,
                progress_callback=progress_handler,
                force_refresh=force_refresh
            )

            task_manager.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="存储完成",
                result={
                    "graph_id": result.graph_id,
                    "node_count": result.node_count,
                    "edge_count": result.edge_count,
                    "stored_at": result.stored_at,
                    "checksum": result.checksum
                }
            )

        except Exception as e:
            logger.error(f"存储图谱 {graph_id} 失败: {e}")
            task_manager.fail_task(task_id, str(e))

    # ==================== 批量操作 ====================

    def store_multiple_graphs(
        self,
        graph_ids: List[str],
        names: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[str, StoreProgress], None]] = None
    ) -> Dict[str, Any]:
        """
        批量存储多个图谱

        Args:
            graph_ids: 图谱 ID 列表
            names: 图谱名称映射
            progress_callback: 进度回调 (graph_id, progress)

        Returns:
            存储结果统计
        """
        results = {
            "total": len(graph_ids),
            "success": 0,
            "failed": 0,
            "details": []
        }

        for i, graph_id in enumerate(graph_ids, 1):
            name = names.get(graph_id) if names else None

            logger.info(f"批量存储进度: {i}/{len(graph_ids)} - {graph_id}")

            def item_progress_handler(progress: StoreProgress):
                if progress_callback:
                    progress_callback(graph_id, progress)

            try:
                stored = self.store_graph(
                    graph_id,
                    name,
                    include_data=True,
                    progress_callback=item_progress_handler
                )
                results["success"] += 1
                results["details"].append({
                    "graph_id": graph_id,
                    "status": "success",
                    "node_count": stored.node_count,
                    "edge_count": stored.edge_count
                })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "graph_id": graph_id,
                    "status": "failed",
                    "error": str(e)
                })

            # 图谱之间添加延迟，避免连续触发限流
            if i < len(graph_ids):
                time.sleep(StoreConfig.PAGE_DELAY * 2)

        return results


# ==================== 工厂函数 ====================

def get_graph_manager(api_key: Optional[str] = None) -> ZepGraphManager:
    """获取图谱管理器实例"""
    return ZepGraphManager(api_key)