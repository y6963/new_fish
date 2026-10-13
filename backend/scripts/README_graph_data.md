# 图谱数据获取脚本使用说明

## 📁 脚本位置

所有脚本位于: `/home/A/ysy/fish/backend/scripts/`

## 🚀 快速开始

### 1. 激活虚拟环境

```bash
cd /home/A/ysy/fish/backend
source .venv/bin/activate
```

### 2. 快速预览项目

查看所有可用项目：
```bash
python3 scripts/preview_project.py
```

预览指定项目（快速查看统计信息）：
```bash
python3 scripts/preview_project.py proj_584f702adfdd
```

输出示例：
```
================================================================================
📊 项目: proj_584f702adfdd
================================================================================

📋 基本信息:
  名称: Unnamed Project
  状态: graph_completed
  图谱ID: mirofish_30d6bd2f072e4576
  模拟需求: 预测一下这个事件后双方未来5年的营收状况

📦 本体定义:
  实体类型 (10):
    - Influencer: 拥有大量粉丝的公众人物或大V，如罗永浩...
    - Founder: 企业的创始人或核心灵魂人物，如贾国龙...
    ...

🕸️ 图谱统计:
  节点数: 33
  边数: 126

📈 实体类型分布:
  RestaurantChain: 9
  ConsumerGroup: 6
  ...

🔗 关系类型分布:
  AFFECTS: 44
  RESPONDS_TO: 18
  ...
```

### 3. 获取完整图谱数据

获取单个项目的完整数据（包括节点、边、原始文本、分块等）：
```bash
python3 scripts/fetch_project_graph_detail.py proj_584f702adfdd
```

指定输出目录：
```bash
python3 scripts/fetch_project_graph_detail.py proj_584f702adfdd ./my_output
```

输出文件：
```
outputs/{project_id}_{timestamp}/
├── project_config.json      # 项目配置（本体定义、参数等）
├── extracted_text.txt       # 提取的原始文本
├── text_chunks.json         # 文本分块数据
├── graph_data.json          # 完整图谱数据（节点和边）
├── analysis_report.json     # 分析报告
└── README.txt               # 说明文件
```

### 4. 批量获取所有项目

获取所有项目的图谱数据：
```bash
python3 scripts/fetch_graph_data.py
```

获取指定项目：
```bash
python3 scripts/fetch_graph_data.py proj_584f702adfdd
```

---

## 📊 数据格式说明

### project_config.json

```json
{
  "project_id": "proj_584f702adfdd",
  "graph_id": "mirofish_30d6bd2f072e4576",
  "simulation_requirement": "预测一下这个事件后双方未来5年的营收状况",
  "ontology": {
    "entity_types": [
      {
        "name": "Influencer",
        "description": "拥有大量粉丝的公众人物或大V，如罗永浩...",
        "examples": ["罗永浩"]
      }
      // ...
    ],
    "edge_types": [
      {
        "name": "ACCUSED_BY",
        "description": "指控或批评关系，如罗永浩指控西贝使用预制菜"
      }
      // ...
    ]
  },
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

### text_chunks.json

```json
{
  "chunk_size": 500,
  "chunk_overlap": 50,
  "total_chunks": 6,
  "chunks": [
    {
      "index": 0,
      "text": "=== 测试剧本_罗永浩西贝事件.md ===...",
      "length": 485
    }
    // ...
  ]
}
```

### graph_data.json

```json
{
  "graph_id": "mirofish_30d6bd2f072e4576",
  "node_count": 33,
  "edge_count": 126,
  "nodes": [
    {
      "uuid": "f14c7494-97f0-4754-871a-680b6532fb57",
      "name": "消费者群体",
      "labels": ["ConsumerGroup", "Entity"],
      "summary": "消费者群体持续对西贝预制菜的高价产生负面反应...",
      "attributes": {
        "demographic": "价格敏感型用户",
        "sentiment_trend": "抵制、观望"
      },
      "created_at": "2026-09-21T11:15:XX"
    }
    // ...
  ],
  "edges": [
    {
      "uuid": "edge_001",
      "name": "ACCUSED_BY",
      "fact": "罗永浩指控西贝使用预制菜",
      "source_node_uuid": "xxx",
      "target_node_uuid": "xxx",
      "source_node_name": "罗永浩",
      "target_node_name": "西贝莜面村",
      "attributes": {
        "accusation_content": "西贝使用预制菜还那么贵"
      },
      "created_at": "2026-09-21T11:15:XX"
    }
    // ...
  ]
}
```

### analysis_report.json

```json
{
  "project_id": "proj_584f702adfdd",
  "graph_id": "mirofish_30d6bd2f072e4576",
  "timestamp": "20260922_165600",
  "statistics": {
    "text_length": 3060,
    "chunks_count": 6,
    "nodes_count": 33,
    "edges_count": 126
  },
  "entity_types": {
    "RestaurantChain": 9,
    "ConsumerGroup": 6,
    "Investor": 2
  },
  "edge_types": {
    "AFFECTS": 44,
    "RESPONDS_TO": 18,
    "WORKS_FOR": 10
  },
  "top_entities": [
    {
      "name": "消费者群体",
      "type": "ConsumerGroup",
      "summary": "消费者群体持续对西贝预制菜的高价产生负面反应..."
    }
    // ...
  ]
}
```

---

## 🔍 常用命令示例

### 查看所有项目
```bash
python3 scripts/preview_project.py
```

### 快速查看某个项目
```bash
python3 scripts/preview_project.py proj_584f702adfdd
```

### 获取完整数据
```bash
python3 scripts/fetch_project_graph_detail.py proj_584f702adfdd
```

### 批量获取所有项目
```bash
python3 scripts/fetch_graph_data.py
```

---

## 📦 可用项目列表

运行以下命令查看所有可用项目：

```bash
python3 scripts/preview_project.py
```

或者手动查看：

```bash
ls -1 /home/A/ysy/fish/backend/uploads/projects/
```

---

## ⚠️ 注意事项

1. **需要网络连接**: 脚本需要访问 Zep 云端服务
2. **API Key**: 确保 `ZEP_API_KEY` 已配置（在虚拟环境中自动加载）
3. **输出目录**: 默认输出到 `outputs/graph_data/`
4. **数据量**: 图谱数据可能较大，请耐心等待

---

## 🎯 实际案例

### 西贝预制菜争议事件（proj_584f702adfdd）

**模拟需求**: 预测一下这个事件后双方未来5年的营收状况

**实体类型**:
- Influencer (大V): 罗永浩
- Founder (创始人): 贾国龙
- CorporateExecutive (高管): 张丽平
- Investor (投资人): 林来嵘、大中矿业实控人
- RestaurantChain (餐饮品牌): 西贝、太二、海底捞、全聚德等
- ConsumerGroup (消费者): 消费者群体、价格敏感型用户、亲子家庭

**关系类型**:
- ACCUSED_BY: 指控关系
- RESPONDS_TO: 回应关系
- WORKS_FOR: 任职关系
- INVESTED_IN: 投资关系
- AFFECTS: 影响关系

**图谱规模**: 33 节点, 126 边

---

## 📞 故障排除

### 错误: ModuleNotFoundError: No module named 'flask'

**解决**: 确保已激活虚拟环境
```bash
source .venv/bin/activate
```

### 错误: ZEP_API_KEY 未配置

**解决**: 检查配置文件或环境变量

### 错误: graph_id 为空

**解决**: 项目可能还未完成图谱构建，请先运行构建流程

---

## 💡 下一步

1. 使用 `preview_project.py` 快速查看项目统计
2. 使用 `fetch_project_graph_detail.py` 获取完整数据
3. 分析 `graph_data.json` 中的节点和边
4. 参考 `analysis_report.json` 了解整体结构
5. 将数据用于报告、可视化或其他分析

---

**祝您分析顺利！** 🎉