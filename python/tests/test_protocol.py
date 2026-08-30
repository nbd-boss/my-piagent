from __future__ import annotations

from io import StringIO
from pathlib import Path

from pipilot_runtime.protocol import run_jsonl
from pipilot_runtime.runtime import PiPilotRuntime
from pipilot_runtime.context import ContextEngine
from pipilot_runtime.types import (
    PROTOCOL_VERSION,
    Cancel,
    HostHello,
    RouteDecided,
    RuntimeError,
    RuntimeReady,
    TaskState,
    TaskStatus,
    TaskFinished,
    ToolRequest,
    ToolResult,
    Steer,
    UserMessage,
)


def hello() -> HostHello:
    return HostHello(protocolVersion=PROTOCOL_VERSION, taskId="runtime", requestId="hello")


def test_runtime_requires_handshake() -> None:
    runtime = PiPilotRuntime()
    responses = runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="Explain this repository",
        ),
    )

    assert isinstance(responses[0], RuntimeError)
    assert responses[0].code == "handshake_required"
    assert responses[0].fatal is True


def test_runtime_streams_and_finishes_after_user_message(tmp_path: Path) -> None:
    runtime = PiPilotRuntime(context_engine=ContextEngine(tmp_path))

    ready = runtime.handle(hello())
    responses = runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="Explain this repository",
        ),
    )

    assert isinstance(ready[0], RuntimeReady)
    assert isinstance(responses[0], RouteDecided)
    assert responses[0].execution_class == "high_frequency"
    assert responses[1].type == "assistant_delta"
    assert isinstance(responses[2], TaskFinished)
    assert responses[2].status == "success"
    initial_context = runtime.initial_context_for_task("task-1")
    assert initial_context is not None
    assert tuple(block.name for block in initial_context.blocks) == ("AGENTS.md", "UserTask")


def test_runtime_waits_for_clarification_without_persisting_a_task(tmp_path: Path) -> None:
    runtime = PiPilotRuntime(tmp_path)
    runtime.handle(hello())

    responses = runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="帮我处理一下",
        ),
    )

    assert isinstance(responses[0], RouteDecided)
    assert responses[0].intent == "ambiguous"
    assert responses[0].execution_class is None
    assert responses[0].clarification_question is not None
    assert len(responses) == 2
    assert responses[1].type == "assistant_delta"
    assert runtime.load_task("task-1") is None


def test_runtime_reroutes_a_clarification_response_in_the_same_task(tmp_path: Path) -> None:
    runtime = PiPilotRuntime(tmp_path)
    runtime.handle(hello())
    runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="帮我处理一下认证问题",
        ),
    )

    responses = runtime.handle(
        Steer(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-2",
            content="先定位认证流程，不要修改代码。",
        ),
    )

    assert isinstance(responses[0], RouteDecided)
    assert responses[0].intent == "inspect"
    assert responses[0].execution_class == "high_frequency"
    assert isinstance(responses[2], TaskFinished)
    assert responses[2].status == "success"
    snapshot = runtime.load_task("task-1")
    assert snapshot is not None
    assert "用户补充" in snapshot.latest_request


def test_cancel_finishes_task_as_cancelled() -> None:
    runtime = PiPilotRuntime()
    runtime.handle(hello())

    responses = runtime.handle(
        Cancel(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="cancel-1",
            reason="User changed the request",
        ),
    )

    assert isinstance(responses[0], TaskFinished)
    assert responses[0].status == "cancelled"
    assert responses[0].summary == "User changed the request"


def test_runtime_blocks_a_repeated_tool_failure() -> None:
    runtime = PiPilotRuntime()
    runtime.handle(hello())
    failure = ToolResult(
        protocolVersion=PROTOCOL_VERSION,
        taskId="task-1",
        requestId="request-1",
        toolCallId="call-1",
        tool="read",
        argumentsFingerprint="same-arguments",
        status="failed",
        content="File not found.",
        errorCategory="execution",
    )

    assert runtime.handle(failure) == []
    repeated = runtime.handle(failure)

    assert isinstance(repeated[0], RuntimeError)
    assert repeated[0].code == "repeated_tool_failure"


def test_runtime_records_tool_results_in_an_active_react_round(tmp_path: Path) -> None:
    runtime = PiPilotRuntime(trace_directory=tmp_path)
    runtime.handle(hello())
    runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="修复登录问题",
        ),
    )
    runtime.start_react_round("task-1", "定位根因。", "搜索登录接口。")
    runtime.record_tool_request(
        "task-1",
        ToolRequest(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-2",
            toolCallId="call-1",
            tool="grep",
            arguments={"pattern": "email.lower"},
        ),
    )
    runtime.handle(
        ToolResult(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-2",
            toolCallId="call-1",
            tool="grep",
            argumentsFingerprint="fingerprint",
            status="success",
            content="auth/login.py:42",
        ),
    )
    runtime.complete_react_round("task-1", "success", "已定位根因。", ("auth/login.py:42",))
    runtime.checkpoint("task-1", "completed", "根因已确认。", ("email 未判空。",), "修改校验。")

    context = runtime.execution_context_for_task("task-1")
    assert context is not None
    assert context.open_items == ("修改校验。",)
    assert (tmp_path / "task-1.jsonl").exists()


def test_runtime_persists_route_and_cancellation_state(tmp_path: Path) -> None:
    runtime = PiPilotRuntime(tmp_path)
    runtime.handle(hello())
    runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="修复登录问题",
        ),
    )
    runtime.handle(
        Cancel(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="cancel-1",
        ),
    )

    restored = PiPilotRuntime(tmp_path)
    snapshot = restored.load_task("task-1")
    assert snapshot is not None
    assert snapshot.status == "cancelled"


def test_runtime_returns_a_serialized_task_state(tmp_path: Path) -> None:
    runtime = PiPilotRuntime(tmp_path)
    runtime.handle(hello())
    runtime.handle(
        UserMessage(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            content="解释认证流程",
        ),
    )

    responses = runtime.handle(
        TaskStatus(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="status-1",
        ),
    )

    assert isinstance(responses[0], TaskState)
    assert responses[0].found is True
    assert responses[0].latest_request == "解释认证流程"
    assert responses[0].execution_class == "high_frequency"


def test_jsonl_reports_invalid_messages_and_continues() -> None:
    input_stream = StringIO(
        "not-json\n"
        '{"protocolVersion":1,"taskId":"runtime","requestId":"hello","type":"host_hello"}\n'
        '{"protocolVersion":1,"taskId":"task-1","requestId":"request-1","type":"user_message","content":"Explain the repository"}\n',
    )
    output_stream = StringIO()
    error_stream = StringIO()

    exit_code = run_jsonl(input_stream, output_stream, error_stream)
    output = [line for line in output_stream.getvalue().splitlines() if line]

    assert exit_code == 0
    assert '"code":"invalid_json"' in output[0]
    assert '"type":"runtime_ready"' in output[1]
    assert '"type":"route_decided"' in output[2]
    assert '"type":"assistant_delta"' in output[3]
    assert '"type":"task_finished"' in output[4]


def test_tool_result_accepts_execution_metadata() -> None:
    result = ToolResult(
        protocolVersion=PROTOCOL_VERSION,
        taskId="task-1",
        requestId="request-1",
        toolCallId="call-1",
        tool="bash",
        argumentsFingerprint="0b0f",
        status="failed",
        content="Command timed out.",
        durationMs=30_000,
        outputReference=".pipilot/output/call-1.txt",
        errorCategory="timeout",
    )

    assert result.duration_ms == 30_000
    assert result.tool == "bash"
    assert result.arguments_fingerprint == "0b0f"
    assert result.output_reference == ".pipilot/output/call-1.txt"
    assert result.error_category == "timeout"
