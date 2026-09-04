"""
ChatEx 配置管理模块。
所有路径均相对于项目根目录（chatex/）解析。
支持通过环境变量覆盖各配置项。
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

# ── 模型路径 ──────────────────────────────────────────────────────────────────
MODEL_FILENAME = os.getenv(
    "CHATEX_MODEL_FILENAME",
    "qwen3-5-2B-Q4_K_M.gguf",
)
MODEL_PATH = DATA_DIR.parent / "models" / MODEL_FILENAME  # models/qwen3-5-2B-Q4_K_M.gguf

# ── 服务端口 ──────────────────────────────────────────────────────────────────
LLAMA_HOST = os.getenv("CHATEX_LLAMA_HOST", "127.0.0.1")
LLAMA_PORT = int(os.getenv("CHATEX_LLAMA_PORT", "8848"))   # llama-server 监听端口
APP_PORT = int(os.getenv("CHATEX_APP_PORT", "9090"))       # FastAPI / pywebview 监听端口

# ── llama-server 推理参数 ────────────────────────────────────────────────────
CTX_SIZE = int(os.getenv("CHATEX_CTX_SIZE", "8192"))        # 上下文窗口
THREADS = int(os.getenv("CHATEX_THREADS", "8"))            # CPU 线程数
N_PREDICT = int(os.getenv("CHATEX_N_PREDICT", "-1"))       # 每次最多生成 token（-1 = 不限）
CACHE_TYPE_K = os.getenv("CHATEX_CACHE_TYPE_K", "q8_0")    # K cache 类型
CACHE_TYPE_V = os.getenv("CHATEX_CACHE_TYPE_V", "q8_0")    # V cache 类型
REASONING_FORMAT = os.getenv("CHATEX_REASONING_FORMAT", "none")  # off/on/auto
ENABLE_THINKING = os.getenv("CHATEX_ENABLE_THINKING", "false").lower() == "true"

# ── 对话历史 ──────────────────────────────────────────────────────────────────
MAX_HISTORY = int(os.getenv("CHATEX_MAX_HISTORY", "20"))    # 每条对话最多携带的消息数

# ── 其他 ──────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("CHATEX_LOG_LEVEL", "info")
SHUTDOWN_WAIT_SECONDS = int(os.getenv("CHATEX_SHUTDOWN_WAIT", "3"))  # 关闭前等待 llama-server 退出的秒数
# ── 在线 API 配置（可选，持久化到 data/settings.json）──────────────────────
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
API_MODEL = _settings.get("api_model", "qwen-plus")


def save_api_settings(base_url: str, api_key: str, api_model: str) -> None:
    """保存 API 配置到 settings.json（KEY 明文存储，仅本地使用）。"""
    global API_BASE_URL, API_KEY, API_MODEL
    data = {"api_base_url": base_url, "api_key": api_key, "api_model": api_model}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    API_BASE_URL, API_KEY, API_MODEL = base_url, api_key, api_model


def is_api_enabled() -> bool:
    """在线 API 是否可用。"""
    return bool(API_BASE_URL and API_KEY)



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
    """校验配置，返回错误列表（为空则配置有效）。"""
    errors: list[str] = []
    if not MODEL_PATH.exists():
        errors.append(f"模型文件不存在: {MODEL_PATH}")
    llama_server = ROOT_DIR / "llama" / "llama-server.exe"
    if not llama_server.exists():
        errors.append(f"llama-server.exe 不存在: {llama_server}")
    return errors

