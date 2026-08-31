"""
统一健康检查端点。

同时检测 llama-server（本地推理）和 FastAPI（本服务）是否就绪，
供前端 checkServer() 查询状态用。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

from app.server import is_ready as llama_is_ready

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict:
    llama_ok = llama_is_ready()
    return {
        "status": "ok" if llama_ok else "degraded",
        "llama": "ready" if llama_ok else "not_ready",
        "fastapi": "ok",
    }
