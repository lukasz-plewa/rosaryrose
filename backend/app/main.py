"""FastAPI - main entry point (Phase 3, with authentication).

All /api/roses/* endpoints require a logged-in AND approved user.
- A leader sees only their own roses (rose.owner_id == user.id).
- The admin (email matching ADMIN_EMAIL env) sees all roses.

The /api/auth/* endpoints are public; /api/admin/* is admin-only.

Error messages returned to the client are in Polish (UI is Polish);
code, comments and docstrings are in English.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Response, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import services
from .auth import get_approved_user, is_admin
from .auth_endpoints import router as auth_router, admin_router
from .config import settings
from .models import init_db, get_session, User, Rose
from .rotation import (generate_periods, find_period_for_month,
                       mystery_for, POLISH_MONTHS)
from .renderer import render_table


# --- Schemas ---

class RoseIn(BaseModel):
    name: str
    subtitle: str = ""
    start_date: date
    change_day: int = Field(25, ge=1, le=31)
    excluded_months: List[int] = Field(default_factory=list)


class RoseOut(RoseIn):
    id: int
    owner_id: Optional[int] = None
    owner_email: Optional[str] = None


class PersonIn(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class PersonOut(PersonIn):
    id: int
    rose_id: int
    active: bool


class CompositionEntryOut(BaseModel):
    position: int
    person_id: Optional[int]
    person_name: Optional[str]


class SetPositionIn(BaseModel):
    person_id: Optional[int]
    effective_from: date


class HistoryEntryOut(BaseModel):
    valid_from: date
    valid_to: Optional[date]
    person_id: Optional[int]
    person_name: Optional[str]


class MonthDataEntryOut(BaseModel):
    position: int
    person_name: Optional[str]
    mystery: str


class MonthDataOut(BaseModel):
    rose_id: int
    rose_name: str
    year: int
    month: int
    month_name: str
    period_start: date
    period_end: date
    entries: List[MonthDataEntryOut]


# --- App ---

app = FastAPI(title="Rosary Rose API")

# SessionMiddleware is required by Authlib (Google OAuth uses the session for state/nonce).
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# In production, the frontend is served by the same app, so CORS isn't strictly needed.
# It's useful in development when the frontend is served separately.
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router)
app.include_router(admin_router)


@app.on_event("startup")
def _startup():
    init_db()


# --- Helper: rose access check ---

def _get_rose_for_user(db, rose_id: int, user: User) -> Rose:
    """Loads a rose by id, checking that the user is allowed to access it.

    Raises 404 if the rose doesn't exist, 403 if the user is not allowed.
    """
    r = services.get_rose(db, rose_id)
    if not r:
        raise HTTPException(404, "Nie znaleziono róży")
    if not is_admin(user) and r.owner_id != user.id:
        raise HTTPException(403, "Brak dostępu do tej róży")
    return r


def _rose_to_out(r: Rose) -> RoseOut:
    return RoseOut(
        id=r.id, name=r.name, subtitle=r.subtitle, start_date=r.start_date,
        change_day=r.change_day, excluded_months=list(r.excluded_months or []),
        owner_id=r.owner_id,
        owner_email=(r.owner.email if r.owner else None),
    )


# --- ROSE ---

@app.get("/api/roses", response_model=List[RoseOut])
def api_list_roses(current: User = Depends(get_approved_user)):
    """Admin sees all roses; a leader sees only their own."""
    with get_session() as db:
        roses = services.list_roses(db, owner_id=current.id, include_all=is_admin(current))
        return [_rose_to_out(r) for r in roses]


@app.post("/api/roses", response_model=RoseOut)
def api_create_rose(data: RoseIn, current: User = Depends(get_approved_user)):
    with get_session() as db:
        r = services.create_rose(db, owner_id=current.id, **data.model_dump())
        return _rose_to_out(r)


@app.get("/api/roses/{rose_id}", response_model=RoseOut)
def api_get_rose(rose_id: int, current: User = Depends(get_approved_user)):
    with get_session() as db:
        r = _get_rose_for_user(db, rose_id, current)
        return _rose_to_out(r)


@app.put("/api/roses/{rose_id}", response_model=RoseOut)
def api_update_rose(rose_id: int, data: RoseIn,
                    current: User = Depends(get_approved_user)):
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)  # access check
        r = services.update_rose(db, rose_id, **data.model_dump())
        return _rose_to_out(r)


@app.delete("/api/roses/{rose_id}")
def api_delete_rose(rose_id: int, current: User = Depends(get_approved_user)):
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)
        services.delete_rose(db, rose_id)
        return {"ok": True}


# --- PERSON ---

@app.get("/api/roses/{rose_id}/persons", response_model=List[PersonOut])
def api_list_persons(rose_id: int, include_inactive: bool = False,
                     current: User = Depends(get_approved_user)):
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)
        return [PersonOut(id=p.id, rose_id=p.rose_id, full_name=p.full_name,
                          email=p.email, phone=p.phone, notes=p.notes, active=p.active)
                for p in services.list_persons(db, rose_id, include_inactive)]


@app.post("/api/roses/{rose_id}/persons", response_model=PersonOut)
def api_create_person(rose_id: int, data: PersonIn,
                      current: User = Depends(get_approved_user)):
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)
        p = services.create_person(db, rose_id, **data.model_dump())
        return PersonOut(id=p.id, rose_id=p.rose_id, **data.model_dump(), active=True)


@app.put("/api/persons/{person_id}", response_model=PersonOut)
def api_update_person(person_id: int, data: PersonIn,
                      current: User = Depends(get_approved_user)):
    with get_session() as db:
        # Check that the user has access to the rose this person belongs to.
        from .models import Person
        existing = db.get(Person, person_id)
        if not existing:
            raise HTTPException(404, "Nie znaleziono osoby")
        _get_rose_for_user(db, existing.rose_id, current)
        p = services.update_person(db, person_id, **data.model_dump())
        return PersonOut(id=p.id, rose_id=p.rose_id, full_name=p.full_name,
                         email=p.email, phone=p.phone, notes=p.notes, active=p.active)


@app.delete("/api/persons/{person_id}")
def api_delete_person(person_id: int, current: User = Depends(get_approved_user)):
    with get_session() as db:
        from .models import Person
        existing = db.get(Person, person_id)
        if not existing:
            raise HTTPException(404, "Nie znaleziono osoby")
        _get_rose_for_user(db, existing.rose_id, current)
        services.delete_person(db, person_id)
        return {"ok": True}


# --- COMPOSITION ---

@app.get("/api/roses/{rose_id}/composition", response_model=List[CompositionEntryOut])
def api_composition(rose_id: int, at: Optional[date] = None,
                    current: User = Depends(get_approved_user)):
    if at is None: at = date.today()
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)
        comp = services.get_composition_at(db, rose_id, at)
        return [CompositionEntryOut(position=pos, person_id=(p.id if p else None),
                                     person_name=(p.full_name if p else None))
                for pos, p in comp]


@app.put("/api/roses/{rose_id}/composition/{position}")
def api_set_position(rose_id: int, position: int, data: SetPositionIn,
                     current: User = Depends(get_approved_user)):
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)
        services.set_position_for_period(db, rose_id, position,
                                          data.person_id, data.effective_from)
        return {"ok": True}


@app.get("/api/roses/{rose_id}/positions/{position}/history",
         response_model=List[HistoryEntryOut])
def api_position_history(rose_id: int, position: int,
                         current: User = Depends(get_approved_user)):
    with get_session() as db:
        _get_rose_for_user(db, rose_id, current)
        hist = services.history_for_position(db, rose_id, position)
        return [HistoryEntryOut(valid_from=h.valid_from, valid_to=h.valid_to,
                                 person_id=h.person_id,
                                 person_name=(h.person.full_name if h.person else None))
                for h in hist]


# --- MONTH DATA ---

@app.get("/api/roses/{rose_id}/month", response_model=MonthDataOut)
def api_month(rose_id: int, year: int = Query(...), month: int = Query(..., ge=1, le=12),
              current: User = Depends(get_approved_user)):
    with get_session() as db:
        rose = _get_rose_for_user(db, rose_id, current)

        ps = services.period_start_for_month(db, rose, year, month)
        if not ps: raise HTTPException(404, f"Brak okresu dla {year}-{month:02d}")

        composition = services.get_composition_at(db, rose_id, ps)
        cfg = services.build_config_for_date(db, rose, ps)
        periods = generate_periods(cfg, until=date(year + 1, 12, 31))
        p = find_period_for_month(periods, year, month)
        if not p: raise HTTPException(404, "Brak okresu")

        entries = []
        for pos, person in composition:
            entries.append(MonthDataEntryOut(
                position=pos,
                person_name=(person.full_name if person else None),
                mystery=mystery_for(pos, p.cycle_index),
            ))
        return MonthDataOut(
            rose_id=rose_id, rose_name=rose.name,
            year=year, month=month, month_name=POLISH_MONTHS[month],
            period_start=p.period_start, period_end=p.period_end,
            entries=entries,
        )


# --- PNG ---

@app.get("/api/roses/{rose_id}/png")
def api_png(rose_id: int, year: Optional[int] = None, month: Optional[int] = None,
            year_to: Optional[int] = None, month_to: Optional[int] = None,
            current: User = Depends(get_approved_user)):
    if year is None or month is None:
        today = date.today()
        year, month = today.year, today.month
    with get_session() as db:
        rose = _get_rose_for_user(db, rose_id, current)
        ps = services.period_start_for_month(db, rose, year, month)
        if not ps: raise HTTPException(404, "Brak okresu dla podanego miesiąca")

        cfg = services.build_config_for_date(db, rose, ps)
        end_y = (year_to or year) + 2
        periods = generate_periods(cfg, until=date(end_y, 12, 31))

        chosen = []
        if year_to and month_to:
            y, m = year, month
            while (y, m) <= (year_to, month_to):
                p = find_period_for_month(periods, y, m)
                if p and p not in chosen: chosen.append(p)
                m += 1
                if m > 12: m = 1; y += 1
        else:
            p = find_period_for_month(periods, year, month)
            if not p: raise HTTPException(404, "Brak okresu")
            chosen = [p]

        png_bytes = render_table(cfg, chosen, include_note=True)
        return Response(content=png_bytes, media_type="image/png")


# --- FRONTEND ---

# Try several locations for the frontend (dev vs Docker layouts).
def _find_frontend_dir() -> Optional[Path]:
    here = Path(__file__).resolve().parent  # .../app
    candidates = [
        here.parent.parent / "frontend",  # dev: backend/../frontend
        here.parent / "frontend",          # Docker: /app/frontend (when backend/app is at /app)
        Path("/app/frontend"),             # explicit fallback
    ]
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c
    return None


FRONTEND_DIR = _find_frontend_dir()
if FRONTEND_DIR is not None:
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")
