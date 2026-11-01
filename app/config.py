"""
ChatEx 配置管理模块。
所有路径均相对于项目根目录（chatex/）解析。
支持通过环境变量覆盖各配置项。

模型调用说明：
  已完全摒弃本地 llama-server 推理，统一使用外接在线大模型 API。
  软件运行时要求用户先配置 API（base_url + api_key + model）并通过连接测试，
  之后才能进行对话。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent          # chatex/
DATA_DIR = ROOT_DIR / os.getenv("CHATEX_DATA_DIR", "data")
SKILLS_DIR = DATA_DIR / os.getenv("CHATEX_SKILLS_DIR", "skills")
CONVS_DIR = DATA_DIR / os.getenv("CHATEX_CONVS_DIR", "conversations")

# ── 服务端口 ──────────────────────────────────────────────────────────────────
APP_PORT = int(os.getenv("CHATEX_APP_PORT", "9090"))       # FastAPI / pywebview 监听端口，固定不变

# ── 对话历史 ──────────────────────────────────────────────────────────────────
MAX_HISTORY = int(os.getenv("CHATEX_MAX_HISTORY", "20"))    # 每条对话最多携带的消息数

# ── 其他 ──────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("CHATEX_LOG_LEVEL", "info")
SHUTDOWN_WAIT_SECONDS = int(os.getenv("CHATEX_SHUTDOWN_WAIT", "3"))

# ── 在线 API 配置（持久化到 data/settings.json）────────────────────────────
_SETTINGS_FILE = DATA_DIR / "settings.json"


def _load_settings() -> dict:
    """从 settings.json 加载持久化的 API 配置，失败则返回空字典。"""
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


_settings = _load_settings()

API_BASE_URL = _settings.get("api_base_url", "")
API_KEY = _settings.get("api_key", "")
API_MODEL = _settings.get("api_model", "")


def save_api_settings(base_url: str, api_key: str, api_model: str) -> None:
    """保存 API 配置到 settings.json（KEY 明文存储，仅本地使用）。"""
    global API_BASE_URL, API_KEY, API_MODEL
    data = {"api_base_url": base_url, "api_key": api_key, "api_model": api_model}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    API_BASE_URL, API_KEY, API_MODEL = base_url, api_key, api_model


def is_api_configured() -> bool:
    """三项 API 配置是否齐备（base_url + key + model 均非空）。

    仅代表"配置完整"，不代表"已连通"。是否可用以用户完成严格测试连接为准
    （前端通过 /api/settings/test-connection 验证连通后再放行）。
    """
    return bool(API_BASE_URL.strip() and API_KEY.strip() and API_MODEL.strip())


def ensure_dirs() -> None:
    """确保所有数据目录存在，并初始化空 settings.json（如果不存在）。"""
    for d in (DATA_DIR, SKILLS_DIR, CONVS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    # 首次启动时创建空白 settings.json，避免用户打开设置弹窗看到空字段
    if not _SETTINGS_FILE.exists():
        _SETTINGS_FILE.write_text(
            json.dumps({}, ensure_ascii=False), encoding="utf-8"
        )


def validate() -> list[str]:
    """校验配置，返回错误列表（为空则配置有效）。

    本地推理已废弃，无需校验模型文件与 llama-server 是否存在。
    """
    return []
