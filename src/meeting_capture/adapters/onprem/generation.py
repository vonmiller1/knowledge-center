"""On-prem GenerationPort: the fail-fast sovereign placeholder."""

from __future__ import annotations

from ...config import Settings
from ...ports.generation import ExtractionRequest, NarrationRequest


class OnPremGenerationAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract(self, request: ExtractionRequest) -> str:
        raise NotImplementedError(
            "on-prem generation is a client-hosted model; see docs/onprem-migration.md"
        )

    def narrate(self, request: NarrationRequest) -> str:
        raise NotImplementedError(
            "on-prem generation is a client-hosted model; see docs/onprem-migration.md"
        )
