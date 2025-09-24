from __future__ import annotations

import io
import json
import uuid
from collections import deque
from typing import Any

import pytest

from backend.app.api.routes_docs import UploadCompleteRequest
from backend.app.core.config import settings
from backend.app.api.routes_auth import (
    DEFAULT_LOCAL_LOGIN_EMAIL,
    DEFAULT_LOCAL_LOGIN_PASSWORD,
)
from backend.app.ingest import crawler as crawler_module
from backend.app.models import Conversation, Document, Job, Namespace, NamespaceMember, User
from backend.app.models.documents import DocumentStatus
from backend.app.rag import ollama_client, retrieval


def test_local_login_success(app: Any) -> None:
    response = app.post(
        "/auth/local-login",
        json={"email": settings.LOCAL_LOGIN_EMAIL, "password": settings.LOCAL_LOGIN_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Logged in"

    session_cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
    assert session_cookie

    app.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)
    me_response = app.get("/auth/me")
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert me_payload["user"]["email"] == settings.LOCAL_LOGIN_EMAIL


def test_local_login_rejects_bad_credentials(app: Any) -> None:
    response = app.post(
        "/auth/local-login",
        json={"email": settings.LOCAL_LOGIN_EMAIL, "password": "wrong"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["detail"] == "Invalid email or password"


def test_local_login_accepts_default_credentials(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "LOCAL_LOGIN_EMAIL", "other@example.com")
    monkeypatch.setattr(settings, "LOCAL_LOGIN_PASSWORD", "supersecret")

    response = app.post(
        "/auth/local-login",
        json={
            "email": DEFAULT_LOCAL_LOGIN_EMAIL,
            "password": DEFAULT_LOCAL_LOGIN_PASSWORD,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["detail"] == "Logged in"


def test_auth_guard_requires_session(app: Any) -> None:
    response = app.post(
        "/api/docs/upload-init",
        json={
            "namespace_id": str(uuid.uuid4()),
            "filename": "example.pdf",
        },
    )
    assert response.status_code == 401


def test_upload_ingest_happy_path(
    app: Any,
    session_factory,
    auth_session: dict[str, str],
    ingest_calls: list[tuple[str, str | None]],
    fake_minio,
) -> None:
    namespace_id = uuid.uuid4()
    user_id = uuid.UUID(auth_session["user_id"])

    with session_factory() as session:
        user = User(id=user_id, email="user@example.com")
        namespace = Namespace(id=namespace_id, slug="demo", name="Demo")
        membership = NamespaceMember(namespace_id=namespace_id, user_id=user_id)
        session.add_all([user, namespace, membership])
        session.commit()

    client = app
    client.cookies.set(settings.SESSION_COOKIE_NAME, auth_session["cookie"])

    headers = {"X-CSRF-Token": auth_session["csrf_token"]}
    init_payload = {
        "namespace_id": str(namespace_id),
        "filename": "handbook.pdf",
        "content_type": "application/pdf",
    }
    init_response = client.post(
        "/api/docs/upload-init", json=init_payload, headers=headers
    )
    assert init_response.status_code == 200
    assert "X-RateLimit-Limit" in init_response.headers
    document_id = uuid.UUID(init_response.json()["document_id"])

    with session_factory() as session:
        document = session.get(Document, document_id)
        assert document is not None
        fake_minio.put_object(
            settings.MINIO_BUCKET,
            document.uri,
            io.BytesIO(b"sample document"),
            len(b"sample document"),
            content_type="application/pdf",
        )

    complete_payload = UploadCompleteRequest(
        document_id=document_id,
        namespace_id=namespace_id,
        title="University Handbook",
        metadata={"tag": "policy"},
    ).model_dump()

    complete_response = client.post(
        "/api/docs/complete", json=complete_payload, headers=headers
    )
    assert complete_response.status_code == 200
    body = complete_response.json()
    assert body["status"] == "uploaded"
    assert body["metadata"]["size_bytes"] == len(b"sample document")

    with session_factory() as session:
        job = session.query(Job).filter(Job.namespace_id == namespace_id).one()
        assert job.payload.get("document_id") == str(document_id)
        job_id = job.id

    assert ingest_calls
    recorded_document_id, recorded_job_id = ingest_calls[0]
    assert recorded_document_id == str(document_id)
    assert recorded_job_id == str(job_id)


def test_crawl_depth_restriction() -> None:
    crawler = object.__new__(crawler_module._Crawler)
    crawler.max_depth = 1
    crawler.seen = set()

    queue: deque[tuple[str, int]] = deque()
    crawler._enqueue_links(queue, ["https://example.com/a"], depth=1)
    assert queue.pop()[1] == 1

    queue.clear()
    crawler._enqueue_links(queue, ["https://example.com/b"], depth=2)
    assert not queue


def test_retrieval_namespace_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class DummyResult:
        def all(self) -> list[Any]:
            return []

    class DummySession:
        def execute(self, stmt):
            captured["statement"] = stmt
            return DummyResult()

    namespace_id = uuid.uuid4()

    monkeypatch.setattr(retrieval.embeddings, "embed", lambda texts: [[0.1, 0.2]])
    retrieval.retrieve("hello", namespace_id, session=DummySession(), top_k=1)

    stmt = captured["statement"]
    compiled = stmt.compile()
    assert compiled.params["namespace_id_1"] == namespace_id
    sql = str(stmt)
    assert "chunks" in sql and "namespace_id" in sql


def test_chat_stream_sse_smoke(
    app: Any,
    session_factory,
    auth_session: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    user_id = uuid.UUID(auth_session["user_id"])

    with session_factory() as session:
        user = User(id=user_id, email="streamer@example.com")
        namespace = Namespace(id=namespace_id, slug="stream", name="Stream")
        membership = NamespaceMember(namespace_id=namespace_id, user_id=user_id)
        document = Document(
            id=uuid.uuid4(),
            namespace_id=namespace_id,
            uri="placeholder",
            title="Guide",
            content_type="text/plain",
            status=DocumentStatus.INGESTED.value,
        )
        conversation = Conversation(id=conversation_id, namespace_id=namespace_id, user_id=user_id)
        session.add_all([user, namespace, membership, document, conversation])
        session.commit()

    async def fake_stream(prompt: str):  # pragma: no cover - simple async generator
        yield {"response": "Hello "}
        yield {"response": "world", "done": False}
        yield {"done": True}

    monkeypatch.setattr(retrieval, "retrieve", lambda *args, **kwargs: [])
    monkeypatch.setattr(ollama_client, "stream_generate", fake_stream)

    client = app
    client.cookies.set(settings.SESSION_COOKIE_NAME, auth_session["cookie"])
    params = {
        "conversation_id": str(conversation_id),
        "namespace_id": str(namespace_id),
        "q": "How are you?",
    }

    events = b""
    with client.stream(
        "GET",
        "/api/chat/stream",
        params=params,
        headers={"X-CSRF-Token": auth_session["csrf_token"]},
    ) as response:
        assert response.status_code == 200
        events = b"".join(response.iter_bytes())
    assert b"Hello" in events
    assert b"done" in events
    assert response.headers["content-type"].startswith("text/event-stream")
