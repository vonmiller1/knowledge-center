"""TaskRouterPort: the A2A/MCP boundary to external task and calendar systems (slice 6).

Creating an assignment in a downstream system (a ticket, a calendar hold) is consequential: it is
an action taken in another system on somebody's behalf. So a register entry that is consequential
(unowned or externally binding) must be review-approved before it routes, and the approved entry
carries its review id into the external system's audit trail. The port names the hand-off; the
adapters own the tool call. ``create_task`` returns the external task id (never empty).

The engine, not this port, decides WHEN a task may be created. The port cannot enforce approval on
its own, so ``domain/capture_service.py`` refuses to call it for an unapproved consequential entry
and a test asserts zero adapter calls in that case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "TaskAssignment",
    "TaskRouterPort",
]


@dataclass(frozen=True, slots=True)
class TaskAssignment:
    """One assignment to create downstream, carrying the register provenance and any review id."""

    source_entry_id: str
    title: str
    owner: str
    market: str
    due_date: str = ""
    review_ref: str = ""


@runtime_checkable
class TaskRouterPort(Protocol):
    def create_task(self, assignment: TaskAssignment) -> str:
        """Create ``assignment`` in the external system and return its task id."""
        ...
