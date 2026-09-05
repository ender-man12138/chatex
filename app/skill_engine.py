"""
Skill 引擎 — create-ex 工具适配层（深度集成版）。

对接 skills/create-ex/prompts/ 下的各分析提示词：
- intake.md → 信息录入引导（前端向导使用）
- memory_analyzer.md + memory_builder.md → 关系记忆分析
- persona_analyzer.md + persona_builder.md → 人物性格分析
- merger.md → 增量材料合并策略
- correction_handler.md → 纠偏处理流程
- session_summary.md → 会话摘要格式
- scene_director.md → 多前任场景模式（预留）
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_CREATE_EX_DIR = Path(__file__).resolve().parent.parent / "skills" / "create-ex"
_PROMPTS_DIR = _CREATE_EX_DIR / "prompts"
_TOOLS_DIR = _CREATE_EX_DIR / "tools"
_prompts_cache = None


def _load_prompts() -> dict[str, str]:
    global _prompts_cache
    if _prompts_cache is not None:
        return _prompts_cache
    cache: dict[str, str] = {}
    if _PROMPTS_DIR.exists():
        for f in sorted(_PROMPTS_DIR.glob("*.md")):
            cache[f.stem] = f.read_text(encoding="utf-8")
    _prompts_cache = cache
    return cache


def get_prompt(name: str) -> str:
    """获取原始 create-ex prompt（供调试或高级用法）。"""
    return _load_prompts().get(name, "")


def list_prompts() -> list[str]:
    return list(_load_prompts().keys())


# ── 小模型友好型提示词构建器 ───────────────────────────────────────────────────

def _combine_prompts(analyzer_key: str, builder_key: str,
                     name: str, summary: str = "", personality: str = "",
                     raw_material: str = "", source_type: str = "text",
                     existing_content: str = "") -> str:
    """将 analyzer + builder prompt 合并为一条小模型友好的提示词。"""
    if len(raw_material) > 3000:
        raw_material = raw_material[:3000] + "\n[...材料已截断...]"

    info_parts = []
    if summary:
        info_parts.append(f"简介：{summary}")
    if personality:
        info_parts.append(f"性格标签：{personality}")

    context = "；".join(info_parts) if info_parts else "（暂无额外信息）"

    analyzer_raw = _load_prompts().get(analyzer_key, "")
    builder_raw = _load_prompts().get(builder_key, "")

    lines = [
        "你是情感回忆记录师，负责从聊天记录等材料中提取信息，生成结构化的关系记忆文档。",
        "",
        f"## 对象：{name}",
        f"## 已知信息：{context}",
        f"## 材料来源：{source_type}",
        "",
        "## 分析维度参考",
        analyzer_raw[:1500] if len(analyzer_raw) > 1500 else analyzer_raw,
        "",
        "## 输出格式要求",
        builder_raw[:1500] if len(builder_raw) > 1500 else builder_raw,
        "",
        "## 原始材料",
        raw_material,
        "",
        "---",
        "",
        "请严格按上述格式输出，只输出 Markdown 内容，不要有任何其他文字。",
        "所有 {placeholder} 必须替换为实际内容，信息不足时标注 [待补充]，不要虚构。",
    ]
    return "\n".join(lines)


def build_memory_prompt(name: str, summary: str = "", personality: str = "",
                        raw_material: str = "", source_type: str = "text") -> str:
    """构建关系记忆分析提示词（memory_analyzer + memory_builder 合并）。"""
    return _combine_prompts("memory_analyzer", "memory_builder",
                            name, summary, personality, raw_material, source_type)


def build_persona_prompt(name: str, summary: str = "", personality: str = "",
                         raw_material: str = "", source_type: str = "text") -> str:
    """构建人物性格分析提示词（persona_analyzer + persona_builder 合并）。"""
    return _combine_prompts("persona_analyzer", "persona_builder",
                            name, summary, personality, raw_material, source_type)


def build_merge_prompt(name: str, existing_content: str, new_content: str,
                       layer: str = "memory") -> str:
    """构建增量合并提示词（merger 策略 + 对应 builder）。"""
    builder_key = "memory_builder" if layer == "memory" else "persona_builder"
    builder_raw = _load_prompts().get(builder_key, "")
    merger_raw = _load_prompts().get("merger", "")

    lines = [
        "你是关系记忆的增量更新助手。用户追加了新的聊天材料，你需要将新信息合并到现有文档中。",
        "",
        f"## 对象：{name}",
        f"## 更新层级：{layer}",
        "",
        "## 合并原则",
        merger_raw[:1000] if len(merger_raw) > 1000 else merger_raw,
        "",
        "## 目标输出格式",
        builder_raw[:1000] if len(builder_raw) > 1000 else builder_raw,
        "",
        "## 现有内容",
        existing_content[:2000] if len(existing_content) > 2000 else existing_content,
        "",
        "## 新增材料",
        new_content[:2000] if len(new_content) > 2000 else new_content,
        "",
        "---",
        "",
        "请输出合并后的完整新文档（只输出 Markdown，不要其他文字）。",
        "在新增内容前标注：<!-- [追加于 YYYY-MM-DD，来源：新导入材料] -->",
    ]
    return "\n".join(lines)


def build_session_summary_prompt(name: str, rounds: int, messages: list[dict]) -> str:
    """构建会话摘要提示词（session_summary 格式）。"""
    summary_proto = _load_prompts().get("session_summary", "")
    # 提取格式部分
    format_match = re.search(r"```markdown\s*\n(.*?)\n\s*```", summary_proto, re.DOTALL)
    template = format_match.group(1) if format_match else summary_proto[:600]

    full_text = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages[-20:])
    return (
        f"请为以下对话生成会话摘要。\n\n"
        f"格式要求：\n{template}\n\n"
        f"日期：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"前任：{name}\n"
        f"轮次：{rounds}\n\n"
        f"对话记录：\n{full_text}"
    )


# ── 旧接口兼容（保留 build_analyze_prompt 以防其他地方调用）────────────────────

def build_analyze_prompt(name: str, summary: str = "", personality: str = "",
                         raw_material: str = "", source_type: str = "text") -> str:
    """兼容旧版单步分析提示词。新版本建议使用 build_memory_prompt + build_persona_prompt。"""
    if len(raw_material) > 2500:
        raw_material = raw_material[:2500] + "\n[...截断...]"
    lines = [
        f"你是情感回忆记录师。根据以下信息生成 Relationship Memory + Persona。",
        f"## 前任：{name}",
    ]
    if summary:
        lines.append(f"简介：{summary}")
    if personality:
        lines.append(f"性格：{personality}")
    lines += [
        f"材料来源：{source_type}",
        f"## 原始材料\n{raw_material}",
        f"---",
        f"请按以下格式输出，只输出Markdown内容：",
        f"<!-- MEMORY -->",
        f"# {name} 的关系记忆",
        f"## 关系概览\n- 在一起时长：\n- 认识方式：",
        f"## 时间线（关键事件）",
        f"## 共同记忆\n### 常去的地方\n### Inside Jokes\n### 关键片段",
        f"## 日常模式\n## 争吵与和好\n## 甜蜜档案\n## 分手档案",
        f"<!-- PERSONA -->",
        f"# {name} 的人物性格",
        f"## Layer 0：硬规则\n1. 你是{name}，不是AI\n2. 不说ta绝不可能说的话\n3. 保持ta的棱角\n4. 分手是事实",
        f"## Layer 1：身份\n- 花名：{name}",
        f"## Layer 2：说话风格\n### 口头禅/语气词\n### 示例对话（3段）",
        f"## Layer 3：情感模式\n### 依恋类型\n### 生气/难过/开心时的反应",
        f"## Layer 4：关系行为\n### 在关系中的角色\n### 吵架模式\n### 底线",
        f"要求：基于材料不虚构，信息不足标[待补充]。",
    ]
    return "\n".join(lines)


# ── create-ex 工具调用 ─────────────────────────────────────────────────────────

def _run_tool(tool_name: str, args: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    script = _TOOLS_DIR / tool_name
    if not script.exists():
        return 1, "", f"工具不存在: {script}"
    try:
        r = subprocess.run([sys.executable, str(script)] + args,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=30, cwd=cwd)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def run_parser(file_path: str, target_name: str, output_path: str, source_type: str = "auto") -> dict:
    ext = Path(file_path).suffix.lower().lstrip(".")
    tool = "wechat_parser.py" if ext in ("txt", "csv", "json", "html", "htm", "db", "sqlite") else "qq_parser.py"
    rc, out, err = _run_tool(tool, ["--file", file_path, "--target", target_name,
                                     "--output", output_path, "--format", source_type], str(_TOOLS_DIR))
    return {"tool": tool, "returncode": rc, "stdout": out, "stderr": err}


def run_combine_skill(base_dir: str, slug: str) -> tuple[int, str, str]:
    return _run_tool("skill_writer.py", ["--action", "combine", "--base-dir", base_dir, "--slug", slug], base_dir)


def run_backup(base_dir: str, slug: str) -> str:
    rc, out, _ = _run_tool("version_manager.py", ["--action", "backup", "--base-dir", base_dir, "--slug", slug], base_dir)
    return out.strip() if rc == 0 else ""


def run_list_skills(base_dir: str) -> list[dict]:
    skills = []
    d = Path(base_dir)
    if d.exists():
        for s in sorted(d.iterdir()):
            m = s / "meta.json"
            if s.is_dir() and m.exists():
                try:
                    data = json.loads(m.read_text(encoding="utf-8"))
                    skill_md = s / "skill.md"
                    memory_md = s / "memory.md"
                    persona_md = s / "persona.md"
                    skills.append({
                        "slug": s.name, "name": data.get("name", s.name),
                        "version": data.get("version", "v0"),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "profile": data.get("profile", {}),
                        "source": data.get("source", "text"),
                        "has_skill": skill_md.exists(),
                        "has_memory": memory_md.exists(),
                        "has_persona": persona_md.exists(),
                    })
                except Exception:
                    pass
    return skills


def run_list_versions(base_dir: str, slug: str) -> list[str]:
    rc, out, _ = _run_tool("version_manager.py", ["--action", "list", "--base-dir", base_dir, "--slug", slug], base_dir)
    if rc != 0:
        return []
    return [m.group(1) for m in re.finditer(r"(\S+)", out)
            if m.group(1) not in ("历史版本", "个）：")]


def get_session_summaries(skill_dir: Path, max_count: int = 3) -> list[str]:
    d = skill_dir / "sessions"
    if not d.exists():
        return []
    files = sorted(d.glob("*.md"), reverse=True)[:max_count]
    return [f.read_text(encoding="utf-8") for f in files]


def save_session_summary(skill_dir: Path, slug: str, text: str) -> Path:
    d = skill_dir / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    p.write_text(text, encoding="utf-8")
    return p


__all__ = [
    "get_prompt", "list_prompts",
    "build_memory_prompt", "build_persona_prompt", "build_merge_prompt",
    "build_session_summary_prompt",
    "build_analyze_prompt",  # 兼容旧版
    "run_parser", "run_combine_skill", "run_backup",
    "run_list_skills", "run_list_versions",
    "get_session_summaries", "save_session_summary",
]
