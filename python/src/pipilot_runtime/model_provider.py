"""Minimal boundary for model calls made by the Agent Runtime."""

from __future__ import annotations

from typing import Protocol


class ModelProvider(Protocol):
    """Returns an untrusted JSON-compatible value for a structured prompt."""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> object | None:
        """Run one structured completion without exposing provider-specific types."""
