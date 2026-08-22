"""Managed SpeechToTextPort: Google Cloud Speech-to-Text v2, with the SDK imported LAZILY.

The SDK import is the first statement in the method, so the class constructs under the offline
profiles with no cloud SDK installed (the portability proof) and REFUSES at call time when nothing
is reachable. Deployment wiring (project, recognizer, CMEK) is a runbook step, not a code default.
"""

from __future__ import annotations

from speech_lexicon_kit import TranscriptionRequest, TranscriptionResult

from ...config import Settings


class CloudTranscriptionAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        from google.cloud import speech_v2  # lazy: offline profiles never import it

        speech_v2.SpeechClient()
        raise NotImplementedError("managed transcription is deployment-wired; see docs/runbook.md")
