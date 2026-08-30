"""Deterministic guard against repeating a tool call that already failed identically."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .types import ToolResult


@dataclass(frozen=True)
class RecoveryDecision:
    """Whether the Agent should stop before repeating a failed operation."""

    should_block: bool
    failure_count: int


class RecoveryGuard:
    """Tracks same-tool, same-arguments failures per task without retrying itself."""

    def __init__(self) -> None:
        self._failures: dict[str, dict[tuple[str, str, str, str], int]] = defaultdict(dict)

    def observe(self, result: ToolResult) -> RecoveryDecision:
        """Record a result and block the second identical failure for one task."""

        if result.status != "failed" or result.tool is None or result.arguments_fingerprint is None:
            return RecoveryDecision(should_block=False, failure_count=0)

        fingerprint = (
            result.tool,
            result.arguments_fingerprint,
            result.error_category or "execution",
            result.content,
        )
        task_failures = self._failures[result.task_id]
        count = task_failures.get(fingerprint, 0) + 1
        task_failures[fingerprint] = count
        return RecoveryDecision(should_block=count >= 2, failure_count=count)

    def clear(self, task_id: str) -> None:
        """Discard a completed or cancelled task's transient failure history."""

        self._failures.pop(task_id, None)
