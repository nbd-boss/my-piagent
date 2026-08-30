from pipilot_runtime.recovery import RecoveryGuard
from pipilot_runtime.types import PROTOCOL_VERSION, ToolResult


def failed_result(arguments_fingerprint: str = "args-1") -> ToolResult:
    return ToolResult(
        protocolVersion=PROTOCOL_VERSION,
        taskId="task-1",
        requestId="request-1",
        toolCallId="call-1",
        tool="read",
        argumentsFingerprint=arguments_fingerprint,
        status="failed",
        content="File not found.",
        errorCategory="execution",
    )


def test_blocks_the_second_identical_tool_failure() -> None:
    guard = RecoveryGuard()

    first = guard.observe(failed_result())
    second = guard.observe(failed_result())

    assert first.should_block is False
    assert second.should_block is True
    assert second.failure_count == 2


def test_allows_a_changed_tool_input_after_a_failure() -> None:
    guard = RecoveryGuard()
    guard.observe(failed_result())

    decision = guard.observe(failed_result("args-2"))

    assert decision.should_block is False
    assert decision.failure_count == 1
