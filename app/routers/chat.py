"""
ChatEx routing module for chat endpoints.
Provides /api/chat (send message) and /api/conversations (conversation management).
Conversation history is stored as JSON files in data/conversations/.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app import config
from app.server import build_openai_url, is_ready

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    conversation_id: str | None = Field(None, description="Conversation ID, auto-create if not provided")


class ChatResponse(BaseModel):
    conversation_id: str
    response: str
    role: str = "assistant"


class ConversationInfo(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


def _conv_path(conversation_id: str) -> Path:
    return config.CONVS_DIR / f"{conversation_id}.json"


def _load_conversation(conversation_id: str) -> list[dict]:
    path = _conv_path(conversation_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except (json.JSONDecodeError, KeyError):
        return []


def _save_conversation(conversation_id: str, title: str, messages: list[dict]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    path = _conv_path(conversation_id)
    created_at = now
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            created_at = old.get("created_at", now)
        except Exception:
            pass
    data = {
        "id": conversation_id,
        "title": title,
        "created_at": created_at,
        "updated_at": now,
        "messages": messages,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _truncate_messages(messages: list[dict]) -> list[dict]:
    if len(messages) <= config.MAX_HISTORY:
        return messages
    return messages[-config.MAX_HISTORY:]


SYSTEM_PROMPT = (
    "You are a local chat assistant named ChatEx. "
    "You run entirely on the user'\''s local device and do not upload any data. "
    "Please answer the user'\''s questions in a concise and friendly manner."
)


def _strip_thinking(text: str) -> str:
    """Remove thinking tags from model output."""
    return re.sub(r"<think(?:ing)?\b.*?</think(?:ing)?>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not is_ready():
        raise HTTPException(status_code=503, detail="Inference service not ready, check llama-server")

    conv_id = req.conversation_id or uuid.uuid4().hex[:12]
    messages = _load_conversation(conv_id)
    messages.append({"role": "user", "content": req.message})
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + _truncate_messages(messages)

    client = AsyncOpenAI(base_url=build_openai_url(), api_key="not-needed")
    try:
        stream = await client.chat.completions.create(
            model="qwen3.5-2b",
            messages=api_messages,
            stream=True,
            temperature=0.7,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
                "reasoning_effort": "off",
            },
        )
        parts: list[str] = []
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        response_text = _strip_thinking("".join(parts))
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

    messages.append({"role": "assistant", "content": response_text})
    title = req.message[:30] + ("..." if len(req.message) > 30 else "")
    _save_conversation(conv_id, title, messages)
    return ChatResponse(conversation_id=conv_id, response=response_text)


@router.get("/conversations", response_model=list[ConversationInfo])
async def list_conversations() -> list[ConversationInfo]:
    convs: list[ConversationInfo] = []
    if not config.CONVS_DIR.exists():
        return convs
    for path in sorted(config.CONVS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            convs.append(ConversationInfo(
                id=data["id"],
                title=data.get("title", "Untitled"),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                message_count=len(data.get("messages", [])),
            ))
        except Exception:
            continue
    return convs


@router.get("/conversations/{conversation_id}", response_model=dict)
async def get_conversation(conversation_id: str) -> dict:
    path = _conv_path(conversation_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str) -> dict:
    path = _conv_path(conversation_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Conversation not found")
    path.unlink()
    return {"deleted": True}
