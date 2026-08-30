"""Small, ordered values used to render the initial model context."""

from __future__ import annotations

from dataclasses import dataclass

INITIAL_CONTEXT_ORDER = ("AGENTS.md", "UserTask")


@dataclass(frozen=True)
class ContextBlock:
    """One rendered context section and the facts from which it was built."""

    name: str
    content: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class InitialContext:
    """The stable context supplied before any execution-specific evidence."""

    blocks: tuple[ContextBlock, ContextBlock]

    def __post_init__(self) -> None:
        names = tuple(block.name for block in self.blocks)
        if names != INITIAL_CONTEXT_ORDER:
            raise ValueError(f"Initial context blocks must be ordered as {INITIAL_CONTEXT_ORDER}")

    def render(self) -> str:
        """Serialize blocks in their fixed prompt order."""

        return "\n\n".join(block.content for block in self.blocks)
