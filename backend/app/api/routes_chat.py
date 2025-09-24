"""Chat endpoints for the RAG assistant."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Iterable, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.db import SessionLocal, get_session
from ..models import Conversation, Message, NamespaceMember
from ..rag import ollama_client, retrieval

logger = logging.getLogger(__name__)

router = APIRouter()

SYSTEM_PROMPT = (
    "You are the Heidelberg University IT support assistant. "
    "Use only the provided knowledge base excerpts to answer user questions. "
    "If the answer is not contained in the context, reply that you do not know. "
    "When you reference information from a context snippet include a footnote marker in the form [^N] where N matches the source number."
)


class ChatStartRequest(BaseModel):
    namespace_id: uuid.UUID = Field(..., description="Namespace containing the knowledge base")
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Optional existing conversation identifier"
    )


class ChatStartResponse(BaseModel):
    conversation_id: uuid.UUID


class _CitationPayload(BaseModel):
    doc_id: uuid.UUID
    ord: int
    title: str | None = None
    chunk_id: uuid.UUID | None = None
    text: str | None = None


def _require_user_id(request: Request) -> uuid.UUID:
    raw_user_id = getattr(request.state, "user_id", None)
    if not raw_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc


def _assert_namespace_membership(session: Session, namespace_id: uuid.UUID, user_id: uuid.UUID) -> None:
    stmt: Select[Any] = select(NamespaceMember.id).where(
        NamespaceMember.namespace_id == namespace_id,
        NamespaceMember.user_id == user_id,
    )
    exists = session.execute(stmt).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Namespace access denied")


@router.post("/start", response_model=ChatStartResponse, summary="Ensure a conversation exists")
async def chat_start(
    payload: ChatStartRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ChatStartResponse:
    """Create a conversation within the namespace if needed."""

    user_id = _require_user_id(request)
    _assert_namespace_membership(session, payload.namespace_id, user_id)

    if payload.conversation_id:
        conversation = session.get(Conversation, payload.conversation_id)
        if (
            conversation is None
            or conversation.namespace_id != payload.namespace_id
            or (conversation.user_id and conversation.user_id != user_id)
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return ChatStartResponse(conversation_id=conversation.id)

    conversation = Conversation(namespace_id=payload.namespace_id, user_id=user_id)
    session.add(conversation)
    session.flush()
    return ChatStartResponse(conversation_id=conversation.id)


def _load_recent_messages(session: Session, conversation_id: uuid.UUID) -> List[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(settings.CHAT_HISTORY_LIMIT)
    )
    rows = session.execute(stmt).scalars().all()
    return list(reversed(rows))


def _build_context(chunks: Iterable[retrieval.RetrievedChunk]) -> tuple[str, List[_CitationPayload]]:
    context_lines: List[str] = []
    citations: List[_CitationPayload] = []
    for idx, chunk in enumerate(chunks, start=1):
        title = chunk.title or "Untitled document"
        context_lines.append(f"[{idx}] {title}\n{chunk.text.strip()}")
        citations.append(
            _CitationPayload(
                doc_id=chunk.document_id,
                ord=chunk.ordinal,
                title=chunk.title,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
            )
        )
    context = "\n\n".join(context_lines) if context_lines else "(no supporting context found)"
    return context, citations


def _format_history(messages: Iterable[Message], latest_user_input: str) -> str:
    lines: List[str] = []
    for message in messages:
        role = "User" if message.role == "user" else "Assistant"
        content = message.content.strip()
        if not content:
            continue
        lines.append(f"{role}: {content}")
    lines.append(f"User: {latest_user_input.strip()}")
    lines.append("Assistant:")
    return "\n".join(lines)


def _sse_payload(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@router.get("/stream", summary="Stream chat completions over SSE")
async def chat_stream(
    request: Request,
    conversation_id: uuid.UUID = Query(...),
    namespace_id: uuid.UUID = Query(...),
    q: str = Query(..., min_length=1),
) -> StreamingResponse:
    """Handle a chat turn by retrieving context and streaming model tokens."""

    user_id = _require_user_id(request)
    question = q.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty query")

    session = SessionLocal()
    try:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None or conversation.namespace_id != namespace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if conversation.user_id and conversation.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conversation access denied")

        _assert_namespace_membership(session, namespace_id, user_id)

        history = _load_recent_messages(session, conversation_id)

        retrieved_chunks = retrieval.retrieve(question, namespace_id, session=session)
        context, citations = _build_context(retrieved_chunks)

        conversation.updated_at = datetime.now(timezone.utc)
        if not conversation.title:
            conversation.title = question[:80]

        message = Message(
            conversation_id=conversation.id,
            user_id=user_id,
            role="user",
            content=question,
        )
        session.add(message)
        session.commit()
    finally:
        session.close()

    prompt = "\n\n".join(
        [
            SYSTEM_PROMPT,
            "Context:",
            context,
            "Conversation:",
            _format_history(history, question),
        ]
    )

    async def event_stream() -> AsyncIterator[str]:
        assistant_reply: List[str] = []
        try:
            async for chunk in ollama_client.stream_generate(prompt):
                token = chunk.get("response") or chunk.get("token")
                if token:
                    assistant_reply.append(token)
                    yield _sse_payload({"token": token})
                if chunk.get("done"):
                    break
        except Exception:
            logger.exception("Ollama streaming failure")
            yield _sse_payload({"done": True, "error": "model_error"})
            return

        payload = {
            "done": True,
            "citations": [citation.model_dump() for citation in citations],
        }
        yield _sse_payload(payload)

        response_text = "".join(assistant_reply).strip()
        with SessionLocal() as write_session:
            conversation = write_session.get(Conversation, conversation_id)
            if conversation is None:
                return
            conversation.updated_at = datetime.now(timezone.utc)
            assistant_message = Message(
                conversation_id=conversation.id,
                user_id=None,
                role="assistant",
                content=response_text,
            )
            assistant_message.metadata = {
                "citations": [citation.model_dump() for citation in citations]
            }
            write_session.add(assistant_message)
            write_session.commit()

    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "text/event-stream",
        "Connection": "keep-alive",
    }
    return StreamingResponse(event_stream(), headers=headers, media_type="text/event-stream")
