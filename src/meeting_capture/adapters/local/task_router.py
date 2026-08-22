"""Local TaskRouterPort: an in-memory task store standing in for the A2A/MCP tool call (SDK-free).

Records the assignments the service decided to route, so slice 6's proofs run offline: an
unapproved consequential entry results in ZERO create_task calls, and an approved one lands here
carrying its review id. It is not a no-op; a silent router would make the "zero calls" proof
vacuous.
"""

from __future__ import annotations

from ...config import Settings
from ...ports.task_router import TaskAssignment


class LocalTaskRouterAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tasks: list[TaskAssignment] = []

    def create_task(self, assignment: TaskAssignment) -> str:
        if not assignment.source_entry_id.strip():
            raise ValueError("TaskAssignment.source_entry_id must be non-empty")
        self._tasks.append(assignment)
        return f"task:{len(self._tasks)}:{assignment.source_entry_id}"

    @property
    def tasks(self) -> tuple[TaskAssignment, ...]:
        """The assignments created so far, for inspection in tests and the demo."""
        return tuple(self._tasks)
