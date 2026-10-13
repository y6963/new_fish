# MiroFish 知识图谱包格式（mirofish-graph-pack v1）

目标：让一份图谱**脱离 MiroFish 系统**也能保存、查看、重建、验证。

- 入口脚本：`backend/scripts/graph_pack.py`（三个子命令 `export` / `restore` / `verify`）
- 不依赖数据库、不依赖 Flask 服务、不依赖前端构建
- 查看器 `viewer.html` 内联了 d3 与全部数据，双击即可离线浏览

---

## 一、包里有什么

一个图谱包就是一个目录，自带校验和与自描述清单：

| 文件 | 内容 | 一行几条 |
|---|---|---|
| `manifest.json` | 格式版本、来源（graph_id / project_id / simulation_id）、导出时间、计数、各文件 sha256、本体类型清单 | — |
| `nodes.jsonl` | 节点：`uuid` `name` `labels` `label`(主类型) `summary` `attributes` `created_at` | 1 节点 |
| `edges.jsonl` | 关系：`uuid` `name`(关系类型) `fact` 两端 uuid 与名字 `attributes` `created_at` `valid_at` `invalid_at` `expired_at` `episodes` | 1 关系 |
| `episodes.jsonl` | 原始文本：`uuid` `content` `source_description` `created_at` `source` | 1 段原文 |
| `ontology.json` | 本体快照：**实体类型**与**关系类型**定义 | — |
| `checksums.sha256` | 三个 jsonl 的校验和 | — |
| `viewer.html` | 独立查看器（数据 + d3 全内联，离线可用） | — |
| `graph.db` | 可选：同一份数据的 SQLite 副本（表 + 索引 + 关系视图），任何语言可直接查 | — |

选 JSONL 而不是单个大 JSON：节点/关系数量会持续增长，逐行格式便于流式读写、
便于 diff、便于只取前 N 条做抽样验证。

`manifest.json` 示例：

```json
{
  "format": "mirofish-graph-pack",
  "format_version": 1,
  "exported_at": "2026-10-08T14:33:42",
  "source": { "graph_id": "mirofish_a2b57893b31644d1", "project_id": null, "simulation_id": null },
  "counts": { "nodes": 349, "edges": 1159, "episodes": 94 },
  "files": { "nodes.jsonl": { "sha256": "a48e7af2…", "rows": 349 }, "...": {} },
  "ontology_included": true,
  "ontology": { "entity_types": ["Politician", "MediaOutlet", "..."], "edge_types": ["MEMBER_OF", "FUNDS", "..."] }
}
```

---

## 二、三条命令

```bash
cd backend

# 1) 导出（三种定位方式任选）
./.venv/bin/python scripts/graph_pack.py export --sim sim_xxxx
./.venv/bin/python scripts/graph_pack.py export --project proj_xxxx
./.venv/bin/python scripts/graph_pack.py export --graph-id mirofish_xxxx --out-dir /tmp/pack

# 2) 恢复到一张新的 Zep 图谱
./.venv/bin/python scripts/graph_pack.py restore --pack uploads/graph_packs/demo_v1 \
    --graph-id mirofish_restored_full1 --workers 6

# 3) 校验一致性（不给 --graph-id 时拿原图自检）
./.venv/bin/python scripts/graph_pack.py verify --pack uploads/graph_packs/demo_v1 \
    --graph-id mirofish_restored_full1

# 4) 转成 SQLite，给别的系统直接 SQL 查（不联网、不启服务）
./.venv/bin/python scripts/graph_pack.py sqlite --pack uploads/graph_packs/demo_v1

# 5) 离线重建查看器（改过 jsonl 之后不用重新拉云端）
./.venv/bin/python scripts/graph_pack.py viewer --pack uploads/graph_packs/demo_v1
```

常用开关：

| 开关 | 作用 |
|---|---|
| `--limit-nodes N` / `--limit-edges N` | 只处理前 N 条，用于快速冒烟 |
| `--no-episodes` | 导出时跳过原文（包更小） |
| `--no-viewer` | 不生成查看器 |
| `--with-episodes` | 恢复时回放原文（会触发云端重新抽取，可能多出节点，默认关闭） |
| `--with-attributes` | 恢复时写入属性（设了本体后多数属性会被拒，默认关闭） |
| `--force` | 目标图谱已存在时继续追加写入 |
| `--wait-seconds N` | 写入后等待异步落库多久再结束（默认 60s） |

---

## 三、恢复是怎么做的（不是重新抽取一遍）

Zep 提供两个「直接写结构」的接口，绕开了文本抽取：

| 接口 | 用途 |
|---|---|
| `graph.add_nodes` | 直接建节点（名字、单个实体类型、摘要、创建时间），每批最多 100 |
| `graph.add_fact_triple` | 直接建关系（事实文本、关系名、两端名字、时序字段、uuid） |

所以恢复是**结构级复制**，不是把原文重新喂给大模型再抽一遍，一致性可以量化验证。

流程：新建图谱 → 恢复本体 → 分批写节点 → 并发写关系 → 等待异步落库 → 输出 `restore_report_<图id>.json`。

---

## 四、已知限制（实测，不是猜的）

| 限制 | 表现 | 处理 |
|---|---|---|
| **节点 uuid 不可保留** | 服务端返回 `uuid cannot be supplied: Zep assigns node UUIDs` | 一致性改用「名称 + 类型 + 摘要」口径 |
| **关系 uuid 也不保留** | 传了 `fact_uuid` 但读回是新 uuid | 关系按事实文本匹配校验 |
| **summary 上限 500 字符** | 超长直接 400 | 导出时保留全文，恢复时截断，校验按前 500 字比较 |
| **自环关系无法写入** | `source and target node names cannot be the same` | 计入失败清单，报告中单列（本次 1159 条中有 49 条自环） |
| **属性受本体约束** | `attribute 'name' is not defined in ontology for labels [Person]` | 默认不写属性；需要时用 `--with-attributes`，失败会记入报告 |
| **跨图不能引用节点 uuid** | `source_node_uuid … belongs to a different graph` | 只传名字，由服务端按名字解析或新建 |
| **回放原文会二次抽取** | `graph.add` 会再跑一遍抽取，可能新增/合并节点 | 默认关闭，只在需要"连原文一起恢复"时用 |
| **写关系会顺带新建节点** | 关系两端名字在图中不存在时自动新建（本次 349 → 359） | 先写节点再写关系，可减少误建 |
| **节点摘要是派生物，会被云端重写** | 写完关系后，Zep 会异步按新事实重新概括节点摘要；等得越久改写越彻底（实测落库后立刻校验 34%，放 45 分钟后只剩 2%） | 不要把摘要当硬指标；想把它覆盖回原文可用 `--nodes-only`，但见下条 |
| **add_nodes 不按名字去重** | 名字相同也会新建节点，重复写一遍会让节点数翻倍（349 → 708） | 节点只写一次；`--nodes-only` 仅作实验，正式恢复不要用 |

---

## 五、一致性校验口径

`verify` 输出 `verify_report_<图id>.json` 与同名 `.md`：

**节点**

| 指标 | 口径 |
|---|---|
| 名称命中率 | 源节点名在目标图中存在（**主指标**） |
| 实体类型一致率 | 名称命中的节点里，主类型相同（**主指标**） |
| 摘要一致率 | 仅参考：Zep 会按写入的关系异步重写摘要，数值随时间下降 |
| UUID 命中率 | 仅参考（Zep 限制导致必然为 0） |

**关系**

| 指标 | 口径 |
|---|---|
| 事实文本命中率 | 优先按 uuid 匹配，匹配不到按 `fact` 全文匹配 |
| 两端实体一致率 | 命中的关系里，源/目标名字都对得上 |
| 时序字段一致率 | `valid_at` / `invalid_at` / `expired_at` 逐项比对（精确到秒） |

---

## 五·补 给别的系统用：SQLite 副本

`sqlite` 子命令把三个 jsonl 落成 `graph.db`（约 1.5 MB / 千级节点）：

| 表 / 视图 | 内容 |
|---|---|
| `nodes` | 节点（uuid、名称、类型、摘要、属性 JSON、创建时间） |
| `edges` | 关系（fact、两端 uuid 与名字、时序字段、来源 episode JSON） |
| `episodes` | 原文（建图文档块与模拟活动记录） |
| `meta` | 包来源、导出时间、各类计数 |
| `v_relations` | 已 join 好的关系视图：`源名 / 关系 / 目标名 / 事实 / 时序` |

索引建在 `nodes.name`、`nodes.label`、`edges.name`、`edges.source_name`、`edges.target_name` 上。

```sql
-- 某人相关的所有关系
SELECT relation, target_name, fact FROM v_relations WHERE source_name LIKE '%特朗普%';

-- 某类关系的Top 实体
SELECT source_name, count(*) c FROM v_relations WHERE relation='OPPOSES' GROUP BY 1 ORDER BY c DESC;

-- 只看还有效的事实（时序图谱）
SELECT * FROM v_relations WHERE invalid_at IS NULL AND expired_at IS NULL;
```

这样后续任何系统接入图谱能力，都**不需要装 Zep SDK、不需要起 MiroFish**，读一个文件即可。

---

## 六、独立查看器

`viewer.html` 是一个自包含文件（约 1.7 MB，含内联 d3 与全部数据）：

- 力导向布局，节点按实体类型着色
- 左侧图例可点击隐藏某类实体
- 点节点看类型/摘要/属性，点关系看事实原文、时序字段与来源 episode
- 顶部搜索框按名字定位
- **不需要启动 MiroFish、不需要联网**，双击即可打开

---

## 七、后续可做的增强

1. 自环关系的兜底方案（例如改成一条"自身属性边"或落成节点属性）——目前 49 条自环只能丢弃
2. 恢复失败条目的自动重试队列（目前只记入报告，用 `--retry-failed` 手工重跑）
3. 查看器加一个「关系列表」标签页（上千条边时力导向图看不清，列表更好用）
4. Parquet / 图数据库（Neo4j）导出，便于更大图谱的分析与可视化
