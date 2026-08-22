"""Schema validation of model extraction: well-formed candidates survive, the rest are discarded."""

from __future__ import annotations

import json

from speech_lexicon_kit import ChannelRole, SpeakerTurn, Transcript

from meeting_capture.domain.candidates import parse_candidates


def _transcript() -> Transcript:
    return Transcript(
        transcript_id="t1",
        locale="en-SG",
        turns=(
            SpeakerTurn(
                index=0,
                speaker_id="Priya (FICTIONAL)",
                role=ChannelRole.PARTICIPANT,
                text="I will prepare the pack.",
                start_ms=0,
                end_ms=1000,
            ),
        ),
    )


def _payload(*candidates: dict[str, object]) -> str:
    return json.dumps({"candidates": list(candidates)})


def test_a_well_formed_candidate_is_kept() -> None:
    raw = _payload(
        {
            "id": "c1",
            "kind": "action",
            "text": "prepare the pack",
            "owner_ref": "Priya",
            "due_phrase": "in 5 days",
            "citation": {"turn_index": 0, "char_start": 0, "char_end": 10},
        }
    )
    parse = parse_candidates(raw, _transcript())
    assert len(parse.candidates) == 1
    assert not parse.discarded


def test_a_candidate_with_a_bad_citation_is_discarded_not_repaired() -> None:
    raw = _payload(
        {
            "kind": "action",
            "text": "x",
            "owner_ref": "Priya",
            "citation": {"turn_index": 0, "char_start": 5, "char_end": 2},
        }
    )
    parse = parse_candidates(raw, _transcript())
    assert parse.candidates == ()
    assert len(parse.discarded) == 1


def test_a_candidate_missing_required_fields_is_discarded() -> None:
    raw = _payload({"kind": "action"})  # no text, no citation
    parse = parse_candidates(raw, _transcript())
    assert parse.candidates == ()
    assert len(parse.discarded) == 1


def test_a_non_json_payload_yields_no_candidates_rather_than_crashing() -> None:
    parse = parse_candidates("not json at all", _transcript())
    assert parse.candidates == ()
    assert len(parse.discarded) == 1


def test_a_payload_that_is_not_the_expected_shape_is_discarded() -> None:
    parse = parse_candidates(json.dumps({"items": []}), _transcript())
    assert parse.candidates == ()
    assert len(parse.discarded) == 1


def test_valid_and_invalid_candidates_are_partitioned() -> None:
    raw = _payload(
        {
            "kind": "action",
            "text": "ok",
            "owner_ref": "Priya",
            "citation": {"turn_index": 0, "char_start": 0, "char_end": 2},
        },
        {"kind": "action"},  # invalid
    )
    parse = parse_candidates(raw, _transcript())
    assert len(parse.candidates) == 1
    assert len(parse.discarded) == 1
