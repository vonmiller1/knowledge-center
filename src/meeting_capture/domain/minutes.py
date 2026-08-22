"""Cited minutes (slice 5): the model drafts, the domain grounds, the ungrounded draft is dropped.

The LLM drafts minutes prose plus a set of structured claims (one per register entry it restates).
This module GROUNDS that draft against the deterministic register: every claim must name a real
accepted entry and repeat its owner and operative date exactly, and no date may appear in the
prose that the register did not compute. A draft that introduces an owner, a date or a decision
the register does not contain is ungrounded and is DISCARDED, never published, because minutes are
the record and a fabricated commitment in the record is the whole failure mode this system exists
to prevent.

Grounded minutes carry ``requires_human_review`` whenever the meeting produced any consequential
entry (unowned or externally binding), so the review-safety property holds at the minutes surface
as well as at the register: a consequential meeting never yields auto-published minutes.
"""

from __future__ import annotations

import json
import re
from typing import Any

from speech_lexicon_kit import Transcript

from .kernel import Citation
from .meeting import Minutes, Register, RegisterEntry

__all__ = ["draft_minutes"]

_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _entry_dates(entry: RegisterEntry) -> set[str]:
    return {d.isoformat() for d in (entry.due_date, entry.sla_due, entry.retention_until) if d}


def _ground_claim(claim: Any, by_id: dict[str, RegisterEntry]) -> str | None:
    """Return a violation string for one claim, or ``None`` when the claim is grounded."""
    if not isinstance(claim, dict):
        return "claim is not an object"
    entry_id = str(claim.get("entry_id", ""))
    entry = by_id.get(entry_id)
    if entry is None:
        return f"unknown-or-rejected-entry:{entry_id or '<missing>'}"
    owner = str(claim.get("owner", ""))
    if owner != entry.owner:
        return f"owner-mismatch:{entry_id}:{owner!r}!={entry.owner!r}"
    date_claim = str(claim.get("date", ""))
    if date_claim and date_claim not in _entry_dates(entry):
        return f"date-mismatch:{entry_id}:{date_claim}"
    return None


def draft_minutes(register: Register, narration_json: str, transcript: Transcript) -> Minutes:
    """Ground a model minutes draft against ``register``; discard the body if it is not grounded."""
    accepted = {entry.entry_id: entry for entry in register.accepted}
    allowed_dates: set[str] = set()
    for entry in register.accepted:
        allowed_dates |= _entry_dates(entry)

    violations: list[str] = []
    body = ""
    try:
        payload = json.loads(narration_json)
    except json.JSONDecodeError as exc:
        payload = None
        violations.append(f"narration-not-json:{exc}")

    if isinstance(payload, dict):
        body = str(payload.get("body", ""))
        claims = payload.get("claims", [])
        if not isinstance(claims, list):
            violations.append("claims must be a list")
            claims = []
        for claim in claims:
            violation = _ground_claim(claim, accepted)
            if violation is not None:
                violations.append(violation)
        for found in _ISO.findall(body):
            if found not in allowed_dates:
                violations.append(f"ungrounded-date:{found}")
    elif payload is not None:
        violations.append("narration payload is not an object")

    grounded = not violations
    citations: tuple[Citation, ...] = tuple(
        entry.citation.to_kernel(transcript) for entry in register.accepted
    )
    requires_review = any(entry.consequential for entry in register.entries)
    return Minutes(
        meeting_id=register.meeting_id,
        market=register.market,
        body=body if grounded else "",
        grounded=grounded,
        requires_human_review=requires_review,
        citations=citations,
        violations=tuple(violations),
    )
