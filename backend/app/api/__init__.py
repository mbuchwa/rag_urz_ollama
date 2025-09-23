"""API package exports."""
from . import routes_admin, routes_auth, routes_chat, routes_crawl, routes_docs

__all__ = [
    "routes_admin",
    "routes_auth",
    "routes_chat",
    "routes_crawl",
    "routes_docs",
]
