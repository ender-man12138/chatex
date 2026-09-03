# ChatEx Agent Rules

## 测试完成后必须清理（最高优先级）

每次测试、修改完成后，**在给出反馈之前**，必须执行以下清理：

```powershell
# 1. 杀掉所有相关进程
Get-Process -Name python,pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name llama* -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. 等待端口释放
Start-Sleep -Seconds 2

# 3. 确认清理结果
netstat -ano | findstr "9090 9091 8848" | findstr LISTENING
Get-Process -Name python -ErrorAction SilentlyContinue
```

**如果有任何进程因权限问题杀不掉，直接告知用户需要手动关闭的 PID 列表，不要自己换端口继续跑。**

---

## 禁止行为

- **不得**因为端口被占用就自动换端口（9090/9091/9092...）继续运行
- **不得**在给出最终反馈前留下任何后台服务或 pywebview 窗口
- **不得**启动多个服务器实例叠加运行
- **不得**让用户在回复之前还要自己去关进程

---

## 启动流程规范

当需要启动服务测试时：

1. 先执行清理脚本（见上方）
2. 确认端口干净后，再启动 `main.py`
3. 测试完毕，立即再次执行清理脚本
4. 清理完毕后再输出反馈

---

## 端口约定

| 服务 | 端口 | 说明 |
|------|------|------|
| FastAPI / pywebview | 9090 | 主服务端口，固定不变 |
| llama-server | 8848 | 推理服务端口，固定不变 |

任何情况下不得修改这两个端口。如遇冲突，必须彻底清理后再启动。

---

## 禁止使用脚本批量修改代码和文件

**不得**使用 Python、PowerShell、Node.js 或其他任何脚本语言批量修改代码或文件。

- 所有文件修改必须使用 `Edit`（SearchReplace）工具逐个操作
- 不得通过 `RunCommand` 调用 Python/PowerShell/Node 等脚本来写入、替换或批量处理文件内容
- 即使用于诊断或调试，也不得用脚本直接修改源文件
- 涉及中文乱码等编码问题的修复，也必须逐行用 SearchReplace 手动替换

---

## Git 操作规范

- **提交（commit）与推送（push）由用户手动操作，Agent 禁止执行**
- **拉取（pull / fetch）是允许的**
- Agent 只负责修改本地文件，不负责版本控制操作

---

## 绝对禁止修改的文件与文件夹

以下文件/文件夹**绝对不允许 Agent 修改**，即使是为了"完善"也不行。
用户未明确说出"修改/改动/修复/重写"等动词前，不得触碰任何一个字。

| 路径 | 原因 |
|------|------|
| skills/create-ex/ | ex-skill 工具链原文件，前后端只适配兼容，不得重构或改动其本身 |
| plan.md | 项目方案文档，用户要求保留原样 |
| python/ | 内嵌 Python 运行时，LFS 跟踪 |
| llama/ | llama.cpp 二进制，LFS 跟踪 |
| models/ | GGUF 模型文件，LFS 跟踪 |
| venv/ | 开发虚拟环境 |
| .git/ | 版本控制元数据 |

**规则：没有用户明确说"修改、改动、修复、重写"等关键词，不要擅自动上述任何文件。**
**"完善""改进""优化"等模糊词汇也不代表允许修改，必须等用户明确指令。**