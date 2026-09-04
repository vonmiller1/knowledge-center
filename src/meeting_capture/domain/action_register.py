"""The deterministic action register (slice 4): the consequential engine, pure and replayable.

This is the differentiation. The model proposes candidates; THIS decides. Every acceptance,
rejection, owner, date and escalation is computed by stdlib code from the candidate, the diarized
transcript and the market retention pack, with an explicit ``as_of``. Given the same inputs it
returns the same register, byte for byte, forever. The model never writes an entry.

The acceptance checks are the ones the plan names: the citation span must land in a real turn,
an action's owner must resolve to a participant, and a due phrase that was given must parse. A
candidate that fails any check is REJECTED with the reason recorded, not repaired. An accepted
commitment that is unowned (a group action with nobody assigned) or externally binding (a signed
obligation to a customer or vendor) is consequential: ``requires_human_review`` is set so slice 5
routes it to human-review-console before anything acts on it.

Owner resolution distinguishes three outcomes so a hallucination is not mistaken for a genuine
gap: a name that IS a participant resolves; ``I`` / ``we`` with nobody named is unassigned
(accepted, flagged); a name that is NOT a participant is unresolvable (rejected), because the
model attributed the commitment to somebody who was never in the room.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date

from speech_lexicon_kit import ChannelRole, Transcript

from .dates import parse_due
from .meeting import (
    Candidate,
    CommitmentKind,
    DecisionState,
    OwnerResolution,
    Register,
    RegisterEntry,
    RegisterOutcome,
)
from .retention import RetentionPack

__all__ = ["ActionRegisterEngine", "UnknownMarketError"]

_GROUP_REFS: frozenset[str] = frozenset({"", "we", "us", "team", "everyone", "all", "group"})
_SELF_REFS: frozenset[str] = frozenset({"i", "me", "my", "myself"})
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


class UnknownMarketError(ValueError):
    """Raised when a meeting names a market this engine has no retention pack for (fail closed)."""


def _normalize(text: str) -> str:
    """A stable key for dedupe: lowercased, punctuation dropped, whitespace collapsed."""
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


class ActionRegisterEngine:
    """Turn model candidates into an accepted/rejected register, deterministically and cited."""

    def __init__(self, packs: Mapping[str, RetentionPack]) -> None:
        self._packs = dict(packs)

    @property
    def markets(self) -> tuple[str, ...]:
        return tuple(sorted(self._packs))

    def build(
        self,
        transcript: Transcript,
        candidates: Iterable[Candidate],
        *,
        market: str,
        as_of: date,
        meeting_id: str,
    ) -> Register:
        pack = self._packs.get(market)
        if pack is None:
            raise UnknownMarketError(
                f"no retention pack for market {market!r}; known markets are {self.markets}"
            )
        roster = self._roster(transcript)
        ordered = list(candidates)
        superseded = {c.supersedes.strip() for c in ordered if c.supersedes.strip()}
        seen: set[tuple[str, str, str]] = set()
        entries: list[RegisterEntry] = []
        for position, candidate in enumerate(ordered, start=1):
            entries.append(
                self._evaluate(
                    candidate,
                    transcript=transcript,
                    roster=roster,
                    pack=pack,
                    as_of=as_of,
                    entry_id=f"{meeting_id}-e{position}",
                    superseded=superseded,
                    seen=seen,
                )
            )
        return Register(meeting_id=meeting_id, market=market, as_of=as_of, entries=tuple(entries))

    def _evaluate(
        self,
        candidate: Candidate,
        *,
        transcript: Transcript,
        roster: Mapping[str, ChannelRole],
        pack: RetentionPack,
        as_of: date,
        entry_id: str,
        superseded: set[str],
        seen: set[tuple[str, str, str]],
    ) -> RegisterEntry:
        reasons: list[str] = []

        if not candidate.citation.resolvable(transcript):
            reasons.append("citation-unresolvable")

        owner, role, resolution = self._resolve_owner(candidate, transcript, roster)
        if candidate.kind is CommitmentKind.ACTION and resolution is OwnerResolution.UNRESOLVABLE:
            reasons.append("owner-unresolved")

        due_date = parse_due(candidate.due_phrase, as_of) if candidate.due_phrase.strip() else None
        if (
            candidate.kind is CommitmentKind.ACTION
            and candidate.due_phrase.strip()
            and due_date is None
        ):
            reasons.append("due-unparseable")

        key = (candidate.kind.value, _normalize(candidate.text), owner)
        if key in seen:
            reasons.append("duplicate")

        state = self._state(candidate, superseded)
        if reasons:
            return RegisterEntry(
                entry_id=entry_id,
                kind=candidate.kind,
                text=candidate.text,
                owner=owner,
                owner_resolution=resolution,
                state=state,
                outcome=RegisterOutcome.REJECTED,
                citation=candidate.citation,
                due_date=due_date,
                reasons=tuple(reasons),
            )

        seen.add(key)
        if candidate.kind is CommitmentKind.ACTION:
            sla_due = pack.sla_due(as_of, due_date=due_date)
        else:
            sla_due = pack.decision_due(as_of)
        requires_review = (
            (candidate.kind is CommitmentKind.ACTION and resolution is OwnerResolution.UNASSIGNED)
            or role is ChannelRole.THIRD_PARTY
            or pack.is_externally_binding(candidate.text)
        )
        return RegisterEntry(
            entry_id=entry_id,
            kind=candidate.kind,
            text=candidate.text,
            owner=owner,
            owner_resolution=resolution,
            state=state,
            outcome=RegisterOutcome.ACCEPTED,
            citation=candidate.citation,
            due_date=due_date,
            sla_due=sla_due,
            retention_until=pack.retention_until(as_of),
            requires_human_review=requires_review,
        )

    @staticmethod
    def _roster(transcript: Transcript) -> dict[str, ChannelRole]:
        roster: dict[str, ChannelRole] = {}
        for turn in transcript.turns:
            # A speaker's role is fixed across the meeting; first sighting wins deterministically.
            roster.setdefault(turn.speaker_id, turn.role)
        return roster

    @staticmethod
    def _state(candidate: Candidate, superseded: set[str]) -> DecisionState:
        if candidate.candidate_id in superseded:
            return DecisionState.SUPERSEDED
        if candidate.kind is CommitmentKind.ACTION:
            return DecisionState.AGREED
        return candidate.decision_state

    @staticmethod
    def _resolve_owner(
        candidate: Candidate,
        transcript: Transcript,
        roster: Mapping[str, ChannelRole],
    ) -> tuple[str, ChannelRole, OwnerResolution]:
        ref = candidate.owner_ref.strip().lower()
        if ref in _GROUP_REFS:
            return "", ChannelRole.UNKNOWN, OwnerResolution.UNASSIGNED
        if ref in _SELF_REFS:
            if candidate.citation.resolvable(transcript):
                turn = transcript.turns[candidate.citation.turn_index]
                return turn.speaker_id, turn.role, OwnerResolution.RESOLVED
            return "", ChannelRole.UNKNOWN, OwnerResolution.UNRESOLVABLE
        for speaker_id in sorted(roster):
            lowered = speaker_id.lower()
            if ref == lowered or ref in lowered or lowered in ref:
                return speaker_id, roster[speaker_id], OwnerResolution.RESOLVED
        return "", ChannelRole.UNKNOWN, OwnerResolution.UNRESOLVABLE
