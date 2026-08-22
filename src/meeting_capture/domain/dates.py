"""Deterministic due-date resolution: a phrase plus an explicit ``as_of``, never a clock.

The action register computes SLA and retention dates, and a date engine that read the wall clock
would give a different answer on every replay, so the whole layer is pure: every function that
needs "now" takes ``as_of`` from the caller (the meeting date), exactly as the speech kit does.

The grammar is deliberately small and total. Every phrase resolves to a single date or to
``None`` (NEEDS_INFO), and ``None`` is consequential: the register REJECTS an action whose due
phrase was given but could not be parsed rather than guessing a date, because a fabricated
deadline is worse than an acknowledged gap.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

__all__ = ["parse_due"]

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_IN_N = re.compile(r"\bin\s+(\d{1,3})\s+(day|days|week|weeks|business day|business days)\b")
_BY_WEEKDAY = re.compile(
    r"\b(?:by|next|on|this)\s+"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
)

_WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _add_business_days(start: date, count: int) -> date:
    """``count`` business days after ``start`` (Mon..Fri), skipping weekends deterministically."""
    current = start
    remaining = count
    while remaining > 0:
        current = current + timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _end_of_month(as_of: date) -> date:
    if as_of.month == 12:
        return date(as_of.year, 12, 31)
    return date(as_of.year, as_of.month + 1, 1) - timedelta(days=1)


def _next_weekday(as_of: date, weekday: int) -> date:
    """The next occurrence of ``weekday`` STRICTLY after ``as_of`` (never ``as_of`` itself)."""
    delta = (weekday - as_of.weekday()) % 7
    return as_of + timedelta(days=delta or 7)


def parse_due(phrase: str, as_of: date) -> date | None:
    """Resolve a natural due phrase to a date relative to ``as_of``, or ``None`` if unparseable.

    Supported, in priority order: an explicit ISO date (``2026-09-01``); ``in N days`` /
    ``in N weeks`` / ``in N business days``; ``tomorrow``; ``end of month`` / ``eom``;
    ``next week``; and ``by/next/on/this <weekday>``. Anything else is ``None``, which the engine
    treats as NEEDS_INFO rather than inventing a deadline.
    """
    text = phrase.strip().lower()
    if not text:
        return None

    iso = _ISO.search(text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    in_n = _IN_N.search(text)
    if in_n:
        n = int(in_n.group(1))
        unit = in_n.group(2)
        if unit.startswith("business"):
            return _add_business_days(as_of, n)
        if unit.startswith("week"):
            return as_of + timedelta(weeks=n)
        return as_of + timedelta(days=n)

    if "tomorrow" in text:
        return as_of + timedelta(days=1)
    if "end of month" in text or re.search(r"\beom\b", text):
        return _end_of_month(as_of)
    if "next week" in text:
        return as_of + timedelta(days=7)

    weekday = _BY_WEEKDAY.search(text)
    if weekday:
        return _next_weekday(as_of, _WEEKDAYS[weekday.group(1)])

    return None
