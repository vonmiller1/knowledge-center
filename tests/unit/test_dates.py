"""The deterministic due-date parser: every branch, and the NEEDS_INFO refusal."""

from __future__ import annotations

from datetime import date

from meeting_capture.domain.dates import parse_due

_MON = date(2026, 8, 3)  # a Monday, so weekday arithmetic is checkable by eye


def test_iso_date_is_taken_verbatim() -> None:
    assert parse_due("by 2026-09-01", _MON) == date(2026, 9, 1)


def test_in_n_days_and_weeks() -> None:
    assert parse_due("in 5 days", _MON) == date(2026, 8, 8)
    assert parse_due("in 2 weeks", _MON) == date(2026, 8, 17)


def test_business_days_skip_the_weekend() -> None:
    # Monday + 5 business days lands on the next Monday, not the Saturday.
    assert parse_due("in 5 business days", _MON) == date(2026, 8, 10)


def test_next_weekday_is_strictly_after_as_of() -> None:
    # as_of is Monday; "by Monday" means the NEXT Monday, never today.
    assert parse_due("by monday", _MON) == date(2026, 8, 10)
    assert parse_due("by friday", _MON) == date(2026, 8, 7)


def test_relative_words() -> None:
    assert parse_due("tomorrow", _MON) == date(2026, 8, 4)
    assert parse_due("next week", _MON) == date(2026, 8, 10)
    assert parse_due("end of month", _MON) == date(2026, 8, 31)


def test_unparseable_is_none_not_a_guess() -> None:
    assert parse_due("by soon", _MON) is None
    assert parse_due("whenever", _MON) is None
    assert parse_due("", _MON) is None


def test_a_bad_iso_date_is_rejected_not_clamped() -> None:
    assert parse_due("2026-13-40", _MON) is None
