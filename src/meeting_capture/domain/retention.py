"""Per-market retention packs, as DATA rather than code.

A retention pack is the client's policy: how long an action has before it breaches SLA, how long
a decision waits for review, how many years the record is retained, and which words mark a
commitment as externally binding (a signed obligation to a customer or vendor, which must reach a
human). The numbers are the bank's, and they differ per market, so they live in versioned YAML
under ``config/packs/`` and are VALIDATED here. Reading those files is not: the YAML parse
lives at the config boundary in :mod:`meeting_capture.packs`, and this module takes documents
that are already plain mappings, so the core depends on no parser. An unknown field REFUSES at
load: a pack that carries a key the engine does not understand is a policy the engine is not
applying, and silently ignoring it is how a retention rule goes unenforced.

The engine holds one pack per market and fails closed on a market it has no pack for, so a
meeting from an unconfigured jurisdiction yields no verdict rather than a guessed one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

__all__ = ["RetentionPack", "build_pack_set", "load_pack_mapping"]

_REQUIRED: frozenset[str] = frozenset(
    {
        "market",
        "action_sla_days",
        "decision_review_days",
        "retention_years",
        "external_binding_markers",
    }
)


class RetentionPackError(ValueError):
    """Raised when a retention pack is malformed, incomplete or carries an unknown field."""


@dataclass(frozen=True, slots=True)
class RetentionPack:
    """One market's retention and escalation policy, validated at construction."""

    market: str
    action_sla_days: int
    decision_review_days: int
    retention_years: int
    external_binding_markers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.market.strip():
            raise RetentionPackError("RetentionPack.market must be non-empty")
        for name, value in (
            ("action_sla_days", self.action_sla_days),
            ("decision_review_days", self.decision_review_days),
            ("retention_years", self.retention_years),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RetentionPackError(f"RetentionPack.{name} must be a non-negative int")

    def sla_due(self, as_of: date, *, due_date: date | None) -> date:
        """The SLA date for an action: its explicit due date if any, else the pack window."""
        if due_date is not None:
            return due_date
        return _add_days(as_of, self.action_sla_days)

    def decision_due(self, as_of: date) -> date:
        """The review-by date for a decision, from the pack's decision window."""
        return _add_days(as_of, self.decision_review_days)

    def retention_until(self, as_of: date) -> date:
        """The retention horizon: ``as_of`` plus the retention window, in whole years."""
        return _add_years(as_of, self.retention_years)

    def is_externally_binding(self, text: str) -> bool:
        """True when the (already-redacted) commitment text names an external-binding marker."""
        lowered = text.lower()
        return any(marker.lower() in lowered for marker in self.external_binding_markers)


def _add_days(start: date, days: int) -> date:
    from datetime import timedelta

    return start + timedelta(days=days)


def _add_years(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        # 29 February in a non-leap target year: fall back to 28 February, deterministically.
        return start.replace(year=start.year + years, day=28)


def _pack_from_mapping(data: Mapping[str, Any], source: str) -> RetentionPack:
    keys = set(data)
    unknown = keys - _REQUIRED
    if unknown:
        raise RetentionPackError(f"{source}: unknown field(s) {sorted(unknown)}; refusing to load")
    missing = _REQUIRED - keys
    if missing:
        raise RetentionPackError(f"{source}: missing field(s) {sorted(missing)}")
    markers = data["external_binding_markers"]
    if not isinstance(markers, list) or not all(isinstance(m, str) for m in markers):
        raise RetentionPackError(f"{source}: external_binding_markers must be a list of strings")
    return RetentionPack(
        market=str(data["market"]),
        action_sla_days=int(data["action_sla_days"]),
        decision_review_days=int(data["decision_review_days"]),
        retention_years=int(data["retention_years"]),
        external_binding_markers=tuple(str(m) for m in markers),
    )


def load_pack_mapping(data: Mapping[str, Any], source: str = "<mapping>") -> RetentionPack:
    """Build one pack from an already-parsed mapping (the seam tests drive)."""
    return _pack_from_mapping(data, source)


def build_pack_set(
    documents: Iterable[tuple[str, Any]], *, origin: str = "<documents>"
) -> dict[str, RetentionPack]:
    """Validate already-parsed pack documents into one set, keyed by market code.

    ``documents`` is ``(source, parsed)`` pairs in the order the boundary read them; ``source``
    names where each came from so a refusal points at a file. Every rule that makes a SET of
    packs valid rather than one pack valid lives here, because they are policy and not parsing:
    two packs claiming the same market is a configuration error rather than a silent
    last-one-wins, and an empty set refuses rather than yielding an engine with no policy at
    all. ``origin`` names the place the documents came from, for that second refusal.
    """
    packs: dict[str, RetentionPack] = {}
    for source, loaded in documents:
        if not isinstance(loaded, dict):
            raise RetentionPackError(f"{source}: a retention pack must be a mapping")
        pack = _pack_from_mapping(loaded, source)
        if pack.market in packs:
            raise RetentionPackError(f"{source}: market {pack.market!r} is already defined")
        packs[pack.market] = pack
    if not packs:
        raise RetentionPackError(f"no retention packs found under {origin}")
    return packs
