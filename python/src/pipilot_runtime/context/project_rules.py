"""Load project-local AGENTS.md files without depending on the TUI Host."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import ContextBlock


@dataclass(frozen=True)
class ProjectRuleDocument:
    """One AGENTS.md file and its path relative to the workspace root."""

    relative_path: str
    content: str


class ProjectRulesLoader:
    """Load AGENTS.md from the workspace root down to a working directory."""

    def __init__(self, working_directory: Path, workspace_root: Path | None = None) -> None:
        self._working_directory = working_directory.resolve()
        self._workspace_root = (workspace_root or self._find_workspace_root(self._working_directory)).resolve()
        if not self._is_within_workspace(self._working_directory):
            raise ValueError("working_directory must be inside workspace_root")

    def load(self) -> tuple[ProjectRuleDocument, ...]:
        """Return non-empty rule files in root-to-working-directory order."""

        documents: list[ProjectRuleDocument] = []
        for directory in self._directories_from_root():
            path = directory / "AGENTS.md"
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8").strip()
            if content:
                documents.append(ProjectRuleDocument(self._relative_path(path), content))
        return tuple(documents)

    def as_context_block(self) -> ContextBlock:
        """Render all discovered rules while preserving each source path."""

        documents = self.load()
        if not documents:
            return ContextBlock(
                name="AGENTS.md",
                content="## AGENTS.md\nNo project rules file was found.",
                sources=(),
            )

        sections = ["## AGENTS.md"]
        for document in documents:
            sections.append(f"### {document.relative_path}\n{document.content}")
        return ContextBlock(
            name="AGENTS.md",
            content="\n\n".join(sections),
            sources=tuple(document.relative_path for document in documents),
        )

    def _directories_from_root(self) -> tuple[Path, ...]:
        relative_directory = self._working_directory.relative_to(self._workspace_root)
        return (self._workspace_root, *(self._workspace_root / part for part in relative_directory.parts))

    def _relative_path(self, path: Path) -> str:
        return path.relative_to(self._workspace_root).as_posix()

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self._workspace_root)
        except ValueError:
            return False
        return True

    @staticmethod
    def _find_workspace_root(working_directory: Path) -> Path:
        for directory in (working_directory, *working_directory.parents):
            if (directory / ".git").exists():
                return directory
        return working_directory
