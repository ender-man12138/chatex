"""
API 设置路由 — 配置外接大模型（OpenAI 兼容）连接。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


class SettingsSaveReq(BaseModel):
    api_base_url: str = ""
    api_key: str = ""
    api_model: str = "qwen-plus"


@router.get("/api/settings")
async def get_settings() -> dict:
    """返回当前 API 配置（key 脱敏，仅显示前4位）。"""
    key_display = ""
    if config.API_KEY:
        key_display = config.API_KEY[:4] + "..." + config.API_KEY[-4:] if len(config.API_KEY) > 8 else config.API_KEY[:4] + "****"

    return {
        "enabled": config.is_api_enabled(),
        "base_url": config.API_BASE_URL,
        "api_key_display": key_display,
        "api_model": config.API_MODEL,
    }


@router.post("/api/settings")
async def save_settings(req: SettingsSaveReq) -> dict:
    """保存 API 配置。base_url 和 api_key 同时非空时才启用。"""
    if not req.api_base_url and not req.api_key:
        # 清空配置
        config.save_api_settings("", "", req.api_model)
        return {"enabled": False, "message": "已清除 API 配置"}

    if req.api_base_url and not req.api_key:
        raise HTTPException(status_code=400, detail="填写 Base URL 时必须同时填写 API Key")

    if req.api_key and not req.api_base_url:
        raise HTTPException(status_code=400, detail="填写 API Key 时必须同时填写 Base URL")

    config.save_api_settings(req.api_base_url.strip(), req.api_key.strip(), req.api_model.strip() or "qwen-plus")
    return {"enabled": config.is_api_enabled(), "message": "配置已保存"}
