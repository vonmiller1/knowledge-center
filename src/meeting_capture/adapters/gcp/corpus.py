"""Managed CorpusPort: Hrz2 ingestion via Vertex AI Search (Discovery Engine), imported LAZILY."""

from __future__ import annotations

from ...config import Settings
from ...ports.corpus import CorpusDocument, CorpusPassage


class CloudCorpusAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def publish(self, document: CorpusDocument) -> str:
        from google.cloud import discoveryengine  # lazy: offline profiles never import it

        discoveryengine.DocumentServiceClient()
        raise NotImplementedError("managed corpus publish is deployment-wired; see docs/runbook.md")

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[CorpusPassage, ...]:
        from google.cloud import discoveryengine  # lazy: offline profiles never import it

        discoveryengine.SearchServiceClient()
        raise NotImplementedError(
            "managed corpus retrieve is deployment-wired; see docs/runbook.md"
        )
