"""Local GenerationPort: a deterministic stub for the model (SDK-free).

The stub stands in for Gemini so the whole pipeline is replayable offline. Extraction is scripted
per fixture meeting: each scripted candidate names a turn, and the adapter fills the citation from
the LIVE redacted turn text (span 0..len), so a citation always resolves and the candidate text is
exactly what a reviewer sees. For a transcript with no script (an arbitrary API upload) it falls
back to a small, deterministic cue heuristic so the surface still works. Narration is rendered
straight from the register, so the minutes draft is grounded by construction; the ``gcp`` adapter
would produce real prose, and the domain grounds either the same way.

The stub NEVER produces a number or a verdict: it proposes candidate text and drafts prose. Owners,
dates, acceptance and escalation are all the deterministic engine's, which is what keeps the
register identical whether the stub or a live model is bound.
"""

from __future__ import annotations

import json
from typing import Any

from ...config import Settings
from ...ports.generation import ExtractionRequest, NarrationRequest
from ._fixtures import meeting_for_transcript

_ACTION_CUES = ("i will", "i'll", "we will", "we'll", "please", "action:", "follow up", "sign ")
_DECISION_CUES = ("we agreed", "we decided", "decision:", "agreed to", "we will go with")


class LocalGenerationAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract(self, request: ExtractionRequest) -> str:
        transcript = request.transcript
        meeting = meeting_for_transcript(transcript.transcript_id)
        if meeting is not None:
            candidates = self._scripted(request, meeting.scripted)
        else:
            candidates = self._heuristic(request)
        return json.dumps({"candidates": candidates})

    def _scripted(self, request: ExtractionRequest, scripted: Any) -> list[dict[str, Any]]:
        transcript = request.transcript
        out: list[dict[str, Any]] = []
        for index, item in enumerate(scripted):
            if not 0 <= item.turn_index < len(transcript.turns):
                continue
            text = transcript.turns[item.turn_index].text
            out.append(
                {
                    "id": f"{transcript.transcript_id}-c{index}",
                    "kind": item.kind,
                    "text": text,
                    "owner_ref": item.owner_ref,
                    "due_phrase": item.due_phrase,
                    "citation": {
                        "turn_index": item.turn_index,
                        "char_start": 0,
                        "char_end": len(text),
                    },
                    "decision_state": item.decision_state,
                    "supersedes": item.supersedes,
                }
            )
        return out

    def _heuristic(self, request: ExtractionRequest) -> list[dict[str, Any]]:
        transcript = request.transcript
        out: list[dict[str, Any]] = []
        for turn in transcript.turns:
            lowered = turn.text.lower()
            is_decision = any(cue in lowered for cue in _DECISION_CUES)
            is_action = any(cue in lowered for cue in _ACTION_CUES)
            if not (is_decision or is_action):
                continue
            out.append(
                {
                    "id": f"{transcript.transcript_id}-h{turn.index}",
                    "kind": "decision" if is_decision else "action",
                    "text": turn.text,
                    "owner_ref": "" if is_decision else "I",
                    "due_phrase": "",
                    "citation": {
                        "turn_index": turn.index,
                        "char_start": 0,
                        "char_end": len(turn.text),
                    },
                    "decision_state": "agreed" if is_decision else "proposed",
                    "supersedes": "",
                }
            )
        return out

    def narrate(self, request: NarrationRequest) -> str:
        register = request.register
        lines: list[str] = ["# Minutes", ""]
        claims: list[dict[str, str]] = []
        for entry in register.accepted:
            operative = entry.sla_due or entry.due_date
            date_str = operative.isoformat() if operative else ""
            owner = entry.owner or "unassigned"
            lines.append(
                f"- [{entry.kind.value}] {entry.text} (owner: {owner}; due: {date_str or 'n/a'})"
            )
            claims.append({"entry_id": entry.entry_id, "owner": entry.owner, "date": date_str})
        return json.dumps({"body": "\n".join(lines), "claims": claims})
