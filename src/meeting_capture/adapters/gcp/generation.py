"""Managed GenerationPort: Gemini via the Google GenAI SDK, imported LAZILY.

The managed model narrates and extracts; the deterministic engine still owns every number. The
SDK import is lazy so the offline profiles construct this class with no SDK, and it refuses at
call time when no model is reachable.
"""

from __future__ import annotations

from ...config import Settings
from ...ports.generation import ExtractionRequest, NarrationRequest


class CloudGenerationAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract(self, request: ExtractionRequest) -> str:
        from google import genai  # lazy: offline profiles never import it

        genai.Client()
        raise NotImplementedError("managed extraction is deployment-wired; see docs/runbook.md")

    def narrate(self, request: NarrationRequest) -> str:
        from google import genai  # lazy: offline profiles never import it

        genai.Client()
        raise NotImplementedError("managed narration is deployment-wired; see docs/runbook.md")
