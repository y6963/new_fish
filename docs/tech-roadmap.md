# MiroFish 技术路线图（基于代码分析）

> 本文是**现状盘点 + 演进路线**，不是设计稿。每一条结论都标注了代码位置，可逐条复核。
> 代码基线：`git HEAD = 39d8491`，加工作区中已完成的三→四步屏障修复（测试 129 → 183 通过）。

---

## 一、一句话定位

**MiroFish 是一个"多主体社交媒体舆论模拟器"**：把素材变成知识图谱 → 把图谱里的实体变成会发帖的智能体 → 让它们在 Twitter/Reddit 沙箱里互动 → 用 Agent 读结果写报告。

它不是通用预测引擎。它回答的是"**这些主体会怎么说、舆论怎么演化**"，而不是"事情的结果会怎样"（详见第九节边界）。

---

## 二、技术栈与运行时拓扑

### 2.1 依赖清单（`backend/requirements.txt`）

| 层 | 技术 | 版本 | 备注 |
|---|---|---|---|
| 前端 | Vue 3 + Vite + vue-router + vue-i18n + axios + d3 | 3.5 / 7.3 / 4.6 / 11.3 | d3 用于图谱可视化；已支持中英双语 |
| Web 框架 | Flask + flask-cors | 3.x | 单进程，`app.run(threaded=True)`（`run.py:47`） |
| LLM | OpenAI SDK | ≥1.0 | **统一走 OpenAI 协议**，所以任何兼容端点都能换（`config.py:26-28`） |
| 记忆/图谱 | **Zep Cloud** | `==3.25.0`（锁死） | SaaS，`Config.validate()` 明确拒绝 `ZEP_API_URL`（`config.py:70-71`） |
| 模拟引擎 | camel-oasis + camel-ai | 0.2.5 / 0.2.78 | 提供 Twitter/Reddit 沙箱与推荐系统 |
| 文件解析 | PyMuPDF | ≥1.24 | 仅 pdf/md/txt/markdown（`file_parser.py:64`） |
| 数据库 | **无** | — | 全部落在文件系统 + 内存 |

### 2.2 进程模型

```
Flask 主进程
├── threading.Thread            ← 图谱构建、模拟准备（daemon）
├── subprocess                  ← run_*_simulation.py（独立 Python 进程，常驻）
│     └── 命令循环 + IPC 文件轮询（ipc_commands/ ↔ ipc_responses/）
└── Zep Cloud（远端 SaaS）
```

**关键**：模拟子进程跑完轮次后**故意不退出**，停在命令循环里等待采访（`run_parallel_simulation.py`: `wait_for_commands = not args.no_wait`）。这是第 3→4 步所有复杂度问题的根源，已于本次修复中解耦。

### 2.3 接口面

3 个蓝图、**60 条路由**：`/api/graph` 10 条、`/api/simulation` 32 条、`/api/report` 18 条（`app/__init__.py:66-69`）。

---

## 三、五步主链路逐层拆解

> 前端组件：`Step1GraphBuild.vue` → `Step2EnvSetup.vue` → `Step3Simulation.vue` → `Step4Report.vue` → `Step5Interaction.vue`

### 第 1 步｜素材 → 知识图谱

| 项 | 内容 |
|---|---|
| 入口 | `POST /api/graph/ontology/generate`（`api/graph.py:265`）、`POST /api/graph/build`（`:448`） |
| 本体生成 | `ontology_generator.py:203`。LLM 现场设计 **10 个实体类型 + 6–10 个边类型**，强制末尾两个兜底 `Person`/`Organization`，明文禁止抽象实体（`:58-73`）。**这是全系统唯一的领域自适应机制** |
| 输入上限 | 拼接文本 > 5 万字触发等距抽样，最多 60 块、每块 8000 字（`:251-254`） |
| 图谱构建 | `graph_builder.py:75`。文本按 500 字/50 重叠切块 → Zep Batch API 写入 |
| 写入健壮性 | **全系统最扎实的一块**：创建前预校验（`:567`）、非幂等调用不重试、用 operation_id 对账丢失响应（`:270`）、逐 item 校验 UUID（`:690`） |
| 硬约束 | 单块 ≤ 10000 字符、单批 ≤ 350 条、总量 ≤ 50000 条、实体类型 ≤ 10（`utils/ontology.py`） |
| **已知缺陷** | ① `BatchAddItem.created_at` 存在但**未传**（`:470`）→ 所有 episode 时间戳都是"现在"，时序失真；② `source_description` 是硬编码常量；③ 按字符切块会切断来源边界 |

### 第 2 步｜图谱 → 智能体

| 项 | 内容 |
|---|---|
| 实体读取 | `zep_entity_reader.py:221`。只要不是纯 `Entity`/`Node` 标签就保留（`:262`）→ **本体没覆盖的实体静默丢弃** |
| 画像生成 | `oasis_profile_generator.py:274`。每个实体一次 LLM 调用，产出 bio + 2000 字 persona + age/gender/mbti/country/profession。上下文截断 3000 字（`:732`） |
| 行为配置 | `simulation_config_generator.py`。三类：`TimeSimulationConfig`（总时长、作息曲线）、`AgentActivityConfig`（活跃度/发帖率/活跃时段/情绪倾向/立场/影响力权重）、`EventConfig`（初始帖子 + 热点词） |
| **已知缺陷** | ① `follower_count=150` 硬编码、用户名后缀 `random.randint(100,999)`（`:338`）→ **影响力维度是假的**；② `total_simulation_hours`、`hot_topics`、`initial_posts` 全靠 LLM 猜（`:537`、`:648`）；③ 实体数量直接决定画像 LLM 调用次数，是主要成本与耗时来源 |

### 第 3 步｜跑模拟

| 项 | 内容 |
|---|---|
| 准备 | `simulation_manager.py`：生成 profiles CSV/JSON、config YAML、落 `run_state.json` |
| 执行 | `simulation_runner.py`：subprocess 启动 OASIS，平台完成后异步排空图谱 |
| IPC | `simulation_ipc.py`：`ipc_commands/`+`ipc_responses/` 双目录文件轮询。**默认超时 120s**（`:258`）、关闭环境 30s（`:284`） |
| 已修隐患 | ① 进程假存活（加 PID 校验）；② 采访路径拼出两条 system 被 ChatML 拒绝；③ twhin-bert 联网重试拖过 IPC 超时。三个补丁都在 `backend/scripts/` |

### 第 4 步｜报告生成

| 项 | 内容 |
|---|---|
| 入口 | `report_agent.py:1642` `generate_report` |
| 结构 | **三段流水线**：① `plan_outline` 规划大纲（`:1176`）→ ② 逐章节 ReAct（`:1260`）→ ③ `assemble_full_report` 组装（`:1751`） |
| 工具 | 4 个真工具：`insight_forge`、`panorama_search`、`quick_search`、`interview_agents`（`_define_tools` `:925`），另有 5 个兼容别名 |
| 迭代控制 | ReAct 上限 5 轮（`:1326`）；每章节工具调用 **≥3 且 ≤5**（`:1327`、`:882`）；每轮只执行第一个工具调用（`:1460`） |
| 产出 | Markdown。章节增量落盘 `section_NN.md`，最终 `full_report.md` |
| 进度 | 不是 token 流式，是**文件轮询**：前端读 `progress.json`（`:2259`） |
| **重要更正** | `MAX_REFLECTION_ROUNDS = 3`（`:885`）**只有声明、无任何引用**——Reflection 机制没有实现。878 行的注释说有反思阶段，但 `generate_report` 只有规划/生成/组装三步。**写文档时以代码为准** |

### 第 5 步｜采访

`interview_agents` 通过 IPC 向仍在运行的模拟进程提问。**这里的超时是 180 秒**（`zep_tools.py:1381`），因为可能同时问两个平台，比默认 120s 更长。采访失败会被降级成一段 summary 文案（`:1465`），不阻断报告。

---

## 四、关键机制盘点

| 机制 | 实现 | 评价 |
|---|---|---|
| 领域自适应 | 本体由 LLM 现场生成（`ontology_generator`） | **核心资产**，不要动它 |
| 任务状态 | `TaskManager` **内存单例**（`models/task.py:71`） | 重启即丢，薄弱 |
| 项目状态 | `ProjectManager` 落 JSON 到 `uploads/` | 可恢复 |
| 模拟状态 | `run_state.json` 落盘 | 可恢复 |
| 并发 | threading + daemon 线程，无队列、无并发上限 | 单机构，多开模拟会争资源 |
| 重试 | `call_zep_read_with_retry`（`utils/zep.py:126`）：3 次、指数退避、**仅对 transport/408/429/5xx** | 只覆盖 Zep 读；采访路径无重试 |
| 幂等 | Zep Batch 侧做了 operation_id 对账；IPC 侧无幂等键 | 偏弱 |
| 可观测性 | 任务进度 + `progress.json` + `console_log.txt`/`agent_log.jsonl` | 够用但分散 |
| 测试 | 183 条 pytest；Zep 相关用替身模块 | 集中在第 1/3/4 步屏障语义，第 2 步覆盖薄 |

---

## 五、现状成熟度分级

**钢层（可以放心依赖）**
- Zep Batch 写入与失败对账（`graph_builder`）——这一块的对账逻辑写得比一般项目严谨得多
- 本体生成的校验与兜底归一化（`_validate_and_process`）
- 第 3→4 步的状态屏障（本次修复后有 30 条测试守着）

**土层（能跑，但有明显缺口）**
- 模拟执行（依赖 camel-oasis，已打 3 个兼容补丁）
- 报告生成（流水线完整，但 Reflection 没实现、工具调用数被硬编码双端夹逼）
- 智能体画像（质量取决于图谱实体摘要，受本体覆盖度限制）

**纸层（现在是假的/缺失的）**
- 影响力维度：粉丝数硬编码 150
- 时间维度：`created_at` 未传
- 任务状态：重启丢失
- 反思机制：只有常量没有实现
- 检索能力与种子管道：完全没有（这是"一句话输入"最主要的缺口）

---

## 六、技术债清单（按严重度）

| # | 债 | 影响 | 修复成本 |
|---|---|---|---|
| 1 | Zep Cloud 强 SaaS 依赖，版本锁 3.25.0 | 不可自托管、不可替换、单点故障；实体类型上限 10 是硬顶 | 高 |
| 2 | `BatchAddItem.created_at` 未传 | 所有时间语义失真，预测/演化类任务直接受影响 | **低** |
| 3 | 按字符切块，来源边界被切断 | 实体抽取串味；第 3 块后来源信息全丢 | 中 |
| 4 | `follower_count` 硬编码 | 智能体之间没有影响力差异，传播模拟不成立 | 低 |
| 5 | 模拟参数全靠 LLM 猜 | 时长/热点/初始帖子不可控、不可复现 | 中 |
| 6 | `TaskManager` 内存态 | 重启丢任务；残留进程难清理 | 中 |
| 7 | IPC 用文件轮询 | 慢、脆、无背压；采访 180s 超时体验差 | 中 |
| 8 | 无任务队列 / 无并发限制 | 不能水平扩展，多任务互相抢 | 高 |
| 9 | camel-oasis 兼容补丁（3 个 monkey-patch） | 上游升级即失效，需长期维护 | 持续 |
| 10 | Reflection 未实现 + 工具调用数双端硬夹逼 | 报告深度受限，`≤5` 是硬编码在文件常量里 | 低 |
| 11 | 只支持 pdf/md/txt | 网页、数据源、结构化数据进不来 | 低 |

---

## 七、演进路线图

### P0｜稳基（1–2 周）——把"假的"变成"真的"

目标：不动架构，只补缺口。这阶段的每一条都对应技术债表里成本为"低/中"的项。

1. **传 `created_at`**（`graph_builder.py:470`）→ 时间语义恢复。最高性价比。
2. **补齐影响力维度**：从图谱属性/证据传播量推导 `follower_count` 与 `influence_weight`，删掉硬编码的 150 和 `random.randint` 用户名后缀。
3. **改按证据边界分块**：TextBlock 携带 source/time header，长文切块时每块重复 header。
4. **任务状态落盘**：`TaskManager` 增加 JSON 持久化，重启可恢复。
5. **配置去猜测**：有时间线/脉搏数据时直接算 `total_simulation_hours`、`hot_topics`、`initial_posts`，不再全交给 LLM。

### P1｜通用化（3–4 周）——让"输一句话"能跑起来

目标：把今天五步手动操作，压缩成"输入需求 → 自动出报告"。

6. **检索计划层（缺口最大、价值最高）**：LLM 把一句话拆成 N 个检索维度 → 逐维检索 → 汇成种子。**这是跨领域通用的关键，且因为它由 LLM 生成，所以不会锁死领域**。
7. **瘦内核种子格式**：`id / cluster_id / published_at / source_name / author / body` 六个固定字段 + 开放 `extension` 字典。通用容器，不带领域语义。
8. **种子渲染成一等公民**：`renderer` 负责 JSON → 文本（本体阶段按簇渲染成文档列表，图谱阶段按证据渲染成证据块）。
9. **多源检索适配器**：网页/新闻/社媒的最低限度统一，落到同一个瘦内核。
10. **前端入口**：新增"一句话输入"模式，但不替换现有五步流程（保守并行）。

### P2｜能力扩展（1–2 月）

11. **Reflection 真正落地**：实现 `_reflect_and_revise`，并把 `MAX_TOOL_CALLS_PER_SECTION` 等硬编码常量收拢到统一配置（`config.py:56-58` 已有 `REPORT_AGENT_MAX_*` 开关，目前与文件内常量重复定义）。
12. **IPC 升级**：文件轮询 → Unix socket / 轻量队列，解决 180s 超时的根因。
13. **任务队列**：引入 Celery/RQ 或最小化的作业表，支持并发与重试策略。
14. **Zep 抽象层**：定义 GraphStore 接口，Zep 作为默认实现，为将来换自托管留出余地（不急于替换）。
15. **预测闭环**：记录"预测了什么" → 事后回填"实际发生了什么" → 用于校准画像生成与行为参数。这是从"演示"走向"工具"的分水岭。

---

## 八、如果要做"一句话输入 → 自主预测"，缺哪三块

按依赖顺序：

```
① 检索计划（retrieval planner）   ← 完全没有，需新建
② 种子管道（seed pipeline）       ← 完全没有，需新建
③ 前端一句话模式                   ← 需新建，且必须能降级到手动五步
```

其中 ① 是核心。判断标准很简单：**同一套数据结构，能不能同时跑"舆情走势"和"AI 应用市场预测"？** 能，就对了；需要改字段才能跑第二个，就说明领域泄露到数据结构里了。

---

## 九、边界（必须讲清，避免误用）

- 本系统的输出是**舆论演化过程**，不是事件结果。
- "预测谁赢战争""预测股价点位"这类需求超出它的能力：它需要独立的推演/计量引擎，社媒模拟只能作为其中一个输入。
- 目前还有一个根本缺口：**没有校准环节**——预测得准不准，系统自己不知道。这是 P2 第 15 条要解决的，也是从"演示系统"走向"可用工具"的分水岭。
