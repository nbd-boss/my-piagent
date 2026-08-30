from pipilot_runtime.routing import DeterministicMockClassifier, IntentRouter, RouteInput


def create_router() -> IntentRouter:
    return IntentRouter(DeterministicMockClassifier())


def test_routes_code_understanding_to_high_frequency_read_only_execution() -> None:
    decision = create_router().decide(RouteInput(userMessage="解释这个仓库的认证流程"))

    assert decision.intent == "inspect"
    assert decision.execution_class == "high_frequency"


def test_routes_code_change_to_long_task_agent_workspace_write_execution() -> None:
    decision = create_router().decide(RouteInput(userMessage="Fix the login validation bug and add a test"))

    assert decision.intent == "change"
    assert decision.execution_class == "long_task_agent"


def test_routes_external_or_destructive_requests_to_a_long_task() -> None:
    decision = create_router().decide(RouteInput(userMessage="修复后推送到远程仓库"))

    assert decision.intent == "change"
    assert decision.execution_class == "long_task_agent"


def test_routes_a_general_question_to_the_high_frequency_path() -> None:
    decision = create_router().decide(RouteInput(userMessage="What is a context window?"))

    assert decision.intent == "question"
    assert decision.execution_class == "high_frequency"
