"""Deterministic classifier used only for development and offline tests."""

from __future__ import annotations

from .models import RouteDecision, RouteInput


class DeterministicMockClassifier:
    """Keeps the Runtime usable before a model-backed classifier is connected."""

    _CHANGE_TERMS = ("fix", "bug", "implement", "add", "modify", "refactor", "修复", "实现", "修改", "新增", "重构")
    _NO_CHANGE_TERMS = ("do not modify", "don't modify", "不要修改", "不修改", "无需修改")
    _RUN_TERMS = ("test", "tests", "ci", "build", "compile", "运行测试", "构建", "编译")
    _REVIEW_TERMS = ("review", "code review", "审查", "检查 diff")
    _QUESTION_TERMS = ("what is", "how does", "是什么", "为什么", "如何")
    _INSPECT_TERMS = ("explain", "where", "find", "understand", "分析", "解释", "定位", "找出", "哪里")

    def classify(self, route_input: RouteInput) -> RouteDecision | None:
        """Return predictable fixtures without claiming to understand natural language."""

        content = route_input.user_message.lower().strip()
        change_is_forbidden = self._contains(content, self._NO_CHANGE_TERMS)
        if self._contains(content, self._CHANGE_TERMS) and not change_is_forbidden:
            return RouteDecision(
                intent="change",
                executionClass="long_task_agent",
                reason="Development mock detected a repository change request.",
            )
        if self._contains(content, self._RUN_TERMS):
            return RouteDecision(
                intent="run",
                executionClass="long_task_agent",
                reason="Development mock detected a command-driven request.",
            )
        if self._contains(content, self._REVIEW_TERMS):
            return RouteDecision(
                intent="review",
                executionClass="high_frequency",
                reason="Development mock detected a bounded review request.",
            )
        if self._contains(content, self._QUESTION_TERMS):
            return RouteDecision(
                intent="question",
                executionClass="high_frequency",
                reason="Development mock detected a general question.",
            )
        if self._contains(content, self._INSPECT_TERMS) or content.endswith("?") or content.endswith("？"):
            return RouteDecision(
                intent="inspect",
                executionClass="high_frequency",
                reason="Development mock detected a read-only inspection request.",
            )
        return None

    @staticmethod
    def _contains(content: str, terms: tuple[str, ...]) -> bool:
        return any(term in content for term in terms)
