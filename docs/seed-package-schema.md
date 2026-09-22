# Seed Package 数据结构设计

> 目标：用户输入一句话（如"预测一下西贝未来一周的舆情走势"）→ 系统主动检索 → 把异构检索结果整理成 **Seed Package** → 作为 seed 传入第一步（本体生成）与第二步（实体抽取 / 智能体生成）。
>
> 本文所有"代码事实"均来自当前仓库，行号以 HEAD 为准，可复核。

---

## 零、结论先行

1. **整条下游链路只吃纯文本。** 本体生成吃 `List[str]`，图谱构建吃 `str`，Zep 从 episode 文本里抽实体。所以结构化数据**必须渲染进文本**，否则等于没传。
2. **最小单元不是"一篇文档"，而是"一条证据"。** 现有按 500 字机械切块会把不同来源、不同时间的内容切进同一个 chunk，实体抽取必然串味。
3. **时间必须显式传。** `BatchAddItem` 支持 `created_at` 字段，当前没传，导致三天前的旧新闻在图谱里的时间戳是"现在"——舆情演化顺序直接失真。这是最高性价比的一处修复。

---

## 一、代码事实：下游到底在吃什么

| 环节 | 位置 | 输入 | 硬约束 |
|---|---|---|---|
| 本体生成 | `services/ontology_generator.py:203` `generate(document_texts, simulation_requirement, additional_context)` | `List[str]` | 拼接后 > 50000 字会**等距抽样**（`LONG_TEXT_CHUNK_SIZE=8000`，最多 60 块，`:254`） |
| 图谱构建 | `services/graph_builder.py:75` `build_graph_async(text, ontology, chunk_size=500, chunk_overlap=50, batch_size=350)` | 单个 `str` | 单块 ≤ 10000 字符（`:576`），单批 ≤ 350 条，总量 ≤ 50000 条（`:574`） |
| Zep 写入 | `services/graph_builder.py:470` `BatchAddItem(...)` | `data=chunk`, `data_type="text"`, `source_description="MiroFish source document chunk"` | **`created_at` / `name` 字段存在但未传**（`zep_cloud/types/batch_add_item.py`） |
| 实体读取 | `services/zep_entity_reader.py:280` `EntityNode(uuid, name, labels, summary, attributes, related_edges, related_nodes)` | 图谱节点 | 只有 `Entity`/`Node` 标签的节点会被丢弃（`:262`）——本体没覆盖的实体全部丢弃 |
| 画像生成 | `services/oasis_profile_generator.py:721` | 实体名/类型/摘要/属性 + 上下文 | 上下文截断 `context[:3000]`（`:732`） |
| 行为配置 | `services/simulation_config_generator.py:815` | 实体列表 + 文档 | `AgentActivityConfig`：activity_level / posts_per_hour / active_hours / sentiment_bias / stance / influence_weight |
| 事件配置 | `services/simulation_config_generator.py:648` | 同上 | `initial_posts: [{content, poster_type}]`，`poster_type` 必须命中本体类型；`total_simulation_hours` 由 LLM 拍（24–168） |

**关键推论**：

- 结构化信息想活到第 2 步，只有三条路：① 写进 episode 正文；② 写进 `BatchAddItem.metadata`（可回溯，Zep 不使用）；③ 走 `created_at`（Zep 用于时序边）。
- `source_description` 目前是硬编码常量，等于把"这条来自哪、什么时候发的"完全丢掉。
- 第 2.5 步的 `total_simulation_hours`、`hot_topics`、`initial_posts` 现在**全靠 LLM 从文本里猜**。如果 seed 里显式带"预测未来一周"和"当前讨论量增速"，这些值可以直接落，不用猜。

---

## 二、设计主张：三层结构

```
SeedPackage                     ← 一次检索任务的完整交付物（可存档、可重放、可审计）
├── prediction_query            ← 用户那句话被解析成的结构化查询（决定搜什么、跑多久）
├── timeline[]                  ← 事件时间线（决定 initial_posts 的顺序与内容）
├── pulse                       ← 当前舆论脉搏（讨论量/增速/情绪分布/平台分布）
├── gaps[]                      ← 显式留白：没搜到的东西不许 LLM 编
├── clusters[]                  ← 事件簇（去重后的语义单元）
│   └── evidences[]             ← 证据项（原子，一条 = 一条帖子/一篇报道/一个评论）
└── provenance                  ← 检索元数据（引擎、时间、去重策略、合规过滤）
```

**为什么要有 cluster 这一层**：同一条新闻被 30 个渠道转载，如果不聚合，图谱里会出现 30 个"西贝回应"节点与 30 条重复边，实体 summary 被稀释，`influence_weight` 也算不出来（真正的传播规模被拆散了）。聚合后：簇内保留 1 条"主证据"进图谱，其余降级为 `corroborations`（只贡献计数与来源列表）。

---

## 三、EvidenceItem：原子证据

```jsonc
{
  "evidence_id": "E0123",
  "cluster_id": "C007",

  // —— 归属层：谁说的、在哪说的 ——
  "source": {
    "url": "https://weibo.com/xxx/yyy",
    "name": "微博",
    "channel": "weibo",              // weibo|xiaohongshu|douyin|zhihu|news|forum|wechat|gov|paper
    "tier": "first_party",           // official|media|first_party|kol|anonymous|aggregator
    "credibility": 0.85              // 0-1，由 tier + 认证状态推
  },
  "author": {
    "handle": "@老罗的十字路口",
    "display_name": "罗永浩",
    "verified": true,
    "verified_type": "个人认证",
    "follower_count": 1824000,
    "is_anonymous": false
  },

  // —— 时序层：什么时候说的 ——
  "published_at": "2026-09-18T20:31:00+08:00",   // 必填，进 BatchAddItem.created_at
  "crawled_at":   "2026-09-21T10:00:00+08:00",
  "temporal_granularity": "minute",               // exact|minute|hour|day|unknown

  // —— 内容层 ——
  "title": "关于西贝的几点说明",
  "body": "……原文……",
  "language": "zh-CN",
  "is_repost": false,
  "repost_of": null,

  // —— 传播层 ——
  "engagement": {
    "reposts": 12431, "comments": 8902, "likes": 53101,
    "views": null, "read_count": null
  },

  // —— 语义预标注（检索侧可先做，也可留空交给 Zep） ——
  "annotation": {
    "mentioned_entities": [          // 候选实体串，降低 Zep 漏抽
      { "surface": "罗永浩", "guess_type": "Person" },
      { "surface": "西贝",   "guess_type": "Company" },
      { "surface": "贾国龙", "guess_type": "Executive" }
    ],
    "stance": "opposing",            // supportive|opposing|neutral|observer
    "sentiment": -0.72,              // -1 ~ 1
    "claim": "罗永浩质疑西贝使用预制菜却按现做价格收费",  // 一句话事实陈述
    "topic_tags": ["预制菜", "定价争议"]
  }
}
```

**字段取舍说明**：

- `tier` + `credibility` 是必需的。第 2 步画像生成要区分"官方声明"和"匿名网友"，第 2.5 步的 `influence_weight` 也需要它。没有这层，图谱里 100 个实体会被平等对待，模拟出来就是一锅粥。
- `engagement` 必须有，但可以全 null。它是 `influence_weight` 与 `follower_count` 的直接来源——现有代码里这两个数是**硬编码/随机**的（`follower_count=150`、用户名后缀 `random.randint(100,999)`）。
- `annotation.mentioned_entities` 是"给 Zep 的提示"，不是强制约束。它的作用是降低漏抽（Zep 对短文本的实体召回不稳定），并且**不做**强制对齐——Zep 自己抽出来的仍是权威。
- `claim` 一句话事实陈述非常关键：Zep 抽边（`fact`）的质量取决于原文表述。搜索结果里大量是标题党与转述，把 claim 显式写进正文能显著提高边的质量。
- **不设** `entity_type` 强绑定：类型由第一步的本体决定（最多 10 类 + Person/Organization 兜底），seed 阶段硬猜类型会和本体打架。只给 `guess_type` 作为提示。

---

## 四、EventCluster：事件簇

```jsonc
{
  "cluster_id": "C007",
  "headline": "罗永浩质疑西贝预制菜定价",
  "summary": "2026-09-18 晚，罗永浩发微博质疑西贝使用预制菜…西贝于 9-19 发布声明否认…",
  "claim_conflicts": [                 // 冲突必须保留，不许合并成"有人说…有人说…"
    { "claim_a": "E0123", "claim_b": "E0158", "relation": "contradicts" }
  ],
  "first_seen_at": "2026-09-18T20:31:00+08:00",
  "last_seen_at":  "2026-09-20T23:10:00+08:00",
  "evidence_count": 38,
  "channel_distribution": { "weibo": 21, "news": 9, "xiaohongshu": 5, "zhihu": 3 },
  "heat": { "total_engagement": 412300, "peak_at": "2026-09-19T10:00:00+08:00", "trend": "rising" },
  "primary_evidence_id": "E0123",      // 进图谱的主体
  "corroborations": ["E0124", "E0158", "..."]   // 只贡献计数与来源列表
}
```

**为什么冲突要显式建模**：舆情模拟的价值恰恰在于"分歧如何演化"。如果预处理阶段把矛盾说法合成为一句中立描述，模拟就失去了张力，最后所有 agent 趋同。

---

## 五、SeedPackage：种子包

```jsonc
{
  "seed_id": "S_20260921_001",
  "created_at": "2026-09-21T10:47:00+08:00",

  // —— 用户那句话被解析成什么 ——
  "prediction_query": {
    "raw": "预测一下西贝未来一周的舆情走势",
    "subject": "西贝",
    "subject_type": "brand",
    "time_horizon": { "value": 7, "unit": "day" },   // → total_simulation_hours = 168
    "metrics": ["讨论量", "情绪倾向", "负面占比"],
    "platforms": ["微博", "小红书", "抖音"],
    "geography": "中国大陆",
    "baseline_date": "2026-09-21"
  },

  // —— 事件时间线：initial_posts 的直接来源 ——
  "timeline": [
    { "seq": 0, "at": "2026-09-18T20:31:00+08:00", "actor": "罗永浩",
      "event": "发微博质疑西贝预制菜定价", "evidence_id": "E0123", "stage": "trigger" },
    { "seq": 1, "at": "2026-09-19T10:00:00+08:00", "actor": "西贝",
      "event": "官方声明否认使用预制菜", "evidence_id": "E0158", "stage": "response" },
    { "seq": 2, "at": "2026-09-20T15:00:00+08:00", "actor": "媒体",
      "event": "多家媒体探店报道", "evidence_id": "E0201", "stage": "ferment" }
  ],

  // —— 当前舆论脉搏：配置生成的直接依据 ——
  "pulse": {
    "total_mentions": 128000,
    "growth_24h": 3.4,                        // 倍数
    "sentiment_distribution": { "negative": 0.61, "neutral": 0.24, "positive": 0.15 },
    "platform_distribution": { "weibo": 0.52, "xiaohongshu": 0.21, "douyin": 0.18, "other": 0.09 },
    "top_topics": ["预制菜", "定价", "知情权", "餐饮行业标准"],
    "key_influencers": ["罗永浩", "贾国龙", "中国消费者协会"]
  },

  // —— 显式留白 ——
  "gaps": [
    { "what": "西贝官方销售数据", "why": "未公开", "impact": "股价影响无法量化" }
  ],

  "clusters": [ /* 见第四节 */ ],
  "evidences": [ /* 见第三节 */ ],

  "provenance": {
    "engines": ["web_search", "news_api", "weibo_search"],
    "query_expansions": ["西贝 预制菜", "西贝 罗永浩", "西贝 声明"],
    "retrieved_at": "2026-09-21T10:40:00+08:00",
    "dedup_method": "simhash+time_window",
    "raw_count": 1842, "deduped_count": 38,
    "filters_applied": ["去掉无时间信息的结果", "去掉纯营销号"]
  }
}
```

**`gaps` 为什么重要**：LLM 面对缺失信息会编。显式列出"没搜到什么"，并在渲染时写进文本（"【注意】以下方面无公开数据，不得推断：西贝官方销售数据"），能显著降低幻觉。这对预测类任务尤其致命。

**`timeline` 与 `pulse` 的收益**：现有 `_generate_event_config` 让 LLM 从文档里猜 `initial_posts` 和 `hot_topics`。有了这两块，`initial_posts` 可以直接由 timeline 的前 N 条生成（真实发生过的事），`hot_topics` 直接用 `pulse.top_topics`，`total_simulation_hours` 由 `time_horizon` 直接算。准确率提升且不消耗 LLM 额度。

---

## 六、渲染：结构化 → 喂给 Zep 的文本

### 6.1 单条证据渲染模板

```
[证据 E0123 | 事件簇 C007]
发布时间: 2026-09-18 20:31（周四）
来源渠道: 微博（原创首发）
发布者: 罗永浩 @老罗的十字路口（个人认证，粉丝 182.4 万）
可信度: 高（当事人首发）
标题: 关于西贝的几点说明
正文:
……原文……
传播数据: 转发 12431 · 评论 8902 · 点赞 53101
事实要点: 罗永浩质疑西贝使用预制菜却按现做价格收费
立场: 批评西贝 | 情绪: 负面(-0.72)
话题标签: 预制菜 / 定价争议
同类佐证: 另有 37 条（新京报、澎湃新闻、36氪、知乎讨论等）
[证据结束]
```

设计要点：

1. **头部是固定格式的元信息块**。Zep 的实体抽取 LLM 会读到"发布者: 罗永浩 @…（粉丝 182.4 万）"，从而把 follower_count 写进实体属性——这正是画像生成和 `influence_weight` 需要的。
2. **时间写在正文第一行**，同时传给 `BatchAddItem.created_at`。双保险：文本保证抽取时看见，`created_at` 保证边的 `valid_at` 正确。
3. **尾部 `同类佐证`** 让"传播规模"进入图谱，而不必塞 37 条重复内容。
4. 用 `[证据 E0123]` 做锚点，第 4 步报告可以据此回溯引用（现在报告无法溯源）。

### 6.2 分块策略（必须改）

现状：`split_text_into_chunks(text, 500, 50)` 对拼接后的大字符串机械切块。后果：第 3 块以后来源和时间全丢。

建议：

| 内容长度 | 处理 |
|---|---|
| ≤ 800 字（微博/评论/短帖） | 一条证据 = 一个 chunk；过短的同类短帖按时间排序合并到 800 字 |
| 800 ~ 10000 字（新闻/报告） | 按段落切成 N 块，**每块重复渲染证据头**（标 `1/4`、`2/4`…），保证自包含 |
| > 10000 字 | 先抽取（正文摘要 + 关键段落），再走上面的规则 |

即：**`chunk_size` 参数改成"证据驱动"而非"字符驱动"**。

### 6.3 本体阶段的传法（零改造对齐）

`generate(document_texts: List[str])` 接受文档列表，且 `_collect_document_chunks` 会给每篇打 `document_index`。

→ **把每个 EventCluster 渲染成一篇"文档"** 传进去。这样：
- `document_index` 天然等于簇号，长文本抽样是**按簇分层**的（每簇都能被覆盖），而不是等距抽样把某簇整体跳过；
- 抽样时每簇先给 `summary`（300 字）+ 主证据原文，比按 8000 字机械切更公平。

---

## 七、权重与预算

下游成本由图谱节点数决定，而节点数由 seed 内容密度决定。建议预算：

| 项 | 建议上限 | 理由 |
|---|---|---|
| EvidenceItem | 300 ~ 1500 条 | 每条约 1 次 Zep 写入；1500 条约 4~6 批 |
| EventCluster | 30 ~ 80 个 | 本体阶段每簇都要出现在文档列表里 |
| 图谱实体（节点） | 80 ~ 350 个 | **每个实体 = 一次画像 LLM 调用**，是主要成本与时延来源 |
| 实体类型 | 固定 10 | `MAX_ONTOLOGY_TYPES`（`utils/ontology.py`），不可突破 |

---

## 八、落地改动点（函数级）

| # | 文件 | 改动 | 侵入性 |
|---|---|---|---|
| 1 | 新增 `app/models/seed_package.py` | dataclass 定义本文三层结构 + `from_dict/to_dict` | 新增 |
| 2 | 新增 `app/services/seed_renderer.py` | `render_evidence()` / `render_cluster()` / `to_chunks()` / `to_documents()` | 新增 |
| 3 | `graph_builder.py:407` `add_text_batches` | 签名从 `chunks: List[str]` 扩到可接受 `List[Chunk]`，带 `created_at` + `metadata(source_url, evidence_id, tier)`；`source_description` 改为动态 | 中（向后兼容：纯 str 时走原逻辑） |
| 4 | `graph_builder.py:470` | `BatchAddItem(created_at=..., name=...)` | 小 |
| 5 | `api/graph.py:265` `/ontology/generate` | 接受 `seed_package` 或 `clusters`，按簇渲染成 `document_texts` | 小 |
| 6 | `simulation_config_generator.py:537` `_generate_time_config` | 有 `time_horizon` 时直接算 `total_simulation_hours`，跳过 LLM | 小 |
| 7 | `simulation_config_generator.py:648` `_generate_event_config` | 有 `timeline`/`pulse` 时直接构造 `initial_posts` 与 `hot_topics` | 中 |
| 8 | `oasis_profile_generator.py` | `follower_count` / `influence_weight` 从 `author.follower_count` + `engagement` 推导，去掉硬编码 | 中 |

**建议分三期**：

- **M1（最小可用，半天）**：只做 #1 #2 #4 —— 结构化渲染 + 传 `created_at`。不改任何现有签名，在 `/build` 之前把 SeedPackage 渲染成文本即可。收益：来源可追溯、时序正确、传播量入图。
- **M2（去重，一天）**：#3 #5 —— 簇聚合进图谱与本体阶段。
- **M3（配置直出，一天）**：#6 #7 #8 —— 用 timeline/pulse 替掉 LLM 猜测。

---

## 九、待拍板的问题

1. **`annotation` 由谁产出？** 检索侧 LLM 预标注（质量稳、成本高）还是只做实体串的正则召回（便宜、可能漏）？建议先只做 `mentioned_entities` 的正则/词典召回，`stance`/`sentiment` 交给第 2 步。
2. **冲突证据进不进图谱？** 建议进（用 `contradicts` 关系），但需要在本体里预留一条 `CONTRADICTS` 边类型——这会占用 6~10 条边类型额度中的一个。
3. **`tier` 枚举是否固定？** 固定枚举可让本体生成更稳，但会限制长尾渠道。建议固定 6 类 + `other`。
4. **检索结果要不要落盘？** 建议落 `uploads/<project_id>/seed_package.json`，供复现与第 4 步报告溯源。
5. **预算超了怎么砍？** 建议按 `heat.total_engagement` 降序截断，并在 `gaps` 里记录被砍掉的簇。
