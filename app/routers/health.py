"""
统一健康检查端点。

检测 FastAPI（本服务）是否就绪，以及外接在线 API 是否已配置，
供前端 checkServer() 查询状态用。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

from app import config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict:
    api_ready = config.is_api_configured()
    return {
        "status": "ok" if api_ready else "degraded",
        "fastapi": "ok",
        "api_ready": api_ready,
        "api_model": config.API_MODEL,
        "api_base_url": config.API_BASE_URL,
    }
