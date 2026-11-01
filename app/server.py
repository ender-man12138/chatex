"""
[已废弃] llama-server 子进程管理模块。

本地推理已废弃，统一使用外接在线大模型 API。
本模块保留仅为向后兼容（file_import.py 等旧代码可能 import 此模块）。
新的入口与运行流程均不再调用 start_server / stop_server。
"""

from __future__ import annotations

import logging
import socket
import subprocess
import threading
import time
from pathlib import Path

import requests

from app import config

logger = logging.getLogger(__name__)

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_server_proc: subprocess.Popen | None = None
_server_lock = threading.Lock()
_llama_log_thread: threading.Thread | None = None


def get_server_process() -> subprocess.Popen | None:
    return _server_proc


# ── 启动（已废弃：本地推理不再使用）─────────────────────────────────────────
def start_server(timeout: int = 60) -> bool:
    """
    [已废弃] 本地 llama-server 已停用，此函数不应再被调用。
    保留仅为向后兼容，直接返回 False。
    """
    logger.warning("start_server 已废弃：本地推理已停用")
    return False


def _wait_until_ready(timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_proc is None or _server_proc.poll() is not None:
            return False
        if _port_open(config.LLAMA_HOST, config.LLAMA_PORT, connect_timeout=0.5):
            return True
        time.sleep(0.5)
    return False


# ── 停止（已废弃：本地推理不再使用）─────────────────────────────────────────
def stop_server(wait: bool = True, timeout: int = 5) -> bool:
    """
    [已废弃] 本地 llama-server 已停用，此函数不应再被调用。
    保留仅为向后兼容，直接返回 True（无进程需要停止）。
    """
    logger.warning("stop_server 已废弃：本地推理已停用")
    _server_proc = None
    _llama_log_thread = None
    return True


def _kill_server() -> None:
    global _server_proc
    if _server_proc is not None:
        _server_proc.kill()
        _server_proc = None


def _read_llama_output() -> None:
    """后台线程：读取 llama-server 的 stdout，输出到 Python logger。"""
    if _server_proc is None or _server_proc.stdout is None:
        return
    try:
        for line in _server_proc.stdout:
            logger.info("[llama] " + line.rstrip())
    except Exception:
        pass


# ── 状态查询（已废弃：本地推理不再使用）─────────────────────────────────────
def is_running() -> bool:
    """[已废弃] 本地 llama-server 已停用，始终返回 False。"""
    return False


def is_ready() -> bool:
    """[已废弃] 本地 llama-server 已停用，始终返回 False。"""
    return False


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def _port_open(host: str, port: int, connect_timeout: float = 1.0) -> bool:
    """检测 host:port 是否处于监听状态（TCP 层面）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(connect_timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def build_openai_url() -> str:
    """返回 OpenAI 兼容 API 的基础 URL，供 openai 客户端使用。"""
    return f"http://{config.LLAMA_HOST}:{config.LLAMA_PORT}/v1"


def stop_llama_log_thread() -> None:
    global _llama_log_thread
    _llama_log_thread = None

