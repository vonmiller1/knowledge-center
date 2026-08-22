"""On-prem CorpusPort: the fail-fast sovereign placeholder."""

from __future__ import annotations

from ...config import Settings
from ...ports.corpus import CorpusDocument, CorpusPassage


class OnPremCorpusAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def publish(self, document: CorpusDocument) -> str:
        raise NotImplementedError(
            "on-prem corpus is a client-hosted knowledge base; see docs/onprem-migration.md"
        )

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[CorpusPassage, ...]:
        raise NotImplementedError(
            "on-prem corpus is a client-hosted knowledge base; see docs/onprem-migration.md"
        )
