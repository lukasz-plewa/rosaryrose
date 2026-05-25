"""Auth endpoints - register, password login, Google OAuth login, logout, /me.

User-facing error messages (HTTPException details) are kept in Polish because
the UI is Polish; code, comments and docstrings are in English.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from authlib.integrations.starlette_client import OAuth, OAuthError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import users_service
from .auth import (verify_password, create_access_token, COOKIE_NAME,
                   get_current_user, is_admin)
from .config import settings
from .models import User, get_session


router = APIRouter(prefix="/api/auth", tags=["auth"])


# --- Google OAuth setup ---

oauth = OAuth()
if settings.google_client_id and settings.google_client_secret:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


# --- Schemas ---

class RegisterIn(BaseModel):
    email: str
    password: str
    full_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_approved: bool
    is_admin: bool


def _user_to_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, email=u.email, full_name=u.full_name,
        is_approved=u.is_approved or is_admin(u),
        is_admin=is_admin(u),
    )


def _set_login_cookie(response: Response, user_id: int):
    token = create_access_token(user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_hours * 3600,
    )


# --- Endpoints ---

@router.post("/register", response_model=UserOut)
def register(data: RegisterIn, response: Response):
    """Password registration.

    A new user starts as pending; the admin must approve them before they
    can use the app. The exception is when the registered email matches
    ADMIN_EMAIL - that account is auto-approved.
    """
    if len(data.password) < 6:
        raise HTTPException(400, "Hasło musi mieć co najmniej 6 znaków")
    with get_session() as db:
        if users_service.find_user_by_email(db, data.email):
            raise HTTPException(400, "Konto z tym e-mailem już istnieje")
        user = users_service.create_user_with_password(
            db, email=data.email, password=data.password, full_name=data.full_name)
        _set_login_cookie(response, user.id)
        return _user_to_out(user)


@router.post("/login", response_model=UserOut)
def login_password(data: LoginIn, response: Response):
    with get_session() as db:
        user = users_service.find_user_by_email(db, data.email)
        if not user or not user.hashed_password or not verify_password(data.password, user.hashed_password):
            raise HTTPException(401, "Nieprawidłowy e-mail lub hasło")
        if not user.is_active:
            raise HTTPException(401, "Konto wyłączone")
        _set_login_cookie(response, user.id)
        return _user_to_out(user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return _user_to_out(current)


# --- Google OAuth ---

@router.get("/google/login")
async def google_login(request: Request):
    """Redirects to Google. After consent Google redirects back to /api/auth/google/callback."""
    if not settings.google_client_id:
        raise HTTPException(503, "Logowanie Google nie jest skonfigurowane")
    redirect_uri = f"{settings.base_url.rstrip('/')}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request):
    """Callback from Google. Finds or creates the user, sets cookie, redirects to /."""
    from fastapi.responses import RedirectResponse
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        raise HTTPException(400, f"Błąd autoryzacji Google: {e.error}")

    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(400, "Brak danych użytkownika z Google")

    google_sub = userinfo["sub"]
    email = userinfo.get("email")
    name = userinfo.get("name") or ""
    if not email:
        raise HTTPException(400, "Google nie zwróciło e-maila")

    with get_session() as db:
        # 1. Look up by sub first (Google's unique id - the safest match).
        user = users_service.find_user_by_google_sub(db, google_sub)
        # 2. Otherwise, look up by email (user may have registered with a password earlier).
        if not user:
            user = users_service.find_user_by_email(db, email)
            if user:
                users_service.attach_google_to_user(db, user, google_sub)
        # 3. Otherwise, create a new account.
        if not user:
            user = users_service.create_user_from_google(
                db, email=email, google_sub=google_sub, full_name=name)

        if not user.is_active:
            raise HTTPException(401, "Konto wyłączone")

        # Set cookie and redirect to the frontend.
        response = RedirectResponse(url="/", status_code=302)
        _set_login_cookie(response, user.id)
        return response


# --- Admin endpoints for user management ---

admin_router = APIRouter(prefix="/api/admin/users", tags=["admin"])


@admin_router.get("", response_model=list[UserOut])
def list_all_users(current: User = Depends(get_current_user)):
    if not is_admin(current):
        raise HTTPException(403, "Tylko dla administratora")
    with get_session() as db:
        return [_user_to_out(u) for u in users_service.list_users(db)]


@admin_router.get("/pending", response_model=list[UserOut])
def list_pending_users(current: User = Depends(get_current_user)):
    if not is_admin(current):
        raise HTTPException(403, "Tylko dla administratora")
    with get_session() as db:
        return [_user_to_out(u) for u in users_service.list_users(db, pending_only=True)]


@admin_router.post("/{user_id}/approve", response_model=UserOut)
def approve(user_id: int, current: User = Depends(get_current_user)):
    if not is_admin(current):
        raise HTTPException(403, "Tylko dla administratora")
    with get_session() as db:
        u = users_service.approve_user(db, user_id)
        if not u: raise HTTPException(404, "Nie znaleziono użytkownika")
        return _user_to_out(u)


@admin_router.delete("/{user_id}")
def reject(user_id: int, current: User = Depends(get_current_user)):
    if not is_admin(current):
        raise HTTPException(403, "Tylko dla administratora")
    with get_session() as db:
        ok = users_service.reject_user(db, user_id)
        if not ok: raise HTTPException(400, "Nie można odrzucić tego konta (już zatwierdzone lub nie istnieje)")
        return {"ok": True}
