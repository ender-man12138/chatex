"""
API 设置路由 — 配置外接大模型（OpenAI 兼容）连接。

提供：
  - GET  /api/settings                  返回当前配置（key 脱敏）
  - POST /api/settings                  保存配置
  - POST /api/settings/test-connection  严格测试连接，必须返回正确的 chat 响应才视为成功
"""

from __future__ import annotations

import logging

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


class SettingsSaveReq(BaseModel):
    api_base_url: str = ""
    api_key: str = ""
    api_model: str = "qwen-plus"


class TestConnectionReq(BaseModel):
    api_base_url: str = Field(..., description="Base URL（必须非空）")
    api_key: str = Field(..., description="API Key（必须非空）")
    api_model: str = Field("", description="模型名，可选；默认取当前已保存的 API_MODEL")


@router.get("/api/settings")
async def get_settings() -> dict:
    """返回当前 API 配置（key 脱敏，仅显示前4位）。"""
    key_display = ""
    if config.API_KEY:
        key_display = (
            config.API_KEY[:4] + "..." + config.API_KEY[-4:]
            if len(config.API_KEY) > 8 else config.API_KEY[:4] + "****"
        )
    return {
        "enabled": config.is_api_configured(),
        "base_url": config.API_BASE_URL,
        "api_key_display": key_display,
        "api_model": config.API_MODEL,
    }


@router.post("/api/settings")
async def save_settings(req: SettingsSaveReq) -> dict:
    """保存 API 配置。base_url / key / model 同时非空才视为启用。"""
    if not req.api_base_url and not req.api_key and not req.api_model:
        # 三项都空 → 视为清空
        config.save_api_settings("", "", "")
        return {"enabled": False, "message": "已清除 API 配置"}

    if req.api_base_url and not req.api_key:
        raise HTTPException(status_code=400, detail="填写 Base URL 时必须同时填写 API Key")
    if req.api_key and not req.api_base_url:
        raise HTTPException(status_code=400, detail="填写 API Key 时必须同时填写 Base URL")

    # key 留空但已有保存的 key → 保持原 key；否则视为清空 key
    new_key = req.api_key.strip() if req.api_key.strip() else config.API_KEY
    new_base = req.api_base_url.strip()

    if not new_key and not new_base and not req.api_model.strip():
        # 三项都空 → 视为清空
        config.save_api_settings("", "", "")
        return {"enabled": False, "message": "已清除 API 配置"}

    model = req.api_model.strip() or config.API_MODEL or "qwen-plus"
    config.save_api_settings(new_base, new_key, model)
    return {"enabled": config.is_api_configured(), "message": "配置已保存"}


@router.post("/api/settings/test-connection")
async def test_connection(req: TestConnectionReq) -> dict:
    """严格测试连接：必须返回可解析的 chat 响应才算成功。

    用 5s 超时 + 一次最小 chat 请求（"ping"→"pong"）验证：
      1. HTTP 状态 200
      2. 响应包含非空 choices[0].message.content
    失败时返回 success=False 与具体错误，前端据此决定是否允许保存。
    """
    base_url = req.api_base_url.strip()
    api_key = req.api_key.strip()
    model = req.api_model.strip() or config.API_MODEL or "qwen-plus"

    if not base_url or not api_key:
        raise HTTPException(status_code=400, detail="Base URL 与 API Key 均不能为空")

    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "ping"},
        ],
        "max_tokens": 16,
        "temperature": 0.0,
        "stream": False,
    }

    try:
        resp = requests.post(
            endpoint, headers=headers, json=payload, timeout=15,
        )
    except requests.exceptions.Timeout:
        return {"success": False, "error": "连接超时，请检查 Base URL 或网络"}
    except requests.exceptions.ConnectionError as e:
        return {"success": False, "error": f"无法连接：{e}"}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"HTTP 错误：{e}"}
    except Exception as e:
        return {"success": False, "error": f"请求失败：{e}"}

    if resp.status_code != 200:
        try:
            body = resp.text[:300]
        except Exception:
            body = ""
        return {"success": False, "error": f"模型服务返回 {resp.status_code}：{body}"}

    # 验证响应体可解析且包含有效内容
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return {"success": False, "error": "响应格式不符合预期，请确认模型名与服务是否匹配"}

    if not isinstance(content, str) or not content.strip():
        return {"success": False, "error": "模型返回了空内容，请确认模型名是否正确"}

    return {"success": True, "content": content[:200]}
