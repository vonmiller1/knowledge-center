"""The meeting-capture vertical artifacts: candidates, register entries and the register.

The distinction the whole design turns on lives here in the type names. A :class:`Candidate` is
what the MODEL proposed from a redacted transcript; it is unverified and enters nothing. A
:class:`RegisterEntry` is what the deterministic engine ACCEPTED or REJECTED, with every number
and verdict it computed. The model never constructs a ``RegisterEntry``; only
``action_register`` does, which is what keeps the consequential half pure and replayable.

Everything is frozen, validated at construction and pure stdlib on top of the shared speech
kit's :class:`~speech_lexicon_kit.Transcript`. A citation is a character span into a specific
turn, so "turn 4, characters 0..37" means the same thing in the register, the minutes and the
audit record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from hex_service_kit.enums import LenientStrEnum
from speech_lexicon_kit import Transcript

from .kernel import Citation


class MeetingError(ValueError):
    """Raised when a meeting-capture value object violates one of its invariants."""


class CommitmentKind(LenientStrEnum):
    """What a commitment IS: a task somebody must do, or a decision the meeting reached."""

    ACTION = "action"
    DECISION = "decision"


class DecisionState(LenientStrEnum):
    """The state machine a decision moves through; an action is recorded as ``AGREED``."""

    PROPOSED = "proposed"
    AGREED = "agreed"
    SUPERSEDED = "superseded"


class RegisterOutcome(LenientStrEnum):
    """Whether the engine admitted a candidate to the register."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class OwnerResolution(LenientStrEnum):
    """How owner resolution ended, so the engine can tell a hallucination from a genuine gap.

    ``RESOLVED`` names a participant present in the diarized turns. ``UNASSIGNED`` is an honest
    group/self commitment with no specific owner (accepted, but flagged for a human to assign).
    ``UNRESOLVABLE`` names somebody who is NOT a participant (a model hallucination), which the
    engine rejects rather than register against a person who was never in the room.
    """

    RESOLVED = "resolved"
    UNASSIGNED = "unassigned"
    UNRESOLVABLE = "unresolvable"


@dataclass(frozen=True, slots=True)
class SpanCitation:
    """A character span into one turn of a transcript: the provenance of every claim."""

    turn_index: int
    char_start: int
    char_end: int

    def __post_init__(self) -> None:
        if self.turn_index < 0:
            raise MeetingError(f"SpanCitation.turn_index must be >= 0, got {self.turn_index}")
        if self.char_start < 0 or self.char_end < self.char_start:
            raise MeetingError(
                f"SpanCitation span [{self.char_start}, {self.char_end}) is not a valid range"
            )

    def resolvable(self, transcript: Transcript) -> bool:
        """True when this span lands inside a real turn of ``transcript``."""
        if not 0 <= self.turn_index < len(transcript.turns):
            return False
        return self.char_end <= len(transcript.turns[self.turn_index].text)

    def resolve(self, transcript: Transcript) -> str:
        """The exact substring this span cites (raises if it does not land in the transcript)."""
        if not self.resolvable(transcript):
            raise MeetingError(
                f"SpanCitation {self!r} does not resolve against transcript "
                f"{transcript.transcript_id!r}"
            )
        return transcript.turns[self.turn_index].slice_text(self.char_start, self.char_end)

    def to_kernel(self, transcript: Transcript) -> Citation:
        """A kernel :class:`Citation` carrying the cited (already-redacted) snippet."""
        snippet = self.resolve(transcript) if self.resolvable(transcript) else ""
        return Citation(
            source_id=f"turn:{self.turn_index}:{self.char_start}-{self.char_end}",
            title=f"Transcript turn {self.turn_index}",
            snippet=snippet,
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """A model-proposed commitment. Unverified: it enters the register only if the engine accepts.

    ``text`` is already redacted (it comes from the redacted transcript the model saw).
    ``owner_ref`` is whatever the model attributed the commitment to, resolved deterministically
    by the engine against the diarized participants. ``due_phrase`` is the raw phrase, parsed by
    ``dates``.
    """

    candidate_id: str
    kind: CommitmentKind
    text: str
    owner_ref: str
    due_phrase: str
    citation: SpanCitation
    decision_state: DecisionState = DecisionState.PROPOSED
    supersedes: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise MeetingError("Candidate.candidate_id must be non-empty")
        if not self.text.strip():
            raise MeetingError("Candidate.text must be non-empty")


@dataclass(frozen=True, slots=True)
class RegisterEntry:
    """One engine verdict: a candidate accepted (with computed dates) or rejected (with reasons).

    Every date is computed by the engine from the market retention pack plus an explicit
    ``as_of``. ``requires_human_review`` is the R8 trigger: an accepted entry that is unowned or
    externally binding is consequential and must reach a human before anything acts on it.
    """

    entry_id: str
    kind: CommitmentKind
    text: str
    owner: str
    owner_resolution: OwnerResolution
    state: DecisionState
    outcome: RegisterOutcome
    citation: SpanCitation
    due_date: date | None = None
    sla_due: date | None = None
    retention_until: date | None = None
    requires_human_review: bool = False
    reasons: tuple[str, ...] = ()
    review_ref: str = ""

    @property
    def accepted(self) -> bool:
        return self.outcome is RegisterOutcome.ACCEPTED

    @property
    def consequential(self) -> bool:
        """Accepted AND needing a human before it can be acted on (routed under R8)."""
        return self.accepted and self.requires_human_review


@dataclass(frozen=True, slots=True)
class Register:
    """The whole verdict for one meeting: every entry, keyed to the market and the ``as_of``."""

    meeting_id: str
    market: str
    as_of: date
    entries: tuple[RegisterEntry, ...] = field(default=())

    @property
    def accepted(self) -> tuple[RegisterEntry, ...]:
        return tuple(e for e in self.entries if e.accepted)

    @property
    def rejected(self) -> tuple[RegisterEntry, ...]:
        return tuple(e for e in self.entries if not e.accepted)

    @property
    def consequential(self) -> tuple[RegisterEntry, ...]:
        return tuple(e for e in self.entries if e.consequential)


@dataclass(frozen=True, slots=True)
class Minutes:
    """Cited minutes: prose that restates ONLY register entries, plus the grounding verdict.

    ``grounded`` is False when the narrator introduced an owner, date or decision the register
    does not contain; the service discards an ungrounded draft rather than publishing it.
    ``requires_human_review`` is True when the meeting carried any consequential entry.
    """

    meeting_id: str
    market: str
    body: str
    grounded: bool
    requires_human_review: bool
    citations: tuple[Citation, ...] = ()
    violations: tuple[str, ...] = ()
