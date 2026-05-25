"""Business operations on roses.

This is where "current composition of a rose" and "how to change it" live.
The most subtle bit is set_position_for_period - see its docstring for details.
"""
from __future__ import annotations
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from .models import Rose, Person, RoseMembership
from .rotation import RoseConfig, generate_periods, find_period_for_month


# ===== ROSE =====

def list_roses(db: Session, owner_id: Optional[int] = None,
               include_all: bool = False) -> List[Rose]:
    """Lists roses.

    - include_all=True: admin sees everything
    - owner_id != None: a leader sees only their own roses
    """
    q = select(Rose).order_by(Rose.name)
    if not include_all:
        q = q.where(Rose.owner_id == owner_id)
    return list(db.scalars(q).all())


def get_rose(db: Session, rose_id: int) -> Optional[Rose]:
    return db.get(Rose, rose_id)


def create_rose(db: Session, name: str, subtitle: str, start_date: date,
                change_day: int, excluded_months: List[int],
                owner_id: Optional[int] = None) -> Rose:
    r = Rose(name=name, subtitle=subtitle, start_date=start_date,
             change_day=change_day, excluded_months=excluded_months,
             owner_id=owner_id)
    db.add(r); db.commit(); db.refresh(r)
    return r


def update_rose(db: Session, rose_id: int, **fields) -> Optional[Rose]:
    r = db.get(Rose, rose_id)
    if not r:
        return None
    for k, v in fields.items():
        if hasattr(r, k) and v is not None:
            setattr(r, k, v)
    db.commit(); db.refresh(r)
    return r


def delete_rose(db: Session, rose_id: int) -> bool:
    r = db.get(Rose, rose_id)
    if not r: return False
    db.delete(r); db.commit()
    return True


# ===== PERSON =====

def list_persons(db: Session, rose_id: int, include_inactive: bool = False) -> List[Person]:
    q = select(Person).where(Person.rose_id == rose_id)
    if not include_inactive:
        q = q.where(Person.active == True)  # noqa: E712
    return list(db.scalars(q.order_by(Person.full_name)).all())


def create_person(db: Session, rose_id: int, full_name: str,
                  email: Optional[str] = None, phone: Optional[str] = None,
                  notes: Optional[str] = None) -> Person:
    p = Person(rose_id=rose_id, full_name=full_name, email=email, phone=phone, notes=notes)
    db.add(p); db.commit(); db.refresh(p)
    return p


def update_person(db: Session, person_id: int, **fields) -> Optional[Person]:
    p = db.get(Person, person_id)
    if not p: return None
    for k, v in fields.items():
        if hasattr(p, k):
            setattr(p, k, v)
    db.commit(); db.refresh(p)
    return p


def delete_person(db: Session, person_id: int) -> bool:
    """Soft delete: only flips active=False, so historic memberships remain readable."""
    p = db.get(Person, person_id)
    if not p: return False
    p.active = False
    db.commit()
    return True


# ===== MEMBERSHIP - the temporal core =====

def get_composition_at(db: Session, rose_id: int, at_date: date) -> List[Tuple[int, Optional[Person]]]:
    """Returns the composition of the rose effective on `at_date`.

    A list of (position, person|None) of length 20.
    """
    q = select(RoseMembership).where(
        and_(
            RoseMembership.rose_id == rose_id,
            RoseMembership.valid_from <= at_date,
            or_(RoseMembership.valid_to == None, RoseMembership.valid_to >= at_date),  # noqa: E711
        )
    )
    rows = db.scalars(q).all()
    by_pos = {row.position: row.person for row in rows}
    return [(pos, by_pos.get(pos)) for pos in range(1, 21)]


def set_position_for_period(db: Session, rose_id: int, position: int,
                             person_id: Optional[int], effective_from: date) -> RoseMembership:
    """Changes the occupant of `position` starting on `effective_from`.

    Logic:
    1. Find the currently effective row (valid_from <= effective_from AND
       (valid_to IS NULL OR valid_to >= effective_from)).
    2. If it exists and already references the same person - no-op.
    3. If it exists - close it (set valid_to = effective_from - 1 day).
       Exception: if the old row's valid_from equals effective_from (same-day
       overwrite), update it in place instead of creating a duplicate.
    4. Insert a new row with valid_from = effective_from and valid_to = NULL.
    5. (Out of scope for now: scheduling a future change that splits an
       existing future row.)
    """
    if not 1 <= position <= 20:
        raise ValueError(f"Pozycja musi być 1..20, dostałem {position}")

    current = db.scalars(
        select(RoseMembership).where(
            and_(
                RoseMembership.rose_id == rose_id,
                RoseMembership.position == position,
                RoseMembership.valid_from <= effective_from,
                or_(RoseMembership.valid_to == None,  # noqa: E711
                    RoseMembership.valid_to >= effective_from),
            )
        )
    ).first()

    if current and current.person_id == person_id:
        return current  # no change

    if current:
        if current.valid_from == effective_from:
            # Same-day overwrite
            current.person_id = person_id
            db.commit(); db.refresh(current)
            return current
        # Close the old row
        current.valid_to = date.fromordinal(effective_from.toordinal() - 1)

    new_row = RoseMembership(
        rose_id=rose_id, position=position, person_id=person_id,
        valid_from=effective_from, valid_to=None,
    )
    db.add(new_row); db.commit(); db.refresh(new_row)
    return new_row


def history_for_position(db: Session, rose_id: int, position: int) -> List[RoseMembership]:
    """Returns the full assignment history for a position, chronologically."""
    q = select(RoseMembership).where(
        and_(RoseMembership.rose_id == rose_id, RoseMembership.position == position)
    ).order_by(RoseMembership.valid_from)
    return list(db.scalars(q).all())


# ===== HELPER: build a RoseConfig for rotation.py =====

def build_config_for_date(db: Session, rose: Rose, at_date: date) -> RoseConfig:
    """Builds a RoseConfig (the input to rotation.py) using the composition on `at_date`."""
    composition = get_composition_at(db, rose.id, at_date)
    people = [(p.full_name if p else "") for _, p in composition]
    return RoseConfig(
        name=rose.name,
        subtitle=rose.subtitle or "",
        start_date=rose.start_date,
        change_day=rose.change_day,
        excluded_months=list(rose.excluded_months or []),
        people=people,
    )


def period_start_for_month(db: Session, rose: Rose, year: int, month: int) -> Optional[date]:
    """Returns the period_start date for the period labelled (year, month)."""
    periods = generate_periods(
        RoseConfig(rose.name, rose.subtitle or "", rose.start_date,
                   rose.change_day, list(rose.excluded_months or []), [""] * 20),
        until=date(year + 1, 12, 31),
    )
    p = find_period_for_month(periods, year, month)
    return p.period_start if p else None
