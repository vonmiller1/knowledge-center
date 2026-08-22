"""Retention packs: loaded from data, validated, and refusing an unknown field."""

from __future__ import annotations

from datetime import date

import pytest

from meeting_capture.domain.capture_service import default_packs_dir, load_default_packs
from meeting_capture.domain.retention import (
    RetentionPackError,
    load_pack_mapping,
    load_packs,
)

_GOOD = {
    "market": "SG",
    "action_sla_days": 5,
    "decision_review_days": 10,
    "retention_years": 7,
    "external_binding_markers": ["sign", "contract"],
}


def test_the_shipped_packs_load_and_cover_three_markets() -> None:
    packs = load_default_packs()
    assert set(packs) == {"SG", "AU", "JP"}


def test_sla_and_retention_are_computed_from_the_pack() -> None:
    pack = load_pack_mapping(_GOOD)
    as_of = date(2026, 8, 3)
    assert pack.sla_due(as_of, due_date=None) == date(2026, 8, 8)
    assert pack.sla_due(as_of, due_date=date(2026, 9, 1)) == date(2026, 9, 1)
    assert pack.decision_due(as_of) == date(2026, 8, 13)
    assert pack.retention_until(as_of) == date(2033, 8, 3)


def test_external_binding_is_marker_driven() -> None:
    pack = load_pack_mapping(_GOOD)
    assert pack.is_externally_binding("please sign the form") is True
    assert pack.is_externally_binding("update the deck") is False


def test_an_unknown_field_is_refused_not_ignored() -> None:
    with pytest.raises(RetentionPackError):
        load_pack_mapping({**_GOOD, "surprise": 1})


def test_a_missing_field_is_refused() -> None:
    incomplete = {k: v for k, v in _GOOD.items() if k != "retention_years"}
    with pytest.raises(RetentionPackError):
        load_pack_mapping(incomplete)


def test_a_negative_window_is_refused() -> None:
    with pytest.raises(RetentionPackError):
        load_pack_mapping({**_GOOD, "action_sla_days": -1})


def test_load_packs_reads_the_shipped_directory() -> None:
    packs = load_packs(default_packs_dir())
    assert packs["JP"].retention_years == 10
