"""Application configuration - read from ENV with sensible dev defaults.

In production (Railway) set these as service variables:
- ADMIN_EMAIL=your@email.com
- SECRET_KEY=<long random string>
- DATABASE_URL=sqlite:////data/roza.db (production - with volume)
- GOOGLE_CLIENT_ID=...
- GOOGLE_CLIENT_SECRET=...
- BASE_URL=https://your-app.up.railway.app
"""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import secrets


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Admin (a single email is the "permanent" admin) ---
    admin_email: str = "admin@example.com"

    # --- JWT ---
    # In production, set a STABLE SECRET_KEY - otherwise every restart
    # invalidates everyone's session.
    secret_key: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24 * 30  # 30 days

    # --- Database ---
    database_url: str = "sqlite:///./roza.db"

    # --- Google OAuth (optional - without these, Google login is disabled) ---
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # --- Misc ---
    base_url: str = "http://127.0.0.1:8000"  # used for the Google OAuth callback
    cookie_secure: bool = False  # set to True in production (requires HTTPS)


settings = Settings()
