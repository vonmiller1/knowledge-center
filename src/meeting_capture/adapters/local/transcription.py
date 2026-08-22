"""Local SpeechToTextPort: replay a fixture transcript for a known audio URI (SDK-free).

The offline family ANSWERS: given a fixture meeting's audio reference it returns that meeting's
speaker-attributed transcript, so the demo, the eval and the tests run the real ingestion path
with no cloud transcription. An unknown URI raises rather than fabricating an empty transcript.
"""

from __future__ import annotations

from speech_lexicon_kit import TranscriptError, TranscriptionRequest, TranscriptionResult

from ...config import Settings
from ._fixtures import meeting_for_uri


class LocalTranscriptionAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def transcribe(self, request: TranscriptionRequest) -> TranscriptionResult:
        meeting = meeting_for_uri(request.audio.uri)
        if meeting is None:
            raise TranscriptError(f"no fixture transcript for audio {request.audio.uri!r}")
        return TranscriptionResult(transcript=meeting.transcript())
