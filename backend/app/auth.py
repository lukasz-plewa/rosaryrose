"""Authentication.

- Password hashing: bcrypt directly (passlib has compatibility issues with
  bcrypt 4.x).
- Auth token: JWT stored in an httpOnly cookie named 'access_token'.
- FastAPI dependencies:
    get_current_user   - logged-in user (raises 401)
    get_approved_user  - logged-in AND approved (raises 403 if pending)
    get_admin_user     - logged-in AND email == ADMIN_EMAIL from config
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError
from sqlalchemy import select

from .config import settings
from .models import User, get_session


# --- Passwords ---

def hash_password(plain: str) -> str:
    # bcrypt has a 72-byte input limit; truncate for safety.
    pwd = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pwd = plain.encode("utf-8")[:72]
        return bcrypt.checkpw(pwd, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- JWT ---

def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        return int(sub) if sub else None
    except (JWTError, ValueError):
        return None


# --- FastAPI dependencies ---

COOKIE_NAME = "access_token"


def get_current_user(request: Request) -> User:
    """Returns the logged-in user from the cookie. Raises 401 if missing/invalid."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Brak tokenu")

    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Zły token")

    with get_session() as db:
        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Konto nieaktywne")
        return user


def get_approved_user(current: User = Depends(get_current_user)) -> User:
    """Logged-in AND approved. Admin (matched by ADMIN_EMAIL) is always treated as approved."""
    if current.email == settings.admin_email or current.is_approved:
        return current
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Konto oczekuje na zatwierdzenie przez administratora",
    )


def get_admin_user(current: User = Depends(get_current_user)) -> User:
    """Admin only (email matches ADMIN_EMAIL from env)."""
    if current.email != settings.admin_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tylko dla administratora")
    return current


# --- Helpers ---

def find_user_by_email(db, email: str) -> Optional[User]:
    return db.scalars(select(User).where(User.email == email)).first()


def is_admin(user: User) -> bool:
    return user.email == settings.admin_email
