"""Every eval metric can be driven red, and the SLA metric can go red PER MARKET pack.

A metric that cannot fail is not a metric. The eval scores the pipeline against the golden
oracle; here we prove each score distinguishes a clean run from a degraded one, using the
shared harness. The SLA proof runs per market (``assert_each_can_go_red``): a pack mutated in
one market's file must make that market's SLA metric go red, so a broken pack is caught where it
lives rather than hidden inside an aggregate.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from agent_eval_kit import assert_can_go_red, assert_each_can_go_red

from meeting_capture.config import build_container
from meeting_capture.domain.capture_service import (
    CaptureResult,
    MeetingCaptureService,
    load_default_packs,
)
from meeting_capture.domain.retention import RetentionPack

from tests.conftest import local_settings

_AS_OF = date(2026, 8, 3)
_URI = {
    "SG": "fixture://meetings/sg-1",
    "AU": "fixture://meetings/au-1",
    "JP": "fixture://meetings/jp-1",
}

#: The independent, hand-computed SLA oracle per market (mirrors eval/datasets/golden_meetings).
_EXPECTED_SLA: dict[str, dict[str, str]] = {
    "SG": {
        "trs-sg-1-e1": "2026-08-08",
        "trs-sg-1-e2": "2026-08-13",
        "trs-sg-1-e3": "2026-08-08",
        "trs-sg-1-e4": "2026-08-10",
    },
    "AU": {"trs-au-1-e1": "2026-08-10", "trs-au-1-e2": "2026-08-17", "trs-au-1-e3": "2026-09-15"},
    "JP": {"trs-jp-1-e1": "2026-08-06", "trs-jp-1-e2": "2026-08-10"},
}
_EXPECTED_CONSEQUENTIAL: dict[str, set[str]] = {
    "SG": {"trs-sg-1-e3", "trs-sg-1-e4"},
    "AU": {"trs-au-1-e3"},
    "JP": set(),
}


def _capture(pack: RetentionPack) -> CaptureResult:
    market = pack.market
    container = build_container(local_settings())
    service = MeetingCaptureService(
        transcription=container.transcription,
        diarization=container.diarization,
        generation=container.generation,
        corpus=container.corpus,
        task_router=container.task_router,
        review_router=container.review_router,
        audit=container.audit,
        tracer=container.tracer,
        packs={market: pack},
        tenant="eval",
    )
    return service.capture(_URI[market], market=market, as_of=_AS_OF, actor="e")


def _sla_exactness(pack: RetentionPack) -> float:
    result = _capture(pack)
    expected = _EXPECTED_SLA[pack.market]
    by_id = {e.entry_id: e for e in result.register.accepted}
    hits = sum(
        1
        for entry_id, iso in expected.items()
        if entry_id in by_id
        and by_id[entry_id].sla_due is not None
        and by_id[entry_id].sla_due.isoformat() == iso  # type: ignore[union-attr]
    )
    return hits / len(expected)


def _review_safety(pack: RetentionPack) -> float:
    result = _capture(pack)
    got = {e.entry_id for e in result.register.consequential}
    return 1.0 if got == _EXPECTED_CONSEQUENTIAL[pack.market] else 0.0


def test_sla_exactness_can_go_red_per_market() -> None:
    packs = load_default_packs()
    cases: dict[str, tuple[RetentionPack, RetentionPack]] = {}
    for market, pack in packs.items():
        # Mutate the market's own SLA window: a default-SLA action's date must move, going red.
        red = dataclasses.replace(pack, action_sla_days=pack.action_sla_days + 3)
        cases[market] = (pack, red)
    assert_each_can_go_red(_sla_exactness, cases, threshold=0.99, metric="sla_exactness")


def test_review_safety_can_go_red_when_external_binding_stops_being_detected() -> None:
    sg = load_default_packs()["SG"]
    blind = dataclasses.replace(sg, external_binding_markers=())
    assert_can_go_red(
        _review_safety,
        green=sg,
        red=blind,  # with no markers, the signed-contract action is no longer consequential
        threshold=0.99,
        metric="review_safety",
    )
