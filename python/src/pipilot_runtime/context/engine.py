"""Build the initial Python-owned context for a PiCode task."""

from __future__ import annotations

from pathlib import Path

from .models import ContextBlock, InitialContext
from .project_rules import ProjectRulesLoader
from .user_task import UserTask


class ContextEngine:
    """Build only stable initial context; execution evidence is added later."""

    def __init__(self, working_directory: Path | None = None, workspace_root: Path | None = None) -> None:
        self._working_directory = (working_directory or Path.cwd()).resolve()
        self._workspace_root = workspace_root.resolve() if workspace_root is not None else None

    def build_initial_context(self, user_task: UserTask) -> InitialContext:
        """Return AGENTS.md followed by UserTask in the fixed prompt order."""

        rules = ProjectRulesLoader(self._working_directory, self._workspace_root).as_context_block()
        task = ContextBlock(
            name="UserTask",
            content=user_task.render(),
            sources=("user_message", *("steer" for _ in user_task.follow_ups), "host:execution_scope"),
        )
        return InitialContext((rules, task))
