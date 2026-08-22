"""Managed TaskRouterPort: external task/calendar creation over A2A/MCP, imported LAZILY."""

from __future__ import annotations

from ...config import Settings
from ...ports.task_router import TaskAssignment


class CloudTaskRouterAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_task(self, assignment: TaskAssignment) -> str:
        from google.cloud import tasks_v2  # lazy: offline profiles never import it

        tasks_v2.CloudTasksClient()
        raise NotImplementedError("managed task routing is deployment-wired; see docs/runbook.md")
