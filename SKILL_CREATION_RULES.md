# ChatEx 角色创建（Skill）功能开发规则

> 本文档从项目代码、plan.md、DEVELOPER_REPORT.md 及对话历史中提取，
> 汇总所有与「角色/Skill 创建与管理」相关的开发约束与实现规范，供后续开发参考。

---

## 一、两条分析路径（明确分开）

角色创建流程：**输入代号 + 关系背景 + 性格特征** → 创建本地小角色 → 弹出材料分析弹窗

分析弹窗的填与不填，决定走哪条路径：

| 路径 | 触发条件 | LLM 来源 | 文件解析 | 适用场景 |
|------|----------|----------|----------|----------|
| **A 路径：无材料** | 导入材料分析弹窗留空，直接关闭或点取消 | 本地小模型（llama-server 8848） | 不调用 parser | 小角色、快速创建、无需分析 |
| **B 路径：有材料** | 弹窗填写了任意内容（文件上传 **或** 文字粘贴），点击「开始分析」 | 外部 API 大模型 | 上传文件时先调 `wechat_parser.py` 结构化解析 | 大角色、真实聊天记录、需深度分析 |

**核心判断逻辑**（`_client.py`）：
```
has_material = bool(raw_material.strip())
if has_material and config.is_api_enabled():
    → 外部 API 大模型（路径B）
else:
    → 本地 llama-server 小模型（路径A）
```

**禁止行为：**
- 不得将无材料误判为路径B
- 不得将路径B降级为本地小模型（除非外部 API 未配置）
- 上传文件时**必须**先经 `wechat_parser.py` 解析，不可将原始文件文本直接发大模型

---

## 二、文件类型与解析器映射

| 文件扩展名 | 解析工具 | source_type |
|-----------|---------|-------------|
| `.txt` `.csv` `.json` `.html` `.htm` `.db` `.sqlite` | `wechat_parser.py` | `wechat` |
| 其他（含空扩展名） | `qq_parser.py` | `qq` |

- 扩展名由前端 `handleFileSelect` / `handleFileDrop` 保存至 `analyzeFile` 变量
- 实际解析器选择由后端 `skill_engine.run_parser()` 根据扩展名自动判断
- 前端通过 `source_type` 参数（`text/wechat/qq/social`）告知后端期望的格式类别

---

## 三、后端端点清单（角色创建相关）

| 端点 | 方法 | 功能 | 备注 |
|------|------|------|------|
| `POST /api/skills/intake` | POST | 三步向导创建空 Skill（花名→简介→性格） | 前端兼容端点，生成空白 memory/persona 模板 |
| `POST /api/skills/{slug}/import-file` | POST | 上传文件，调用 wechat_parser 解析 | 返回 `parsed_content` 供前端传分析用 |
| `POST /api/skills/{slug}/analyze-memory` | POST | 对原始材料做 memory + persona 分析 | **统一入口**，无论 A/B 路径都走此接口 |
| `POST /api/skills/{slug}/merge` | POST | 增量合并新材料（追加聊天记录） | |
| `POST /api/skills/{slug}/correction` | POST | 手动纠偏指定 memory/persona 内容 | |
| `POST /api/skills/{slug}/correct-llm` | POST | LLM 自动识别并应用纠偏 | |
| `DELETE /api/skills/{slug}` | DELETE | 删除整个 Skill 目录 | |
| `GET /api/skills/{slug}` | GET | 获取 Skill 详情（meta + memory + persona） | |
| `GET /api/skills` | GET | 列出所有 Skill | |
| `GET /api/skills/{slug}/versions` | GET | 列出历史版本（调用 version_manager.py） | |

---

## 四、数据文件结构（data/skills/{slug}/）

```
data/skills/{slug}/
├── meta.json           # 元数据（name, slug, version, source, profile, created_at, updated_at）
├── profile.md          # 用户填写的基础信息
├── memory.md           # 关系记忆（LLM 生成）
├── persona.md          # 人物性格（LLM 生成）
├── skill.md            # SKILL.md（由 skill_writer.py 生成，可选）
├── memories/
│   └── chats/          # 原始导入文件存档 + 解析输出 .analysis.md
└── sessions/           # 会话摘要文件（.md）
```

**meta.json 关键字段：**
```json
{
  "name": "花名",
  "slug": "xxx",
  "version": "v1",
  "source": "text | import",
  "profile": { "summary": "...", "personality": "..." },
  "created_at": "ISO时间",
  "updated_at": "ISO时间"
}
```

---

## 五、ex-skill 工具链使用规范

### 5.1 严禁修改的文件

以下目录**绝对不允许 Agent 修改**，只可调用其接口：

| 路径 | 原因 |
|------|------|
| `skills/create-ex/tools/wechat_parser.py` | ex-skill 解析工具原文件 |
| `skills/create-ex/tools/qq_parser.py` | 同上 |
| `skills/create-ex/tools/skill_writer.py` | 同上 |
| `skills/create-ex/tools/version_manager.py` | 同上 |
| `skills/create-ex/prompts/` | 原始 prompt 模板（仅作参考，不直接使用） |
| `skills/create-ex/` 整个目录 | ex-skill 工具链原文件，前后端只适配兼容，不得重构或改动 |

### 5.2 允许的集成方式

- **调用工具**：通过 `skill_engine.run_parser()`、`run_combine_skill()`、`run_backup()` 等封装函数调用
- **读取 prompt**：通过 `skill_engine._load_prompts()` 读取 `prompts/` 下的 .md 文件并适配
- **输出兼容**：工具的输出格式（stdout/stderr/文件）需在适配层正确解析

### 5.3 run_parser 调用示例

```python
result = run_parser(
    file_path="/path/to/chat.txt",
    target_name="花名",
    output_path="/path/to/output.analysis.md",
    source_type="wechat"   # 或 "qq"/"auto"
)
# result: {"tool": "wechat_parser.py", "returncode": 0, "stdout": "...", "stderr": "..."}
```

---

## 六、Prompt 拼接规范（skill_engine.py）

### 6.1 截断规则

| 内容 | 上限 | 备注 |
|------|------|------|
| `raw_material`（原始材料） | 3000 字 | 超过后截断并加 `[...材料已截断...]` |
| `analyzer_raw`（分析维度 prompt） | 1500 字 | 超过后截断 |
| `builder_raw`（输出格式 prompt） | 1500 字 | 超过后截断 |
| `existing_content`（增量合并现有内容） | 2000 字 | |
| `new_content`（增量合并新材料） | 2000 字 | |

### 6.2 Prompt 结构（通用模板）

```
你是情感回忆记录师，负责从聊天记录等材料中提取信息，生成结构化的关系记忆文档。

## 对象：{name}
## 已知信息：{context}
## 材料来源：{source_type}

## 分析维度参考
{analyzer_raw}

## 输出格式要求
{builder_raw}

## 原始材料
{raw_material}

---

请严格按上述格式输出，只输出 Markdown 内容，不要有任何其他文字。
所有 {placeholder} 必须替换为实际内容，信息不足时标注 [待补充]，不要虚构。
```

---

## 七、分析流程（统一入口）

```
用户点击「开始分析」
    │
    ├─ 无弹窗填写任何内容（路径A）
    │     → 直接关闭弹窗，角色以本地小模型运行
    │
    ├─ 有文件（analyzeFile 非空）
    │     ↓
    │   POST /api/skills/{slug}/import-file (FormData)
    │     ↓ 返回 parsed_content
    │   raw_material = parsed_content（wechat_parser.py 结构化输出）
    │     ↓
    │   has_material = True → 外部 API 大模型
    │   POST /api/skills/{slug}/analyze-memory {raw_material, source_type}
    │
    └─ 纯文字（textarea 非空）
          ↓
        raw_material = textarea 内容
        has_material = True → 外部 API 大模型
          ↓
        POST /api/skills/{slug}/analyze-memory {raw_material, source_type}
                               ↓
               build_memory_prompt() + build_persona_prompt()
               → 调用外部 API 大模型（或本地 llama-server，取决于 is_api_enabled）
                               ↓
               写入 memory.md + persona.md
               → 更新 meta.json updated_at
```

---

## 八、对话运行（Skill Run）系统提示词构造

```python
system_parts = [
    f"你是 {name}，一个基于真实聊天记录创建的虚拟角色。",
    f"简介：{profile.summary}",
    f"性格：{profile.personality}",
    "",
    "## 关系记忆",
    memory_content or "[暂无]",
    "",
    "## 人物性格",
    persona_content or "[暂无]",
]
# 追加最近 N 条会话摘要
if memory_context:
    system_parts += ["", "## 历史对话摘要", memory_context]
```

- 默认取最近 3 条 `sessions/*.md` 摘要
- 对话 ID 可选，不传则生成新对话
- 对话历史存储在 `data/conversations/{conv_id}.json`

---

## 九、已知 Bug 与待修复项（角色创建相关）

| 编号 | 问题 | 位置 | 影响 |
|------|------|------|------|
| P0-1 | `_client.py` 控制流错误，在线 API 分支 return 不可达 | `app/routers/_client.py:22-24` | 部分 Skill 可能错误使用本地模型 |
| P0-2 | `skill_engine.py` prompt 截断策略粗糙，截断点可能在段落中间 | `skill_engine.py:60,82,85` | 小模型理解失败，输出含 `{placeholder}` |
| P0-3 | `skill_writer.py` 生成的 SKILL.md 模板变量未替换 | `skills/create-ex/tools/skill_writer.py` | 对话时模型看到占位符文本 |
| P1-1 | 对话与 Skill 无关联，切换 Skill 无法恢复历史 | `app/routers/chat.py` + `skills_new.py` | 多 Skill 体验差 |
| P2-1 | 前端未实现流式输出，分析进度条无实时反馈 | `frontend/app.js` | 用户感知慢 |

---

## 十、通用开发约束（适用于所有角色创建相关修改）

1. **所有修改必须使用 SearchReplace 工具逐行操作**，禁止用脚本批量修改文件
2. **测试后必须执行清理脚本**（杀进程、释放端口），不得留下后台服务
3. **端口固定**：FastAPI=9090，llama-server=8848，不得修改
4. **commit/push 由用户手动操作**，Agent 只做本地文件修改
5. **禁止修改的文件**：`skills/create-ex/`、`plan.md`、`python/`、`llama/`、`models/`、`venv/`、`.git/`
6. **前端 JS 文件编码为 UTF-8**，避免出现中文乱码（DEVELOPER_REPORT.md 记录的已知问题）
