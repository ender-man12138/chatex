from __future__ import annotations

import json
import logging
from openai import AsyncOpenAI

from app import config
from app.server import build_openai_url

logger = logging.getLogger(__name__)


def get_llm_client(slug: str | None = None, has_material: bool = False) -> AsyncOpenAI:
    """
    根据 skill 的 source 标签选择 LLM 客户端。
    - source == "import" → 在线 API（大模型）
    - 其他情况 → 本地 llama-server（小模型）
    """
    if slug and config.is_api_enabled():
        meta_path = config.SKILLS_DIR / slug / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("source") == "import":
                    logger.debug(f"Skill {slug} (import) 使用在线 API: {config.API_MODEL}")
                    return AsyncOpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)
            except Exception:
                pass

    logger.debug(f"使用本地 llama-server: {build_openai_url()}")
    return AsyncOpenAI(base_url=build_openai_url(), api_key="not-needed")


def get_extra_body(slug: str | None = None, has_material: bool = False) -> dict:
    """
    返回请求 extra_body。
    本地模型关闭思考，API 大模型不关闭思考。
    """
    if slug and config.is_api_enabled():
        meta_path = config.SKILLS_DIR / slug / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("source") == "import":
                    return {}
            except Exception:
                pass

    return {"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "none"}


def get_model_name(slug: str | None = None, has_material: bool = False) -> str:
    """返回当前应使用的模型名称。"""
    if has_material and config.is_api_enabled():
        return config.API_MODEL

    if slug and config.is_api_enabled():
        meta_path = config.SKILLS_DIR / slug / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("source") == "import":
                    return config.API_MODEL
            except Exception:
                pass
    return "qwen3.5-2b"
