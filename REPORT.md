# ChatEx 项目报告

> 本地离线聊天工具 · llama.cpp + FastAPI + pywebview  
> 更新日期：2026-08-24

---

## 一、项目概述

ChatEx 是一个完全本地离线运行的桌面聊天应用，使用已下载的 Qwen3.5-2B GGUF 模型通过 llama.cpp 提供推理能力。数据不离开本机，不依赖外部网络或 AI 服务。支持导入聊天记录生成「前任 Skill」进行角色扮演对话。

**技术栈**

| 组件 | 选型 | 说明 |
|------|------|------|
| 后端 | Python 3.12 + FastAPI | 异步 HTTP 服务 |
| 推理引擎 | llama.cpp（llama-server.exe） | CPU 运行，OpenAI 兼容 API |
| 桌面窗口 | pywebview | 基于系统 WebView，轻量 |
| 前端 | 单页 HTML + CSS + JS | FastAPI StaticFiles 托管 |
| 存储 | JSON 文件 | 对话历史 + Skill 数据 |

---

## 二、目录结构

```
chatex/
├── main.py                 FastAPI 入口 + pywebview 窗口管理
├── REPORT.md               项目报告（本文件）
├── app/
│   ├── config.py           配置管理（路径、端口、环境变量覆盖）
│   ├── server.py           llama-server 子进程启停与守护
│   └── routers/
│       ├── chat.py         聊天接口（POST /api/chat）及对话管理
│       ├── skills.py       Skill CRUD、分析、对话运行
│       └── file_import.py  文件/文本导入与解析
├── frontend/
│   └── index.html          聊天界面（侧栏 + 消息 + 输入）
├── llama/                  llama.cpp 完整二进制包
├── models/
│   └── qwen3-5-2B-Q4_K_M.gguf   基底模型（~1.27 GB）
├── python/                 内嵌 Python 3.12 embed 版
├── venv/                   开发虚拟环境
├── data/                   运行时数据（gitignored）
│   ├── conversations/      对话历史 JSON
│   └── skills/             Skill 数据（生成后存放于此）
├── skills/
│   └── create-ex/          ex-skill 工具（prompts/tools/，参考用）
├── requirements.txt
└── .gitignore
```

---

## 三、核心接口

### 3.1 聊天接口（chat.py）

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/chat` | POST | 发送消息，流式调用 llama-server |
| `/api/conversations` | GET | 列出所有对话摘要 |
| `/api/conversations/{id}` | GET | 获取单个对话历史 |
| `/api/conversations/{id}` | DELETE | 删除对话 |

### 3.2 Skill 管理接口（skills.py）

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/skills/` | GET | 列出所有 Skill |
| `/api/skills/` | POST | 创建新 Skill（收集花名/基本信息） |
| `/api/skills/{slug}` | GET | 获取 Skill 详情（memory/persona/SKILL.md） |
| `/api/skills/{slug}/analyze` | POST | 调用模型分析原材料，生成 memory.md + persona.md |
| `/api/skills/{slug}/combine` | POST | 手动重新组合 SKILL.md |
| `/api/skills/{slug}/run` | POST | 以 Skill 上下文运行对话（注入 SKILL.md 作为 system prompt） |
| `/api/skills/{slug}/correction` | POST | 对话纠偏（写入 Correction 记录） |
| `/api/skills/{slug}` | DELETE | 删除 Skill |
| `/api/skills/{slug}/versions` | GET | 列出历史版本 |

### 3.3 导入接口（file_import.py）

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/import/file/{slug}` | POST | 上传聊天记录文件（微信/QQ/社交媒体） |
| `/api/import/text/{slug}` | POST | 直接粘贴聊天记录文本 |

---

## 四、Skill 创建流程

```
用户输入花名 + 基本信息 + 性格画像
    ↓
POST /api/skills/  →  创建 meta.json，生成 slug
    ↓
用户导入原材料（聊天记录/文本）
    ↓
POST /api/import/text/{slug}  →  解析消息，提取风格特征
    ↓
POST /api/skills/{slug}/analyze  →  调用模型生成 memory.md + persona.md
    ↓
POST /api/skills/{slug}/combine  →  组合 SKILL.md
    ↓
POST /api/skills/{slug}/run  →  以 Skill 上下文对话
```

**两层架构：**
- **Part A（memory.md）**：关系记忆——时间线、共同经历、inside jokes、争吵/甜蜜模式
- **Part B（persona.md）**：人物性格——5 层结构（硬规则→身份→说话风格→情感模式→关系行为）

---

## 五、配置项（app/config.py）

| 配置项 | 默认值 | 环境变量 |
|--------|--------|----------|
| `MODEL_PATH` | `models/qwen3-5-2B-Q4_K_M.gguf` | `CHATEX_MODEL_FILENAME` |
| `LLAMA_PORT` | `8848` | `CHATEX_LLAMA_PORT` |
| `APP_PORT` | `9090` | `CHATEX_APP_PORT` |
| `CTX_SIZE` | `8192` | `CHATEX_CTX_SIZE` |
| `THREADS` | `8` | `CHATEX_THREADS` |
| `MAX_HISTORY` | `20` | `CHATEX_MAX_HISTORY` |
| `ENABLE_THINKING` | `false` | `CHATEX_ENABLE_THINKING` |
| `SKILLS_DIR` | `data/skills/` | `CHATEX_SKILLS_DIR` |

---

## 六、当前状态

- [x] 项目目录结构搭建
- [x] 内嵌 Python 3.12 + pip（`python/`）
- [x] 开发虚拟环境 + 所有依赖安装（`venv/`）
- [x] llama.cpp 二进制就位（`llama/`）
- [x] 模型文件就位（`models/qwen3-5-2B-Q4_K_M.gguf`）
- [x] `app/config.py` 配置管理
- [x] `app/server.py` llama-server 子进程管理
- [x] `app/routers/chat.py` 基础聊天接口 + 对话管理
- [x] `app/routers/skills.py` Skill 全生命周期管理
- [x] `app/routers/file_import.py` 文件/文本导入与解析
- [x] `main.py` FastAPI 入口 + pywebview 窗口 + 关闭确认
- [x] `frontend/index.html` 完整聊天界面（侧栏 + 消息 + 输入）
- [x] 端到端测试通过（create → analyze → run）
- [x] 前端 Skill 管理界面（列表、创建模态框、详情查看、删除、补充材料、与 Skill 对话）
- [x] ex-skill prompts/tools 深度集成（完成）
- [ ] PyInstaller 打包 launcher.exe（待开发）
- [ ] 内嵌 Python + 完整分发包测试

---

## 七、启动方式

```powershell
cd E:\wh\10nodata\program\chatex
.\venv\Scripts\python.exe main.py
```

---

*本报告在项目迭代过程中持续更新。*



