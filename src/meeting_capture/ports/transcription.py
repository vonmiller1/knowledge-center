"""SpeechToTextPort: transcript ingestion (slice 2), re-exported from the shared speech kit.

The speech-to-text boundary and its request/result types are NOT redeclared here: they come from
``speech-lexicon-kit`` so a transcript citation ("turn 4, characters 0..37") means the same thing
in this repo, the conversation-QA scorecard and the comms-surveillance case. Re-exporting once
keeps a single import site for the boundary set, exactly as ``IdentityPort`` is re-exported from
the commons in ``ports/__init__.py``.
"""

from __future__ import annotations

from speech_lexicon_kit import (
    AudioRef,
    SpeechToTextPort,
    TranscriptionRequest,
    TranscriptionResult,
)

__all__ = [
    "AudioRef",
    "SpeechToTextPort",
    "TranscriptionRequest",
    "TranscriptionResult",
]
