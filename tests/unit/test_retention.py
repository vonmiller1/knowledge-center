"""Retention packs: loaded from data, validated, and refusing an unknown field."""

from __future__ import annotations

from datetime import date

import pytest

from meeting_capture.domain.retention import (
    RetentionPackError,
    build_pack_set,
    load_pack_mapping,
)
from meeting_capture.packs import default_packs_dir, load_default_packs, load_packs

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


def test_the_core_builds_a_pack_set_from_documents_with_no_parser_involved() -> None:
    """The seam the config boundary sits on: mappings in, validated packs out, no YAML."""
    packs = build_pack_set(
        [("<a>", dict(_GOOD)), ("<b>", {**_GOOD, "market": "AU"})], origin="<test>"
    )
    assert set(packs) == {"SG", "AU"}


def test_two_documents_claiming_one_market_refuse_rather_than_last_one_winning() -> None:
    with pytest.raises(RetentionPackError, match="already defined"):
        build_pack_set([("<a>", dict(_GOOD)), ("<b>", dict(_GOOD))], origin="<test>")


def test_an_empty_document_set_refuses_rather_than_yielding_an_engine_with_no_policy() -> None:
    with pytest.raises(RetentionPackError, match="<test>"):
        build_pack_set([], origin="<test>")


def test_a_document_that_is_not_a_mapping_is_refused_by_the_core_not_the_parser() -> None:
    with pytest.raises(RetentionPackError, match="must be a mapping"):
        build_pack_set([("<a>", ["not", "a", "mapping"])], origin="<test>")
