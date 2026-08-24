"""
ChatEx — FastAPI 主入口 + pywebview 桌面窗口。

启动流程：
1. 启动 llama-server 子进程（后台）
2. 启动 FastAPI + uvicorn（后台线程）
3. 等待 FastAPI 就绪
4. 启动 pywebview 窗口（主线程，阻塞直到窗口关闭）
5. 用户关闭窗口时弹出确认：完全退出 / 只关前端
"""

from __future__ import annotations

import logging
import signal
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import webview

from app import config
from app.routers import chat as chat_router
from app.routers import skills as skills_router
from app.routers import file_import as import_router
from app.routers import health as health_router
from app.server import start_server, stop_server, is_running

# ── 日志 ──────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── 全局状态 ──────────────────────────────────────────────────────────────────
_keep_alive = False


# ── 生命周期 ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    config.ensure_dirs()
    errors = config.validate()
    if errors:
        logger.error("配置校验失败: {}".format("; ".join(errors)))

    if not start_server(timeout=60):
        logger.error("llama-server 启动失败，请检查模型路径或端口占用")
    yield
    stop_server(wait=True, timeout=config.SHUTDOWN_WAIT_SECONDS)


# ── FastAPI 应用 ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="ChatEx",
    description="本地离线聊天工具",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 前端静态文件
frontend_dir = config.ROOT_DIR / "frontend"
app.mount("/frontend", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
app.include_router(chat_router.router)
app.include_router(skills_router.router)
app.include_router(import_router.router)
app.include_router(health_router.router)


# ── pywebview JS API ──────────────────────────────────────────────────────────
class JSAPI:
    def is_llama_running(self) -> bool:
        return is_running()

    def exit(self) -> None:
        global _keep_alive
        _keep_alive = False
        logger.info("用户选择完全退出")
        if webview.windows:
            webview.windows[0].destroy()

    def keep_running(self) -> None:
        global _keep_alive
        _keep_alive = True
        logger.info("用户选择保持服务运行，关闭前端")
        if webview.windows:
            webview.windows[0].destroy()


# ── 关闭事件处理 ──────────────────────────────────────────────────────────────
def _on_closing(window) -> bool:
    global _keep_alive
    result = window.create_confirmation_dialog(
        "关闭 ChatEx？",
        "确定：完全退出（关闭前端 + 停止推理服务）\n"
        "取消：只关闭前端窗口（推理服务保持运行）",
    )
    _keep_alive = not result
    logger.info("用户选择: {}".format("保持服务运行" if _keep_alive else "完全退出"))
    return True


# ── 启动入口 ──────────────────────────────────────────────────────────────────
def _run_server(host: str, port: int, ready_event: threading.Event) -> None:
    """在后台线程中运行 uvicorn，就绪后触发 ready_event。"""
    srv_config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(srv_config)
    ready_event.set()
    server.run()


def main() -> None:
    global _keep_alive

    logger.info("正在启动 ChatEx …")

    # 1. 启动 FastAPI（非守护线程，确保进程存活）
    ready = threading.Event()
    server_thread = threading.Thread(
        target=_run_server,
        args=(config.LLAMA_HOST, config.APP_PORT, ready),
        daemon=False,
        name="fastapi-server",
    )
    server_thread.start()
    logger.info("FastAPI 正在启动 http://%s:%d …", config.LLAMA_HOST, config.APP_PORT)

    # 2. 等待 FastAPI 就绪
    if not ready.wait(timeout=15):
        logger.error("FastAPI 启动超时")
        return
    logger.info("FastAPI 已就绪")

    # 3. 启动 pywebview 窗口（阻塞直到窗口关闭）
    api = JSAPI()
    win = webview.create_window(
        title="ChatEx",
        url=f"http://{config.LLAMA_HOST}:{config.APP_PORT}/frontend",
        js_api=api,
        width=900,
        height=640,
        resizable=True,
        confirm_close=False,
        background_color="#1a1a2e",
        min_size=(480, 360),
    )
    win.events.closing += _on_closing
    webview.start()

    # 4. 窗口关闭后清理
    logger.info("pywebview 窗口已关闭，清理资源 …")
    stop_server(wait=True, timeout=config.SHUTDOWN_WAIT_SECONDS)
    if not _keep_alive:
        logger.info("ChatEx 已完全退出")
    else:
        logger.info("前端已关闭，llama-server 仍在运行（%s:%d）", config.LLAMA_HOST, config.LLAMA_PORT)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: exit(0))
    main()


