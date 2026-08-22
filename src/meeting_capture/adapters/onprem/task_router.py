"""On-prem TaskRouterPort: the fail-fast sovereign placeholder."""

from __future__ import annotations

from ...config import Settings
from ...ports.task_router import TaskAssignment


class OnPremTaskRouterAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_task(self, assignment: TaskAssignment) -> str:
        raise NotImplementedError(
            "on-prem task routing is a client-hosted integration; see docs/onprem-migration.md"
        )
