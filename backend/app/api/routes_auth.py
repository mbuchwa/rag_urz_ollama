"""Authentication endpoints leveraging OIDC."""
from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pydantic import BaseModel

from ..auth import get_oidc_client
from ..core.config import settings
from ..core.db import get_session
from ..models import Namespace, NamespaceMember, User

router = APIRouter()

logger = logging.getLogger(__name__)


class LocalLoginRequest(BaseModel):
    """Request payload for the development local login flow."""

    email: str
    password: str


@router.get("/login", summary="Initiate OIDC login")
async def oidc_login(request: Request) -> Any:
    """Redirect the user to the OIDC provider for authentication."""

    oauth = get_oidc_client()
    return await oauth.oidc.authorize_redirect(request, settings.OIDC_REDIRECT_URI)


@router.get("/callback", summary="OIDC redirect URI")
async def oidc_callback(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    """Process the authorization code callback and establish a session."""

    oauth = get_oidc_client()

    try:
        token = await oauth.oidc.authorize_access_token(request)
        claims = await _extract_claims(oauth, request, token)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("OIDC callback failed: %s", exc)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/login?error=oidc",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        logger.error("OIDC callback missing required claims: sub=%s email=%s", sub, email)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL.rstrip('/')}/login?error=profile",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    display_name = (
        claims.get("name")
        or claims.get("preferred_username")
        or claims.get("given_name")
        or email
    )

    user = await _upsert_user(session, sub=sub, email=email, display_name=display_name)

    request.session.clear()
    request.session["user_id"] = str(user.id)
    request.session["csrf_token"] = secrets.token_urlsafe(32)

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}/callback",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/me", summary="Current user profile")
async def read_current_user(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Return the authenticated user profile and namespaces."""

    raw_user_id = request.session.get("user_id")
    if not raw_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        user_uuid = uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    stmt = (
        select(User)
        .options(selectinload(User.namespaces).selectinload(NamespaceMember.namespace))
        .where(User.id == user_uuid)
    )
    user = session.execute(stmt).scalar_one_or_none()
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    csrf_token = request.session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = csrf_token

    namespaces: list[dict[str, Any]] = []
    for membership in user.namespaces:
        namespace = membership.namespace
        if not namespace:
            continue
        namespaces.append(
            {
                "id": str(namespace.id),
                "slug": namespace.slug,
                "name": namespace.name,
                "role": membership.role,
            }
        )

    namespaces.sort(key=lambda item: item["name"])

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
        },
        "namespaces": namespaces,
        "csrf_token": csrf_token,
    }


@router.post("/logout", summary="Terminate the current session")
async def logout(request: Request) -> JSONResponse:
    """Clear the session cookie for the authenticated user."""

    request.session.clear()
    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME,
        path="/",
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/local-login", summary="Authenticate with a development account")
async def local_login(
    payload: LocalLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Allow development logins using static credentials."""

    if not settings.LOCAL_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    expected_email = settings.LOCAL_LOGIN_EMAIL.strip().lower()
    expected_password = settings.LOCAL_LOGIN_PASSWORD
    if isinstance(expected_password, str):
        expected_password = expected_password.strip()
    else:  # pragma: no cover - defensive
        expected_password = str(expected_password)

    provided_email = payload.email.strip().lower()
    provided_password = payload.password.strip()

    if provided_email != expected_email or provided_password != expected_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    user = await _upsert_user(
        session,
        sub=f"local:{expected_email}",
        email=expected_email,
        display_name=payload.email,
    )

    request.session.clear()
    request.session["user_id"] = str(user.id)
    request.session["csrf_token"] = secrets.token_urlsafe(32)

    return JSONResponse({"detail": "Logged in"})


async def _extract_claims(oauth: Any, request: Request, token: dict[str, Any]) -> dict[str, Any]:
    """Resolve user claims from the ID token or userinfo endpoint."""

    userinfo = await oauth.oidc.userinfo(token=token)
    if userinfo:
        return dict(userinfo)
    return dict(oauth.oidc.parse_id_token(request, token))


async def _upsert_user(
    session: Session, *, sub: str, email: str, display_name: str | None
) -> User:
    """Create or update a user based on the OIDC subject and email."""

    stmt = select(User).where(User.oidc_sub == sub)
    user = session.execute(stmt).scalar_one_or_none()

    if user is None:
        stmt = select(User).where(User.email == email)
        user = session.execute(stmt).scalar_one_or_none()

    if user is None:
        user = User(email=email, display_name=display_name, oidc_sub=sub)
        session.add(user)
    else:
        user.email = email
        user.display_name = display_name
        if not user.oidc_sub:
            user.oidc_sub = sub

    session.flush()
    if not user.namespaces:
        slug = settings.DEFAULT_NAMESPACE_SLUG.strip()
        if slug:
            stmt = select(Namespace).where(Namespace.slug == slug)
            namespace = session.execute(stmt).scalar_one_or_none()
            if namespace is None:
                namespace_name = settings.DEFAULT_NAMESPACE_NAME or slug.replace("-", " ").title()
                namespace = Namespace(slug=slug, name=namespace_name)
                session.add(namespace)
                session.flush()

            membership = NamespaceMember(namespace=namespace, user=user)
            session.add(membership)
            session.flush()
    return user
