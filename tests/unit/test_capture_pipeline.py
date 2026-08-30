"""The end-to-end capture pipeline: determinism, redact-before-model, R8 routing, review gates."""

from __future__ import annotations

from datetime import date

from meeting_capture.adapters.local.generation import LocalGenerationAdapter
from meeting_capture.config import build_container
from meeting_capture.domain.capture_service import MeetingCaptureService
from meeting_capture.packs import load_default_packs
from meeting_capture.ports.generation import ExtractionRequest, NarrationRequest

from tests.conftest import local_settings

_SG = "fixture://meetings/sg-1"
_AS_OF = date(2026, 8, 3)


class _SpyGeneration:
    """Wraps the real local adapter and records the transcript text the model was handed."""

    def __init__(self, settings: object) -> None:
        self._inner = LocalGenerationAdapter(settings)  # type: ignore[arg-type]
        self.seen_texts: list[str] = []

    def extract(self, request: ExtractionRequest) -> str:
        self.seen_texts.extend(turn.text for turn in request.transcript.turns)
        return self._inner.extract(request)

    def narrate(self, request: NarrationRequest) -> str:
        self.seen_texts.extend(turn.text for turn in request.transcript.turns)
        return self._inner.narrate(request)


def _service(generation: object | None = None) -> tuple[MeetingCaptureService, object]:
    container = build_container(local_settings())
    gen = generation if generation is not None else container.generation
    service = MeetingCaptureService(
        transcription=container.transcription,
        diarization=container.diarization,
        generation=gen,  # type: ignore[arg-type]
        corpus=container.corpus,
        task_router=container.task_router,
        review_router=container.review_router,
        audit=container.audit,
        tracer=container.tracer,
        packs=load_default_packs(),
        tenant="demo-bank",
    )
    return service, container


def test_the_model_never_sees_an_unredacted_identifier() -> None:
    spy = _SpyGeneration(local_settings())
    service, _ = _service(spy)
    service.capture(_SG, market="SG", as_of=_AS_OF, actor="analyst@bank.example")
    assert spy.seen_texts, "the model must have been called"
    assert not any("S1234567D" in text for text in spy.seen_texts), (
        "a raw NRIC reached the generation port; redaction must run BEFORE the model"
    )


def test_capture_is_deterministic() -> None:
    service_a, _ = _service()
    service_b, _ = _service()
    first = service_a.capture(_SG, market="SG", as_of=_AS_OF, actor="a@bank.example")
    second = service_b.capture(_SG, market="SG", as_of=_AS_OF, actor="a@bank.example")
    assert first.transcript_digest == second.transcript_digest
    assert first.register == second.register


def test_consequential_entries_are_routed_under_r8() -> None:
    service, container = _service()
    result = service.capture(_SG, market="SG", as_of=_AS_OF, actor="a@bank.example")
    consequential = result.register.consequential
    assert consequential, "the SG meeting has externally-binding and third-party commitments"
    for entry in consequential:
        assert entry.review_ref, "a consequential entry must carry its routing reference"
    # The local review router enqueued one review per consequential entry.
    assert len(container.review_router.outbox.pending()) == len(consequential)


def test_minutes_publish_is_withheld_until_review_then_allowed() -> None:
    service, container = _service()
    result = service.capture(_SG, market="SG", as_of=_AS_OF, actor="a@bank.example")
    assert result.minutes.requires_human_review is True
    assert service.publish_minutes(result, review_approved=False) is None
    assert container.corpus.documents == ()
    doc_id = service.publish_minutes(result, review_approved=True)
    assert doc_id
    assert len(container.corpus.documents) == 1


def test_task_routing_refuses_an_unapproved_consequential_entry() -> None:
    service, container = _service()
    result = service.capture(_SG, market="SG", as_of=_AS_OF, actor="a@bank.example")
    # An approved (review-referenced) consequential entry routes and carries its review id.
    approved = result.register.consequential[0]
    task_id = service.dispatch_task(approved, market="SG")
    assert task_id
    assert container.task_router.tasks[0].review_ref == approved.review_ref

    # A consequential entry with no review reference produces ZERO downstream calls.
    from meeting_capture.domain.capture_service import _with_review_ref

    unapproved = _with_review_ref(approved, "")
    before = len(container.task_router.tasks)
    assert service.dispatch_task(unapproved, market="SG") is None
    assert len(container.task_router.tasks) == before


def test_the_audit_record_is_redacted() -> None:
    service, container = _service()
    service.capture(_SG, market="SG", as_of=_AS_OF, actor="a@bank.example")
    records = container.audit.log.read_all()
    assert records
    assert not any("S1234567D" in str(r.get("redacted_summary", "")) for r in records)
