"""Schema validation of the model's extraction output (slice 3).

The model proposes candidate decisions and actions as JSON. It is an LLM, so the output is
untrusted: a field may be missing, a type may be wrong, a citation may be malformed. This module
is the schema boundary. Every candidate is validated structurally and DISCARDED on failure rather
than repaired, because a silently repaired candidate is a fact nobody proposed, and the register
that follows would be computed from it.

What survives here is still only a CANDIDATE. Whether it enters the register (owner resolvable,
citation lands in a real turn, due phrase parseable) is the deterministic engine's decision, not
this module's. The split is deliberate: parsing proves the shape, the engine proves the content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from speech_lexicon_kit import Transcript

from .meeting import Candidate, CommitmentKind, DecisionState, MeetingError, SpanCitation

__all__ = ["ExtractionParse", "DiscardedCandidate", "parse_candidates"]


@dataclass(frozen=True, slots=True)
class DiscardedCandidate:
    """One raw candidate the schema rejected, with the reason (for the audit trail and demo)."""

    raw: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExtractionParse:
    """The outcome of validating a model extraction: what survived, and what was discarded."""

    candidates: tuple[Candidate, ...]
    discarded: tuple[DiscardedCandidate, ...] = ()


def _require_str(obj: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = obj.get(key, "")
    if not isinstance(value, str):
        raise MeetingError(f"field {key!r} must be a string")
    if not allow_empty and not value.strip():
        raise MeetingError(f"field {key!r} must be non-empty")
    return value


def _citation(obj: Any) -> SpanCitation:
    if not isinstance(obj, dict):
        raise MeetingError("citation must be an object")
    try:
        turn_index = int(obj["turn_index"])
        char_start = int(obj["char_start"])
        char_end = int(obj["char_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MeetingError(f"citation is missing or has a non-integer field: {exc}") from exc
    return SpanCitation(turn_index=turn_index, char_start=char_start, char_end=char_end)


def _one(obj: Any, index: int, transcript: Transcript) -> Candidate:
    if not isinstance(obj, dict):
        raise MeetingError("candidate must be an object")
    kind = CommitmentKind(_require_str(obj, "kind"))
    state_raw = obj.get("decision_state", DecisionState.PROPOSED.value)
    if not isinstance(state_raw, str):
        raise MeetingError("decision_state must be a string")
    return Candidate(
        candidate_id=str(obj.get("id") or f"cand-{index}"),
        kind=kind,
        text=_require_str(obj, "text"),
        owner_ref=_require_str(obj, "owner_ref", allow_empty=True),
        due_phrase=_require_str(obj, "due_phrase", allow_empty=True),
        citation=_citation(obj.get("citation")),
        decision_state=DecisionState(state_raw),
        supersedes=str(obj.get("supersedes") or ""),
    )


def parse_candidates(raw_json: str, transcript: Transcript) -> ExtractionParse:
    """Validate a model extraction payload; keep well-formed candidates, discard the rest.

    A payload that is not JSON, or not a ``{"candidates": [...]}`` object, yields an empty parse
    with a single discard record rather than raising: a broken model response is a bad input, not
    a crash, and the pipeline continues on whatever candidates were valid (here, none).
    """
    try:
        loaded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return ExtractionParse(candidates=(), discarded=(DiscardedCandidate(raw_json, str(exc)),))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("candidates"), list):
        return ExtractionParse(
            candidates=(),
            discarded=(DiscardedCandidate(raw_json, "payload is not {'candidates': [...]}"),),
        )

    kept: list[Candidate] = []
    discarded: list[DiscardedCandidate] = []
    for index, obj in enumerate(loaded["candidates"]):
        try:
            kept.append(_one(obj, index, transcript))
        except (MeetingError, ValueError) as exc:
            discarded.append(DiscardedCandidate(json.dumps(obj, default=str), str(exc)))
    return ExtractionParse(candidates=tuple(kept), discarded=tuple(discarded))
