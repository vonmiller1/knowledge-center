"""The deterministic action register engine: acceptance, rejection, owners, dates, dedupe."""

from __future__ import annotations

from datetime import date

import pytest
from speech_lexicon_kit import ChannelRole, SpeakerTurn, Transcript

from meeting_capture.domain.action_register import ActionRegisterEngine, UnknownMarketError
from meeting_capture.domain.meeting import (
    Candidate,
    CommitmentKind,
    DecisionState,
    OwnerResolution,
    RegisterOutcome,
    SpanCitation,
)
from meeting_capture.domain.retention import load_pack_mapping

_AS_OF = date(2026, 8, 3)
_PACK = load_pack_mapping(
    {
        "market": "SG",
        "action_sla_days": 5,
        "decision_review_days": 10,
        "retention_years": 7,
        "external_binding_markers": ["sign", "contract", "vendor"],
    }
)


def _transcript() -> Transcript:
    turns = (
        SpeakerTurn(
            index=0,
            speaker_id="Priya (FICTIONAL)",
            role=ChannelRole.PARTICIPANT,
            text="I will prepare the pack.",
            start_ms=0,
            end_ms=1000,
        ),
        SpeakerTurn(
            index=1,
            speaker_id="Auditor (FICTIONAL)",
            role=ChannelRole.THIRD_PARTY,
            text="I will sign the vendor contract.",
            start_ms=1000,
            end_ms=2000,
        ),
    )
    return Transcript(transcript_id="t1", locale="en-SG", turns=turns)


def _cand(
    cid: str,
    kind: str,
    owner_ref: str,
    turn: int,
    *,
    due: str = "",
    state: str = "proposed",
    supersedes: str = "",
) -> Candidate:
    text = _transcript().turns[turn].text if turn < len(_transcript().turns) else "x"
    return Candidate(
        candidate_id=cid,
        kind=CommitmentKind(kind),
        text=text,
        owner_ref=owner_ref,
        due_phrase=due,
        citation=SpanCitation(turn_index=turn, char_start=0, char_end=len(text)),
        decision_state=DecisionState(state),
        supersedes=supersedes,
    )


def _engine() -> ActionRegisterEngine:
    return ActionRegisterEngine({"SG": _PACK})


def test_a_self_action_resolves_to_the_speaker_and_gets_the_sla_default() -> None:
    register = _engine().build(
        _transcript(), [_cand("c1", "action", "I", 0)], market="SG", as_of=_AS_OF, meeting_id="m"
    )
    entry = register.entries[0]
    assert entry.outcome is RegisterOutcome.ACCEPTED
    assert entry.owner == "Priya (FICTIONAL)"
    assert entry.owner_resolution is OwnerResolution.RESOLVED
    assert entry.sla_due == date(2026, 8, 8)
    assert entry.retention_until == date(2033, 8, 3)
    assert entry.requires_human_review is False


def test_a_hallucinated_owner_is_rejected() -> None:
    register = _engine().build(
        _transcript(),
        [_cand("c1", "action", "Nonexistent Person", 0)],
        market="SG",
        as_of=_AS_OF,
        meeting_id="m",
    )
    entry = register.entries[0]
    assert entry.outcome is RegisterOutcome.REJECTED
    assert "owner-unresolved" in entry.reasons
    assert entry.owner_resolution is OwnerResolution.UNRESOLVABLE


def test_an_unparseable_due_is_rejected() -> None:
    register = _engine().build(
        _transcript(),
        [_cand("c1", "action", "I", 0, due="by soon")],
        market="SG",
        as_of=_AS_OF,
        meeting_id="m",
    )
    assert register.entries[0].outcome is RegisterOutcome.REJECTED
    assert "due-unparseable" in register.entries[0].reasons


def test_a_citation_that_does_not_land_is_rejected() -> None:
    bad = Candidate(
        candidate_id="c1",
        kind=CommitmentKind.ACTION,
        text="ghost",
        owner_ref="I",
        due_phrase="",
        citation=SpanCitation(turn_index=99, char_start=0, char_end=1),
    )
    register = _engine().build(_transcript(), [bad], market="SG", as_of=_AS_OF, meeting_id="m")
    assert register.entries[0].outcome is RegisterOutcome.REJECTED
    assert "citation-unresolvable" in register.entries[0].reasons


def test_an_external_binding_action_is_consequential() -> None:
    register = _engine().build(
        _transcript(),
        [_cand("c1", "action", "I", 1)],  # third-party speaker + "sign vendor contract"
        market="SG",
        as_of=_AS_OF,
        meeting_id="m",
    )
    entry = register.entries[0]
    assert entry.outcome is RegisterOutcome.ACCEPTED
    assert entry.requires_human_review is True
    assert entry.consequential is True


def test_an_unassigned_group_action_is_accepted_but_flagged() -> None:
    register = _engine().build(
        _transcript(),
        [_cand("c1", "action", "we", 0)],
        market="SG",
        as_of=_AS_OF,
        meeting_id="m",
    )
    entry = register.entries[0]
    assert entry.outcome is RegisterOutcome.ACCEPTED
    assert entry.owner_resolution is OwnerResolution.UNASSIGNED
    assert entry.requires_human_review is True


def test_duplicates_are_dropped() -> None:
    register = _engine().build(
        _transcript(),
        [_cand("c1", "action", "I", 0), _cand("c2", "action", "I", 0)],
        market="SG",
        as_of=_AS_OF,
        meeting_id="m",
    )
    assert register.entries[0].accepted
    assert "duplicate" in register.entries[1].reasons


def test_a_superseded_decision_is_marked() -> None:
    register = _engine().build(
        _transcript(),
        [
            _cand("d1", "decision", "we", 0, state="agreed"),
            _cand("d2", "decision", "we", 1, state="agreed", supersedes="d1"),
        ],
        market="SG",
        as_of=_AS_OF,
        meeting_id="m",
    )
    assert register.entries[0].state is DecisionState.SUPERSEDED


def test_an_unknown_market_fails_closed() -> None:
    with pytest.raises(UnknownMarketError):
        _engine().build(
            _transcript(),
            [_cand("c1", "action", "I", 0)],
            market="ZZ",
            as_of=_AS_OF,
            meeting_id="m",
        )


def test_the_engine_is_deterministic_across_runs() -> None:
    candidates = [_cand("c1", "action", "I", 0), _cand("c2", "action", "I", 1)]
    first = _engine().build(_transcript(), candidates, market="SG", as_of=_AS_OF, meeting_id="m")
    second = _engine().build(_transcript(), candidates, market="SG", as_of=_AS_OF, meeting_id="m")
    assert first == second
