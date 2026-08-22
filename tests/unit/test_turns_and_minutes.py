"""Deterministic assembly + redaction (slice 2) and minutes grounding (slice 5)."""

from __future__ import annotations

import json
from datetime import date

from speech_lexicon_kit import ChannelRole, SpeakerSegment, SpeakerTurn, Transcript

from meeting_capture.domain.action_register import ActionRegisterEngine
from meeting_capture.domain.candidates import parse_candidates
from meeting_capture.domain.meeting import (
    Candidate,
    CommitmentKind,
    Register,
    SpanCitation,
)
from meeting_capture.domain.minutes import draft_minutes
from meeting_capture.domain.pii import PII_PATTERNS
from meeting_capture.domain.retention import load_pack_mapping
from meeting_capture.domain.turns import assemble, redact_for_model, transcript_digest

_PACK = load_pack_mapping(
    {
        "market": "SG",
        "action_sla_days": 5,
        "decision_review_days": 10,
        "retention_years": 7,
        "external_binding_markers": ["sign"],
    }
)


def _raw_transcript() -> Transcript:
    return Transcript(
        transcript_id="t1",
        locale="en-SG",
        turns=(
            SpeakerTurn(
                index=0,
                speaker_id="unknown",
                role=ChannelRole.UNKNOWN,
                text="I will prepare the pack. Reach me at NRIC S1234567D.",
                start_ms=0,
                end_ms=2000,
            ),
        ),
    )


def _segments() -> tuple[SpeakerSegment, ...]:
    return (
        SpeakerSegment(
            speaker_id="Priya (FICTIONAL)",
            start_ms=0,
            end_ms=2000,
            role=ChannelRole.PARTICIPANT,
        ),
    )


def test_assembly_is_byte_identical_across_replays() -> None:
    first = assemble(_raw_transcript(), _segments())
    second = assemble(_raw_transcript(), _segments())
    assert transcript_digest(first) == transcript_digest(second)


def test_assembly_assigns_the_diarized_speaker_and_role() -> None:
    assembled = assemble(_raw_transcript(), _segments())
    assert assembled.turns[0].speaker_id == "Priya (FICTIONAL)"
    assert assembled.turns[0].role is ChannelRole.PARTICIPANT


def test_redaction_masks_pii_and_strips_word_offsets() -> None:
    assembled = assemble(_raw_transcript(), _segments())
    redacted = redact_for_model(assembled, PII_PATTERNS)
    assert "S1234567D" not in redacted.turns[0].text
    assert redacted.turns[0].words == ()
    # Turn-level timing survives so the minutes timeline still resolves.
    assert redacted.turns[0].start_ms == 0


def _register() -> tuple[Register, Transcript]:
    transcript = redact_for_model(assemble(_raw_transcript(), _segments()), PII_PATTERNS)
    text = transcript.turns[0].text
    candidate = Candidate(
        candidate_id="c1",
        kind=CommitmentKind.ACTION,
        text=text,
        owner_ref="I",
        due_phrase="",
        citation=SpanCitation(turn_index=0, char_start=0, char_end=len(text)),
    )
    engine = ActionRegisterEngine({"SG": _PACK})
    register = engine.build(
        transcript, [candidate], market="SG", as_of=date(2026, 8, 3), meeting_id="m"
    )
    return register, transcript


def test_grounded_minutes_are_kept() -> None:
    register, transcript = _register()
    entry = register.accepted[0]
    narration = json.dumps(
        {
            "body": f"# Minutes\n- {entry.text} due {entry.sla_due.isoformat()}",
            "claims": [
                {
                    "entry_id": entry.entry_id,
                    "owner": entry.owner,
                    "date": entry.sla_due.isoformat(),
                }
            ],
        }
    )
    minutes = draft_minutes(register, narration, transcript)
    assert minutes.grounded is True
    assert minutes.body


def test_a_fabricated_date_in_the_body_makes_minutes_ungrounded() -> None:
    register, transcript = _register()
    narration = json.dumps({"body": "# Minutes\n- something due 2099-01-01", "claims": []})
    minutes = draft_minutes(register, narration, transcript)
    assert minutes.grounded is False
    assert minutes.body == "", "an ungrounded draft is discarded, never published"


def test_a_claim_against_a_wrong_owner_is_a_violation() -> None:
    register, transcript = _register()
    entry = register.accepted[0]
    narration = json.dumps(
        {
            "body": "# Minutes",
            "claims": [{"entry_id": entry.entry_id, "owner": "Somebody Else", "date": ""}],
        }
    )
    minutes = draft_minutes(register, narration, transcript)
    assert minutes.grounded is False


def test_the_parse_round_trips_through_the_local_extraction_shape() -> None:
    # A candidate JSON the local generation adapter would emit parses to exactly one candidate.
    transcript = redact_for_model(assemble(_raw_transcript(), _segments()), PII_PATTERNS)
    text = transcript.turns[0].text
    raw = json.dumps(
        {
            "candidates": [
                {
                    "id": "c1",
                    "kind": "action",
                    "text": text,
                    "owner_ref": "I",
                    "due_phrase": "",
                    "citation": {"turn_index": 0, "char_start": 0, "char_end": len(text)},
                }
            ]
        }
    )
    assert len(parse_candidates(raw, transcript).candidates) == 1
