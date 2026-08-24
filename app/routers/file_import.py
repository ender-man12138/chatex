"""
文件导入路由。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel, Field

from app import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/import", tags=["import"])


class TextImportReq(BaseModel):
    text: str = Field(..., description="聊天记录文本")


class ImportResult(BaseModel):
    slug: str
    source_type: str
    message_count: int
    target_messages: int
    raw_text_preview: str
    analysis_summary: dict


@router.post("/file/{slug}", response_model=ImportResult)
async def upload_file(slug: str, file: UploadFile = File(...), source_type: str = "auto") -> ImportResult:
    safe_slug = re.sub(r"[^\w\-]", "_", slug)
    save_dir = config.SKILLS_DIR / safe_slug / "memories" / "chats"
    save_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "import").suffix.lower()
    save_path = save_dir / f"{uuid.uuid4().hex[:8]}{ext}"
    data = await file.read()
    save_path.write_bytes(data)
    result = await analyze_file(str(save_path), source_type, safe_slug)
    return ImportResult(slug=safe_slug, source_type=result.get("format", "unknown"),
        message_count=result.get("total_messages", 0), target_messages=result.get("target_messages", 0),
        raw_text_preview=result.get("raw_text", "")[:500], analysis_summary=result.get("analysis", {}))


@router.post("/text/{slug}", response_model=ImportResult)
async def import_text(slug: str, req: TextImportReq) -> ImportResult:
    safe_slug = re.sub(r"[^\w\-]", "_", slug)
    save_dir = config.SKILLS_DIR / safe_slug / "memories" / "chats"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"text_{uuid.uuid4().hex[:8]}.txt"
    save_path.write_text(req.text, encoding="utf-8")
    result = await analyze_file(str(save_path), "text", safe_slug)
    return ImportResult(slug=safe_slug, source_type="text",
        message_count=result.get("total_messages", 0), target_messages=result.get("target_messages", 0),
        raw_text_preview=result.get("raw_text", "")[:500], analysis_summary=result.get("analysis", {}))


async def analyze_file(file_path: str, source_type: str, target_name: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        return {"error": f"文件不存在: {file_path}"}
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    fmt = source_type if source_type != "auto" else _detect_format(path, raw_text)
    messages = _parse_messages(raw_text, fmt, target_name)
    analysis = _analyze(messages, target_name)
    return {"format": fmt, "total_messages": len(messages),
            "target_messages": len([m for m in messages if target_name in m.get("sender", "")]),
            "raw_text": raw_text, "analysis": analysis, "messages": messages[:200]}


def _detect_format(path: Path, raw_text: str) -> str:
    ext = path.suffix.lower()
    if ext == ".json": return "liuhen"
    elif ext == ".csv": return "wechatmsg_csv"
    elif ext in (".html", ".htm"): return "wechatmsg_html"
    elif ext in (".db", ".sqlite"): return "pywxdump"
    elif ext == ".txt":
        return "wechatmsg_txt" if re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", raw_text[:2000]) else "plaintext"
    elif ext in (".mht", ".mhtml"): return "qq_mht"
    return "plaintext"


def _parse_messages(raw_text: str, fmt: str, target_name: str) -> list[dict]:
    messages = []
    if fmt in ("wechatmsg_txt", "plaintext"):
        msg_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+?)$")
        current_msg = None
        for line in raw_text.splitlines():
            match = msg_pattern.match(line)
            if match:
                if current_msg: messages.append(current_msg)
                timestamp, sender = match.groups()
                current_msg = {"timestamp": timestamp.strip(), "sender": sender.strip(), "content": ""}
            elif current_msg and line.strip():
                current_msg["content"] += line + "\n"
        if current_msg: messages.append(current_msg)
    elif fmt == "liuhen":
        try:
            data = json.loads(raw_text)
            msg_list = data if isinstance(data, list) else data.get("messages", data.get("data", []))
            for msg in msg_list:
                messages.append({"timestamp": msg.get("time", ""), "sender": msg.get("sender", ""), "content": msg.get("content", "")})
        except Exception:
            messages = [{"timestamp": "", "sender": "unknown", "content": raw_text[:5000]}]
    else:
        messages = [{"timestamp": "", "sender": "unknown", "content": raw_text}]
    return messages


def _analyze(messages: list[dict], target_name: str) -> dict:
    target_msgs = [m for m in messages if target_name in m.get("sender", "")]
    lengths = [len(m["content"]) for m in target_msgs if m.get("content")]
    avg_length = sum(lengths) / len(lengths) if lengths else 0
    return {"total_messages": len(messages), "target_messages": len(target_msgs),
            "avg_message_length": round(avg_length, 1),
            "message_style": "短句连发型" if avg_length < 20 else "长段落型",
            "sample_messages": [m["content"] for m in target_msgs[:10] if m.get("content")]}
