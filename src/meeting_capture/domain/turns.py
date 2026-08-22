"""Deterministic transcript assembly and redaction: the pure half of ingestion (slice 2).

Two operations, both pure and both replayable to the byte:

* :func:`assemble` joins a recogniser's turns with a diarizer's speaker segments using the shared
  speech kit's ``merge_diarization`` (largest-overlap wins, fixed tie-break), so the same audio
  yields the same speaker labels on every run. ``digest`` from the kit turns "this is
  deterministic" into something a test asserts.
* :func:`redact_for_model` masks personal data in every turn BEFORE the transcript is ever handed
  to the model. It strips per-word offsets from the redacted copy on purpose: masking changes
  character lengths, so a word offset computed on the original no longer lines up, and a stale
  offset is worse than an absent one. Turn-level timing (``start_ms`` / ``end_ms``) survives, so
  the minutes timeline still resolves, and every downstream stage (extraction, the register, the
  minutes) sees ONLY the redacted transcript.
"""

from __future__ import annotations

from collections.abc import Iterable

from pii_kit import Pattern, redact
from speech_lexicon_kit import (
    SpeakerSegment,
    SpeakerTurn,
    Transcript,
    digest,
    merge_diarization,
)

__all__ = ["assemble", "redact_for_model", "transcript_digest"]


def assemble(transcript: Transcript, segments: Iterable[SpeakerSegment]) -> Transcript:
    """Merge diarization segments into ``transcript`` deterministically, preserving metadata."""
    merged = merge_diarization(transcript.turns, tuple(segments))
    return Transcript(
        transcript_id=transcript.transcript_id,
        locale=transcript.locale,
        turns=merged,
        started_at=transcript.started_at,
        ended_at=transcript.ended_at,
        audio_duration_ms=transcript.audio_duration_ms,
        engine=transcript.engine,
    )


def redact_for_model(transcript: Transcript, patterns: tuple[Pattern, ...]) -> Transcript:
    """Return a copy of ``transcript`` with every turn's text masked and word offsets stripped."""
    masked_turns: list[SpeakerTurn] = []
    for turn in transcript.turns:
        masked_turns.append(
            SpeakerTurn(
                index=turn.index,
                speaker_id=turn.speaker_id,
                role=turn.role,
                text=redact(turn.text, patterns),
                start_ms=turn.start_ms,
                end_ms=turn.end_ms,
                channel=turn.channel,
                words=(),
                language=turn.language,
            )
        )
    return Transcript(
        transcript_id=transcript.transcript_id,
        locale=transcript.locale,
        turns=tuple(masked_turns),
        started_at=transcript.started_at,
        ended_at=transcript.ended_at,
        audio_duration_ms=transcript.audio_duration_ms,
        engine=transcript.engine,
    )


def transcript_digest(transcript: Transcript) -> str:
    """The canonical digest of a transcript: equal iff two assemblies are byte-identical."""
    return digest(transcript)
