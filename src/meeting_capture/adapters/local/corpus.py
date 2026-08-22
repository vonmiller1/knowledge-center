"""Local CorpusPort: an in-memory governed corpus standing in for Hrz2 (SDK-free).

Publish stores the (already-redacted) minutes; retrieve does a substring search over what was
published, so slice 5's publish round-trip and "past decisions are retrievable with citations"
run offline. It is deliberately not a no-op: a silent corpus would let a repo claim the Hrz2
dependency is wired while nothing landed.
"""

from __future__ import annotations

from ...config import Settings
from ...ports.corpus import CorpusDocument, CorpusPassage


class LocalCorpusAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._docs: dict[str, CorpusDocument] = {}

    def publish(self, document: CorpusDocument) -> str:
        if not document.doc_id.strip():
            raise ValueError("CorpusDocument.doc_id must be non-empty")
        self._docs[document.doc_id] = document
        return document.doc_id

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[CorpusPassage, ...]:
        needle = query.strip().lower()
        if not needle:
            return ()
        hits: list[CorpusPassage] = []
        for doc in self._docs.values():
            if needle in doc.body.lower() or needle in doc.title.lower():
                hits.append(
                    CorpusPassage(
                        doc_id=doc.doc_id,
                        title=doc.title,
                        snippet=doc.body[:160],
                        score=1.0,
                    )
                )
        return tuple(hits[:limit])

    @property
    def documents(self) -> tuple[CorpusDocument, ...]:
        """Published documents, for inspection in tests and the demo."""
        return tuple(self._docs.values())
