"""On-prem SpeechToTextPort: the fail-fast sovereign placeholder.

A placeholder that returned a transcript would be a false portability claim. It RAISES
``NotImplementedError`` so a client migrating on premises wires their own recognizer here and
cannot ship a stub that silently produced nothing.
"""

from __future__ import annotations

from speech_lexicon_kit import TranscriptionRequest, TranscriptionResult

from ...config import Settings


class OnPremTranscriptionAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        raise NotImplementedError(
            "on-prem transcription is a client-provided recognizer; see docs/onprem-migration.md"
        )
