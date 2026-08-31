import sys
sys.path.insert(0, r"E:\wh\10nodata\program\chatex")

code = '''"""
ChatEx FastAPI 主应用入口。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
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

from app.routers import health, chat, skills, file_import
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(skills.router)
app.include_router(file_import.router)

frontend_path = config.ROOT_DIR / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")


@app.get("/")
async def root():
    return {"message": "ChatEx API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=config.APP_PORT, reload=False, log_level=config.LOG_LEVEL)
'''

with open(r"E:\wh\10nodata\program\chatex\main.py", "w", encoding="utf-8") as f:
    f.write(code)
print("Written main.py successfully")
