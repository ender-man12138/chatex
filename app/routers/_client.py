from __future__ import annotations

import json
import logging
from openai import AsyncOpenAI

from app import config
from app.server import build_openai_url

logger = logging.getLogger(__name__)


def get_llm_client(slug: str | None = None, has_material: bool = False) -> AsyncOpenAI:
    """
    根据 skill 来源标签和是否有分析材料选择 LLM 客户端。
    - has_material=True（路径B）→ 在线 API（大模型）
    - slug 为 None 或 source=="text" 且无材料 → 本地 llama-server（小模型）
    """
    if has_material and config.is_api_enabled():
        logger.debug(f"Skill {slug} (有材料) 使用在线 API: {config.API_MODEL}")
        return AsyncOpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)

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
