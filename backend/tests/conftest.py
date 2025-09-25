from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
import sys

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import JSON
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import UUID as PGUUID

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import settings
from backend.app.core import db as db_module
from backend.app.core import s3 as s3_module
from backend.app.core.antivirus import NoopScanner, set_scanner
from backend.app.main import create_app
from backend.app.models import Base
from backend.app.workers import tasks as tasks_module
from backend.app.api import routes_docs, routes_chat, routes_crawl


class FakeScanner:
    def scan(self, *, bucket: str, object_key: str, size: int, content_type: str) -> None:  # noqa: D401 - interface compat
        return None


class FakeObject:
    def __init__(self, data: bytes, content_type: str) -> None:
        self._data = data
        self.content_type = content_type
        self.size = len(data)

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:  # pragma: no cover - compatibility
        return None

    def release_conn(self) -> None:  # pragma: no cover - compatibility
        return None


class FakeMinio:
    def __init__(self) -> None:
        self._buckets: set[str] = set()
        self._objects: dict[tuple[str, str], FakeObject] = {}

    def bucket_exists(self, name: str) -> bool:
        return name in self._buckets

    def make_bucket(self, name: str) -> None:
        self._buckets.add(name)

    def presigned_put_object(self, bucket: str, object_name: str, *, expires: object | None = None) -> str:
        if bucket not in self._buckets:
            self._buckets.add(bucket)
        return f"https://minio.local/{bucket}/{object_name}"

    def put_object(self, bucket: str, object_name: str, data, length: int, *, content_type: str = "application/octet-stream") -> None:  # type: ignore[override]
        payload = data.read() if hasattr(data, "read") else data
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if bucket not in self._buckets:
            self._buckets.add(bucket)
        self._objects[(bucket, object_name)] = FakeObject(bytes(payload), content_type)

    def stat_object(self, bucket: str, object_name: str):
        obj = self._objects.get((bucket, object_name))
        if not obj:
            raise FileNotFoundError(object_name)
        return obj

    def get_object(self, bucket: str, object_name: str) -> FakeObject:
        obj = self._objects.get((bucket, object_name))
        if not obj:
            raise FileNotFoundError(object_name)
        return obj


@pytest.fixture()
def fake_minio(monkeypatch: pytest.MonkeyPatch) -> FakeMinio:
    client = FakeMinio()

    monkeypatch.setattr(s3_module, "get_minio_client", lambda: client)
    monkeypatch.setattr(routes_docs, "get_minio_client", lambda: client)
    monkeypatch.setattr(tasks_module, "get_minio_client", lambda: client)
    return client


@pytest.fixture()
def scanner_stub() -> Iterator[None]:
    set_scanner(FakeScanner())
    try:
        yield
    finally:
        set_scanner(NoopScanner())


def _patch_json_columns() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.type.__class__.__name__ == "JSONB":
                column.type = JSON()


@pytest.fixture()
def engine() -> Iterator:
    _patch_json_columns()
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_functions(dbapi_connection, _):  # pragma: no cover - sqlite setup
        dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid.uuid4()))

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def session_factory(engine) -> sessionmaker:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)

    @event.listens_for(factory, "before_flush")
    def _ensure_uuid_defaults(session, flush_context, instances):  # pragma: no cover - fixture wiring
        for obj in session.new:
            mapper = getattr(obj.__class__, "__mapper__", None)
            if not mapper or "id" not in mapper.c:
                continue
            column = mapper.c["id"]
            column_type = getattr(column.type, "python_type", None)
            if column_type is uuid.UUID or isinstance(column.type, PGUUID):
                if getattr(obj, "id", None) is None:
                    obj.id = uuid.uuid4()

    return factory


def _session_ctx(factory: sessionmaker):
    def _get_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _get_session


@pytest.fixture()
def ingest_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    calls: list[tuple[str, str | None]] = []

    class _Task:
        def delay(self, document_id: str, job_id: str | None = None) -> None:
            calls.append((document_id, job_id))

    monkeypatch.setattr(tasks_module, "ingest_document", _Task())
    monkeypatch.setattr(routes_docs, "ingest_document", _Task())
    return calls


@pytest.fixture()
def crawl_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    class _Task:
        def delay(self, job_id: str) -> SimpleNamespace:
            calls.append(job_id)
            return SimpleNamespace(id=f"task-{job_id}")

    monkeypatch.setattr(tasks_module, "crawl_site", _Task())
    return calls


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker, fake_minio: FakeMinio, scanner_stub) -> TestClient:
    session_ctx = _session_ctx(session_factory)

    monkeypatch.setattr(db_module, "SessionLocal", session_factory)
    monkeypatch.setattr(routes_chat, "SessionLocal", session_factory)
    monkeypatch.setattr(tasks_module, "SessionLocal", session_factory)

    app = create_app()
    app.dependency_overrides[db_module.get_session] = session_ctx
    app.dependency_overrides[routes_docs.get_session] = session_ctx
    app.dependency_overrides[routes_crawl.get_session] = session_ctx
    app.dependency_overrides[routes_chat.get_session] = session_ctx
    return TestClient(app)


@pytest.fixture()
def auth_session() -> dict[str, str]:
    user_id = str(uuid.uuid4())
    csrf_token = "test-csrf-token"
    signer = itsdangerous.TimestampSigner(settings.SESSION_SECRET)
    payload = base64.b64encode(
        json.dumps({"user_id": user_id, "csrf_token": csrf_token}).encode("utf-8")
    )
    cookie = signer.sign(payload).decode("utf-8")
    return {"cookie": cookie, "user_id": user_id, "csrf_token": csrf_token}
