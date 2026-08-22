"""Synthetic meeting fixtures: the offline transcripts, diarization and scripted extraction.

One home for the fictional meetings the local adapters, the demo and the eval all replay, so
"deterministic" is a property of shared data rather than three copies that drift. Every party is
obviously fictional and every identifier is synthetic (an RFC-style planted NRIC, an ``.example``
address). Three meetings span three markets (SG / AU / JP) so the per-market retention packs are
each exercised and each can be proved able to make the SLA metric go red.

The scripted extraction is what a MODEL would return from the redacted transcript. It is keyed by
turn: each scripted candidate names the turn it came from, and the local generation adapter fills
the citation span from the LIVE redacted turn text, so a citation always resolves regardless of
how redaction changed a length. Commitment turns are kept free of personal data; the planted NRIC
lives in a non-commitment turn so redaction has something to mask without disturbing a citation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from speech_lexicon_kit import ChannelRole, SpeakerSegment, SpeakerTurn, Transcript

__all__ = [
    "FIXTURE_MEETINGS",
    "FixtureMeeting",
    "RawTurn",
    "ScriptedCandidate",
    "meeting_for_uri",
]


@dataclass(frozen=True, slots=True)
class RawTurn:
    speaker_id: str
    role: ChannelRole
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class ScriptedCandidate:
    """What the model 'extracted' for one turn; the adapter fills the citation from live text."""

    turn_index: int
    kind: str
    owner_ref: str
    due_phrase: str = ""
    decision_state: str = "proposed"
    supersedes: str = ""


@dataclass(frozen=True, slots=True)
class FixtureMeeting:
    meeting_id: str
    transcript_id: str
    audio_uri: str
    locale: str
    market: str
    as_of: date
    turns: tuple[RawTurn, ...]
    scripted: tuple[ScriptedCandidate, ...]
    planted_nric: str = ""

    def transcript(self) -> Transcript:
        """The recogniser's transcript (speaker-attributed turns, before diarization merge)."""
        turns = tuple(
            SpeakerTurn(
                index=index,
                speaker_id=turn.speaker_id,
                role=turn.role,
                text=turn.text,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                channel=0,
            )
            for index, turn in enumerate(self.turns)
        )
        return Transcript(
            transcript_id=self.transcript_id,
            locale=self.locale,
            turns=turns,
            audio_duration_ms=self.turns[-1].end_ms if self.turns else 0,
            engine="fixture-recognizer",
        )

    def segments(self) -> tuple[SpeakerSegment, ...]:
        """One diarizer segment per turn, so the merge join is genuinely exercised offline."""
        return tuple(
            SpeakerSegment(
                speaker_id=turn.speaker_id,
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                channel=0,
                role=turn.role,
            )
            for turn in self.turns
        )


_PART = ChannelRole.PARTICIPANT
_THIRD = ChannelRole.THIRD_PARTY

_SG = FixtureMeeting(
    meeting_id="mtg-sg-2026-08-03",
    transcript_id="trs-sg-1",
    audio_uri="fixture://meetings/sg-1",
    locale="en-SG",
    market="SG",
    as_of=date(2026, 8, 3),
    planted_nric="S1234567D",
    turns=(
        RawTurn("Priya Menon (FICTIONAL)", _PART, "Good morning, let us start.", 0, 3000),
        RawTurn(
            "Wei Lim (FICTIONAL)",
            _PART,
            "I will prepare the onboarding pack.",
            3000,
            8000,
        ),
        RawTurn(
            "Priya Menon (FICTIONAL)",
            _PART,
            "We agreed to adopt the new KYC checklist.",
            8000,
            12000,
        ),
        RawTurn(
            "Sanjay Rao (FICTIONAL)",
            _PART,
            "Wei Lim will sign the vendor contract in 5 days.",
            12000,
            17000,
        ),
        RawTurn(
            "External Auditor (FICTIONAL)",
            _THIRD,
            "I will send the audit note next week.",
            17000,
            21000,
        ),
        RawTurn(
            "Sanjay Rao (FICTIONAL)",
            _PART,
            "Wei Lim will circulate the deck by soon.",
            21000,
            25000,
        ),
        RawTurn(
            "Priya Menon (FICTIONAL)",
            _PART,
            "Alex will book the boardroom in 3 days.",
            25000,
            29000,
        ),
        RawTurn(
            "Wei Lim (FICTIONAL)",
            _PART,
            "You can reach me at NRIC S1234567D for follow up.",
            29000,
            33000,
        ),
    ),
    scripted=(
        ScriptedCandidate(1, "action", "I"),
        ScriptedCandidate(2, "decision", "we", decision_state="agreed"),
        ScriptedCandidate(3, "action", "Wei Lim", "in 5 days"),
        ScriptedCandidate(4, "action", "I", "next week"),
        ScriptedCandidate(5, "action", "Wei Lim", "by soon"),
        ScriptedCandidate(6, "action", "Alex", "in 3 days"),
    ),
)

_AU = FixtureMeeting(
    meeting_id="mtg-au-2026-08-03",
    transcript_id="trs-au-1",
    audio_uri="fixture://meetings/au-1",
    locale="en-AU",
    market="AU",
    as_of=date(2026, 8, 3),
    turns=(
        RawTurn("Grace Nguyen (FICTIONAL)", _PART, "Thanks all for joining.", 0, 2500),
        RawTurn(
            "Tom Baker (FICTIONAL)",
            _PART,
            "I will update the risk register.",
            2500,
            7000,
        ),
        RawTurn(
            "Grace Nguyen (FICTIONAL)",
            _PART,
            "We decided to pause the migration.",
            7000,
            11000,
        ),
        RawTurn(
            "Tom Baker (FICTIONAL)",
            _PART,
            "Grace Nguyen will sign the customer commitment by 2026-09-15.",
            11000,
            16000,
        ),
    ),
    scripted=(
        ScriptedCandidate(1, "action", "I"),
        ScriptedCandidate(2, "decision", "we", decision_state="agreed"),
        ScriptedCandidate(3, "action", "Grace Nguyen", "by 2026-09-15"),
    ),
)

_JP = FixtureMeeting(
    meeting_id="mtg-jp-2026-08-03",
    transcript_id="trs-jp-1",
    audio_uri="fixture://meetings/jp-1",
    locale="en-JP",
    market="JP",
    as_of=date(2026, 8, 3),
    turns=(
        RawTurn("Aiko Tanaka (FICTIONAL)", _PART, "Let us begin.", 0, 2000),
        RawTurn(
            "Ken Sato (FICTIONAL)",
            _PART,
            "I will draft the board summary.",
            2000,
            6000,
        ),
        RawTurn(
            "Aiko Tanaka (FICTIONAL)",
            _PART,
            "We agreed to renew the license.",
            6000,
            10000,
        ),
    ),
    scripted=(
        ScriptedCandidate(1, "action", "I"),
        ScriptedCandidate(2, "decision", "we", decision_state="agreed"),
    ),
)

FIXTURE_MEETINGS: tuple[FixtureMeeting, ...] = (_SG, _AU, _JP)

_BY_URI: dict[str, FixtureMeeting] = {m.audio_uri: m for m in FIXTURE_MEETINGS}
_BY_TRANSCRIPT: dict[str, FixtureMeeting] = {m.transcript_id: m for m in FIXTURE_MEETINGS}


def meeting_for_uri(uri: str) -> FixtureMeeting | None:
    return _BY_URI.get(uri)


def meeting_for_transcript(transcript_id: str) -> FixtureMeeting | None:
    return _BY_TRANSCRIPT.get(transcript_id)
