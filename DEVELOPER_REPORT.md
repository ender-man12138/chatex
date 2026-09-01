# ChatEx 项目开发报告

> **生成时间**: 2026-09-01  
> **项目状态**: 核心功能完成，存在若干Bug需修复，打包未完成

---

## 一、项目概述

**ChatEx** 是一个完全本地离线的桌面聊天应用，核心功能是：
1. 使用本地 Qwen3.5-2B GGUF 模型提供推理能力
2. 导入聊天记录生成「前任 Skill」进行角色扮演对话
3. 支持对话历史管理、纠偏进化、版本回滚

### 技术栈
| 组件 | 选型 |
|------|------|
| 后端 | Python 3.12 + FastAPI |
| 推理引擎 | llama.cpp (独立子进程) |
| 桌面窗口 | pywebview |
| 前端 | 单页 HTML + CSS + JS |
| 存储 | JSON 文件 |

---

## 二、核心功能实现状态

### ✅ 已完成功能

| 功能模块 | 实现状态 | 说明 |
|----------|----------|------|
| FastAPI 服务启动 | ✅ 完整 | `main.py` 集成 lifespan，自动启停 llama-server |
| 端口配置 | ✅ 正确 | FastAPI: 9090, llama-server: 8848（已按 AGENTS.md 修改） |
| llama-server 子进程管理 | ✅ 完整 | 健康检查、优雅关闭、超时处理 |
| 基础聊天接口 | ✅ 完整 | `/api/chat` 流式输出，对话历史管理 |
| Skill CRUD | ✅ 完整 | 创建/读取/删除 Skill |
| Skill 分析流程 | ⚠️ 部分完成 | memory/persona 两步分析，但 prompt 拼接有bug |
| 文件导入解析 | ✅ 完整 | 支持 txt/csv/json/html 格式 |
| 前端聊天界面 | ✅ 完整 | 侧栏对话列表 + 主聊天区 + Skill面板 |
| Intake 三步向导 | ✅ 完整 | 花名/简介/性格输入 |
| 纠偏机制 | ✅ 完整 | 手动和LLM自动两种模式 |
| ex-skill prompts/tools 适配 | ✅ 完成 | skill_engine.py 桥接层 |

### ❌ 未完成功能

| 功能 | 状态 | 影响 |
|------|------|------|
| PyInstaller 打包 | 未开始 | 无法生成分发版 launcher.exe |
| 内嵌 Python + 完整打包测试 | 未开始 | 目标用户环境隔离方案未验证 |
| scene 多前任模式 | 未实现 | prompts/scene_director.md 存在但未接入 |
| session summary 自动生成 | 未触发 | 代码存在但无自动触发逻辑 |

---

## 三、已知 Bug 和严重问题

### 🔴 P0 - 关键Bug（必须修复）

#### 1. `_client.py` 控制流错误（行22-24）
```python
def get_llm_client(slug):
    if slug and config.is_api_enabled():
        ...
        return AsyncOpenAI(...)  # ← 这个return永远不会被执行！
            return AsyncOpenAI(...)  # ← 语法错误：else后直接return，条件分支失效
        ...
    return AsyncOpenAI(...)
```
**后果**: 在线 API 分支的 `return` 在 `if` 块内嵌套过深，实际执行的是最后的通用 return。需要重构为：
```python
if not (slug and config.is_api_enabled()):
    logger.debug(f"使用本地 llama-server: {build_openai_url()}")
    return AsyncOpenAI(base_url=build_openai_url(), api_key="not-needed")

meta_path = config.SKILLS_DIR / slug / "meta.json"
if meta_path.exists():
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("source") == "import":
            return AsyncOpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)
    except Exception:
        pass

logger.debug(f"使用本地 llama-server: {build_openai_url()}")
return AsyncOpenAI(base_url=build_openai_url(), api_key="not-needed")
```

#### 2. skill_engine.py 字符串截断导致分析失败
```python
def _combine_prompts(...):
    lines = [
        ...
        analyzer_raw[:1500] if len(analyzer_raw) > 1500 else analyzer_raw,  # ← 截断问题
        ...
    ]
```
当 analyzer_raw 超过 1500 字符时被截断，导致 prompt 不完整，模型输出异常。建议增加截断逻辑的可配置性，或改用更智能的截断策略（如保留完整段落）。

#### 3. SKILL.md 生成时模板变量未替换
`skill_writer.py` 中的 `combine_skill()` 函数生成的 SKILL.md 包含大量 `{name}`, `{age_range}` 等占位符，这些变量从未被填充：
- memory.md 和 persona.md 内容可以正确插入
- 但 persona.md 的 5 层结构本身仍包含 `{placeholder}` 变量

**表现**: data/skills/ex-04c5e9/SKILL.md 中 Layer 1-4 全部是原始模板文本，模型无法据此生成正确回复。

### 🟡 P1 - 重要问题

#### 4. 中文编码问题
`frontend/app.js` 中存在乱码问题（显示为 `鏆傛棤瀵硅瘽` 等），说明 JS 文件保存编码不正确或读取时有编码问题。

#### 5. 对话与 Skill 关联缺失
当前实现中，对话历史和 Skill 没有关联关系：
- `chat.py` 的对话存储在 `data/conversations/{conv_id}.json`
- `skills_new.py` 的对话也存储在同一个目录
- 前端切换 Skill 后无法恢复到该 Skill 的历史对话
- 每个 Skill 应有独立的对话空间

#### 6. 前端数据加载不一致
- `loadConversations()` 从 `/api/conversations` 加载全局对话
- 但每个 Skill 可能有多个对话，应该按 Skill 筛选

### 🟢 P2 - 体验优化

#### 7. 缺少流式输出
`chat.py` 实现了流式调用 `stream=True`，但前端 `app.js` 接收的是完整响应后一次性渲染：
```javascript
const data = await resp.json();  // ← 应该是流式读取
typingRow.querySelector('.bubble').innerHTML = formatAiContent(data.response);
```

#### 8. 前端状态管理简单
使用全局变量而非状态管理，多用户并发场景下可能有竞态问题（虽然桌面应用单实例下影响有限）。

#### 9. 缺少键盘快捷键
- Enter 发送 ✓
- Shift+Enter 换行 ✓
- 缺少 Ctrl+C 复制消息、Ctrl+E 编辑纠正等效率快捷键

---

## 四、开发约束与规则

### 严格禁止修改的文件/目录（AGENTS.md 规定）
| 路径 | 原因 |
|------|------|
| `skills/create-ex/` | ex-skill 工具链原文件，只可适配不可修改 |
| `plan.md` | 项目方案文档，保留原样 |
| `python/` | 内嵌 Python 运行时，LFS 跟踪 |
| `llama/` | llama.cpp 二进制，LFS 跟踪 |
| `models/` | GGUF 模型文件，LFS 跟踪 |
| `venv/` | 开发虚拟环境 |
| `.git/` | 版本控制元数据 |

### 端口约定（不可修改）
| 服务 | 端口 |
|------|------|
| FastAPI / pywebview | 9090 |
| llama-server | 8848 |

### Git 操作规范
- 提交(commit)与推送(push)由用户手动操作
- Agent 只负责修改本地文件

---

## 五、现有数据质量评估

### 已创建的 Skills
| Slug | 名称 | 来源 | 状态 |
|------|------|------|------|
| ex-04c5e9 | ??? | text | ⚠️ persona.md 含模板变量 |
| ex-2e8f3c | ?? | text | ⚠️ memory/persona 均为空模板 |
| bot013039 | Bot013039 | text | 基础创建 |
| check | Check | text | 基础创建 |
| testbot | TestBot | text | 基础创建 |
| intakebot | IntakeBot | text | 基础创建 |

**问题**: 数据分析输出的 persona.md 仍包含 `{name}`, `{mbti}` 等占位符，说明 prompt 截断或模型理解存在问题。

---

## 六、后续开发建议

### 优先修复项（按重要性排序）

1. **修复 `_client.py` 控制流** - 影响在线API分支选择
2. **修复 SKILL.md 生成逻辑** - 确保 persona.md 模板变量被正确填充
3. **优化 prompt 拼接截断策略** - 避免关键指令被截断
4. **修复前端中文编码** - 解决乱码问题
5. **建立对话-Skill关联** - 为每个 Skill 创建独立对话空间
6. **实现流式输出前端** - 提升用户体验
7. **完成 PyInstaller 打包** - 生成分发版

### 长期规划

1. **Scene 模式** - 实现多前任同场对话（已有 prompt）
2. **Session Summary 自动触发** - 对话结束后自动生成摘要
3. **版本管理界面** - 可视化回滚历史版本
4. **更多数据源支持** - 照片 EXIF、朋友圈截图 OCR

---

## 七、项目健康度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | ⭐⭐⭐⭐☆ | FastAPI 分层清晰，ex-skill 集成合理 |
| 代码质量 | ⭐⭐⭐☆☆ | 存在明显控制流bug，需仔细审查 |
| 功能完整性 | ⭐⭐⭐☆☆ | 核心功能可用，边缘场景待完善 |
| 用户体验 | ⭐⭐⭐☆☆ | 界面美观但交互细节不足 |
| 文档完整性 | ⭐⭐⭐⭐☆ | plan.md/REPORT.md/AGENTS.md 齐全 |
| 可扩展性 | ⭐⭐⭐⭐☆ | prompts/tools 分离设计便于扩展 |

**综合评估**: 项目核心架构已完成，存在若干需紧急修复的Bug，建议按优先级逐步修复后再进入打包发布阶段。

---

*报告由 AgnesCode Agent 生成 · 基于项目代码静态分析*
