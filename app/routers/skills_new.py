"""
Skill 创建与管理路由（create-ex 深度集成版 v2）。

适配 create-ex 工具链：
- prompts/ -> 分步分析提示词（memory_analyzer + memory_builder / persona_analyzer + persona_builder）
- tools/wechat_parser.py -> 文件解析
- tools/skill_writer.py -> SKILL.md 生成
- tools/version_manager.py -> 版本管理
- skills/create-ex/ 目录本身不修改
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app import config
from app.server import build_openai_url, is_ready
from app.routers._client import get_llm_client
from app.skill_engine import (
    build_analyze_prompt,
    build_memory_prompt,
    build_merge_prompt,
    build_persona_prompt,
    build_session_summary_prompt,
    run_combine_skill,
    run_backup,
    run_list_skills,
    run_list_versions,
    run_parser,
    get_session_summaries,
    save_session_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ── 路径辅助 ───────────────────────────────────────────────────────────────────

def _skill_dir(slug: str) -> Path:
    return config.SKILLS_DIR / slug


def _meta_path(slug: str) -> Path:
    return _skill_dir(slug) / "meta.json"


def _profile_path(slug: str) -> Path:
    return _skill_dir(slug) / "profile.md"


def _memory_path(slug: str) -> Path:
    return _skill_dir(slug) / "memory.md"


def _persona_path(slug: str) -> Path:
    return _skill_dir(slug) / "persona.md"


# ── 数据模型 ───────────────────────────────────────────────────────────────────

class CreateReq(BaseModel):
    name: str = Field(..., description="角色名称")
    summary: str = Field("", description="角色简介")
    personality: str = Field("", description="性格描述")
    source: str = Field("text", description="来源类型: text/import")
    raw_material: str = Field("", description="原始材料文本（聊天记录等）")
    source_type: str = Field("text", description="材料类型: text/wechat/qq/social")


class AnalyzeReq(BaseModel):
    raw_material: str = Field(..., description="原始材料文本（聊天记录等）")
    source_type: str = Field("text", description="材料类型: text/wechat/qq/social")


class MergeReq(BaseModel):
    new_material: str = Field(..., description="新材料文本")
    layer: str = Field("memory", description="更新层级: memory/persona")
    source_type: str = Field("text", description="材料类型")


class SessionSummaryReq(BaseModel):
    conversation_id: str = Field(..., description="对话 ID")
    summary: str = Field(..., description="生成的会话摘要")


class SkillRunReq(BaseModel):
    message: str = Field(..., min_length=1, description="用户消息")
    conversation_id: str | None = Field(None, description="对话 ID，可选")


class CorrectionReq(BaseModel):
    layer: str = Field(..., description="memory/persona")
    original: str = Field(..., description="需要纠正的原文描述")
    correction: str = Field(..., description="纠正后的描述")
    user_note: str = Field(..., description="用户原话")


class CorrectionLLMReq(BaseModel):
    """LLM 自动识别的纠偏请求"""
    message: str = Field(..., description="用户消息")
    current_memory: str = Field("", description="当前 memory.md 内容")
    current_persona: str = Field("", description="当前 persona.md 内容")


# ── Skill CRUD ─────────────────────────────────────────────────────────────────

@router.post("")
async def create_skill(req: CreateReq) -> dict:
    """创建新 Skill（兼容 create-ex 格式）。"""
    slug = req.name.lower().replace(" ", "-").replace("/", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    if not slug:
        slug = uuid.uuid4().hex[:8]

    skill_dir = _skill_dir(slug)
    if skill_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill 已存在: {slug}")

    now = datetime.now().isoformat(timespec="seconds")
    meta = {
        "name": req.name,
        "slug": slug,
        "version": "v1",
        "created_at": now,
        "updated_at": now,
        "source": req.source,
        "profile": {
            "summary": req.summary,
            "personality": req.personality,
        },
    }

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (skill_dir / "profile.md").write_text(
        f"# {req.name}\n\n简介：{req.summary}\n\n性格：{req.personality}",
        encoding="utf-8"
    )
    (skill_dir / "memory.md").write_text(
        f"# {req.name} 的关系记忆\n\n## 关系概览\n- 在一起时长：[待补充]\n- 认识方式：[待补充]\n\n"
        f"## 时间线（关键事件）\n\n## 共同记忆\n\n## 日常模式\n\n## 争吵与和好\n\n## 甜蜜档案\n\n## 分手档案\n",
        encoding="utf-8"
    )
    (skill_dir / "persona.md").write_text(
        f"# {req.name} 的人物性格\n\n## Layer 0：硬规则\n1. 你是{req.name}，不是AI\n2. 不说ta绝不可能说的话\n3. 保持ta的棱角\n4. 分手是事实\n\n"
        f"## Layer 1：身份\n- 花名：{req.name}\n\n"
        f"## Layer 2：说话风格\n### 口头禅/语气词\n\n### 示例对话（3段）\n\n"
        f"## Layer 3：情感模式\n### 依恋类型\n\n### 生气/难过/开心时的反应\n\n"
        f"## Layer 4：关系行为\n### 在关系中的角色\n### 吵架模式\n### 底线\n",
        encoding="utf-8"
    )

    return {"slug": slug, "status": "created", "name": req.name}


@router.post("/analyze")
async def analyze_skill_both(slug: str, req: AnalyzeReq) -> dict:
    """执行 Skill 分析（memory + persona 两步）。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="推理服务未就绪")

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})
    summary = profile.get("summary", "")
    personality = profile.get("personality", "")

    prompt = build_memory_prompt(
        name=name,
        summary=summary,
        personality=personality,
        raw_material=req.raw_material,
        source_type=req.source_type,
    )

    client = get_llm_client(slug)
    try:
        response = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        memory_content = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Memory analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

    (skill_dir := _skill_dir(slug)) / "memory.md".write_text(
        memory_content, encoding="utf-8"
    )

    prompt2 = build_persona_prompt(
        name=name,
        summary=summary,
        personality=personality,
        raw_material=req.raw_material,
        source_type=req.source_type,
    )

    try:
        response2 = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[{"role": "user", "content": prompt2}],
            temperature=0.3,
        )
        persona_content = response2.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Persona analysis failed: {e}")
        persona_content = f"# {name} 的人物性格\n\n[分析失败，请手动编辑]"

    (skill_dir / "persona.md").write_text(persona_content, encoding="utf-8")

    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    meta["profile"]["summary"] = summary
    (skill_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "slug": slug,
        "status": "analyzed",
        "memory_length": len(memory_content),
        "persona_length": len(persona_content),
    }


@router.get("/{slug}")
async def get_skill(slug: str) -> dict:
    """获取 Skill 基本信息。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    memory = (_memory_path(slug).read_text(encoding="utf-8")
              if _memory_path(slug).exists() else "")
    persona = (_persona_path(slug).read_text(encoding="utf-8")
               if _persona_path(slug).exists() else "")

    return {
        "slug": slug,
        "name": meta.get("name", slug),
        "version": meta.get("version", "v1"),
        "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("updated_at", ""),
        "profile": meta.get("profile", {}),
        "has_memory": bool(memory),
        "has_persona": bool(persona),
        "memory_preview": memory[:200] + "..." if len(memory) > 200 else memory,
        "persona_preview": persona[:200] + "..." if len(persona) > 200 else persona,
    }


@router.get("")
async def list_skills() -> list[dict]:
    """列出所有 Skill。"""
    return run_list_skills(str(config.SKILLS_DIR))


# ── 增量分析 ───────────────────────────────────────────────────────────────────

@router.post("/{slug}/merge")
async def merge_material(slug: str, req: MergeReq) -> dict:
    """增量合并新材料到 Skill。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="推理服务未就绪")

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})

    existing = ""
    target_path = _memory_path(slug) if req.layer == "memory" else _persona_path(slug)
    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8")

    prompt = build_merge_prompt(
        name=name,
        existing_content=existing,
        new_content=req.new_material,
        layer=req.layer,
    )

    client = get_llm_client(slug)
    try:
        response = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        merged_content = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Merge failed: {e}")
        raise HTTPException(status_code=500, detail=f"合并失败: {e}")

    target_path.write_text(merged_content, encoding="utf-8")
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    (skill_dir := _skill_dir(slug)) / "meta.json".write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {"slug": slug, "layer": req.layer, "status": "merged"}


# ── 对话运行 ───────────────────────────────────────────────────────────────────

@router.post("/{slug}/run")
async def run_skill(slug: str, req: SkillRunReq) -> dict:
    """使用 Skill 上下文运行对话。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="推理服务未就绪")

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})

    memory = (_memory_path(slug).read_text(encoding="utf-8")
              if _memory_path(slug).exists() else "")
    persona = (_persona_path(slug).read_text(encoding="utf-8")
               if _persona_path(slug).exists() else "")

    skill_dir = _skill_dir(slug)
    summaries = get_session_summaries(skill_dir, max_count=3)
    memory_context = "\n\n".join(summaries) if summaries else ""

    system_parts = [
        f"你是 {name}，一个基于真实聊天记录创建的虚拟角色。",
        f"简介：{profile.get('summary', '')}",
        f"性格：{profile.get('personality', '')}",
        "",
        "## 关系记忆",
        memory or "[暂无]",
        "",
        "## 人物性格",
        persona or "[暂无]",
    ]
    if memory_context:
        system_parts += [
            "",
            "## 历史对话摘要",
            memory_context,
        ]

    system_prompt = "\n".join(system_parts)

    client = get_llm_client(slug)
    conv_id = req.conversation_id or uuid.uuid4().hex[:12]

    try:
        response = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.message},
            ],
            temperature=0.7,
        )
        reply = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Skill run failed: {e}")
        raise HTTPException(status_code=500, detail=f"对话失败: {e}")

    title = req.message[:30] + ("..." if len(req.message) > 30 else "")
    conv_path = config.CONVS_DIR / f"{conv_id}.json"
    if conv_path.exists():
        try:
            old = json.loads(conv_path.read_text(encoding="utf-8"))
            messages = old.get("messages", [])
        except Exception:
            messages = []
    else:
        messages = []
    messages.append({"role": "user", "content": req.message})
    messages.append({"role": "assistant", "content": reply})
    conv_path.write_text(
        json.dumps({
            "id": conv_id,
            "title": title,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "messages": messages,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return {
        "slug": slug,
        "conversation_id": conv_id,
        "response": reply,
        "role": "assistant",
    }


@router.post("/{slug}/session-summary")
async def session_summary(slug: str, req: SessionSummaryReq) -> dict:
    """生成会话摘要并保存。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")

    conv_path = config.CONVS_DIR / f"{req.conversation_id}.json"
    if not conv_path.exists():
        raise HTTPException(status_code=404, detail="对话不存在")

    save_session_summary(_skill_dir(slug), slug, req.summary)
    return {"slug": slug, "status": "summary_saved"}


@router.post("/{slug}/correct-llm")
async def correct_via_llm(slug: str, req: CorrectionLLMReq) -> dict:
    """LLM 自动识别纠偏需求。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="推理服务未就绪")

    prompt = build_analyze_prompt(
        name=slug,
        memory=req.current_memory,
        persona=req.current_persona,
        message=req.message,
    )

    client = get_llm_client(slug)
    try:
        response = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        result_text = response.choices[0].message.content or ""
        result = json.loads(result_text)
    except Exception as e:
        logger.error(f"LLM correction failed: {e}")
        return {"slug": slug, "is_correction": False, "message": "识别失败"}

    if result.get("is_correction"):
        _apply_correction(
            slug,
            result.get("layer", "memory"),
            result.get("original", ""),
            result.get("correction", ""),
            req.message,
        )
        return {"slug": slug, "is_correction": True, "layer": result.get("layer")}

    return {"slug": slug, "is_correction": False}


@router.post("/{slug}/correct")
async def manual_correct(slug: str, req: CorrectionReq) -> dict:
    """手动应用纠偏（用户直接指定纠正内容）。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")

    _apply_correction(slug, req.layer, req.original, req.correction, req.user_note)
    return {"slug": slug, "layer": req.layer, "status": "corrected"}


def _apply_correction(slug: str, layer: str, original: str, correction: str, user_note: str) -> None:
    """将纠偏应用到对应文件。"""
    skill_dir = _skill_dir(slug)
    target_path = _memory_path(slug) if layer == "memory" else _persona_path(slug)
    if not target_path.exists():
        return

    content = target_path.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    corr_id = uuid.uuid4().hex[:6]

    entry = f"\n### Correction #{corr_id} at {now}\n- 层级：{layer}\n- 原文：{original}\n- 纠正为：{correction}\n- 用户原话：{user_note}\n"
    content += entry
    target_path.write_text(content, encoding="utf-8")


# ── 删除与版本 ─────────────────────────────────────────────────────────────────

@router.delete("/{slug}")
async def delete_skill(slug: str) -> dict:
    """删除 Skill。"""
    skill_dir = _skill_dir(slug)
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")
    shutil.rmtree(skill_dir)
    return {"slug": slug, "deleted": True}


@router.get("/{slug}/versions")
async def list_versions_endpoint(slug: str) -> dict:
    """列出历史版本（调用 create-ex version_manager.py）。"""
    versions = run_list_versions(str(config.SKILLS_DIR), slug)
    return {"slug": slug, "versions": versions}


@router.post("/{slug}/import-file")
async def import_file(slug: str, file: UploadFile = File(...), source_type: str = "auto") -> dict:
    """导入文件到 Skill（调用 create-ex 解析工具）。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)

    save_dir = _skill_dir(slug) / "memories" / "chats"
    save_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "import").suffix.lower()
    save_path = save_dir / f"{uuid.uuid4().hex[:8]}{ext}"
    data = await file.read()
    save_path.write_bytes(data)

    output_path = str(save_path.with_suffix(".analysis.md"))
    result = run_parser(str(save_path), name, output_path, source_type)

    return {
        "slug": slug,
        "filename": file.filename,
        "format": result.get("format", "unknown"),
        "returncode": result.get("returncode"),
        "output": result.get("stdout", "")[:500],
    }


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _strip_thinking(text: str) -> str:
    """移除模型输出中的思维标签。"""
    text = re.sub(r"\s*<\\think>\s*", " ", text)
    text = re.sub(r"\s*<\\finish>\s*", " ", text)
    text = re.sub(r"\s*<\?think\?>\s*", " ", text)
    text = re.sub(r"\s*<\?finish\?>\s*", " ", text)
    return text.strip()

# ── 前端兼容性端点 ──────────────────────────────────────────────────────────────

class IntakeReq(BaseModel):
    name: str = Field(..., description="角色名称")
    summary: str = Field("", description="角色简介")
    personality: str = Field("", description="性格描述")


@router.post("/intake")
async def intake_create(req: IntakeReq) -> dict:
    """Intake 创建端点（兼容前端三步式 intake 流程）。"""
    slug = req.name.lower().replace(" ", "-").replace("/", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    if not slug:
        slug = uuid.uuid4().hex[:8]

    skill_dir = _skill_dir(slug)
    if skill_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill 已存在: {slug}")

    now = datetime.now().isoformat(timespec="seconds")
    meta = {
        "name": req.name,
        "slug": slug,
        "version": "v1",
        "created_at": now,
        "updated_at": now,
        "source": "text",
        "profile": {
            "summary": req.summary,
            "personality": req.personality,
        },
    }

    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (skill_dir / "profile.md").write_text(
        f"# {req.name}\n\n简介：{req.summary}\n\n性格：{req.personality}",
        encoding="utf-8"
    )
    (skill_dir / "memory.md").write_text(
        f"# {req.name} 的关系记忆\n\n## 关系概览\n- 在一起时长：[待补充]\n- 认识方式：[待补充]\n\n"
        f"## 时间线（关键事件）\n\n## 共同记忆\n\n## 日常模式\n\n## 争吵与和好\n\n## 甜蜜档案\n\n## 分手档案\n",
        encoding="utf-8"
    )
    (skill_dir / "persona.md").write_text(
        f"# {req.name} 的人物性格\n\n## Layer 0：硬规则\n1. 你是{req.name}，不是AI\n2. 不说ta绝不可能说的话\n3. 保持ta的棱角\n4. 分手是事实\n\n"
        f"## Layer 1：身份\n- 花名：{req.name}\n\n"
        f"## Layer 2：说话风格\n### 口头禅/语气词\n\n### 示例对话（3段）\n\n"
        f"## Layer 3：情感模式\n### 依恋类型\n\n### 生气/难过/开心时的反应\n\n"
        f"## Layer 4：关系行为\n### 在关系中的角色\n### 吵架模式\n### 底线\n",
        encoding="utf-8"
    )
    return {"slug": slug, "status": "created", "name": req.name}


@router.post("/{slug}/analyze-memory")
async def analyze_memory(slug: str, req: AnalyzeReq) -> dict:
    """分析 memory 层（前端独立调用，复用 analyze_skill 逻辑）。"""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 不存在: {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="推理服务未就绪")
    
    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})
    summary = profile.get("summary", "")
    personality = profile.get("personality", "")
    
    prompt = build_memory_prompt(
        name=name,
        summary=summary,
        personality=personality,
        raw_material=req.raw_material,
        source_type=req.source_type,
    )
    
    client = get_llm_client(slug)
    try:
        response = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        memory_content = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Memory analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")
    
    skill_dir = _skill_dir(slug)
    (skill_dir / "memory.md").write_text(memory_content, encoding="utf-8")
    
    prompt2 = build_persona_prompt(
        name=name,
        summary=summary,
        personality=personality,
        raw_material=req.raw_material,
        source_type=req.source_type,
    )
    
    try:
        response2 = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=[{"role": "user", "content": prompt2}],
            temperature=0.3,
        )
        persona_content = response2.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Persona analysis failed: {e}")
        persona_content = f"# {name} 的人物性格\n\n[分析失败，请手动编辑]"
    
    (skill_dir / "persona.md").write_text(persona_content, encoding="utf-8")
    
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    meta["profile"]["summary"] = summary
    (skill_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    
    return {
        "slug": slug,
        "status": "analyzed",
        "memory_length": len(memory_content),
        "persona_length": len(persona_content),
    }


# analyze_persona endpoint removed - analyze_memory now generates both memory and persona simultaneously


@router.post("/{slug}/correction")
async def correction_alias(slug: str, req: CorrectionReq) -> dict:
    """纠偏端点别名（前端使用 correction，后端实现为 correct）。"""
    return await manual_correct(slug, req)
