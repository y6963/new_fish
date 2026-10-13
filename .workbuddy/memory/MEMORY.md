# MiroFish 项目长期笔记

## 一、运行约定（改动前必读）

- **模拟进程常驻**：`run_parallel_simulation.py` 默认进 IPC 命令循环（interview/batch_interview/close_env），
  **跑完不退出**。任何"等进程退出再收尾"的逻辑都不可靠 —— 报告曾因此卡死。
- **报告就绪只有一个判定**：`SimulationRunState.is_report_ready()`（`simulation_runner.py:172`）=
  runner_status ∈ {COMPLETED, STOPPED} 或（全部启用平台完成 且 graph_ingestion ∈ {completed, skipped}）。
  前端只读 `run-status` 的 `report_ready`；闸门实现只有 `api/report.py::_report_readiness_barrier`。
- **图谱收尾与进程退出解耦**：`simulation_end` 后异步排空 updater（不杀进程，保采访）；
  失败可 `POST /api/simulation/<id>/graph-ingestion/retry`。
- **平台判定按"启用的平台"**，不能硬要求 twitter+reddit 都完成；单平台模拟合法。
- **无数据库**：持久化全靠文件系统（`uploads/`、`run_state.json`、项目 JSON）；
  `TaskManager` 是内存单例（`models/task.py:71`），重启丢任务。
- **可恢复性只有一处**：五段流程里**只有「建图谱」能续跑**（`api/graph.py:529` 起的
  `resume_existing_batch`：靠 Zep 云端批次 + `project.json` 的 `zep_batch_id`，
  用 `operation_id=sha256(graph_id+chunks)` 校验输入未变；批次没了返回 409 `recoverable`）。
  其余四段产物虽落盘，但**没有任何续跑入口**，断了＝重跑。
  最狠的是模拟：重跑前 `os.remove` 删库（`run_parallel_simulation.py:1151/1342`）→ 世界清零。

## 一·补 图谱独立导出 / 恢复 / 校验（graph_pack.py）

- `backend/scripts/graph_pack.py`：`export` / `restore` / `verify` 三个子命令；
  格式说明 `docs/graph-pack-format.md`。包 = manifest.json + nodes/edges/episodes 三个 jsonl
  + ontology.json + checksums.sha256 + **viewer.html（内联 d3 与数据，离线可看）**。
- 恢复**不重跑 LLM 抽取**：用 `client.graph.add_nodes`（直接建节点）
  与 `client.graph.add_fact_triple`（直接建关系，可带 valid_at/invalid_at/expired_at）。
- **Zep 直写接口的实测硬限制（SDK 文档与实际不符）**：
  节点 uuid 不能自带（服务端分配，故 uuid 无法保留）；summary ≤ 500；fact ≤ 250；
  自环关系禁止（两端同名）；写入的属性必须在本体里定义过；不能跨图引用节点 uuid。
  → 一致性校验口径必须是「名称+类型+摘要」「事实文本+两端名字」，uuid 命中率只作参考。

## 二、按功能链路找代码（问"XX 功能在哪"先看这节）

| 环节 | 入口 | 实现 |
|---|---|---|
| ① 上传文件 | `POST /api/graph/ontology/generate` | `api/graph.py:312` `request.files.getlist` → `models/project.py:257 save_file_to_project` |
| ② 解析文件 | 同上（同步） | `utils/file_parser.py:81 extract_text`（只支持 pdf/md/markdown/txt，`:67`）→ `services/text_processor.py:37 preprocess_text` → `:291 save_extracted_text` |
| ③ 本体生成 | 同上 | `services/ontology_generator.py:203 generate()` → `utils/ontology.py` 规范化 → 存 `project.json` 的 `ontology` |
| ④ 本体上传 Zep | `POST /api/graph/build` | `graph_builder.set_ontology:313`（动态造 Pydantic 类）→ `client.graph.set_ontology:399`。**全项目只调一次**（`api/graph.py:720`） |
| ⑤ 图谱创建 | `POST /api/graph/build` | `api/graph.py:460 _build_graph_impl`（切块 `:671` → create_graph:709 → set_ontology:720 → add_text_batches:742 → 等 batch:765） |

**切块与来源头的实测结论（2026-09-28，6 个 md 文件实测）**：
`extract_from_multiple` 会给每篇加 `=== 文档 N: 文件名 ===`，但**头只在每篇最开头出现一次**；
按 500/50 切块后，**同一篇的第 2 块及以后完全没有来源标记**。
实测 6 篇 4805 字 → 11 块，其中 **5 块（45%）不带任何来源信息**。
→ 多文件输入时接近一半的文本块在 Zep 里是"无源"的，报告阶段按来源归因会失真。
（旧笔记写的"第 3 块之后来源头全丢"不准确，正确说法是"每篇只有首块带源"。）
**解法（已做成脚本）**：`test_scenarios/_tag_sources.py` 在正文里自动补 `（以上及以下均出自：素材 N · 媒体 · 日期）`，
阈值 `--every 120` 实测可达 **100% 带源块**（250 只有 94%）。以后任何多来源素材合集都先跑它。
| ⑥ 挑演员 | `GET /api/simulation/entities/<graph_id>` | `services/zep_entity_reader.py`（丢掉只有 Entity/Node 标签的节点）→ `simulation_manager.py:299 filter_defined_entities` |
| ⑦ 人设创建 | `POST /api/simulation/prepare` | `services/oasis_profile_generator.py:274 generate_profile_from_entity`；上下文拼装在 `_build_entity_context:457`（**硬截断 3000 字符**：`:732`） |
| ⑧ 世界参数 | 同 prepare | `services/simulation_config_generator.py:244 generate_config`；作息/初始帖/时长**全靠 LLM 猜**（`:537/648`），`follower_count=150` 硬编码 |
| ⑨ 跑模拟 | `POST /api/simulation/start` | `simulation_runner.py:598 subprocess.Popen` → `scripts/run_*_simulation.py` → **OASIS**；日志 tail 回 `zep_graph_memory_updater:494` |
| ⑩ 出报告 | `POST /api/report/generate` | `report_agent.py:1576 generate_report`（**注意：旧笔记写 1642，已漂移**）+ `zep_tools.py`（4 个检索工具） |
| ⑪ 与 Agent 交互 | `POST /api/simulation/interview` / `/report/chat` | `simulation_ipc.py:219 send_interview`（文件轮询，默认 60s）→ OASIS 子进程里的 Agent |

**三处核心逻辑不在 `app/services/`**：
① `app/utils/file_parser.py`（文件怎么进来）；② `backend/scripts/run_*.py`（真正执行体）；
③ `site-packages` 的 OASIS/camel（每步动作决策）。

**写 Zep 的入口只有 4 处**：`graph_builder.py:399`（本体）、`:436`/`:490`（批次文本）；
`zep_graph_memory_updater.py:494`（模拟动作）。其余全是读。

**模型调用两条出口**：`utils/llm_client.py`（ontology/report/zep_tools）
与 `utils/openai_chat_compat.py::create_chat_completion`（profile/config）。

## 三、图谱、本体、记忆

- **本体 = schema（模具），图谱 = 实例（铸件）**。本体不产生任何节点/边，
  节点边全由 episode（文本）在 **Zep 云端黑盒抽取**。本地 `project.json` 只有 ontology，实体边只在 Zep。
  → 提升抽取质量只有两个杠杆：本体定义质量、喂进去的文本质量。
  **本项目没有可改的抽取 prompt**，别去 graph_builder 里找。
- **更新只有"追加文本"一种方式**：文档 chunk 走 Batch API（`graph_builder.add_text_batches:407`，
  batch.create:436 → add:490 → process:546，`operation_id=sha256(graph_id+chunks)` 幂等记账）；
  Agent 动作走 `client.graph.add`（`:494`，**带 created_at**）。
  ⚠ `graph_builder.py:470` 的 BatchAddItem **没传 created_at** → 文档 episode 时间全是"现在"。
- **记忆 = 时序边**：`valid_at / invalid_at / expired_at`（`zep_tools.py:87`）。
  矛盾不覆盖——旧边置失效、新边新建，所以能表达"态度变化"。
  更新器参数：`BATCH_SIZE=5`、`MAX_EPISODE_CHARS=9500`、`SEND_INTERVAL=0.5s`，daemon 线程 `_worker_loop:410`；
  `graph.add` 无幂等键 → 失败记入 `_failed_batches` fail closed(`:532`)。
- **600s 超时源头**：`app/utils/zep.py:28 ZEP_INGESTION_WAIT_TIMEOUT_SECONDS = 600`。
- **图谱可全量导出**：`scripts/export_graph.py --sim <sim_id>`（或 `--project` / 直接给 graph_id）
  → `uploads/graph_export_<gid>.json`，含 nodes/edges/episodes。
  ⚠ **`episode.get_by_graph_id()` 不传 `lastn` 默认只给 4 条**（实测全集 94 条），必须显式传大值。
- **本体对抽取的约束力很弱**（2026-10-08 实测 349 节点/1159 边）：
  55% 节点**无类型标签**（地理名、#话题、模型名等噪音）；44% 的边是 Zep 兜底的 `RELATES_TO`；
  本体自定义的 FUNDS/ANALYZES/ADVOCATES_FOR/VOTES_FOR/REGULATES **出现 0 次**。
  → 提升质量靠喂什么文本，不靠把本体写精细。
- **图谱的角色**：点=演员名单，边=人物小传+报告证据。跑模拟**完全不碰图谱**（scripts 零 zep 引用）。
  边不被用的地方：`_summarize_entities:410`、`_generate_agent_config_by_rule:910`、
  `_save_twitter_csv:1139`（CSV 无 follows 列 → **初始社交网络不是从图谱来的**）。

## 四、易踩的坑

- **中文实体类型名被静默丢弃**：`ontology_generator._to_pascal_case:22` 按 `[^a-zA-Z0-9]+` 分词，
  中文全被当分隔符 → 返回 `Unknown` → `:466` 跳过，不报错。
- **越重要的节点人设越残缺**：`oasis_profile_generator.py:732` `context[:3000]` 硬截断，
  拼接顺序（属性→事实边→关联实体→Zep 检索）决定谁被挤掉。
- **模拟中断 = 集体失忆**：scripts 无 checkpoint；重跑后帖子还在（SQLite），但每个 Agent 忘了说过什么
  （camel 默认 `InMemoryKeyValueStorage`）。Agent 记忆窗口未设 `message_window_size` → token 超限丢最旧。
  采访不污染记忆：`interview_record` 默认 False。
- **睁眼范围极窄**：`env.py:82-84` twitter 每轮每 agent 只看 2 条推荐帖、3 条关注帖。
  并发上限 `semaphore=30`（`run_parallel_simulation.py:1144`）。
- 硬限制：单块 ≤10000 字符、单批 ≤350 条、总量 ≤50000 条、`MAX_ONTOLOGY_TYPES=10`（末两位必须 Person/Organization）。
- IPC 超时：默认 120s（`simulation_runner.py:1970`）、单采访 60s、关环境 30s；180s 只是双平台采访。
- 报告层：`MAX_REFLECTION_ROUNDS=3` **零引用，Reflection 没实现**；实际只有
  plan_outline(1176) → 每章 ReAct(1260) → assemble(1751)；每章工具调用 3~5 次，每轮只执行第一个。
  报告不读模拟日志。
- 死代码：`build_graph_async`(:75)、`_build_graph_worker`(:121)、`_wait_for_episodes`(:720)、
  `zep_tools._local_search`(:542)。**graph_builder 其余方法全被真调用**，它是工具箱，流水线在 `api/graph.py:460`。

## 五、OASIS 兼容补丁（backend/scripts/，三个 run_* 入口都 apply）

三方库在 site-packages，**不要直接改**，一律项目侧 monkey-patch。

| 补丁 | 解决什么 |
|---|---|
| `oasis_message_patch.py` | 采访/test 路径拼出两条 system 被 chat template 拒（400）。注入点 `ChatAgent._aget_model_response`（一处覆盖三路径）；合并时以第一条 system 为准；仍拒则折叠进首条 user 重试 |
| `oasis_recsys_patch.py` | `env.py:81` 硬编码 `recsys_type="twhin-bert"`，HF 不可达每次白等约 150s。改 `local_files_only=True` + 失败记忆；可选 `MIROFISH_TWITTER_RECSYS=twitter` 换 TF-IDF |

通用三条：先看降级路径（`platform.py:372-375` 是 except→log→return，等 150s 与立刻失败等价）；
注入点选最上游公共函数；补丁三件套=幂等+失败静默降级+环境变量可关。

## 六、工程约定

- 测试：`cd backend && ./.venv/bin/python -m pytest tests/ -q`（基线 183 passed）。
  守报告屏障的：`tests/test_zep_report_barrier.py`、`tests/test_report_after_platform_completion.py`。
- 沙箱限制：`rpds`/`torch` .so mmap 失败 → 无法 import camel/oasis，测试用替身模块；
  `vite build` wasm 内存不足 → 前端用 `@vue/compiler-sfc` 逐组件编译校验；
  `/proc` 与 `ps` 是隔离视图 → **不能用进程表判存活**，改用 `os.kill(pid, 0)` 或磁盘证据。
- **核对别人（其他 AI/协作者）的交接**：不信自述只看磁盘（`git status --short` + `git diff --stat`）；
  逐句验证"当前逻辑是 X"；用 `git worktree add /tmp/mf-head HEAD` 拉基线跑测试定位改动；
  看失败测试名字（往往就是被删的不变量）；找"放宽+提前放行"这类叠加效应。
- **长文档交付前必须 grep 查乱码**（历史上出现过 "lecture fixes"、"bombs"、"摻 Avatar" 等无关串）。
- 参考文档：`docs/debugging-guide.md`（L0–L4 分层断点）、`docs/tech-roadmap.md`（P0/P1/P2）、
  `docs/seed-package-schema.md`。零成本看 prompt：`Cls.__new__(Cls)` 绕过 `__init__`，不烧 token。
