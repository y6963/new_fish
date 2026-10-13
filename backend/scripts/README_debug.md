# MiroFish 调试指南

## 🧭 前后端怎么配合（先看这一节）

系统跑起来是**两个进程**：

- 前端 Vite：**localhost:3000**（页面在这里）
- 后端 Flask：**localhost:5001**（接口在这里）

浏览器**永远访问 3000**。凡是 `/api` 开头的请求，由 Vite 自动转发给 5001
（配置见 `frontend/vite.config.js`）。所以在浏览器眼里只有一个地址。

### 三条路线，从轻到重

| 你想干什么 | 要起什么 | 在哪打断点 |
|---|---|---|
| 只想看数据长什么样 | **什么都不用起**：`python scripts/debug_pipeline.py <id>` | 不需要断点 |
| 调后端某一步的逻辑 | 只起后端（IDE 里用配置 1），用 curl / Postman 发请求 | VSCode |
| 界面 + 接口完整走一遍 | 后端（IDE 配置 1）+ 前端（终端 `npm run dev`） | Python 在 VSCode，Vue 在浏览器 F12 |

### 完整联调的标准顺序

1. **先起后端**：VSCode → `F5` → 选「1. Flask 后端 (5001)」
   → 等终端出现 `Running on http://...:5001` 再动下一步
2. **再起前端**：另开一个终端 → `cd frontend` → `npm run dev`
   → 浏览器会自动打开 `localhost:3000`
3. 在页面上点你要测的操作，VSCode 里的断点就会停下来

> 📌 **前端命令取决于你当前在哪个目录**（这条最容易搞混）：
>
> | 当前目录 | 命令 |
> |---|---|
> | `frontend/` | `npm run dev` |
> | 项目根目录 | `npm run frontend`（它内部就是 `cd frontend && npm run dev`） |
>
> `npm run frontend` 这个名字**只存在于根目录的 `package.json`**，
> 在 `frontend/` 里敲会报 `Missing script: "frontend"`。

> ⚠️ **不要用根目录的 `npm run dev`**。它确实能一次把前后端都起来
> （`package.json` 里用 concurrently 拼的），但后端那条命令是 `uv run python run.py`，
> **没有挂调试器，断点一个都命中不了**。要调试就必须拆成上面两步。

### 这条路上的四个坑

- **浏览器开 3000，不是 5001。** 直接开 5001 只会拿到一串 JSON，没有页面。
- **`.env` 里别设 `FLASK_DEBUG=true`。** 开了之后 Flask 会启用 reloader 再派生一个子进程，
  断点会跟着漂到那个子进程里去、表现为"停不下来"。默认值就是 `False`，别改。
- **改 Python 必须重启后端**，Flask 不像前端那样自动热更新；**改 Vue 保存即生效**。
- 端口被占（尤其上次没正常退出）时，后端会起不来 —— 先确认 5001 没人占。

---

## 🚀 快速开始

### 1. 激活虚拟环境
```bash
cd /home/A/ysy/fish/backend
source .venv/bin/activate
```

### 2. 使用调试脚本（推荐，无需启动服务）

查看所有可用项目：
```bash
python scripts/preview_project.py
```

逐步调试某个项目的完整数据流（**步骤 1~10 全覆盖**）：
```bash
python scripts/debug_pipeline.py <project_id>
```

常用变体：
```bash
python scripts/debug_pipeline.py <project_id> --offline        # 跳过联网步骤（不连 Zep）
python scripts/debug_pipeline.py --sim <simulation_id>         # 直接从模拟那一步开始看（6~10）
python scripts/debug_pipeline.py --prompt ontology <project_id> # 只看喂给大模型的提示词，不花钱
DEBUG_PREVIEW=1500 python scripts/debug_pipeline.py <project_id> # 调整预览长度
```

示例：
```bash
python scripts/debug_pipeline.py proj_584f702adfdd
python scripts/debug_pipeline.py --sim sim_2996e504cfe0
```

不带参数运行会列出所有可用的项目和模拟：
```bash
python scripts/debug_pipeline.py
```

---

## 📊 调试脚本说明

### debug_pipeline.py - 完整数据流调试

这个脚本会逐步打印每个阶段的输入输出：

```
================================================================================
  开始调试项目: proj_584f702adfdd
================================================================================

================================================================================
  步骤1: 原始文件
================================================================================
📄 文件: ea6adfba.md
长度: 3036 字符
前500字符:
# 罗永浩 x 西贝预制菜风波舆情推演与财务预测
...

================================================================================
  步骤2: 提取的文本 (extracted_text.txt)
================================================================================
文本长度: 3060 字符
...

================================================================================
  步骤3: 项目配置 (project.json)
================================================================================
项目ID: proj_584f702adfdd
图谱ID: mirofish_30d6bd2f072e4576
模拟需求: 预测一下这个事件后双方未来5年的营收状况
...

================================================================================
  步骤4: 文本分块 (发送给Zep的数据)
================================================================================
分块参数: chunk_size=500, overlap=50
分块数量: 9
...

================================================================================
  步骤5: 从Zep获取图谱数据
================================================================================
✅ 获取成功!
节点数: 33
边数: 126
实体类型分布:
  - RestaurantChain: 9
  - ConsumerGroup: 6
  ...
```

---

## 🎯 关键断点位置

### 方式1: Flask API断点调试

启动Flask服务：
```bash
python run.py
```

在以下文件的关键函数打断点：

#### 断点1: 本体生成入口
- **文件**: `/app/api/graph.py`
- **行号**: 265
- **函数**: `generate_ontology()`
- **查看内容**: 
  - 上传的文件
  - 模拟需求
  - 提取的文本

#### 断点2: 图谱构建
- **文件**: `/app/api/graph.py`
- **行号**: 430
- **函数**: `build_graph()`
- **查看内容**:
  - 分块后的文本
  - 本体定义
  - 发送给Zep的数据

#### 断点3: 实体读取
- **文件**: `/app/api/simulation.py`
- **行号**: 111
- **函数**: `get_entities()`
- **查看内容**:
  - 图谱节点
  - 过滤逻辑

#### 断点4: Profile生成
- **文件**: `/app/api/simulation.py`
- **行号**: 1058
- **函数**: `generate_profiles()`
- **查看内容**:
  - EntityNode列表
  - 生成的人设配置

#### 断点5: 配置生成
- **文件**: `/app/api/simulation.py`
- **行号**: 1341
- **函数**: `generate_config()`
- **查看内容**:
  - 模拟参数
  - Agent配置

---

### 方式2: 服务层断点调试

#### OntologyGenerator
- **文件**: `/app/services/ontology_generator.py`
- **函数**: `generate()`
- **输入**: 文档文本列表、模拟需求
- **输出**: 本体定义（实体类型、关系类型）

#### GraphBuilder
- **文件**: `/app/services/graph_builder.py`
- **函数**: `add_text_batches()`
- **输入**: 分块文本
- **输出**: 图谱数据（节点、边）

#### OasisProfileGenerator
- **文件**: `/app/services/oasis_profile_generator.py`
- **函数**: `generate_profiles()`
- **输入**: EntityNode列表
- **输出**: Agent人设配置

#### SimulationConfigGenerator
- **文件**: `/app/services/simulation_config_generator.py`
- **函数**: `generate()`
- **输入**: simulation_id、模拟需求、实体列表
- **输出**: 模拟参数配置

---

### 方式3: 手动查看输出文件

每个阶段的输出都保存在文件系统中：

#### 阶段1: 原始文件
```bash
cat /home/A/ysy/fish/backend/uploads/projects/<project_id>/files/*.md
```

#### 阶段2: 提取的文本
```bash
cat /home/A/ysy/fish/backend/uploads/projects/<project_id>/extracted_text.txt
```

#### 阶段3: 项目配置（含本体定义）
```bash
cat /home/A/ysy/fish/backend/uploads/projects/<project_id>/project.json | python3 -m json.tool
```

#### 阶段4: 模拟配置
```bash
cat /home/A/ysy/fish/backend/uploads/simulations/<simulation_id>/simulation_config.json | python3 -m json.tool
```

#### 阶段5: Agent Profiles
```bash
cat /home/A/ysy/fish/backend/uploads/simulations/<simulation_id>/reddit_profiles.json | python3 -m json.tool
```

#### 阶段6: 模拟动作日志
```bash
tail -50 /home/A/ysy/fish/backend/uploads/simulations/<simulation_id>/twitter/actions.jsonl
```

---

## 📁 关键文件路径

### 项目目录结构
```
uploads/
├── projects/
│   └── <project_id>/
│       ├── files/                 # 原始上传文件
│       │   └── *.md
│       ├── extracted_text.txt     # 提取的纯文本
│       └── project.json           # 项目配置（包含本体定义、图谱ID）
│
└── simulations/
    └── <simulation_id>/
        ├── simulation_config.json   # 模拟配置
        ├── reddit_profiles.json     # Reddit Agent人设
        ├── twitter_profiles.csv     # Twitter Agent人设
        ├── run_state.json           # 运行状态
        ├── twitter/
        │   └── actions.jsonl        # Twitter动作日志
        └── reddit/
            └── actions.jsonl        # Reddit动作日志
```

### 脚本目录
```
scripts/
├── preview_project.py           # 快速预览项目
├── debug_pipeline.py            # 完整数据流调试
├── fetch_project_graph_detail.py # 获取完整图谱数据
└── fetch_graph_data.py          # 批量获取图谱数据
```

---

## 🔍 调试示例：查看发送到Zep的数据

```bash
# 1. 查看项目配置
cat project.json | grep -A5 "chunk_size"

# 2. 手动分块文本
python3 -c "
from app.services.text_processor import TextProcessor
text = open('uploads/projects/proj_584f702adfdd/extracted_text.txt').read()
chunks = TextProcessor.split_text(text, chunk_size=500, overlap=50)
print(f'分块数量: {len(chunks)}')
print(f'总字符数: {len(text)}')
for i, chunk in enumerate(chunks[:3]):
    print(f'\n--- Chunk {i} ---')
    print(chunk[:200])
"

# 3. 这就是发送到Zep的数据！
```

---

## 📦 导出图谱数据（nodes / edges / episodes）

图谱只存在于 Zep 云端，本地没有副本。要看它抽出了什么，用这个脚本导出：

```bash
./.venv/bin/python scripts/export_graph.py --sim sim_e65a8f86393d      # 从模拟 ID 取
./.venv/bin/python scripts/export_graph.py --project proj_cbbcf8b78580  # 或从项目 ID 取
./.venv/bin/python scripts/export_graph.py mirofish_xxxx                # 或直接给 graph_id

# 可选参数
--out /tmp/g.json       # 指定输出路径（默认 uploads/graph_export_<gid>.json）
--lastn 200             # 只取最近 N 条 episode
--no-episodes           # 跳过原始文本，只要节点和边（更快）
```

产出 JSON 的结构：

| 字段 | 内容 |
|---|---|
| `nodes[]` | uuid / name / labels（类型）/ summary（摘要）/ attributes / created_at |
| `edges[]` | fact（事实原文）/ fact_type / 首尾节点名 / `valid_at` `invalid_at` `expired_at`（时序）/ episodes（来源文本 id） |
| `episodes[]` | 原始文本本体：content / source_description / created_at |

判断抽取质量看两个数：
- `labels` 为空的节点占比 —— 空 = 没归入本体定义的类型，通常是地名、话题标签这类噪音
- `fact_type` 里 `RELATES_TO` 的占比 —— 这是 Zep 的兜底关系，占比越高说明本体越没生效

> ⚠️ **坑**：`client.graph.episode.get_by_graph_id()` **不传 `lastn` 时只返回 4 条**。
> 实测同一张图：默认 4 条、`lastn=500` 才拿到全部 94 条。脚本已默认设 1000，
> 自己写代码调这个接口时**必须显式传大值**，否则会静默丢掉九成原始文本。

---

## 🎨 IDE调试技巧

### PyCharm
1. 打开项目：`File -> Open -> /home/A/ysy/fish/backend`
2. 设置断点：在关键函数点击行号左侧
3. 启动调试：`Run -> Debug 'run'`
4. 调用API触发断点

### VS Code
1. 打开项目：`File -> Open Folder -> /home/A/ysy/fish/backend`
2. 设置断点：在关键函数点击行号左侧
3. 启动调试：按 `F5` 或点击调试图标
4. 调用API触发断点

### 关键断点建议

```python
# /app/api/graph.py:265 - generate_ontology()
def generate_ontology():
    try:
        # ✅ 断点1：查看输入
        simulation_requirement = request.form.get('simulation_requirement', '')
        uploaded_files = request.files.getlist('files')
        
        # 处理逻辑...
        
        # ✅ 断点2：查看输出
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "ontology": ontology
            }
        })
```

---

## 📋 调试清单

### 检查点1: 原始文件
- [ ] 文件是否存在
- [ ] 文件内容是否正确
- [ ] 文件编码是否UTF-8

### 检查点2: 文本提取
- [ ] extracted_text.txt 是否生成
- [ ] 内容是否完整
- [ ] 是否正确去除格式

### 检查点3: 本体定义
- [ ] 实体类型数量是否合理（通常5-15个）
- [ ] 关系类型数量是否合理（通常5-10个）
- [ ] 是否有示例（examples字段）

### 检查点4: 图谱构建
- [ ] graph_id 是否生成
- [ ] 节点数量
- [ ] 边数量
- [ ] 实体类型分布

### 检查点5: Agent生成
- [ ] Profile数量是否等于Entity数量
- [ ] persona 是否有内容
- [ ] interested_topics 是否有内容

### 检查点6: 模拟配置
- [ ] time_config 是否合理
- [ ] agent_configs 数量
- [ ] initial_posts 是否有内容

---

## ⚠️ 常见问题

### 问题1: 模块导入失败
**错误**: `ModuleNotFoundError: No module named 'flask'` / `No module named 'app'`

**九成是 IDE 用的解释器不是项目的虚拟环境** —— 尤其"运行时一切正常、按 F5 才报错"时，必是这条。

本项目是 **editable 方式安装**的（`backend` 目录被写进了 `backend/.venv` 的搜索路径），
依赖只存在于那一个虚拟环境里。用系统 Python 跑必然全军覆没，跟"到底装没装"无关。

处理：
1. 看 VSCode 右下角状态栏当前选的解释器，应该是 `backend/.venv`
2. 不对就 `Ctrl+Shift+P` → `Python: Select Interpreter` → 选它
3. Windows 路径是 `.venv\Scripts\python.exe`，macOS / Linux 是 `.venv/bin/python`
4. 终端里验证：`python -c "import sys,flask;print(sys.executable)"`

本项目已配好 `.vscode/settings.json`（默认解释器 + 代码补全会认识 `app`）
与 `.vscode/launch.json`（5 个配置都显式指定了解释器和工作目录，含 Windows 路径覆盖），
**重启 VSCode 后自动生效**。

如果换成对的解释器仍然报错，且错误形如 `ImportError: xxx.so: cannot open shared object`
或 `DLL load failed` —— 那不是环境问题，是某个包的原生扩展加载失败，要查 Python 版本是否匹配。

### 问题2: ZEP_API_KEY 未配置
**错误**: `Zep API key not configured`

**解决**: 检查 `.env` 文件或环境变量
```bash
echo $ZEP_API_KEY
```

### 问题3: 项目文件不存在
**错误**: `项目不存在: xxx`

**解决**: 检查项目ID是否正确
```bash
ls -1 /home/A/ysy/fish/backend/uploads/projects/
```

### 问题4: 图谱数据获取失败
**错误**: `Failed to get graph data`

**解决**: 
1. 检查网络连接
2. 确认Zep服务可用
3. 确认graph_id正确

---

## 🎯 推荐调试流程

### 流程1: 使用调试脚本（快速）
```bash
# 单步查看每个阶段
python scripts/debug_pipeline.py proj_584f702adfdd
```

### 流程2: 使用IDE断点（详细）
```bash
# 启动Flask服务
python run.py

# 在IDE中设置断点
# 调用API
curl -X POST http://localhost:5001/api/ontology/generate \
  -F "files=@test.md" \
  -F "simulation_requirement=测试"
```

### 流程3: 手动查看文件（简单）
```bash
# 查看每个阶段的输出文件
ls -la uploads/projects/<project_id>/
ls -la uploads/simulations/<simulation_id>/
```

---

## 📞 获取帮助

如果遇到问题：
1. 查看 `debug_pipeline.py` 的输出
2. 检查日志文件
3. 确认依赖已安装
4. 验证网络连接

---

**祝您调试顺利！** 🚀