"""GenerationPort: the ONLY model seam, and it produces prose, never a number or a verdict.

The model does two things and nothing else: it EXTRACTS candidate commitments from a redacted
transcript (slice 3), and it DRAFTS minutes that restate register entries (slice 5). Both return
a JSON string that the domain validates and may discard; the model never returns a decision, an
owner assignment, a date or an escalation, because those are the deterministic engine's and the
whole determinism claim rests on the model being unable to move a number.

With the local (stub) adapter bound, the pipeline is fully deterministic: identical inputs give an
identical register and identical minutes. Swapping in the ``gcp`` adapter changes only the words in
the drafts, never a figure in the register.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from speech_lexicon_kit import Transcript

from ..domain.meeting import Register

__all__ = [
    "ExtractionRequest",
    "GenerationPort",
    "NarrationRequest",
]


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    """A redacted transcript to extract candidate commitments from."""

    transcript: Transcript


@dataclass(frozen=True, slots=True)
class NarrationRequest:
    """A computed register (and its redacted transcript) to draft grounded minutes from."""

    register: Register
    transcript: Transcript


@runtime_checkable
class GenerationPort(Protocol):
    def extract(self, request: ExtractionRequest) -> str:
        """Return a JSON ``{"candidates": [...]}`` payload; the domain schema-validates it."""
        ...

    def narrate(self, request: NarrationRequest) -> str:
        """Return a JSON ``{"body": ..., "claims": [...]}`` draft; the domain grounds it."""
        ...
