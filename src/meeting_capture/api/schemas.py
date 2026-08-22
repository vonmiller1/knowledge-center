"""API request/response schemas (Pydantic) mapped to/from the pure-domain models."""

from __future__ import annotations

from pydantic import BaseModel

from ..domain.capture_service import CaptureResult
from ..domain.meeting import RegisterEntry
from ..domain.models import TriageResult


class TriageRequest(BaseModel):
    subject: str
    text: str


class CaptureRequest(BaseModel):
    audio_uri: str
    market: str
    #: ISO date the SLA and retention windows are computed against (the meeting date).
    as_of: str
    meeting_id: str = ""


class RegisterEntryModel(BaseModel):
    entry_id: str
    kind: str
    text: str
    owner: str
    owner_resolution: str
    state: str
    outcome: str
    due_date: str = ""
    sla_due: str = ""
    retention_until: str = ""
    requires_human_review: bool = False
    reasons: list[str] = []
    review_ref: str = ""

    @classmethod
    def from_domain(cls, entry: RegisterEntry) -> RegisterEntryModel:
        return cls(
            entry_id=entry.entry_id,
            kind=entry.kind.value,
            text=entry.text,
            owner=entry.owner,
            owner_resolution=entry.owner_resolution.value,
            state=entry.state.value,
            outcome=entry.outcome.value,
            due_date=entry.due_date.isoformat() if entry.due_date else "",
            sla_due=entry.sla_due.isoformat() if entry.sla_due else "",
            retention_until=entry.retention_until.isoformat() if entry.retention_until else "",
            requires_human_review=entry.requires_human_review,
            reasons=list(entry.reasons),
            review_ref=entry.review_ref,
        )


class CaptureResponse(BaseModel):
    meeting_id: str
    market: str
    as_of: str
    transcript_digest: str
    minutes_body: str
    minutes_grounded: bool
    requires_human_review: bool
    entries: list[RegisterEntryModel] = []
    review_refs: dict[str, str] = {}

    @classmethod
    def from_domain(cls, result: CaptureResult) -> CaptureResponse:
        return cls(
            meeting_id=result.meeting_id,
            market=result.market,
            as_of=result.as_of.isoformat(),
            transcript_digest=result.transcript_digest,
            minutes_body=result.minutes.body,
            minutes_grounded=result.minutes.grounded,
            requires_human_review=result.minutes.requires_human_review,
            entries=[RegisterEntryModel.from_domain(e) for e in result.register.entries],
            review_refs=dict(result.review_refs),
        )


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class TriageResponse(BaseModel):
    subject: str
    severity: str
    decision: str
    summary: str
    requires_human_review: bool
    #: Where the escalation WENT (rule R8): the Hrz7 review id, or the local queue reference.
    #: Empty only when the result did not escalate. A caller can tell a routed escalation from
    #: a flag that stopped here, which is the whole point of the rule.
    review_ref: str = ""
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(cls, result: TriageResult, *, review_ref: str = "") -> TriageResponse:
        return cls(
            subject=result.subject,
            severity=result.severity.value,
            decision=result.decision.value,
            summary=result.summary,
            requires_human_review=result.requires_human_review,
            review_ref=review_ref,
            citations=[
                CitationModel(source_id=c.source_id, title=c.title, snippet=c.snippet)
                for c in result.citations
            ],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
