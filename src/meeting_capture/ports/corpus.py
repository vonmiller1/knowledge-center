"""CorpusPort: the enterprise-knowledge-base governed-knowledge boundary (slice 5's publish target).

Review-approved minutes publish into the enterprise-knowledge-base so past decisions become
retrievable WITH citations, which is the row's mandatory enterprise-knowledge-base dependency. The
port names the hand-off; the adapters own the ingestion. ``publish`` returns the corpus document id
(never empty, so a caller can record what landed), and ``retrieve`` is how a later meeting or an
operator finds a prior decision. Retrieval that finds nothing returns an empty tuple; a consumer
that needs grounding treats empty as a refusal rather than inventing an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "CorpusDocument",
    "CorpusPassage",
    "CorpusPort",
]


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    """A governed document to publish: already-redacted minutes, tagged for retrieval."""

    doc_id: str
    title: str
    market: str
    body: str
    tags: tuple[str, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class CorpusPassage:
    """One retrieved passage plus its provenance, so an answer can cite it."""

    doc_id: str
    title: str
    snippet: str
    score: float = 0.0


@runtime_checkable
class CorpusPort(Protocol):
    def publish(self, document: CorpusDocument) -> str:
        """Ingest ``document`` into the governed corpus and return its stored id."""
        ...

    def retrieve(self, query: str, *, limit: int = 5) -> tuple[CorpusPassage, ...]:
        """Return up to ``limit`` passages matching ``query``, or an empty tuple."""
        ...
