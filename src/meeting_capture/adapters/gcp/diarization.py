"""Managed DiarizationPort: Google Cloud Speech diarization, SDK imported LAZILY."""

from __future__ import annotations

from speech_lexicon_kit import DiarizationRequest, DiarizationResult

from ...config import Settings


class CloudDiarizationAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        from google.cloud import speech_v2  # lazy: offline profiles never import it

        speech_v2.SpeechClient()
        raise NotImplementedError("managed diarization is deployment-wired; see docs/runbook.md")
