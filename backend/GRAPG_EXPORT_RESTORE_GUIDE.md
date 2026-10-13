# 知识图谱导出与恢复系统

## 功能概述

本系统实现了两个核心功能：

1. **知识图谱独立导出与持久化**：将 Zep Cloud 图谱导出为独立格式，支持 JSON、SQLite、Cypher 三种格式
2. **知识图谱恢复与验证**：从导出的文件恢复图谱数据，并验证恢复前后数据的一致性

## 实现的核心类

### 1. GraphExporter - 图谱导出器

**位置**: `backend/app/services/graph_exporter.py`

**功能**:
- `fetch_graph_from_zep(graph_id)`: 从 Zep Cloud 获取图谱数据
- `export_to_json(graph_id)`: 导出为 JSON 文件
- `export_to_sqlite(graph_id)`: 导出为 SQLite 数据库
- `export_to_cypher(graph_id)`: 导出为 Cypher 格式（Neo4j 兼容）
- `export_graph(graph_id, format)`: 统一导出接口
- `list_exports()`: 列出所有导出文件

**使用示例**:

```python
from app.services.graph_exporter import GraphExporter, ExportFormat

exporter = GraphExporter()

# 导出为 JSON
path, data = exporter.export_to_json('your_graph_id')
print(f"导出到: {path}")
print(f"节点数: {data['node_count']}, 边数: {data['edge_count']}")
print(f"校验和: {data['checksum']}")

# 导出为 SQLite
db_path = exporter.export_to_sqlite('your_graph_id')

# 导出为 Cypher
cypher_path = exporter.export_to_cypher('your_graph_id')

# 统一导出接口
path = exporter.export_graph('your_graph_id', ExportFormat.JSON)
```

### 2. GraphRestore - 图谱恢复器

**位置**: `backend/app/services/graph_exporter.py`

**功能**:
- `load_from_json(filepath)`: 从 JSON 文件加载
- `load_from_sqlite(filepath)`: 从 SQLite 数据库加载
- `load_exported_graph(filepath)`: 自动识别格式并加载
- `get_local_graph_data(filepath)`: 获取前端显示所需格式的数据

**使用示例**:

```python
from app.services.graph_exporter import GraphRestore

restorer = GraphRestore()

# 加载本地导出的图谱
graph = restorer.load_exported_graph('/path/to/export.json')

# 获取前端显示用的数据格式
display_data = restorer.get_local_graph_data('/path/to/export.json')
# 返回格式与 Zep API 一致，前端无需修改即可显示
```

### 3. GraphValidator - 图谱验证器

**位置**: `backend/app/services/graph_exporter.py`

**功能**:
- `validate_export(graph_id, export_filepath)`: 验证导出文件与原始图谱的一致性
- `verify_local_graph(filepath)`: 验证本地图谱文件的完整性

**验证报告包含**:
- 节点数量对比
- 边数量对比
- 校验和对比
- 缺失的节点/边列表
- 额外的节点/边列表
- 不匹配的节点/边详情

**使用示例**:

```python
from app.services.graph_exporter import GraphValidator

validator = GraphValidator()

# 验证导出文件与原始图谱的一致性
report = validator.validate_export('your_graph_id', '/path/to/export.json')

if report['is_valid']:
    print("✓ 图谱验证通过")
else:
    print("✗ 图谱验证失败")
    print(f"缺失节点: {report['nodes']['missing']}")
    print(f"不匹配节点: {report['nodes']['mismatch']}")
    print(f"缺失边: {report['edges']['missing']}")

# 验证本地文件完整性
report = validator.verify_local_graph('/path/to/export.json')
```

## API 接口

### 1. 导出图谱

```
POST /api/graph/export/{graph_id}
Content-Type: application/json

{
    "format": "json"  // json | sqlite | cypher
}

Response:
{
    "success": true,
    "data": {
        "file_path": "/path/to/exported/file.json",
        "filename": "GraphName_20240115_143022.json",
        "format": "json",
        "download_url": "/api/graph/download/GraphName_20240115_143022.json",
        "graph_info": {
            "name": "图谱名称",
            "node_count": 100,
            "edge_count": 200,
            "checksum": "abc123...",
            "exported_at": "2024-01-15T14:30:22"
        }
    }
}
```

### 2. 列出导出文件

```
GET /api/graph/export/list

Response:
{
    "success": true,
    "data": [
        {
            "filename": "GraphName_20240115_143022.json",
            "size": 12345,
            "created_at": "2024-01-15T14:30:22",
            "format": "json"
        }
    ]
}
```

### 3. 下载导出文件

```
GET /api/graph/download/{filename}
```

### 4. 获取本地图谱数据

```
GET /api/graph/local/{filename}

Response:
{
    "success": true,
    "data": {
        "graph_id": "exported_abc123",
        "nodes": [...],
        "edges": [...],
        "node_count": 100,
        "edge_count": 200,
        "is_local": true,
        "original_zep_graph_id": "mirofish_xxx",
        "source_file": "GraphName.json"
    }
}
```

### 5. 验证本地图谱文件

```
GET /api/graph/validate/{filename}

Response:
{
    "success": true,
    "data": {
        "is_valid": true,
        "graph_id": "exported_abc123",
        "name": "图谱名称",
        "node_count": 100,
        "edge_count": 200,
        "checksum": "abc123..."
    }
}
```

### 6. 验证导出文件与原始图谱的一致性

```
POST /api/graph/verify/{graph_id}
Content-Type: application/json

{
    "export_filename": "GraphName.json"
}

Response:
{
    "success": true,
    "data": {
        "is_valid": true,
        "checksum": {
            "original": "abc123",
            "exported": "abc123",
            "match": true
        },
        "nodes": {
            "missing": [],
            "extra": [],
            "mismatch": []
        },
        "edges": {
            "missing": [],
            "extra": [],
            "mismatch": []
        }
    }
}
```

## 前端使用

### 导入 API 方法

```javascript
import {
  exportGraph,
  listExports,
  getLocalGraphData,
  validateLocalGraph,
  verifyGraphExport,
  getExportDownloadUrl
} from '@/api/graph'

// 导出图谱
const result = await exportGraph('your_graph_id', 'json')
const downloadUrl = result.data.download_url

// 获取本地图谱数据显示
const graphData = await getLocalGraphData('exported_file.json')
// graphData 可以直接传给 GraphPanel 组件显示

// 验证图谱一致性
const report = await verifyGraphExport('your_graph_id', 'exported_file.json')
if (report.data.is_valid) {
    console.log('数据一致，导出成功')
}
```

## 数据存储格式

### JSON 格式

```json
{
    "graph_id": "exported_abc123",
    "original_zep_graph_id": "mirofish_xxx",
    "name": "图谱名称",
    "exported_at": "2024-01-15T14:30:22",
    "export_version": "1.0",
    "node_count": 100,
    "edge_count": 200,
    "checksum": "sha256_hash",
    "nodes": [
        {
            "uuid": "node-uuid",
            "name": "节点名称",
            "labels": ["Entity", "Person"],
            "summary": "节点摘要",
            "attributes": {
                "age": 30,
                "occupation": "Engineer"
            },
            "created_at": "2024-01-10T10:00:00"
        }
    ],
    "edges": [
        {
            "uuid": "edge-uuid",
            "name": "WORKED_AT",
            "fact": "John worked at Google",
            "fact_type": "WORKED_AT",
            "source_node_uuid": "node-1",
            "target_node_uuid": "node-2",
            "attributes": {},
            "created_at": "2024-01-10T10:00:00",
            "valid_at": null,
            "invalid_at": null
        }
    ]
}
```

### SQLite 格式

包含三张表：
- `graph_meta`: 图谱元数据
- `nodes`: 节点数据
- `edges`: 边数据

### Cypher 格式（Neo4j 兼容）

```cypher
// Create Nodes
CREATE (n:Person {uuid: "xxx", name: "John", summary: "..."});

// Create Relationships
MATCH (s {uuid: "node-1"}), (t {uuid: "node-2"}) 
CREATE (s)-[r:WORKED_AT {fact: "John worked at Google"}]->(t);
```

## 验证流程

### 自动验证

导出过程中会自动计算图谱数据的 SHA256 校验和，存储在导出文件中。

### 一致性验证

验证流程：
1. 从原始 Zep 图谱重新获取数据
2. 加载导出的文件
3. 比较以下内容：
   - 节点数量和边数量
   - 每个节点的 UUID、名称、标签、属性
   - 每条边的 UUID、类型、源节点、目标节点、属性
   - 整体校验和

### 验证报告

```json
{
    "is_valid": true,
    "checksum": {
        "original": "abc123",
        "exported": "abc123",
        "match": true
    },
    "nodes": {
        "missing": [],      // 在原始图中存在，导出文件中不存在
        "extra": [],        // 在导出文件中存在，原始图中不存在
        "mismatch": []      // 存在但不匹配
    },
    "edges": {
        "missing": [],
        "extra": [],
        "mismatch": []
    }
}
```

## 文件存储位置

```
UPLOAD_FOLDER/
└── exports/
    ├── GraphName_20240115_143022.json
    ├── GraphName_20240115_143022.db
    └── GraphName_20240115_143022.cypher
```

## 注意事项

1. **导出顺序**: 建议先使用 `verifyGraphExport` 验证导出文件与原始图谱的一致性
2. **文件管理**: 定期清理不需要的导出文件
3. **版本兼容性**: 当前版本号为 "1.0"，后续可能增加新字段
4. **离线使用**: 导出的 JSON/SQLite 文件可以完全脱离 MiroFish 系统使用

## 下一步计划

1. 添加导出的图谱自动同步到本地数据库的功能
2. 支持将导出的图谱重新上传到 Zep Cloud
3. 添加图谱对比功能（比较两个版本的图谱差异）
4. 支持更多导出格式（如 GraphML、GEXF 等）