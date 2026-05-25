"""Database models.

Phase 3: added User and owner_id on Rose for authorization.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (String, Integer, Date, DateTime, ForeignKey, JSON, Boolean,
                        create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker, Session)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    # hashed_password may be None if the user only signs in via Google
    hashed_password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # google_sub = unique Google user id ('sub' from the OAuth token), if linked
    google_sub: Mapped[Optional[str]] = mapped_column(String(200), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    # Admin approval flag. The admin (matched by ADMIN_EMAIL env) is always considered approved.
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    roses: Mapped[List["Rose"]] = relationship(back_populates="owner")


class Rose(Base):
    __tablename__ = "roses"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str] = mapped_column(String(200), default="")
    start_date: Mapped[date] = mapped_column(Date)
    change_day: Mapped[int] = mapped_column(Integer, default=25)
    excluded_months: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    owner: Mapped[Optional["User"]] = relationship(back_populates="roses")
    persons: Mapped[List["Person"]] = relationship(
        back_populates="rose", cascade="all, delete-orphan")
    memberships: Mapped[List["RoseMembership"]] = relationship(
        back_populates="rose", cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    rose_id: Mapped[int] = mapped_column(ForeignKey("roses.id"))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    rose: Mapped["Rose"] = relationship(back_populates="persons")


class RoseMembership(Base):
    """Temporal record: a person held a position in a rose during a period.

    Each row represents (rose, position) being assigned to a specific person
    from valid_from up to and including valid_to (NULL = still current).

    Rules:
    - position is 1..20
    - For a given (rose_id, position) and a given day there is EXACTLY ONE row
      where valid_from <= day AND (valid_to IS NULL OR valid_to >= day)
    - person_id may be NULL, meaning "vacant" during that period

    The temporal design preserves history: changing the roster never overwrites
    past data, it just closes the old row (sets valid_to) and opens a new one.
    """
    __tablename__ = "rose_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    rose_id: Mapped[int] = mapped_column(ForeignKey("roses.id"))
    position: Mapped[int] = mapped_column(Integer)
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("persons.id"), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    rose: Mapped["Rose"] = relationship(back_populates="memberships")
    person: Mapped[Optional["Person"]] = relationship()


# --- Engine setup ---

_engine = None
_SessionLocal = None


def init_db(db_url: Optional[str] = None) -> None:
    global _engine, _SessionLocal
    from .config import settings
    url = db_url or settings.database_url
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    _engine = create_engine(url, echo=False, future=True, connect_args=connect_args)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("init_db() not called")
    return _SessionLocal()
