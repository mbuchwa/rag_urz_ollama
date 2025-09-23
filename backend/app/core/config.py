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

    OIDC_CLIENT_ID: str = Field(default="client-id")
    OIDC_CLIENT_SECRET: str = Field(default="client-secret")
    OIDC_ISSUER: str = Field(default="https://example.com/oidc")
    OIDC_REDIRECT_URI: str = Field(default="http://localhost:8000/auth/callback")

    FRONTEND_URL: str = Field(default="http://localhost:3000")

    SESSION_SECRET: str = Field(default="change-me")
    SESSION_COOKIE_NAME: str = Field(default="rag_session")
    SESSION_COOKIE_SECURE: bool = Field(default=True)

    OLLAMA_HOST: str = Field(default="http://ollama:11434")

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
