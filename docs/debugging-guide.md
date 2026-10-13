# MiroFish 调试手册

> 目标：让你能**独立定位**"哪一步出了问题"，而不是靠猜。
> 所有命令都在 `/home/A/ysy/fish/backend` 下用项目虚拟环境执行：`.venv/bin/python`。

---

## 零、先看这个：一条命令看完全流程（不用起服务）

打任何断点之前先跑它 —— 会把每一步的**输入和输出**直接打印出来，不启动后端、不消耗 token：

```bash
cd /home/A/ysy/fish/backend
./.venv/bin/python scripts/debug_pipeline.py <project_id>
```

覆盖 10 步：

| 步骤 | 看到什么 |
|---|---|
| 1 | 原始文件 |
| 2 | 提取后的纯文本（步骤 1 的输出 = 步骤 4 的输入） |
| 3 | 项目配置 + 本体（实体类型、关系类型） |
| 4 | **真正发给 Zep 的文本块**（来源头、切块边界） |
| 5 | Zep 里实际抽出来的节点、边、类型分布 |
| 6 | 智能体人设（bio / persona / 人设卡字段） |
| 7 | 模拟配置（时长、作息、初始帖） |
| 8 | 模拟跑出来的动作 + 世界数据库各表行数 |
| 9 | **回写图谱的原文**（动作被翻译成什么样） |
| 10 | 报告（大纲、章节、进度、成稿开头） |

它会**自动顺着 project → simulation → report 往下追**，不用手记 ID。

| 想干什么 | 命令 |
|---|---|
| 离线看（不连 Zep） | 加 `--offline` |
| 已知模拟 ID，从模拟那一步看起 | `--sim <simulation_id>` |
| 只看喂给大模型的提示词（**不花钱**） | `--prompt ontology <project_id>` |
| 不知道有哪些 ID | 不带参数直接跑，会列出来 |
| 预览太短 / 太长 | `DEBUG_PREVIEW=1500 ...` |

> 跑完这一步再决定去哪一层打断点，比直接开 IDE 单步快得多。

---

## 一、先选层，再动手（最重要）

不同层的调试手段完全不同，选错了会白费一小时。

| 层 | 是什么 | 能不能打断点 | 推荐手段 |
|---|---|---|---|
| **L0 纯函数** | 切块、本体校验、摘要拼装 | ✅ 能 | 直接 python 跑，秒级 |
| **L1 提示词** | LLM 收到的 prompt | ✅ 能 | **打断点看变量** |
| **L2 API** | Flask 路由 | ✅ 能 | curl / Postman + 断点 |
| **L3 Zep** | 实体抽取 | ❌ 不能（远端黑盒） | 看落盘 JSON + Zep 控制台 |
| **L4 模拟子进程** | OASIS 独立进程 | ❌ 不能（进程隔离） | 日志 + 手动跑脚本 |

**经验法则：80% 的问题在 L1（提示词）和 L3（Zep 看不见）这两层。**

---

## 二、环境与启动

```bash
# 后端（端口 5001）
cd /home/A/ysy/fish/backend && ./.venv/bin/python run.py

# 前端（端口 3000，已配 proxy: /api → localhost:5001）
cd /home/A/ysy/fish/frontend && npm run dev
```

| 东西在哪 | 路径 |
|---|---|
| 日志（按天滚动） | `backend/logs/YYYY-MM-DD.log` |
| 项目元数据 / 本体 | `backend/uploads/projects/<project_id>/` |
| 模拟产物 | `backend/uploads/simulations/<sim_id>/` |
| 报告 | `backend/uploads/reports/` |
| 配置 | 项目根目录 `.env`（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME` / `ZEP_API_KEY`） |

实时看日志：`tail -f backend/logs/$(date +%F).log`

### 调试器配置（VSCode / Cursor）

项目根目录 `.vscode/launch.json` 已经配好了 4 个启动项，直接选就行：

| 启动项 | 用在哪一层 | 说明 |
|---|---|---|
| **1. Flask 后端 (5001)** | L2 | 路由、service 里都能打断点 |
| **2. 模拟脚本（只跑 2 轮）** | L4 | **模拟是独立进程，只有这样直接跑才断得进去**；会让你填 sim id，默认 `--twitter-only --max-rounds 2 --no-wait` |
| **3. 全流程输入输出** | 第零节 | 就是 `debug_pipeline.py`，填 project id |
| **4. 只看本体提示词** | L1 | 打印 prompt 但不调用模型 |

两个注意点：

- **`--no-reload` 必须加**（Flask 配置里已加）：开了 reload 会派生子进程，断点命中不了。
- **Windows 要把 `python` 路径换成 `.venv/Scripts/python.exe`**（配置里已注释标明）。
- 模拟配置里的 `justMyCode: false` 别去掉，否则断不进 `site-packages` 里的 OASIS 源码。

---

## 三、逐阶段调试清单

### 阶段 0｜文件 → 文本

| | |
|---|---|
| 入口 | `app/utils/file_parser.py:137` `extract_from_multiple` |
| 输入 | 上传的 pdf/md/txt |
| 输出 | 一个大字符串，每篇带 `=== 文档 N: 文件名 ===` 头 |
| 断点 | `:154`（看每篇提取结果）、`:156`（提取失败分支） |
| 落盘 | `uploads/projects/<id>/text.txt` |

```bash
./.venv/bin/python -c "
from app.utils.file_parser import FileParser, split_text_into_chunks
t = FileParser.extract_from_multiple(['你的文件.md'])
print('总字数', len(t))
c = split_text_into_chunks(t, 500, 50)
print('块数', len(c), '首块长度', len(c[0]))
print(c[0][:200])
"
```

---

### 阶段 ①｜本体生成（LLM）

| | |
|---|---|
| 入口 | `app/services/ontology_generator.py:203` `generate` |
| 输入 | `document_texts: List[str]` + `simulation_requirement` |
| 输出 | 10 个实体类型 + 6–10 个边类型 |
| **断点** | **`:267`（`combined_text` 拼好后）、`:235`（调用前看完整 messages）** |
| 落盘 | `uploads/projects/<id>/project.json` 的 `ontology` 字段 |

**关键断点在 `:235`** —— 在这里看 `messages`，就是 LLM 实际收到的全部内容。这是排查"为什么生成的类型不对"的第一步。

**不花钱的调试法**（构建 prompt 但不调用 LLM）：

```bash
./.venv/bin/python -c "
from app.services.ontology_generator import OntologyGenerator
g = OntologyGenerator.__new__(OntologyGenerator)   # 绕过 __init__，不创建 LLMClient
msg = g._build_user_message(['罗永浩质疑西贝预制菜'], '预测西贝舆情走势', None)
print(msg)
"
```

> 用 `__new__` 是为了不触发 `LLMClient()` 构造，这样**不消耗任何 token** 就能看到完整 prompt。

**验证 LLM 返回后的处理逻辑**（纯函数，可离线）：

```bash
./.venv/bin/python -c "
from app.services.ontology_generator import OntologyGenerator
o = OntologyGenerator.__new__(OntologyGenerator)
bad = {'entity_types':[{'name':'celebrity'},{'name':'罗永浩的粉丝'}],
       'edge_types':[{'name':'criticizes','source_targets':[{'source':'Celebrity','target':'Company'}]}]}
r = o._validate_and_process(bad)
print([x['name'] for x in r['entity_types']])
print([x['name'] for x in r['edge_types']])
"
```

实测输出：

```
Entity type name 'celebrity' auto-converted to 'Celebrity'
['Celebrity', 'Person', 'Organization']
['CRITICIZES']
```

**这里面有个值得记住的行为**：`'罗永浩的粉丝'` 被**静默丢弃**了。原因是 `_to_pascal_case`（`:22`）用 `[^a-zA-Z0-9]+` 分词，中文全被当分隔符去掉 → 结果为空 → 返回 `Unknown` → `:466` 跳过。
👉 **中文类型名不会被报错，只会消失。** 排查"少了一个类型"时要想到这里。

---

### 阶段 ②｜装载本体（纯代码）

| | |
|---|---|
| 入口 | `app/services/graph_builder.py:313` `set_ontology` |
| 输入 | 上一阶段的 ontology dict |
| 输出 | 动态生成的 Pydantic 类 → 推给 Zep |
| 断点 | `:352`（`entity_class = type(...)` 之后看类）、`:399`（`set_ontology` 调用前看最终 payload） |

常见故障：属性名撞上 Zep 保留字（`name`/`uuid`/`created_at`…）会被 `safe_attr_name`（`:324`）改名成 `entity_xxx`。

---

### 阶段 ③｜实体抽取（**Zep 服务端，打不了断点**）

| | |
|---|---|
| 入口 | `graph_builder.py:407` `add_text_batches` |
| 输入 | chunks（每个 ≤ 10000 字符） |
| 输出 | Zep 内部的节点与边 |
| **断点** | **只能在 `:470` 看"发出去什么"**，抽取过程看不到 |
| 看结果 | `curl http://localhost:5001/api/graph/data/<graph_id>` |

**这一层的调试要点**：

1. 断点打在 `:470`，确认 `chunk` 内容——**你现在看到的文本块就是 Zep 唯一能看到的东西**。来源、时间丢了，就在这里看出来。
2. 抽取质量不行时，别去改 prompt（改不了），去改：
   - 本体的 `description` / `examples`（阶段 ①）
   - 文本块的元信息（阶段 0）
3. 看真实抽取结果：

```bash
curl -s http://localhost:5001/api/graph/data/<graph_id> | python -m json.tool | head -60
```

注意 `zep_entity_reader.py:262` 会**丢弃只有 `Entity`/`Node` 标签的节点**——本体没覆盖的实体在读取阶段就消失了，这不是 Zep 的错。

---

### 阶段 ④｜智能体画像（LLM）

| | |
|---|---|
| 入口 | `app/services/oasis_profile_generator.py:274` |
| 输入 | 实体 + 上下文（属性 / 关联边 / Zep 检索结果） |
| 输出 | bio + 2000 字 persona + age/gender/mbti/… |
| **断点** | **`:530`（`_build_entity_context` 返回处，看喂给 LLM 的上下文）**、`:732`（上下文被截断到 3000 字） |
| 落盘 | `uploads/simulations/<sim_id>/twitter_profiles.csv` / `reddit_profiles.json` |

**画像质量不好，九成是上下文不够**。在 `:530` 断点看 `context` 字符串：如果只有寥寥几句，说明图谱里这个实体的边太少。

---

### 阶段 ⑤⑥｜行为配置 / 事件配置（LLM）

| | |
|---|---|
| 入口 | `simulation_config_generator.py:815`（行为）、`:648`（事件）、`:537`（时间） |
| 输入 | 实体列表（name/type/summary） |
| 输出 | `agent_configs` / `initial_posts` / `total_simulation_hours` |
| **断点** | **`:835`（prompt 组装处）、`:876`（解析 LLM 结果处）** |
| 落盘 | `uploads/simulations/<sim_id>/simulation_config.json` |

离线验证实体摘要拼装：

```bash
./.venv/bin/python -c "
from app.services.zep_entity_reader import EntityNode
from app.services.simulation_config_generator import SimulationConfigGenerator
e = EntityNode(uuid='u1', name='罗永浩', labels=['Entity','Celebrity'],
               summary='锤子科技创始人', attributes={'full_name':'罗永浩'})
g = SimulationConfigGenerator.__new__(SimulationConfigGenerator)
print(g._summarize_entities([e]))
"
```

---

### 阶段 ⑦｜跑模拟（**独立子进程**）

| | |
|---|---|
| 入口 | `app/services/simulation_runner.py` → `subprocess` 起 `scripts/run_parallel_simulation.py` |
| 通信 | 文件轮询：`uploads/simulations/<sim_id>/ipc_commands/` ↔ `ipc_responses/` |
| **断点** | **进不去**。要用下面的方式 |

**调试模拟的三种办法**：

1. **手动跑脚本**（能打断点）：
   ```bash
   cd backend && ./.venv/bin/python scripts/run_parallel_simulation.py --config uploads/simulations/<sim_id>/simulation_config.json
   ```
   直接在 IDE 里 Run/Debug 这个文件，断点就能命中。

2. **看动作日志**：`uploads/simulations/<sim_id>/twitter/actions.jsonl`
   ```bash
   tail -f uploads/simulations/<sim_id>/twitter/actions.jsonl
   ```

3. **看 IPC**：`ls ipc_commands/` 里有没有堆积未消费的命令文件 → 卡住了。

---

### 阶段 ⑧｜报告生成（LLM）

| | |
|---|---|
| 入口 | `app/services/report_agent.py:1576` `generate_report` |
| 输出 | `uploads/reports/<report_id>/section_NN.md` → `full_report.md` |
| **断点** | **`:1197`（大纲 prompt）、`:1308`（章节上下文）、`:1460`（工具调用执行处）** |
| 进度 | `uploads/reports/<report_id>/progress.json` |

**进度不是 token 流式，是文件轮询**。前端读 `progress.json`，所以报告卡住时先看这个文件停在第几章。

---

## 四、四个真实的调试坑

**坑 1：后台线程把异常吞了。**
图谱构建跑在 daemon 线程里（`graph_builder.py:112`），`except` 只调 `fail_task`（`:216`），**不往外抛**。表现是：前端显示"失败"，但日志里没有 traceback。

→ 排查：断点打在 `:213` 的 `except`，或者

```bash
curl -s http://localhost:5001/api/graph/task/<task_id> | python -m json.tool
```

`error` 字段里有完整堆栈。

**坑 2：`TaskManager` 是内存单例。**
`models/task.py:71`。**后端一重启，任务全丢**，前端还拿着旧 task_id 轮询 → 404。
→ 重启后端后必须重新走流程，不要复用旧任务 ID。

**坑 3：LLM 调试烧钱。**
调试本体生成时，一次调用就是几万 token 的输入。
→ 用第三节那个 `__new__` 技巧，只构建 prompt 不调用。确认 prompt 没问题了再真跑。

**坑 4：子进程断点进不去。**
模拟、采访都在独立进程。
→ 要么手动跑脚本（见阶段 ⑦），要么看日志 + IPC 目录。

---

## 五、定位速查表

| 现象 | 先看哪 | 大概率原因 |
|---|---|---|
| 图谱里实体很少 | `/api/graph/data/<id>` | 本体类型没覆盖 → 节点只有 `Entity` 标签 → 被 `:262` 丢弃 |
| 实体类型少了几个 | 阶段 ① 的 log | 中文类型名被 `_to_pascal_case` 静默丢弃 |
| 画像写得很空 | 断点 `oasis_profile_generator.py:530` | 该实体在图上边太少，上下文不够 |
| 模拟跑不动 | `ipc_commands/` 目录 | 命令堆积 = 子进程死了或卡住 |
| 采访超时 | 日志里的耗时 | 默认 120s（双平台采访 180s，`zep_tools.py:1381`） |
| 报告卡住 | `progress.json` | 停在第几章就是哪章的工具调用挂了 |
| 重启后任务 404 | — | `TaskManager` 内存态，必然 |
| 所有 episode 时间是"现在" | — | `BatchAddItem.created_at` 没传（已知缺陷，`graph_builder.py:470`） |

---

## 六、用 pytest 当调试器（最省事）

项目已有 183 条测试，很多用例本身就是"最小复现"。遇到问题时，**复制一个最接近的测试改成你的数据**，比启动服务快得多。

```bash
cd /home/A/ysy/fish/backend
./.venv/bin/python -m pytest tests/ -q                      # 全量（当前 183 passed）
./.venv/bin/python -m pytest tests/test_ontology_generator.py -q -k "名字关键词"
./.venv/bin/python -m pytest tests/ -q -x --pdb             # 失败即进入 pdb
```

`--pdb` 是调试利器：测试一失败就停在出错那一行，可以直接查看所有局部变量。

---

## 七、建议的调试顺序（第一次上手按这个走）

1. 跑 `pytest tests/ -q` 确认基线是 183 passed（不是的话先别动别的）。
2. 用第三阶段的"不花钱调试法"看一眼本体 prompt，确认需求描述传进去了。
3. 断点打在 `graph_builder.py:470`，看一个真实的 chunk 长什么样——**这一步能让你立刻理解为什么实体抽取会串味**。
4. 用 `curl /api/graph/data/<id>` 看抽取结果，对照本体检查有没有漏。
5. 有问题再往回追：是 prompt 的问题，还是文本块的问题。
