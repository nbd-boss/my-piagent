"""User-provided task state used to build the initial model context."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_EXECUTION_SCOPE = "所有相对路径均以当前工作区为根目录。"


@dataclass(frozen=True)
class UserTask:
    """Preserve user input without treating Host facts as user-authored text."""

    original_request: str
    follow_ups: tuple[str, ...] = ()
    execution_scope: str = DEFAULT_EXECUTION_SCOPE

    def __post_init__(self) -> None:
        if not self.original_request.strip():
            raise ValueError("original_request must not be empty")
        if not self.execution_scope.strip():
            raise ValueError("execution_scope must not be empty")
        if any(not follow_up.strip() for follow_up in self.follow_ups):
            raise ValueError("follow_ups must not contain empty messages")

    def with_follow_up(self, content: str) -> UserTask:
        """Append a later user message without rewriting the original request."""

        return UserTask(
            original_request=self.original_request,
            follow_ups=(*self.follow_ups, content),
            execution_scope=self.execution_scope,
        )

    def routing_input(self) -> str:
        """Return the complete user-authored text used for routing."""

        additions = tuple(f"用户补充：{follow_up}" for follow_up in self.follow_ups)
        return "\n\n".join((self.original_request, *additions))

    def render(self) -> str:
        """Render user content and Host-provided scope with distinct labels."""

        sections = [f"## User task\n{self.original_request}"]
        if self.follow_ups:
            constraints = "\n".join(f"- {follow_up}" for follow_up in self.follow_ups)
            sections.append(f"## Follow-up constraints\n{constraints}")
        sections.append(f"## Execution scope (host-provided)\n{self.execution_scope}")
        return "\n\n".join(sections)
