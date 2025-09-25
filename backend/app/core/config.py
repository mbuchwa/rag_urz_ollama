"""Application configuration powered by Pydantic settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global application settings loaded from environment variables."""

    PROJECT_NAME: str = Field(default="URZ RAG Platform")
    VERSION: str = Field(default="0.1.0")

    DATABASE_URL: str = Field(default="postgresql+psycopg://postgres:postgres@db:5432/postgres")
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    MINIO_ENDPOINT: str = Field(default="minio:9000")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin")
    MINIO_SECRET_KEY: str = Field(default="minioadmin")
    MINIO_BUCKET: str = Field(default="rag-data")
    MINIO_PUBLIC_ENDPOINT: str | None = Field(default=None)

    EMBEDDING_MODEL_NAME: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = Field(default=1536)

    RETRIEVAL_TOP_K: int = Field(default=5)
    RETRIEVAL_USE_RERANKER: bool = Field(default=False)
    RERANKER_CANDIDATE_MULTIPLIER: int = Field(default=3)

    OIDC_CLIENT_ID: str = Field(default="client-id")
    OIDC_CLIENT_SECRET: str = Field(default="client-secret")
    OIDC_ISSUER: str = Field(default="https://example.com/oidc")
    OIDC_REDIRECT_URI: str = Field(default="http://localhost:8000/auth/callback")

    FRONTEND_URL: str = Field(default="http://localhost:3000")

    SESSION_SECRET: str = Field(default="change-me")
    SESSION_COOKIE_NAME: str = Field(default="rag_session")
    SESSION_COOKIE_SECURE: bool = Field(default=False)

    LOCAL_LOGIN_ENABLED: bool = Field(default=True)
    LOCAL_LOGIN_EMAIL: str = Field(default="test@uni-heidelberg.de")
    LOCAL_LOGIN_PASSWORD: str = Field(default="testtest")

    OLLAMA_HOST: str = Field(default="http://host.docker.internal:11434")
    OLLAMA_MODEL: str = Field(default="gpt-oss-20b")
    OLLAMA_TIMEOUT: float = Field(default=120.0)

    CHAT_HISTORY_LIMIT: int = Field(default=12)

    UPLOAD_MAX_BYTES: int = Field(default=25 * 1024 * 1024)
    UPLOAD_ALLOWED_MIME_TYPES: tuple[str, ...] = Field(
        default=(
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/html",
            "application/xhtml+xml",
        )
    )

    RATE_LIMIT_CHAT_STREAM: str = Field(default="30/minute")
    RATE_LIMIT_INGESTION: str = Field(default="12/minute")
    RATE_LIMIT_CRAWL: str = Field(default="4/hour")

    DEFAULT_NAMESPACE_SLUG: str = Field(default="psychology")
    DEFAULT_NAMESPACE_NAME: str | None = Field(default="Psychology")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings(**overrides: Any) -> Settings:
    """Return cached settings instance to avoid repeated parsing."""

    if overrides:
        return Settings(**overrides)
    return Settings()


settings = get_settings()
