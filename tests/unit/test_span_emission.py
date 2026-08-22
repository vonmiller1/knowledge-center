"""Each capture-repo path opens ONE span, and no span carries content.

A trace backend is not the WORM audit trail. It has no redaction stage, no retention policy
written against a regulator's requirement, and a far wider read audience than the audit
store. So the value of tracing these paths depends entirely on the spans carrying
structural attributes only: which action, whose, which market. An audio URI, a meeting id,
a transcript turn, a register entry, a minutes line or a planted identifier reaching a span
has left the boundary ``redact_for_model`` and the redact-before-audit calls exist to hold,
and it has left it silently.

Two orchestrators are pinned because both sit on real request paths: the meeting capture
pipeline (API, CLI, agent tool, demo, eval) and the manual triage scaffold (API, CLI, agent
tool, demo). They do not nest: neither drives the other. The capture content case drives
the SG fixture meeting, whose seeded transcript carries a planted NRIC, so the check runs
against input that would actually leak.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest

from meeting_capture.config import Settings, build_container
from meeting_capture.domain.capture_service import (
    CaptureResult,
    MeetingCaptureService,
    load_default_packs,
)
from meeting_capture.domain.models import TriageInput
from meeting_capture.domain.triage_service import TriageService

from tests.fixtures import sample_cases

_SG_URI = "fixture://meetings/sg-1"
_AS_OF = date(2026, 3, 2)

#: Every attribute key each span is allowed to carry. A verdict that started explaining
#: itself on the span (an entry, a digest, a URI) would widen these sets, which is the
#: point of asserting on the set rather than on the individual keys.
_TRIAGE_KEYS = {"action", "actor"}
_CAPTURE_KEYS = {"action", "actor", "market"}


class _RecordingTracer:
    """Captures every span name and attribute so the test can inspect what was emitted."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str) -> Iterator[None]:
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _triage(case: TriageInput) -> _RecordingTracer:
    tracer = _RecordingTracer()
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = TriageService(container.audit, tracer=tracer)  # type: ignore[arg-type]
    service.triage(case, actor=sample_cases.ACTOR)
    return tracer


def _capture() -> tuple[_RecordingTracer, CaptureResult]:
    """The REAL local adapters, exactly as the surfaces wire them, tracer swapped."""
    tracer = _RecordingTracer()
    container = build_container(Settings(profile="local", audit_path=":memory:"))
    service = MeetingCaptureService(
        transcription=container.transcription,
        diarization=container.diarization,
        generation=container.generation,
        corpus=container.corpus,
        task_router=container.task_router,
        review_router=container.review_router,
        audit=container.audit,
        tracer=tracer,  # type: ignore[arg-type]
        packs=load_default_packs(),
        tenant=sample_cases.TENANT,
    )
    result = service.capture(_SG_URI, market="SG", as_of=_AS_OF, actor=sample_cases.ACTOR)
    return tracer, result


def _emitted(tracer: _RecordingTracer) -> str:
    """Every attribute KEY and VALUE that was emitted, as one searchable blob."""
    parts: list[str] = []
    for name, attributes in tracer.spans:
        parts.append(name)
        parts.extend(attributes)
        parts.extend(attributes.values())
    return " ".join(parts)


def test_triaging_a_case_opens_exactly_one_named_span() -> None:
    tracer = _triage(sample_cases.ROUTINE_CASE)
    assert [name for name, _ in tracer.spans] == ["meeting_capture.triage"]


def test_capturing_a_meeting_opens_exactly_one_named_span() -> None:
    tracer, _ = _capture()
    assert [name for name, _ in tracer.spans] == ["meeting_capture.capture"]


def test_the_triage_span_carries_the_structural_attributes_an_operator_needs() -> None:
    _, attributes = _triage(sample_cases.ROUTINE_CASE).spans[0]
    assert attributes["action"] == "triage"
    assert attributes["actor"] == sample_cases.ACTOR


def test_the_capture_span_carries_the_structural_attributes_an_operator_needs() -> None:
    """Enough to answer "whose capture is slow, in which market", and nothing more."""
    tracer, _ = _capture()
    _, attributes = tracer.spans[0]
    assert attributes["action"] == "capture"
    assert attributes["actor"] == sample_cases.ACTOR
    assert attributes["market"] == "SG"


@pytest.mark.parametrize(
    "case",
    [sample_cases.ROUTINE_CASE, sample_cases.ESCALATING_CASE, sample_cases.PII_CASE],
    ids=["routine", "escalating", "pii"],
)
def test_the_triage_attribute_set_is_a_fixed_allowlist_whatever_the_verdict(
    case: TriageInput,
) -> None:
    for _, attributes in _triage(case).spans:
        assert set(attributes) == _TRIAGE_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_TRIAGE_KEYS here deliberately"
        )


def test_the_capture_attribute_set_is_a_fixed_allowlist() -> None:
    """A consequential register must not start attaching its entries to the span."""
    tracer, _ = _capture()
    for _, attributes in tracer.spans:
        assert set(attributes) == _CAPTURE_KEYS, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_CAPTURE_KEYS here deliberately"
        )


def test_no_triage_span_attribute_carries_case_content_or_the_planted_identifier() -> None:
    emitted = _emitted(_triage(sample_cases.PII_CASE)).lower()
    forbidden = (
        sample_cases.PLANTED_NRIC,
        sample_cases.PII_CASE.text,
        sample_cases.PII_CASE.subject,
        "ops@gamma.example",
    )
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_no_capture_span_attribute_carries_meeting_content_or_the_planted_identifier() -> None:
    """The SG fixture transcript plants an NRIC, so a content-shaped attribute would show."""
    tracer, result = _capture()
    emitted = _emitted(tracer).lower()
    forbidden = [
        sample_cases.PLANTED_NRIC,
        _SG_URI,
        result.meeting_id,
        result.transcript_digest,
        *(entry.text for entry in result.register.entries),
    ]
    for literal in forbidden:
        assert literal, "an empty needle would pass this test for the wrong reason"
        assert literal.lower() not in emitted, f"a span attribute carried {literal!r}"


def test_every_emitted_attribute_value_is_a_string_the_port_declares() -> None:
    """``span(name, **attributes: str)``: a non-string would serialise however the SDK felt."""
    capture_tracer, _ = _capture()
    values = [
        value
        for tracer in (_triage(sample_cases.ESCALATING_CASE), capture_tracer)
        for _, attributes in tracer.spans
        for value in attributes.values()
    ]
    assert values
    assert all(isinstance(value, str) for value in values)
