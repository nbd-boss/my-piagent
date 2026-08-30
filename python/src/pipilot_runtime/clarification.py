"""Ephemeral state for a request that needs user clarification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PendingClarification:
    """Keeps the original request until the user supplies missing scope."""

    original_request: str
    question: str
    attempts: int = 0

    def with_response(self, response: str) -> str:
        """Build the complete request that will be routed again."""

        return f"{self.original_request}\n\n用户补充：{response}"
