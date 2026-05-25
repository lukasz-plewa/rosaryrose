"""User-related service operations (kept separate from rose service)."""
from __future__ import annotations
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User
from .auth import hash_password
from .config import settings


def list_users(db: Session, pending_only: bool = False) -> List[User]:
    q = select(User).order_by(User.created_at.desc())
    if pending_only:
        q = q.where(User.is_approved == False)  # noqa: E712
    return list(db.scalars(q).all())


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def find_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalars(select(User).where(User.email == email)).first()


def find_user_by_google_sub(db: Session, sub: str) -> Optional[User]:
    return db.scalars(select(User).where(User.google_sub == sub)).first()


def create_user_with_password(db: Session, email: str, password: str,
                               full_name: str = "") -> User:
    """Creates a password account. Auto-approved only if email == ADMIN_EMAIL."""
    is_admin = email == settings.admin_email
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_approved=is_admin,  # admin is auto-approved
        is_active=True,
    )
    db.add(user); db.commit(); db.refresh(user)
    return user


def create_user_from_google(db: Session, email: str, google_sub: str,
                             full_name: str = "") -> User:
    """Creates an account from Google OAuth data."""
    is_admin = email == settings.admin_email
    user = User(
        email=email,
        google_sub=google_sub,
        full_name=full_name,
        is_approved=is_admin,
        is_active=True,
    )
    db.add(user); db.commit(); db.refresh(user)
    return user


def attach_google_to_user(db: Session, user: User, google_sub: str) -> User:
    """Links a Google sub to an existing account (when a password user later signs in via Google)."""
    user.google_sub = google_sub
    db.commit(); db.refresh(user)
    return user


def approve_user(db: Session, user_id: int) -> Optional[User]:
    u = db.get(User, user_id)
    if not u: return None
    u.is_approved = True
    db.commit(); db.refresh(u)
    return u


def reject_user(db: Session, user_id: int) -> bool:
    """Deletes a pending account.

    We refuse to delete already-approved accounts to avoid orphaning their roses.
    """
    u = db.get(User, user_id)
    if not u: return False
    if u.is_approved:
        return False
    db.delete(u); db.commit()
    return True
