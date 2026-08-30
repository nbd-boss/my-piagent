from pipilot_runtime.routing import IntentRouter, RouteInput


def test_clarifies_an_ambiguous_request_without_selecting_an_execution_class() -> None:
    decision = IntentRouter().decide(RouteInput(userMessage="帮我处理一下"))

    assert decision.intent == "ambiguous"
    assert decision.execution_class is None
    assert decision.clarification_question is not None
