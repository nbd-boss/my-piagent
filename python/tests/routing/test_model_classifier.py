from __future__ import annotations

from dataclasses import dataclass, field

from pipilot_runtime.model_provider import ModelProvider
from pipilot_runtime.routing import IntentRouter, ModelRouteClassifier, RouteInput
from pipilot_runtime.runtime import PiPilotRuntime
from pipilot_runtime.types import PROTOCOL_VERSION, HostHello, RouteDecided, UserMessage


@dataclass
class MockModelProvider(ModelProvider):
    payload: object | None
    requests: list[tuple[str, str]] = field(default_factory=list)

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> object | None:
        self.requests.append((system_prompt, user_prompt))
        return self.payload


def test_model_classifier_parses_a_json_string_and_records_the_structured_input() -> None:
    provider = MockModelProvider(
        '{"intent":"inspect","executionClass":"high_frequency"}',
    )
    decision = IntentRouter(ModelRouteClassifier(provider)).decide(RouteInput(userMessage="解释认证流程"))

    assert decision.intent == "inspect"
    assert len(provider.requests) == 1
    assert '"userMessage":"解释认证流程"' in provider.requests[0][1]


def test_invalid_model_output_becomes_a_clarification() -> None:
    provider = MockModelProvider("I would inspect the authentication flow first.")
    decision = IntentRouter(ModelRouteClassifier(provider)).decide(RouteInput(userMessage="处理认证问题"))

    assert decision.intent == "ambiguous"
    assert decision.clarification_question is not None


def test_runtime_uses_a_model_classifier_when_a_provider_is_supplied() -> None:
    provider = MockModelProvider(
        {
            "intent": "inspect",
            "executionClass": "high_frequency",
        },
    )
    runtime = PiPilotRuntime(model_provider=provider)
    runtime.handle(HostHello(protocolVersion=PROTOCOL_VERSION, taskId="runtime", requestId="hello"))

    responses = runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="Fix the login bug",
        ),
    )

    assert isinstance(responses[0], RouteDecided)
    assert responses[0].intent == "inspect"
    assert len(provider.requests) == 1
