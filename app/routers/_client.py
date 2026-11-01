from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app import config

logger = logging.getLogger(__name__)


def get_online_client() -> AsyncOpenAI | None:
    """返回外接在线大模型 API 的 OpenAI 兼容客户端。

    仅当三项配置齐备（base_url + key + model）时返回客户端，
    否则返回 None。调用方在返回 None 时应向用户提示"请先配置 API"。
    本地 llama-server 已废弃，不再存在本地客户端分支。
    """
    if not config.is_api_configured():
        return None
    return AsyncOpenAI(base_url=config.API_BASE_URL, api_key=config.API_KEY)


def get_online_model() -> str:
    """返回当前应使用的在线模型名称（即 config.API_MODEL）。"""
    return config.API_MODEL


def get_extra_body() -> dict:
    """在线大模型不需要关闭思考，返回空 extra_body。

    保留此函数以便调用点统一；本地模型特有的关闭思考逻辑已移除。
    """
    return {}
