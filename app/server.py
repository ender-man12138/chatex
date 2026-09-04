"""
llama-server 子进程管理模块。

负责启停 llama-server.exe，并处理进程守护、健康检查、优雅关闭。
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


# ── 启动 ──────────────────────────────────────────────────────────────────────
def start_server(timeout: int = 60) -> bool:
    """
    启动 llama-server.exe（后台进程），等待其就绪。
    timeout：最长等待秒数，超时返回 False。
    """
    global _server_proc

    with _server_lock:
        if _server_proc is not None and _server_proc.poll() is None:
            logger.info("llama-server 已在运行")
            return True

        server_exe = config.ROOT_DIR / "llama" / "llama-server.exe"
        if not server_exe.exists():
            logger.error(f"找不到 llama-server.exe: {server_exe}")
            return False

        cmd = [
            str(server_exe),
            "-m", str(config.MODEL_PATH),
            "--host", config.LLAMA_HOST,
            "--port", str(config.LLAMA_PORT),
            "--ctx-size", str(config.CTX_SIZE),
            "--threads", str(config.THREADS),
            "--n-predict", str(config.N_PREDICT),
            "--cache-type-k", config.CACHE_TYPE_K,
            "--cache-type-v", config.CACHE_TYPE_V,
            "--reasoning-format", config.REASONING_FORMAT,
        ]
        if not config.ENABLE_THINKING:
            cmd += ["--chat-template-kwargs", '{"enable_thinking":false}']

        logger.info("正在启动 llama-server …")
        # CREATE_NO_WINDOW 隐藏 CMD 弹窗；shell=False 避免系统默认 shell
        _server_proc = subprocess.Popen(
            cmd,
            cwd=str(config.ROOT_DIR / "llama"),
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        global _llama_log_thread
        _llama_log_thread = threading.Thread(target=_read_llama_output, daemon=True)
        _llama_log_thread.start()

        if not _wait_until_ready(timeout):
            logger.error("llama-server 启动超时")
            _kill_server()
            return False

        logger.info(f"llama-server 已就绪（port={config.LLAMA_PORT}）")
        return True


def _wait_until_ready(timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _server_proc is None or _server_proc.poll() is not None:
            return False
        if _port_open(config.LLAMA_HOST, config.LLAMA_PORT, connect_timeout=0.5):
            return True
        time.sleep(0.5)
    return False


# ── 停止 ──────────────────────────────────────────────────────────────────────
def stop_server(wait: bool = True, timeout: int = 5) -> bool:
    """
    停止 llama-server。
    wait=True 时阻塞直到进程退出或超时。
    """
    global _server_proc

    with _server_lock:
        proc = _server_proc
        if proc is None:
            return True

        if proc.poll() is not None:
            _server_proc = None
            return True

        logger.info("正在停止 llama-server …")
        _server_proc = None
        proc.terminate()

        if wait:
            try:
                proc.wait(timeout=timeout)
                return True
            except subprocess.TimeoutExpired:
                logger.warning("llama-server 未在 {}s 内退出，强制杀死".format(timeout))
                proc.kill()
                return False
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


# ── 状态查询 ──────────────────────────────────────────────────────────────────
def is_running() -> bool:
    with _server_lock:
        if _server_proc is None:
            return False
        if _server_proc.poll() is not None:
            return False
        return _port_open(config.LLAMA_HOST, config.LLAMA_PORT, connect_timeout=0.3)


def is_ready() -> bool:
    """健康检查：能否连上 llama-server 的 /health 端点。"""
    url = f"http://{config.LLAMA_HOST}:{config.LLAMA_PORT}/health"
    try:
        r = requests.get(url, timeout=2)
        return r.status_code == 200
    except Exception:
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

