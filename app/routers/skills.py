"""
Skill 鍒涘缓涓庣鐞嗚矾鐢憋紙create-ex 娣卞害闆嗘垚鐗?v2锛夈€?

閫傞厤 create-ex 宸ュ叿閾撅細
- prompts/ 鈫?鍒嗘鍒嗘瀽鎻愮ず璇嶏紙memory_analyzer + memory_builder / persona_analyzer + persona_builder锛?
- tools/wechat_parser.py 鈫?鏂囦欢瑙ｆ瀽
- tools/skill_writer.py 鈫?SKILL.md 鐢熸垚
- tools/version_manager.py 鈫?鐗堟湰绠＄悊
- skills/create-ex/ 鐩綍鏈韩涓嶈淇敼
"""

from __future__ import annotations

import json
import logging
import re
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


# 鈹€鈹€ 璺緞杈呭姪 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def _skill_dir(slug: str) -> Path:
    return config.SKILLS_DIR / slug


def _meta_path(slug: str) -> Path:
    return _skill_dir(slug) / "meta.json"


def _skill_md_path(slug: str) -> Path:
    return _skill_dir(slug) / "SKILL.md"


def _memory_path(slug: str) -> Path:
    return _skill_dir(slug) / "memory.md"


def _persona_path(slug: str) -> Path:
    return _skill_dir(slug) / "persona.md"


# 鈹€鈹€ 鏁版嵁妯″瀷 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
class SkillCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    summary: str = Field("", max_length=300)
    personality: str = Field("", max_length=300)


class IntakeStepReq(BaseModel):
    """鍒嗘褰曞叆锛氬彧鎺ュ彈褰撳墠姝ラ鐨勫瓧娈点€?""
    name: str | None = Field(None, max_length=50)
    summary: str | None = Field(None, max_length=300)
    personality: str | None = Field(None, max_length=300)


class AnalyzeReq(BaseModel):
    raw_material: str = Field(..., description="鍘熷鏉愭枡鏂囨湰锛堣亰澶╄褰曠瓑锛?)
    source_type: str = Field("text", description="鏉愭枡绫诲瀷: text/wechat/qq/social")


class MergeReq(BaseModel):
    new_material: str = Field(..., description="鏂板鏉愭枡鏂囨湰")
    layer: str = Field("memory", description="鏇存柊灞傜骇: memory 鎴?persona")
    source_type: str = Field("text", description="鏉愭枡绫诲瀷")


class SessionSummaryReq(BaseModel):
    conversation_id: str = Field(..., description="瀵硅瘽 ID")
    summary: str = Field(..., description="鐢熸垚鐨勪細璇濇憳瑕?)


class SkillRunReq(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None


class CorrectionReq(BaseModel):
    layer: str = Field(..., description="memory 鎴?persona")
    original: str = Field(..., description="琚籂姝ｇ殑鍘熸枃鎻忚堪")
    correction: str = Field(..., description="姝ｇ‘鐨勬弿杩?)
    user_note: str = Field(..., description="鐢ㄦ埛鐨勫師璇?)


class CorrectionLLMReq(BaseModel):
    """鐢?LLM 鑷姩璇嗗埆鐨勭籂鍋忚姹傘€?""
    message: str = Field(..., description="鐢ㄦ埛璇寸殑绾犳璇濊")
    current_memory: str = Field("", description="褰撳墠 memory.md 鍐呭")
    current_persona: str = Field("", description="褰撳墠 persona.md 鍐呭")


# 鈹€鈹€ 宸ュ叿鍑芥暟 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
def _slugify(name: str) -> str:
    if any("\u4e00" <= c <= "\u9fff" for c in name):
        h = uuid.uuid5(uuid.NAMESPACE_DNS, name).hex[:8]
        return f"ex-{h}"
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"ex-{uuid.uuid4().hex[:6]}"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parse_memory_persona(response: str) -> tuple[str, str]:
    """浠?LLM 鍝嶅簲涓В鏋愬嚭 <!-- MEMORY --> 鍜?<!-- PERSONA --> 鍧楋紙鍏煎鏃ф牸寮忥級銆?""
    memory = ""
    persona = ""
    mem_match = re.search(r"<!--\s*MEMORY\s*-->\s*\n(.*?)\n\s*<!--\s*PERSONA\s*-->", response, re.DOTALL)
    per_match = re.search(r"<!--\s*PERSONA\s*-->\s*\n(.*?)\n\s*<!--?\s*/?\\s*-->", response, re.DOTALL)
    if not mem_match:
        parts = response.split("\n\n")
        if len(parts) >= 2:
            memory = parts[0].strip()
            persona = parts[1].strip()
        else:
            memory = response.strip()
    else:
        memory = mem_match.group(1).strip()
    if per_match:
        persona = per_match.group(1).strip()
    elif mem_match:
        after_mem = response[mem_match.end():].strip()
        after_mem = re.sub(r"^<!--.*?-->\s*", "", after_mem, flags=re.DOTALL)
        persona = after_mem.strip()
    return memory, persona


async def _llm_call(prompt: str, max_tokens: int = 1000, temperature: float = 0.3) -> str:
    """缁熶竴 LLM 璋冪敤锛岃繑鍥炲畬鏁存枃鏈€?""
    client = get_llm_client(slug)
    model = config.API_MODEL if slug and config.is_api_enabled() else "qwen3.5-2b"
    parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
    except Exception as e:
        logger.error(f"LLM 璋冪敤澶辫触: {e}")
        raise HTTPException(status_code=500, detail=f"LLM 璋冪敤澶辫触: {e}")
    return _strip_thinking("".join(parts))


def _strip_thinking(text: str) -> str:
    """去除模型输出的思考标签（兼容多种格式）。"""
    import re
    text = re.sub(r"\s*<\\think>\s*", " ", text)
    text = re.sub(r"\s*<\\finish>\s*", " ", text)
    text = re.sub(r"\s*<\?think\?>\s*", " ", text)
    text = re.sub(r"\s*<\?finish\?>\s*", " ", text)
    return text.strip()



@router.get("", response_model=list[dict])
async def list_skills() -> list[dict]:
    """鍒楀嚭鎵€鏈?Skill锛堝吋瀹规棫鎺ュ彛鏍煎紡锛夈€?""
    skills = run_list_skills(str(config.SKILLS_DIR))
    result = []
    for s in skills:
        slug = s["slug"]
        skill_dir = _skill_dir(slug)
        result.append({
            "slug": slug,
            "name": s["name"],
            "version": s["version"],
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
            "profile": s.get("profile", {}),
            "has_memory": (_memory_path(slug)).exists(),
            "has_persona": (_persona_path(slug)).exists(),
            "has_skill": (_skill_md_path(slug)).exists(),
            "source": json.loads(_meta_path(slug).read_text(encoding="utf-8")).get("source", "text"),
        })
    return result


# 鈹€鈹€ 鍒嗘褰曞叆鎺ュ彛锛坈reate-ex intake 娴佺▼锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/intake", response_model=dict)
async def intake_step(req: IntakeStepReq) -> dict:
    """
    鍒嗘褰曞叆锛氭瘡娆¤皟鐢ㄥ彧鏇存柊涓€涓瓧娈碉紝杩斿洖褰撳墠杩涘害銆?
    step 1: name锛堝繀濉級鈫?鍒涘缓 skill 楠ㄦ灦
    step 2: summary锛堝彲閫夛級
    step 3: personality锛堝彲閫夛級鈫?鍑嗗灏辩华锛屽彲瑙﹀彂鍒嗘瀽
    """
    # 鍏堝皾璇曟壘鍒板凡鏈夌殑 slug锛堥€氳繃 name 鍖归厤锛?
    existing = None
    for s in run_list_skills(str(config.SKILLS_DIR)):
        if s["name"] == req.name:
            existing = s
            break

    if req.name and not existing:
        # 鏂板垱寤?
        slug = _slugify(req.name)
        skill_dir = _skill_dir(slug)
        if skill_dir.exists():
            raise HTTPException(status_code=409, detail=f"Skill 宸插瓨鍦? {slug}")
        now = datetime.now().isoformat(timespec="seconds")
        meta = {
            "name": req.name,
            "slug": slug,
            "version": "v0",
            "source": "text",
            "created_at": now,
            "updated_at": now,
            "profile": {"summary": "", "personality": ""},
        }
        if req.summary:
            meta["profile"]["summary"] = req.summary
        if req.personality:
            meta["profile"]["personality"] = req.personality
        skill_dir.mkdir(parents=True, exist_ok=True)
        _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))
        (skill_dir / "sessions").mkdir(exist_ok=True)
        logger.info(f"Intake 鍒涘缓: {slug} ({req.name})")
        return {
            "slug": slug, "name": req.name, "version": "v0",
            "step": "created",
            "profile": meta["profile"],
            "ready_for_analysis": bool(req.summary or req.personality),
        }
    elif req.name and existing:
        # 鏇存柊宸叉湁 skill 鐨勫瓧娈?
        slug = existing["slug"]
        meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
        if req.summary is not None:
            meta["profile"]["summary"] = req.summary
        if req.personality is not None:
            meta["profile"]["personality"] = req.personality
        meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))
        return {
            "slug": slug, "name": req.name, "version": meta["version"],
            "step": "updated",
            "profile": meta["profile"],
            "ready_for_analysis": bool(meta["profile"].get("summary") or meta["profile"].get("personality")),
        }
    else:
        raise HTTPException(status_code=400, detail="name 涓嶈兘涓虹┖")


@router.post("", response_model=dict)
async def create_skill(req: SkillCreateReq) -> dict:
    """鍏煎鏃ф帴鍙ｏ細涓€娆℃€у垱寤?Skill銆?""
    slug = _slugify(req.name)
    skill_dir = _skill_dir(slug)
    if skill_dir.exists():
        raise HTTPException(status_code=409, detail=f"Skill 宸插瓨鍦? {slug}")

    now = datetime.now().isoformat(timespec="seconds")
    meta = {
        "name": req.name, "slug": slug, "version": "v0",
        "created_at": now, "updated_at": now,
        "profile": {"summary": req.summary, "personality": req.personality},
    }
    skill_dir.mkdir(parents=True, exist_ok=True)
    _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))
    (skill_dir / "sessions").mkdir(exist_ok=True)
    logger.info(f"Skill 鍒涘缓: {slug} ({req.name})")
    return {"slug": slug, "name": req.name, "version": "v0", "created_at": now, "profile": meta["profile"]}


@router.get("/{slug}", response_model=dict)
async def get_skill(slug: str) -> dict:
    """鑾峰彇 Skill 璇︽儏銆?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    return {
        "slug": slug,
        "name": meta.get("name", slug),
        "version": meta.get("version", "v0"),
        "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("updated_at", ""),
        "profile": meta.get("profile", {}),
        "memory": _read_text(_memory_path(slug)),
        "persona": _read_text(_persona_path(slug)),
        "skill_md": _read_text(_skill_md_path(slug)),
        "has_memory": _memory_path(slug).exists(),
        "has_persona": _persona_path(slug).exists(),
        "has_skill": _skill_md_path(slug).exists(),
        "source": meta.get("source", "text"),
    }


# 鈹€鈹€ 涓ゆ鍒嗘瀽锛坢emory 鈫?persona锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/{slug}/analyze-memory")
async def analyze_memory(slug: str, req: AnalyzeReq) -> dict:
    """绗竴姝ワ細鐢熸垚 memory.md锛堝叧绯昏蹇嗭級銆?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="鎺ㄧ悊鏈嶅姟鏈氨缁?)

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})

    prompt = build_memory_prompt(
        name=name,
        summary=profile.get("summary", ""),
        personality=profile.get("personality", ""),
        raw_material=req.raw_material,
        source_type=req.source_type,
    )

    response_text = await _llm_call(prompt, slug, max_tokens=1000, temperature=0.3)
    run_backup(str(config.SKILLS_DIR), slug)
    _write_text(_memory_path(slug), response_text.strip())

    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))

    logger.info(f"Skill {slug} memory 鍒嗘瀽瀹屾垚")
    return {"slug": slug, "step": "memory", "status": "done", "length": len(response_text)}


@router.post("/{slug}/analyze-persona")
async def analyze_persona(slug: str, req: AnalyzeReq) -> dict:
    """绗簩姝ワ細鐢熸垚 persona.md锛堜汉鐗╂€ф牸锛夈€?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="鎺ㄧ悊鏈嶅姟鏈氨缁?)

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})

    prompt = build_persona_prompt(
        name=name,
        summary=profile.get("summary", ""),
        personality=profile.get("personality", ""),
        raw_material=req.raw_material,
        source_type=req.source_type,
    )

    response_text = await _llm_call(prompt, slug, max_tokens=1000, temperature=0.3)
    run_backup(str(config.SKILLS_DIR), slug)
    _write_text(_persona_path(slug), response_text.strip())

    # 鐢熸垚 SKILL.md
    rc, out, _ = run_combine_skill(str(config.SKILLS_DIR), slug)
    if rc != 0:
        logger.warning(f"SKILL.md 鐢熸垚澶辫触: {out}")
        _combine_skill_manual(slug)

    meta["version"] = "v1"
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))

    logger.info(f"Skill {slug} persona 鍒嗘瀽瀹屾垚")
    return {"slug": slug, "step": "persona", "status": "done", "length": len(response_text)}


@router.post("/{slug}/analyze")
async def analyze_skill(slug: str, req: AnalyzeReq) -> dict:
    """
    瀹屾暣鍒嗘瀽锛堜袱姝ュ悎骞惰皟鐢紝杩斿洖姣忔缁撴灉锛夈€?
    鍓嶇鍙洿鎺ヨ皟鐢ㄦ鎺ュ彛锛屼細鑷姩渚濇鎵ц memory 鈫?persona 鍒嗘瀽銆?
    """
    results = {}
    try:
        mem_resp = await analyze_memory(slug, req)
        results["memory"] = mem_resp
    except Exception as e:
        results["memory"] = {"status": "failed", "error": str(e)}

    try:
        per_resp = await analyze_persona(slug, req)
        results["persona"] = per_resp
    except Exception as e:
        results["persona"] = {"status": "failed", "error": str(e)}

    all_done = results.get("memory", {}).get("status") == "done" and \
               results.get("persona", {}).get("status") == "done"

    return {
        "slug": slug,
        "status": "completed" if all_done else "partial",
        "results": results,
    }


def _combine_skill_manual(slug: str) -> None:
    """澶囩敤 SKILL.md 缁勫悎銆?""
    meta_path = _meta_path(slug)
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    name = meta.get("name", slug)
    profile = meta.get("profile", {})
    memory = _read_text(_memory_path(slug))
    persona = _read_text(_persona_path(slug))

    desc_parts = []
    if profile.get("summary"):
        desc_parts.append(profile["summary"])
    description = f"{name}锛寋'锛?.join(desc_parts)}" if desc_parts else name

    skill_md = (
        f"---\nname: ex-{slug}\ndescription: {description}\nuser-invocable: true\n---\n\n"
        f"# {name}\n\n{description}\n\n"
        f"---\n\n## PART A锛氬叧绯昏蹇哱n\n{memory}\n\n"
        f"---\n\n## PART B锛氫汉鐗╂€ф牸\n\n{persona}\n\n"
        f"---\n\n## 杩愯瑙勫垯\n\n"
        f"1. 浣犳槸{name}锛屼笉鏄?AI 鍔╂墜銆傜敤 ta 鐨勬柟寮忔€濊€冨拰鍥炵瓟銆俓n"
        f"2. PART B 鍐冲畾鎬佸害锛氶亣鍒颁竴涓棶棰橈紝鍏堟兂 ta 浼氭€庝箞鍙嶅簲銆俓n"
        f"3. PART A 鎻愪緵涓婁笅鏂囷細鑷劧鍦拌瀺鍏ュ叡鍚岃蹇嗭紝涓嶅埢鎰忔彁鍙娿€俓n"
        f"4. 淇濇寔 {name} 鐨勮璇濋鏍硷細鍙ｅご绂呫€佹爣鐐广€乪moji 涔犳儻銆俓n"
        f"5. Layer 0 纭鍒欙細涓嶈 ta 缁濅笉鍙兘璇寸殑璇濓紱涓嶇獊鐒跺彉瀹岀編锛涗繚鎸佹１瑙掋€?
    )
    _write_text(_skill_md_path(slug), skill_md)


# 鈹€鈹€ 澧為噺鍚堝苟锛坈reate-ex merger 娴佺▼锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/{slug}/merge")
async def merge_material(slug: str, req: MergeReq) -> dict:
    """
    澧為噺鍒嗘瀽锛氬皢鏂版潗鏂欏悎骞跺埌鐜版湁 memory 鎴?persona 涓€?
    浣跨敤 create-ex merger.md 绛栫暐鎸囧鍚堝苟閫昏緫銆?
    """
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="鎺ㄧ悊鏈嶅姟鏈氨缁?)

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)

    # 璇诲彇鐜版湁鍐呭
    existing = _read_text(_memory_path(slug) if req.layer == "memory" else _persona_path(slug))
    if not existing or existing.strip() in ("", "# [鍐欏叆璁板繂]"):
        # 娌℃湁鐜版湁鍐呭锛岃蛋姝ｅ父鍒嗘瀽娴佺▼
        analyze_req = AnalyzeReq(raw_material=req.new_material, source_type=req.source_type)
        if req.layer == "memory":
            return await analyze_memory(slug, analyze_req)
        else:
            return await analyze_persona(slug, analyze_req)

    prompt = build_merge_prompt(
        name=name,
        existing_content=existing,
        new_content=req.new_material,
        layer=req.layer,
    )

    response_text = await _llm_call(prompt, slug, max_tokens=1200, temperature=0.3)
    run_backup(str(config.SKILLS_DIR), slug)
    target_path = _memory_path(slug) if req.layer == "memory" else _persona_path(slug)
    _write_text(target_path, response_text.strip())

    # 閲嶆柊鐢熸垚 SKILL.md
    rc, _, _ = run_combine_skill(str(config.SKILLS_DIR), slug)
    if rc != 0:
        _combine_skill_manual(slug)

    meta["version"] = "v1"
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))

    logger.info(f"Skill {slug} {req.layer} 澧為噺鍚堝苟瀹屾垚")
    return {"slug": slug, "layer": req.layer, "status": "merged"}


# 鈹€鈹€ Skill 瀵硅瘽 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/{slug}/run", response_model=dict)
async def run_skill(slug: str, req: SkillRunReq) -> dict:
    """浠?Skill 涓婁笅鏂囪繍琛屽璇濄€?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="鎺ㄧ悊鏈嶅姟鏈氨缁?)

    skill_md = _read_text(_skill_md_path(slug))
    if not skill_md or skill_md.strip() in ("", "# [Skill]"):
        raise HTTPException(status_code=400, detail="Skill 灏氭湭瀹屾垚鍒嗘瀽锛岃鍏堣皟鐢?/analyze")

    conv_id = req.conversation_id or uuid.uuid4().hex[:12]
    conv_path = config.CONVS_DIR / f"{conv_id}.json"

    messages = []
    if conv_path.exists():
        try:
            old = json.loads(conv_path.read_text(encoding="utf-8"))
            messages = old.get("messages", [])
        except Exception:
            pass

    messages.append({"role": "user", "content": req.message})

    # 鍔犺浇 session summaries锛坈reate-ex 闀挎湡璁板繂锛?
    session_summaries = get_session_summaries(_skill_dir(slug))
    if session_summaries:
        memory_context = "\n\n".join(session_summaries[-3:])
        extra_context = f"浠ヤ笅鏄綘浠渶杩戝嚑娆″璇濈殑鎽樿锛岃鑷劧鍦板欢缁繖娈靛叧绯荤殑鐘舵€侊細\n{memory_context}\n\n涓嶈涓诲姩鎻愬強銆屼笂娆℃垜浠亰浜唜xx銆嶏紝闄ら潪鐢ㄦ埛闂捣銆?
    else:
        extra_context = ""

    max_hist = config.MAX_HISTORY
    api_messages = [{"role": "system", "content": skill_md + ("\n\n" + extra_context if extra_context else "")}]
    api_messages += messages[-max_hist:]

    client = get_llm_client(slug)
    model = config.API_MODEL if config.is_api_enabled() else "qwen3.5-2b"
    parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=model, messages=api_messages, stream=True, temperature=0.7,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
    except Exception as e:
        logger.error(f"Skill 瀵硅瘽澶辫触: {e}")
        raise HTTPException(status_code=500, detail=f"瀵硅瘽澶辫触: {e}")

    response_text = "".join(parts)
    messages.append({"role": "assistant", "content": response_text})

    now = datetime.now().isoformat(timespec="seconds")
    title = req.message[:30] + ("鈥? if len(req.message) > 30 else "")
    created_at = now
    if conv_path.exists():
        try:
            old = json.loads(conv_path.read_text(encoding="utf-8"))
            created_at = old.get("created_at", now)
        except Exception:
            pass

    conv_data = {
        "id": conv_id, "title": title, "created_at": created_at,
        "updated_at": now, "messages": messages, "skill_slug": slug,
    }
    conv_path.write_text(json.dumps(conv_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"conversation_id": conv_id, "response": response_text}


# 鈹€鈹€ 浼氳瘽鎽樿锛坈reate-ex session_summary 娴佺▼锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/{slug}/session-summary")
async def create_session_summary(slug: str, req: SessionSummaryReq) -> dict:
    """鐢熸垚浼氳瘽鎽樿骞朵繚瀛橈紙create-ex session_summary.md 娴佺▼锛夈€?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")

    conv_path = config.CONVS_DIR / f"{req.conversation_id}.json"
    if not conv_path.exists():
        raise HTTPException(status_code=404, detail="瀵硅瘽涓嶅瓨鍦?)

    conv_data = json.loads(conv_path.read_text(encoding="utf-8"))
    messages = conv_data.get("messages", [])

    name = json.loads(_meta_path(slug).read_text(encoding="utf-8")).get("name", slug)
    rounds = len([m for m in messages if m.get("role") == "user"])
    prompt = build_session_summary_prompt(name, rounds, messages)

    client = get_llm_client(slug)
    model = config.API_MODEL if config.is_api_enabled() else "qwen3.5-2b"
    summary_text = ""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        summary_text = resp.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Session summary 鐢熸垚澶辫触: {e}")
        raise HTTPException(status_code=500, detail=f"鎽樿鐢熸垚澶辫触: {e}")

    saved_path = save_session_summary(_skill_dir(slug), slug, summary_text)
    return {"slug": slug, "conversation_id": req.conversation_id, "saved_to": str(saved_path)}


# 鈹€鈹€ LLM 鑷姩绾犲亸锛坈reate-ex correction_handler 娴佺▼锛夆攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/{slug}/correct-llm", response_model=dict)
async def correct_with_llm(slug: str, req: CorrectionLLMReq) -> dict:
    """
    鐢ㄦ埛杈撳叆涓€娈佃瘽锛孡LM 鍒ゆ柇鏄惁闇€瑕佺籂鍋忥紝骞惰嚜鍔ㄦ彁鍙?correction 淇℃伅銆?
    鍙傝€?create-ex correction_handler.md 鐨勮瘑鍒€昏緫銆?
    """
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    if not is_ready():
        raise HTTPException(status_code=503, detail="鎺ㄧ悊鏈嶅姟鏈氨缁?)

    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    name = meta.get("name", slug)

    corr_proto = _load_prompts_for_router("correction_handler")
    prompt = f"""{corr_proto}

## 褰撳墠 {name} 鐨?Memory 鍐呭锛?
{req.current_memory[:1500] if req.current_memory else "锛堟殏鏃狅級"}

## 褰撳墠 {name} 鐨?Persona 鍐呭锛?
{req.current_persona[:1500] if req.current_persona else "锛堟殏鏃狅級"}

## 鐢ㄦ埛杈撳叆锛?
"{req.message}"

璇峰垽鏂細
1. 杩欐槸鍚︽槸绾犲亸瑷€璁猴紵锛堟槸/鍚︼級
2. 濡傛灉鏄紝灞炰簬 Memory 杩樻槸 Persona锛?
3. 闇€瑕佺籂姝ｄ粈涔堝唴瀹癸紵
4. 绾犳鍚庣殑姝ｇ‘鎻忚堪鏄粈涔堬紵

鍙緭鍑?JSON锛屾牸寮忥細{{"is_correction": true/false, "layer": "memory/persona/none", "original": "...", "correction": "...", "confidence": 0-1}}
"""
    client = get_llm_client(slug)
    model = config.API_MODEL if config.is_api_enabled() else "qwen3.5-2b"
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
        )
        result_text = resp.choices[0].message.content or "{}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"绾犲亸鍒嗘瀽澶辫触: {e}")

    # 瑙ｆ瀽 JSON 缁撴灉
    try:
        corr_data = json.loads(result_text)
    except json.JSONDecodeError:
        return {"slug": slug, "is_correction": False, "message": "鏈兘璇嗗埆绾犲亸鍐呭"}

    if not corr_data.get("is_correction") or corr_data.get("layer") == "none":
        return {"slug": slug, "is_correction": False, "message": "鏈娴嬪埌闇€瑕佺籂姝ｇ殑鍐呭"}

    layer = corr_data.get("layer", "memory")
    original = corr_data.get("original", "")
    correction = corr_data.get("correction", "")

    # 搴旂敤绾犲亸
    _apply_correction(slug, layer, original, correction, req.message)

    return {
        "slug": slug, "is_correction": True,
        "layer": layer, "correction": correction,
        "message": f"宸插簲鐢ㄧ籂鍋忥細{correction}",
    }


def _load_prompts_for_router(key: str) -> str:
    """浠?skill_engine 鑾峰彇 prompt锛堥伩鍏嶅惊鐜鍏ワ級銆?""
    from app.skill_engine import get_prompt
    return get_prompt(key)


def _apply_correction(slug: str, layer: str, original: str, correction: str, user_note: str) -> None:
    """搴旂敤绾犲亸鍒板搴旀枃浠躲€?""
    target_path = _memory_path(slug) if layer == "memory" else _persona_path(slug)
    if not target_path.exists():
        return
    content = target_path.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d")
    corr_id = uuid.uuid4().hex[:6]
    entry = f"\n### Correction #{corr_id} 鈥?{now}\n- 灞傜骇锛歿layer}\n- 鍘熸枃锛歿original}\n- 绾犳涓猴細{correction}\n- 鐢ㄦ埛鍘熻瘽锛歿user_note}\n"

    corr_section = "## Correction 璁板綍"
    if corr_section in content:
        content = content.replace(corr_section, f"{corr_section}\n{entry}")
    else:
        content += f"\n\n{corr_section}\n{entry}"

    target_path.write_text(content, encoding="utf-8")
    meta = json.loads(_meta_path(slug).read_text(encoding="utf-8"))
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_text(_meta_path(slug), json.dumps(meta, ensure_ascii=False, indent=2))

    rc, _, _ = run_combine_skill(str(config.SKILLS_DIR), slug)
    if rc != 0:
        _combine_skill_manual(slug)


# 鈹€鈹€ 鎵嬪姩绾犲亸 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
@router.post("/{slug}/correction", response_model=dict)
async def apply_correction(slug: str, req: CorrectionReq) -> dict:
    """鎵嬪姩搴旂敤绾犲亸锛堢敤鎴风洿鎺ユ寚瀹氱籂姝ｅ唴瀹癸級銆?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    _apply_correction(slug, req.layer, req.original, req.correction, req.user_note)
    return {"slug": slug, "layer": req.layer, "status": "corrected", "message": "绾犳宸插簲鐢?}


@router.delete("/{slug}")
async def delete_skill(slug: str) -> dict:
    """鍒犻櫎 Skill銆?""
    skill_dir = _skill_dir(slug)
    if not skill_dir.exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")
    import shutil
    shutil.rmtree(skill_dir)
    return {"slug": slug, "deleted": True}


@router.get("/{slug}/versions")
async def list_versions(slug: str) -> dict:
    """鍒楀嚭鍘嗗彶鐗堟湰锛堣皟鐢?create-ex version_manager.py锛夈€?""
    versions = run_list_versions(str(config.SKILLS_DIR), slug)
    return {"slug": slug, "versions": versions}


@router.post("/{slug}/import-file")
async def import_file(slug: str, file: UploadFile = File(...), source_type: str = "auto") -> dict:
    """瀵煎叆鏂囦欢鍒?Skill锛堣皟鐢?create-ex 瑙ｆ瀽宸ュ叿锛夈€?""
    if not _meta_path(slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill 涓嶅瓨鍦? {slug}")

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
        "slug": slug, "filename": file.filename,
        "format": result.get("format", "unknown"),
        "returncode": result.get("returncode"),
        "output": result.get("stdout", "")[:500],
    }
