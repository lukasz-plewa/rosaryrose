"""Mystery rotation logic.

Domain rules:
- 20 mysteries in a fixed order (Joyful 1-5, Light 1-5, Sorrowful 1-5, Glorious 1-5).
- 20 positions in a rose.
- Every "mystery month" each person advances to the next mystery (rotation by 1).
- In excluded months (typically July & August) the rotation does NOT happen -
  positions keep the previous mystery for the entire excluded period.
- A "mystery month" runs from change_day of one month to change_day-1 of the next.
  Example: change_day=25 -> "May" mystery month = April 25th to May 24th.

Polish UI strings (mystery names, month names) are kept here because the
generated PNG is the user-facing artifact.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
import calendar

# The 20 mysteries in rotation order (names kept in Polish - UI artifact).
MYSTERIES: List[str] = [
    "I Radosna", "II Radosna", "III Radosna", "IV Radosna", "V Radosna",
    "I Światła", "II Światła", "III Światła", "IV Światła", "V Światła",
    "I Bolesna", "II Bolesna", "III Bolesna", "IV Bolesna", "V Bolesna",
    "I Chwalebna", "II Chwalebna", "III Chwalebna", "IV Chwalebna", "V Chwalebna",
]

POLISH_MONTHS = ["", "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
                 "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"]

ROMAN_MONTHS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


@dataclass(frozen=True)
class RoseConfig:
    name: str
    subtitle: str
    start_date: date
    change_day: int
    excluded_months: List[int]
    people: List[str]  # 20 names (empty string = vacant)


@dataclass(frozen=True)
class MysteryPeriod:
    period_start: date
    period_end: date
    label_month: int
    label_year: int
    cycle_index: int


def _add_one_month(d: date, change_day: int) -> date:
    """Returns the same change_day in the next calendar month (clamped to month length)."""
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(change_day, last))


def generate_periods(cfg: RoseConfig, until: date) -> List[MysteryPeriod]:
    """Generates the list of mystery periods from start_date up to `until`.

    The rotation cycle only advances when a NEW period starts in a non-excluded
    month. In other words: if a change would fall in e.g. July but July is excluded,
    the current period extends until the next non-excluded change date, and the
    cycle_index does NOT increment during the holiday.
    """
    periods: List[MysteryPeriod] = []
    current_start = cfg.start_date
    cycle = 0
    safety = 0
    while current_start <= until and safety < 600:
        safety += 1
        next_change = _add_one_month(current_start, cfg.change_day)
        # Skip excluded months: keep stretching the current period.
        while next_change.month in cfg.excluded_months:
            next_change = _add_one_month(next_change, cfg.change_day)
        period_end = date.fromordinal(next_change.toordinal() - 1)
        periods.append(MysteryPeriod(
            period_start=current_start,
            period_end=period_end,
            # The period's label = the month it ends in. Matches the original
            # spreadsheet convention: e.g. "Maj (25.IV - 24.V)".
            label_month=period_end.month,
            label_year=period_end.year,
            cycle_index=cycle,
        ))
        current_start = next_change
        cycle += 1
    return periods


def mystery_for(position: int, cycle_index: int) -> str:
    """Returns the mystery name for a given position in a given rotation cycle."""
    if not 1 <= position <= 20:
        raise ValueError(f"Pozycja musi być 1..20, dostałem {position}")
    return MYSTERIES[(position - 1 + cycle_index) % 20]


def find_period_for_month(periods: List[MysteryPeriod],
                          year: int, month: int) -> Optional[MysteryPeriod]:
    """Finds the period whose label matches (year, month)."""
    for p in periods:
        if p.label_year == year and p.label_month == month:
            return p
    return None


def label_for_period(p: MysteryPeriod, excluded: List[int]) -> str:
    """Returns the column header text.

    Normal month: 'Maj\\n(25.IV - 24.V)'.
    Period that bridges excluded months: 'Lipiec - Wrzesień'.
    """
    start, end = p.period_start, p.period_end
    months_span = (end.year - start.year) * 12 + (end.month - start.month) + 1
    if months_span > 2:
        # Holiday-bridging period: find the first excluded month inside it.
        cur = start.month
        for _ in range(months_span + 1):
            cur = 1 if cur == 12 else cur + 1
            if cur in excluded:
                return f"{POLISH_MONTHS[cur]} – {POLISH_MONTHS[end.month]}"
    return (f"{POLISH_MONTHS[p.label_month]}\n"
            f"({start.day}.{ROMAN_MONTHS[start.month]} – "
            f"{end.day}.{ROMAN_MONTHS[end.month]})")
