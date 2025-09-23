"""FastAPI application entry point for the RAG platform."""
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .api import routes_admin, routes_auth, routes_chat, routes_crawl, routes_docs
from .core.config import settings
from .core.middleware import AuthenticatedSessionMiddleware


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET,
        session_cookie=settings.SESSION_COOKIE_NAME,
        same_site="lax",
        https_only=settings.SESSION_COOKIE_SECURE,
    )
    app.add_middleware(AuthenticatedSessionMiddleware, api_prefix="/api")

    app.include_router(routes_admin.router, prefix="/admin", tags=["admin"])
    app.include_router(routes_auth.router, prefix="/auth", tags=["auth"])
    app.include_router(routes_chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(routes_crawl.router, prefix="/api/crawl", tags=["crawl"])
    app.include_router(routes_docs.router, prefix="/api/docs", tags=["docs"])

    @app.get("/admin/health", tags=["admin"], summary="Service health check")
    async def health() -> dict[str, str]:
        """Return a simple health payload for docker-compose smoke tests."""
        return {"status": "ok"}

    return app


app = create_app()
