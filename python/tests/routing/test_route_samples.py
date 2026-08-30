from __future__ import annotations

from dataclasses import dataclass

import pytest

from pipilot_runtime.routing import IntentRouter, ModelRouteClassifier, RouteInput


class StaticModelProvider:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> object:
        return self._payload


@dataclass(frozen=True)
class RouteSample:
    name: str
    message: str
    payload: object
    intent: str
    execution_class: str | None


ROUTE_SAMPLES = (
    RouteSample(
        name="general question",
        message="What is a context window?",
        payload={"intent": "question", "executionClass": "high_frequency"},
        intent="question",
        execution_class="high_frequency",
    ),
    RouteSample(
        name="repository inspection",
        message="解释这个仓库的认证流程。",
        payload={"intent": "inspect", "executionClass": "high_frequency"},
        intent="inspect",
        execution_class="high_frequency",
    ),
    RouteSample(
        name="diff review",
        message="审查当前 diff，只报告正确性问题。",
        payload={"intent": "review", "executionClass": "high_frequency"},
        intent="review",
        execution_class="high_frequency",
    ),
    RouteSample(
        name="workspace change",
        message="Fix the login validation bug and add a test.",
        payload={"intent": "change", "executionClass": "long_task_agent"},
        intent="change",
        execution_class="long_task_agent",
    ),
    RouteSample(
        name="command execution",
        message="运行认证模块的测试并分析失败原因。",
        payload={"intent": "run", "executionClass": "long_task_agent"},
        intent="run",
        execution_class="long_task_agent",
    ),
    RouteSample(
        name="insufficient scope",
        message="帮我处理认证问题。",
        payload={
            "intent": "ambiguous",
            "executionClass": None,
            "clarificationQuestion": "你希望我先定位认证问题，还是修改代码并补测试？",
        },
        intent="ambiguous",
        execution_class=None,
    ),
)


@pytest.mark.parametrize("sample", ROUTE_SAMPLES, ids=lambda sample: sample.name)
def test_model_route_samples(sample: RouteSample) -> None:
    router = IntentRouter(ModelRouteClassifier(StaticModelProvider(sample.payload)))

    decision = router.decide(RouteInput(userMessage=sample.message))

    assert decision.intent == sample.intent
    assert decision.execution_class == sample.execution_class
