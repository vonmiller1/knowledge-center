"""On-prem DiarizationPort: the fail-fast sovereign placeholder."""

from __future__ import annotations

from speech_lexicon_kit import DiarizationRequest, DiarizationResult

from ...config import Settings


class OnPremDiarizationAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def diarize(self, request: DiarizationRequest) -> DiarizationResult:
        raise NotImplementedError(
            "on-prem diarization is a client-provided component; see docs/onprem-migration.md"
        )
