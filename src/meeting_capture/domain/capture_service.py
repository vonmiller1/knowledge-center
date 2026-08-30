"""The meeting-capture orchestrator: the one place slices 2 through 6 are wired together.

It depends only on port PROTOCOLS (the same way ``TriageService`` depends on the audit port), so
it stays testable and pure of transport. The order is the security order: ingest, ASSEMBLE
deterministically, REDACT before the model is ever called, extract candidates (model),
schema-validate them, run the deterministic register engine, draft and GROUND minutes, write an
already-redacted audit record, then ROUTE every consequential entry to Hrz7 under rule R8.

Two follow-on actions are gated on human review, because they act in the world:

* :meth:`publish_minutes` refuses to publish minutes into the Hrz2 corpus while they carry an
  unresolved consequential entry, and
* :meth:`dispatch_task` refuses to create an external task for a consequential entry that has no
  review reference, so an unapproved commitment yields ZERO downstream calls.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from pii_kit import redact
from speech_lexicon_kit import AudioRef, Transcript

from ..ports.audit import AuditSinkPort
from ..ports.corpus import CorpusDocument, CorpusPort
from ..ports.diarization import DiarizationPort, DiarizationRequest
from ..ports.generation import ExtractionRequest, GenerationPort, NarrationRequest
from ..ports.observability import ObservabilityTracerPort
from ..ports.review_router import ReviewRouterPort
from ..ports.task_router import TaskAssignment, TaskRouterPort
from ..ports.transcription import SpeechToTextPort, TranscriptionRequest
from .action_register import ActionRegisterEngine
from .candidates import DiscardedCandidate, parse_candidates
from .kernel import AuditEvent, Citation, Decision, Severity, utcnow
from .meeting import Minutes, Register, RegisterEntry
from .minutes import draft_minutes
from .models import TriageResult
from .pii import PII_PATTERNS
from .retention import RetentionPack
from .turns import assemble, redact_for_model, transcript_digest

__all__ = ["CaptureResult", "MeetingCaptureService"]


#: One span per captured meeting. Structural attributes only: see
#: :meth:`MeetingCaptureService.capture`.
_CAPTURE_SPAN = "meeting_capture.capture"


@dataclass(frozen=True, slots=True)
class CaptureResult:
    """The full outcome of capturing one meeting: register, grounded minutes and provenance."""

    meeting_id: str
    market: str
    as_of: date
    register: Register
    minutes: Minutes
    transcript_digest: str
    redacted_transcript: Transcript
    discarded: tuple[DiscardedCandidate, ...] = ()
    review_refs: Mapping[str, str] = field(default_factory=dict)


class MeetingCaptureService:
    """Capture a meeting end to end, deterministically, with the model narrating only."""

    def __init__(
        self,
        *,
        transcription: SpeechToTextPort,
        diarization: DiarizationPort,
        generation: GenerationPort,
        corpus: CorpusPort,
        task_router: TaskRouterPort,
        review_router: ReviewRouterPort,
        audit: AuditSinkPort,
        tracer: ObservabilityTracerPort,
        packs: Mapping[str, RetentionPack],
        tenant: str = "",
    ) -> None:
        self._transcription = transcription
        self._diarization = diarization
        self._generation = generation
        self._corpus = corpus
        self._task_router = task_router
        self._review_router = review_router
        self._audit = audit
        self._tracer = tracer
        self._engine = ActionRegisterEngine(packs)
        self._tenant = tenant

    @property
    def engine(self) -> ActionRegisterEngine:
        return self._engine

    def capture(
        self,
        audio_uri: str,
        *,
        market: str,
        as_of: date,
        actor: str,
        meeting_id: str = "",
        media_type: str = "audio/wav",
    ) -> CaptureResult:
        """Capture one meeting end to end, inside one span.

        The span's attributes are STRUCTURAL only, never the audio URI, the meeting id, a
        transcript turn, a register entry or a minutes line: a trace backend is not the WORM
        audit trail; it has no redaction stage, a wider read audience and no retention rule
        written against a regulator's requirement, so anything content-shaped that reaches a
        span has left the boundary ``redact_for_model`` exists to hold, and left it
        silently.
        """
        with self._tracer.span(_CAPTURE_SPAN, action="capture", actor=actor, market=market):
            return self._capture(
                audio_uri,
                market=market,
                as_of=as_of,
                actor=actor,
                meeting_id=meeting_id,
                media_type=media_type,
            )

    def _capture(
        self,
        audio_uri: str,
        *,
        market: str,
        as_of: date,
        actor: str,
        meeting_id: str = "",
        media_type: str = "audio/wav",
    ) -> CaptureResult:
        request_id = f"cap:{meeting_id or audio_uri}"
        audio = AudioRef(uri=audio_uri, media_type=media_type)

        recognized = self._transcription.transcribe(
            TranscriptionRequest(request_id=request_id, audio=audio, locale="und", diarize=True)
        )
        diarized = self._diarization.diarize(DiarizationRequest(request_id=request_id, audio=audio))
        assembled = assemble(recognized.transcript, diarized.segments)

        # Redact BEFORE the model is ever called: every downstream stage sees only this copy.
        redacted = redact_for_model(assembled, PII_PATTERNS)
        resolved_meeting_id = meeting_id or redacted.transcript_id

        parse = parse_candidates(
            self._generation.extract(ExtractionRequest(transcript=redacted)), redacted
        )
        register = self._engine.build(
            redacted,
            parse.candidates,
            market=market,
            as_of=as_of,
            meeting_id=resolved_meeting_id,
        )
        minutes = draft_minutes(
            register, self._generation.narrate(NarrationRequest(register, redacted)), redacted
        )

        self._record(register, minutes, actor=actor)
        register, review_refs = self._route_consequential(register, actor=actor)
        return CaptureResult(
            meeting_id=resolved_meeting_id,
            market=market,
            as_of=as_of,
            register=register,
            minutes=minutes,
            transcript_digest=transcript_digest(redacted),
            redacted_transcript=redacted,
            discarded=parse.discarded,
            review_refs=review_refs,
        )

    def _record(self, register: Register, minutes: Minutes, *, actor: str) -> None:
        summary = (
            f"{register.meeting_id}: {len(register.accepted)} accepted, "
            f"{len(register.rejected)} rejected, {len(register.consequential)} for review; "
            f"minutes grounded={minutes.grounded}"
        )
        decision = Decision.ESCALATED if register.consequential else Decision.ALLOWED
        severity = Severity.HIGH if register.consequential else Severity.LOW
        self._audit.record(
            AuditEvent(
                action="meeting_capture",
                actor=actor,
                decision=decision,
                severity=severity,
                redacted_summary=redact(summary, PII_PATTERNS),
                citations=minutes.citations,
                timestamp=utcnow(),
            )
        )

    def _route_consequential(
        self, register: Register, *, actor: str
    ) -> tuple[Register, dict[str, str]]:
        """Route every consequential entry to Hrz7 and stamp each entry with its review ref."""
        review_refs: dict[str, str] = {}
        updated: list[RegisterEntry] = []
        for entry in register.entries:
            if entry.consequential:
                ref = self._review_router.route(
                    _entry_to_result(entry, register),
                    maker=actor,
                    tenant=self._tenant,
                )
                review_refs[entry.entry_id] = ref
                updated.append(_with_review_ref(entry, ref))
            else:
                updated.append(entry)
        return Register(
            meeting_id=register.meeting_id,
            market=register.market,
            as_of=register.as_of,
            entries=tuple(updated),
        ), review_refs

    def publish_minutes(
        self, result: CaptureResult, *, review_approved: bool = False
    ) -> str | None:
        """Publish grounded minutes to the Hrz2 corpus; refuse while a review is unresolved.

        Returns the corpus document id, or ``None`` when publication is withheld (ungrounded
        minutes, or consequential minutes that are not yet review-approved).
        """
        minutes = result.minutes
        if not minutes.grounded:
            return None
        if minutes.requires_human_review and not review_approved:
            return None
        return self._corpus.publish(
            CorpusDocument(
                doc_id=f"minutes:{result.meeting_id}",
                title=f"Minutes {result.meeting_id} ({result.market})",
                market=result.market,
                body=minutes.body,
                tags=("minutes", result.market),
            )
        )

    def dispatch_task(self, entry: RegisterEntry, *, market: str) -> str | None:
        """Create an external task for an accepted action; refuse an unapproved consequential one.

        A consequential entry (unowned or externally binding) must carry a review reference
        before it routes, so an unapproved commitment produces ZERO downstream calls (``None``).
        """
        if not entry.accepted:
            return None
        if entry.requires_human_review and not entry.review_ref:
            return None
        due = entry.sla_due or entry.due_date
        return self._task_router.create_task(
            TaskAssignment(
                source_entry_id=entry.entry_id,
                title=entry.text,
                owner=entry.owner,
                market=market,
                due_date=due.isoformat() if due else "",
                review_ref=entry.review_ref,
            )
        )


def _with_review_ref(entry: RegisterEntry, ref: str) -> RegisterEntry:
    return RegisterEntry(
        entry_id=entry.entry_id,
        kind=entry.kind,
        text=entry.text,
        owner=entry.owner,
        owner_resolution=entry.owner_resolution,
        state=entry.state,
        outcome=entry.outcome,
        citation=entry.citation,
        due_date=entry.due_date,
        sla_due=entry.sla_due,
        retention_until=entry.retention_until,
        requires_human_review=entry.requires_human_review,
        reasons=entry.reasons,
        review_ref=ref,
    )


def _entry_to_result(entry: RegisterEntry, register: Register) -> TriageResult:
    """Map a consequential register entry onto the generic R8 escalation envelope."""
    citation = Citation(
        source_id=f"{register.meeting_id}:{entry.entry_id}",
        title=f"{entry.kind.value} in {register.meeting_id}",
        snippet=entry.text,
    )
    return TriageResult(
        subject=f"{register.meeting_id}:{entry.entry_id}",
        severity=Severity.HIGH,
        decision=Decision.ESCALATED,
        summary=f"{entry.kind.value} for {entry.owner or 'unassigned'}: {entry.text}",
        requires_human_review=True,
        citations=(citation,),
    )
