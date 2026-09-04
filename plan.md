# ChatEx — 本地离线聊天工具 技术方案

## 项目概述

完全本地离线运行的桌面聊天应用，使用已下载的 Qwen3.5-2B (.gguf) 模型提供推理能力，支持导入聊天记录生成「前任 Skill」进行角色扮演对话。

---

## 技术栈

| 层级 | 技术选型 | 理由 |
|------|----------|------|
| 后端服务 | Python 3.9+ + FastAPI | 轻量、异步、ex-skill 工具链原生 Python |
| 模型推理 | llama.cpp server（独立子进程） | GGUF 原生支持，CPU 运行，OpenAI 兼容 API |
| 桌面窗口 | pywebview | 基于系统 WebView，打包后 ~15MB，远比 Electron 轻 |
| 前端 | 单页 HTML + CSS + JS | 由 FastAPI 静态服务，开发调试最简单 |
| 数据存储 | JSON 文件 | 结构简单，可读可编辑，无额外依赖 |

---

## 环境内嵌方案

### 为什么不依赖系统 Python

- 目标用户电脑没有 Python，也不想安装
- 开发机同样没有 Python 3，需要自行安装
- 内嵌方式保证完全隔离，不留系统痕迹

### 分发时的目录结构（用户拿到就是这样的）

`
chatex/                           ← 整个文件夹发给用户
├── main.py                       ← 一键启动（pywebview 窗口，关闭窗口即停止全部服务）
│   - 在守护线程中启动 llama-server.exe
│   - 在守护线程中启动 FastAPI
│   - 打开 pywebview 窗口
│   - 窗口关闭时自动停止所有服务
├── python/                       ← 内嵌便携版 Python 3.12（~40MB）
│   ├── python.exe
│   └── Lib/
├── venv/                         ← 项目虚拟环境（~50MB）
│   ├── Lib/site-packages/        ← 所有依赖
│   └── Scripts/
├── llama/                        ← llama.cpp 完整发行版（~30MB）
│   └── llama-server.exe          ← 推理服务
├── app/                          ← 后端代码
├── frontend/                     ← 前端代码
├── skills/
│   └── create-ex/                ← ex-skill 工具（tools/ prompts/）
├── models/
│   └── qwen3-5-2B-Q4_K_M.gguf   ← 基底模型（~1.5GB，可替换）
├── data/                         ← 运行时数据（动态生成，gitignored）
│   ├── conversations/
│   └── skills/
├── requirements.txt
└── README.md
`

### 各组件大小估算

| 组件 | 大小 | 说明 |
|------|------|------|
| Python 3.12 便携版 | ~40MB | https://python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip |
| pip（嵌入后手动安装） | ~20MB | 依赖包展开大小 |
| FastAPI + 依赖 | ~15MB | uvicorn, pydantic, openai, pywebview 等 |
| main.py（可选 PyInstaller 打包） | ~50-80MB | 含 Python 运行时 + 代码 |
| llama-server.exe | ~30MB | https://github.com/ggerganov/llama.cpp/releases |
| Qwen3.5-2B Q4_K_M.gguf | ~1.5GB | 基底模型，可替换 |
| **总计（不含模型）** | ~155-200MB | zip 压缩后约 100-120MB |
| **总计（含模型）** | ~1.7GB | 建议分卷压缩或两段式分发 |

---

## llama.cpp 获取方式

llama.cpp 是独立二进制工具，随项目内置分发，不需要用户单独安装。

下载地址：https://github.com/ggerganov/llama.cpp/releases  
选择 llama-server.exe（约 30MB），放入项目根目录。

---

## 整体架构

`
┌──────────────────────────────────────────────┐
│              main.py                         │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  1. 检查模型文件是否存在               │  │
│  │  2. 启动 llama-server（子进程）         │  │
│  │  3. 启动 FastAPI（守护线程）           │  │
│  │  4. 打开 pywebview 窗口                │  │
│  │  5. 注册窗口关闭回调：停止全部服务     │  │
│  └────────────────────────────────────────┘  │
│                     │                        │
│  ┌──────────────────▼─────────────────────┐  │
│  │         FastAPI 后端服务               │  │
│  │  /api/chat        发送消息              │  │
│  │  /api/skills      Skill CRUD           │  │
│  │  /api/import      导入聊天记录          │  │
│  │  /api/conversations  加载/管理对话历史   │  │
│  │  /api/config      配置读写              │  │
│  │  /api/health      健康检查              │  │
│  └──────────────────┬─────────────────────┘  │
│                     │ HTTP localhost:9090    │
└─────────────────────┼───────────────────────┘
                      │
┌─────────────────────▼───────────────────────┐
│       llama.cpp server（子进程）             │
│  加载 models/{模型文件}.gguf                 │
│  监听 localhost:8848                         │
│  响应 OpenAI 兼容格式                        │
│                                              │
│  退出方式：                                  │
│  - 关闭窗口 → 自动停止所有服务（FastAPI + llama-server）│
└──────────────────────────────────────────────┘
`

---

## 窗口关闭逻辑

窗口关闭时直接停止全部服务，无确认弹窗：

- **关闭窗口**：FastAPI 停止 → llama-server 子进程终止 → 应用退出
- 不存在后台残留进程

---

## ex-skill 集成策略（关键）

ex-skill 由两类文件组成，集成方式不同：

### 1. 工具代码（直接复用）

	ools/ 下的 Python 脚本可以直接运行，无需修改：
- wechat_parser.py — 解析微信/QQ聊天记录，输出文本分析报告
- skill_writer.py — Skill 文件管理（list/create）
- ersion_manager.py — 版本存档与回滚

### 2. Prompt 文件（需要适配）

prompts/ 下的 .md 文件是给 Claude Code 读的指令，包含了工具调用语法（如 Read、Bash），**不能直接发给本地模型**。

**适配方式**：将每个 prompt 的核心提取指令保留，去掉工具调用语法，包装成标准对话 Prompt：

`
原始（ex-skill 给 Claude Code 的）：
  "使用 Read 工具读取文件，然后用 Bash 执行 python3 ..."

适配后（给本地模型的）：
  "请根据以下聊天记录内容，按照下面的维度提取信息，
   以 markdown 格式输出，不要包含任何工具调用说明：
   
   [原始 prompt 的提取维度和输出格式]"
`

已在项目中提供适配后的完整 prompt 版本，存放在 pp/services/prompts/。

---

## 项目目录结构（开发时）

`
chatex/
├── main.py                      # pywebview 一键启动：FastAPI + llama-server + 窗口，关闭窗口即停止全部服务
├── app/
│   ├── __init__.py
│   ├── config.py                # 配置管理（模型路径、端口、对话历史上限等）
│   ├── server.py                # llama-server 子进程管理（启动/停止/日志）
│   ├── skill_engine.py          # Skill 核心逻辑（LLM 调用、对话构建）
│   └── routers/
│       ├── __init__.py
│       ├── chat.py              # 聊天接口
│       ├── skills_new.py        # Skill CRUD
│       ├── file_import.py       # 聊天记录导入（调用 wechat_parser.py）
│       ├── health.py            # 健康检查
│       └── _client.py           # OpenAI 兼容 API 客户端封装
├── frontend/
│   ├── index.html               # 主页面
│   ├── app.js                   # 前端逻辑
│   └── diagnose.html            # 诊断页
├── data/
│   ├── conversations/           # JSON 对话文件（按 slug 分目录）
│   └── skills/                  # Skill 定义文件
│       └── {slug}/
│           ├── persona.md       # 人格画像
│           ├── memory.md        # 关系记忆
│           ├── profile.md       # 用户画像
│           └── meta.json        # 元数据
├── skills/
│   └── create-ex/               # ex-skill 完整复制（只取 tools/ 用）
│       ├── tools/
│       │   ├── wechat_parser.py
│       │   ├── qq_parser.py
│       │   ├── skill_writer.py
│       │   └── version_manager.py
│       └── prompts/             # 原始 prompts（仅作参考，不直接使用）
├── llama/                       # llama.cpp 完整发行版（gitignored）
├── python/                      # 内嵌 Python 3.12（gitignored）
├── venv/                        # 虚拟环境（gitignored）
├── models/                      # 存放 .gguf 模型文件（gitignored）
├── requirements.txt
└── README.md
`

---

## 核心功能流程

### 功能一：创建 Skill（主流程，A 方案）

`
Step 1: 用户输入
  - 代号（必填）
  - 基础信息（一句话描述）
  - 性格画像（MBTI/星座/标签）

Step 2: 上传原材料
  - 选择文件 (.txt / .html)
  - 或粘贴纯文本

Step 3: 解析聊天记录（本地执行，不调用模型）
  llama-server 未运行，仅用 Python 工具：
  subprocess → wechat_parser.py --file xxx.txt --target 代号 --output analysis.txt
  输出：一段包含语料统计和样本的文本报告

Step 4: 生成 persona.md（调用本地模型）
  Prompt = 适配版 persona_analyzer.md
  + 聊天记录分析报告
  → 调用 llama.cpp API → 生成 persona.md

Step 5: 生成 memory.md（调用本地模型）
  Prompt = 适配版 memory_analyzer.md
  + 聊天记录分析报告
  → 调用 llama.cpp API → 生成 memory.md

Step 6: 生成 SKILL.md + meta.json
  skill_writer.py 整合上述文件，生成最终 Skill
  存入 data/skills/{slug}/
`

### 功能二：快速风格设定（B 方案）

`
用户输入人物描述（纯文本，如"话痨双子座的网瘾少女"）
  → 直接调用 persona_builder.md prompt + 本地模型
  → 生成 persona.md（跳过聊天记录导入步骤）
  → 存入 data/skills/{slug}/
  → 与 A 方案共用同一套聊天下发逻辑
`

### 功能三：与 Skill 聊天

`
用户选择 Skill → 选择/新建对话
  → 读取 data/skills/{slug}/persona.md + memory.md
  → 读取 data/conversations/{slug}/conv_XXX.json（获取历史）
  → 构建 messages 数组：
     [
       {role: "system", content: persona.md 内容 + 安全规则},
       {role: "user",   content: "你好"},
       {role: "assistant", content: "嗨~"},
       ...当前消息...
     ]
  → 调用 llama.cpp API（openai 兼容格式）
  → 收到回复
  → 追加到对话历史，保存为 JSON
  → 返回给用户
`

### 功能四：通用聊天（无 Skill）

`
直接发送消息给本地模型
messages = [{role: "user", content: 用户消息}]
不带任何 persona 注入
普通对话模式
`

---

## 数据存储格式

### 对话记录（JSON）

`json
{
  "id": "conv_001",
  "skill_slug": "xiaoming",
  "created_at": "2026-08-22T11:00:00+08:00",
  "updated_at": "2026-08-22T14:30:00+08:00",
  "title": "和xiaomings的第一次对话",
  "messages": [
    { "role": "user",     "content": "在干嘛", "timestamp": "..." },
    { "role": "assistant", "content": "刚吃完饭...", "timestamp": "..." }
  ]
}
`

### Skill 元数据（meta.json）

`json
{
  "slug": "xiaoming",
  "name": "小明",
  "created_at": "2026-08-22",
  "version": 1,
  "source": "wechat|text",
  "message_count": 1247
}
`

---

## 配置项（config.py）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| MODEL_PATH | models/qwen3.5-2b-Q4_K_M.gguf | 模型文件路径 |
| LLAMA_PORT | 8848 | llama.cpp server 监听端口 |
| APP_PORT | 9090 | FastAPI + pywebview 监听端口 |
| MAX_HISTORY | 20 | 每次对话最多携带的历史消息数 |
| DATA_DIR | data/ | 数据根目录 |
| SKILLS_DIR | data/skills/ | Skill 文件目录 |
| CONVS_DIR | data/conversations/ | 对话记录目录 |

---

## 错误处理与回退

- **llama.cpp 未启动**：main.py 启动时检测端口，若未就绪则等待或提示用户
- **模型加载失败**：记录错误日志，提示用户检查模型路径
- **对话历史过大**：自动截断最早的消息，保留最近的 MAX_HISTORY 条
- **Skill 创建中断**：已生成的中间文件保留，支持断点续传式继续
- **文件解析失败**：显示具体错误信息，允许重新选择文件
- **窗口关闭时服务已停止**：关闭窗口即触发全部停止，无额外弹窗

---

## 依赖清单

### Python 依赖（requirements.txt）

`
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.6.0
python-multipart>=0.0.9
pywebview>=5.0.5
openai>=1.30.0          # 仅用于兼容 llama.cpp 的 OpenAI API
requests>=2.31.0
pyinstaller>=6.0.0      # 仅打包时使用
`

### ex-skill 依赖（skills/create-ex/requirements.txt）

`
Pillow>=9.0.0
`

---

## 开发环境搭建（首次运行）

在开发机上执行以下步骤，无需影响系统环境：

### 第一步：安装 Python 3.12

下载地址：https://www.python.org/downloads/release/python-3128/  
选择 **Windows Installer (64-bit)**，安装时勾选 "Add Python to PATH"。

### 第二步：进入项目目录，创建虚拟环境

`powershell
cd E:\wh\10nodata\program\chatex
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
`

### 第三步：下载 llama-server.exe

从 https://github.com/ggerganov/llama.cpp/releases 下载最新 release 的 llama-server.exe，放入项目根目录。

### 第四步：准备模型

将 .gguf 模型文件放入 models/ 目录（或从 https://huggingface.co 下载 Qwen3.5-2B 的 GGUF 版本）。

### 第五步：启动开发

`powershell
python main.py
`

---

## 打包步骤（可选）

`main.py` 目前可直接 `python main.py` 启动，无需打包。若需分发可执行文件，可用 PyInstaller：

`powershell
# 1. 激活虚拟环境
.\venv\Scripts\activate

# 2. 打包
pyinstaller --onefile --windowed ^
  --name ChatEx ^
  --add-data "frontend;frontend" ^
  --add-data "app;app" ^
  main.py

# 3. 输出位置：dist\ChatEx.exe
`

---

## 分发方案

采用 **内嵌 Python + zip 压缩分发**。

### 打包后的用户目录

`
ChatEx/
├── main.py             ← 一键启动程序（关闭窗口即停止全部服务）
├── python/               ← 内嵌便携版 Python 3.12
├── venv/                 ← 虚拟环境（含所有依赖）
├── llama-server.exe      ← 推理服务
├── models/               ← 基底模型（~1.5GB）
├── data/                 ← 运行时数据
└── README.md
`

### 分发包大小估算

| 组合方式 | 大小 | 说明 |
|----------|------|------|
| 仅代码 + Python + launcher + llama.cpp（无模型） | ~150MB | zip 压缩后约 90-100MB |
| 含基底模型 | ~1.7GB | zip 压缩后约 1.2GB |
| 含模型 + 分卷压缩 | ~1.2GB / 卷 | 每卷 700MB，便于传输 |

### 建议的分发策略

由于含模型的分发包超过 1GB，建议采用**两段式分发**：

1. **主程序包**（~100MB）：main.py + Python 环境 + llama.cpp + 代码
2. **模型包**（~1.5GB）：单独提供下载链接，用户自行放入 models/ 目录

主程序包通过 GitHub Release 或码云发布；模型包提供百度网盘/阿里云盘链接，适合国内用户下载。

---

## 发行说明（README 需包含）

- 双击 main.py 即可启动
- 模型文件需放入 models/ 目录（可使用内置基底模型）
- 完全离线运行，不上传任何数据
- 关闭窗口即停止全部服务，无后台残留

---

## 开发计划

1. 搭建 FastAPI 基础框架 + 配置管理
2. 实现 llama.cpp server 子进程管理（检查/启动/停止/守护）
3. 适配 ex-skill 的 prompts（去掉工具调用语法，转为纯文本 prompt）
4. 移植 ex-skill 的 tools/ 目录
5. 实现基础聊天接口（无 Skill，验证 llama.cpp 连通）
6. 实现 Skill 创建向导（含 A/B 两种方案）
7. 实现对话历史管理（JSON 读写、截断、列表）
8. 实现前端聊天界面 + 新建对话角色选择弹窗
9. PyInstaller 打包（可选）
10. 内嵌 Python + 完整打包测试

---

*方案待确认后开始构建，随时可以调整。*
