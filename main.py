"""
ChatEx FastAPI 主应用入口。
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
import webview
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.server import start_server, stop_server

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ChatEx 启动中...")
    config.ensure_dirs()
    if not start_server(timeout=60):
        logger.error("llama-server 启动失败")
    yield
    logger.info("ChatEx 关闭中...")
    stop_server(wait=True)


app = FastAPI(
    title="ChatEx API",
    description="本地离线聊天工具 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import health, chat, skills_new as skills, file_import, settings
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(skills.router)
app.include_router(file_import.router)
app.include_router(settings.router)

frontend_path = config.ROOT_DIR / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


@app.get("/")
async def root():
    return {"message": "ChatEx API", "docs": "/docs"}


def _on_window_closing():
    """窗口关闭时停止所有服务。"""
    logger.info("前端窗口关闭，正在停止服务...")
    stop_server(wait=True)
    logger.info("所有服务已停止。")


def main():
    """启动 FastAPI + pywebview 窗口；关闭窗口即停止全部服务。"""
    host, port = "127.0.0.1", config.APP_PORT
    url = f"http://{host}:{port}"

    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": "main:app", "host": host, "port": port, "log_level": config.LOG_LEVEL},
        daemon=True,
    )
    server_thread.start()
    logger.info("正在等待服务就绪...")
    # 等待 uvicorn 启动（最多 15 秒）
    for _ in range(30):
        import time
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(f"{url}/api/health", timeout=1)
            break
        except Exception:
            pass
    else:
        logger.warning("服务未在规定时间内就绪")

    window = webview.create_window(
        "ChatEx",
        url=url,
        width=1100,
        height=720,
        resizable=True,
        js_api=_DummyJsApi(),
    )
    window.events.closing += _on_window_closing
    webview.start(debug=True)


class _DummyJsApi:
    """供 pywebview 注册的空 JS API，暂无功能接口。"""
    pass


if __name__ == "__main__":
    main()

