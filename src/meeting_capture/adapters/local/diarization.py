"""Local DiarizationPort: replay a fixture meeting's speaker segments (SDK-free)."""

from __future__ import annotations

from speech_lexicon_kit import DiarizationRequest, DiarizationResult, TranscriptError

from ...config import Settings
from ._fixtures import meeting_for_uri


class LocalDiarizationAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        meeting = meeting_for_uri(request.audio.uri)
        if meeting is None:
            raise TranscriptError(f"no fixture diarization for audio {request.audio.uri!r}")
        return DiarizationResult(request_id=request.request_id, segments=meeting.segments())
