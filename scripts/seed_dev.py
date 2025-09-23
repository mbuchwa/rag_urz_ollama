"""Seed the development database with a default user and namespace."""
from __future__ import annotations

import sys
from contextlib import AbstractContextManager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.db import get_session
from backend.app.models import Namespace, NamespaceMember, User


def _get_or_create_user(session, email: str, display_name: str | None = None) -> User:
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(email=email, display_name=display_name)
        session.add(user)
        session.flush()
    return user


def _get_or_create_namespace(session, slug: str, name: str) -> Namespace:
    namespace = session.query(Namespace).filter(Namespace.slug == slug).one_or_none()
    if namespace is None:
        namespace = Namespace(slug=slug, name=name)
        session.add(namespace)
        session.flush()
    return namespace


def _ensure_membership(session, user: User, namespace: Namespace, role: str = "owner") -> NamespaceMember:
    membership = (
        session.query(NamespaceMember)
        .filter(
            NamespaceMember.namespace_id == namespace.id,
            NamespaceMember.user_id == user.id,
        )
        .one_or_none()
    )
    if membership is None:
        membership = NamespaceMember(namespace_id=namespace.id, user_id=user.id, role=role)
        session.add(membership)
        session.flush()
    return membership


def main(context: AbstractContextManager | None = None) -> None:
    """Entry point for seeding data."""

    session_ctx = context or get_session()
    with session_ctx as session:
        user = _get_or_create_user(session, email="dev@example.com", display_name="Dev User")
        namespace = _get_or_create_namespace(session, slug="dev", name="Development")
        membership = _ensure_membership(session, user, namespace)

        print("Seeded development data:")
        print(f"  User ID: {user.id}")
        print(f"  Namespace ID: {namespace.id}")
        print(f"  Membership ID: {membership.id}")


if __name__ == "__main__":
    main()
