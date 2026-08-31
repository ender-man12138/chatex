from __future__ import annotations

import json
import logging
from openai import AsyncOpenAI

from app import config
from app.server import build_openai_url

logger = logging.getLogger(__name__)


def get_llm_client(slug: str | None = None) -> AsyncOpenAI:
    """
    根据 skill 来源标签选择 LLM 客户端。
    - slug 为 None 或 source=="text" → 本地 llama-server
    - slug 存在且 source=="import" → 在线 API
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
