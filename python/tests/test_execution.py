from __future__ import annotations

import json
from pathlib import Path

from pipilot_runtime.execution import ExecutionLedger
from pipilot_runtime.trace import TraceWriter
from pipilot_runtime.types import PROTOCOL_VERSION, ToolRequest, ToolResult


def tool_request() -> ToolRequest:
    return ToolRequest(
        protocolVersion=PROTOCOL_VERSION,
        taskId="task-1",
        requestId="request-1",
        toolCallId="call-1",
        tool="grep",
        arguments={"pattern": "email.lower", "path": "auth/login.py"},
    )


def test_writes_a_redacted_react_trace_and_projects_execution_context(tmp_path: Path) -> None:
    writer = TraceWriter(tmp_path)
    ledger = ExecutionLedger("task-1", writer)
    ledger.start_round("定位登录接口的 500 根因。", "搜索 email 处理逻辑。")
    ledger.record_tool_call(tool_request())
    ledger.record_tool_result(
        ToolResult(
            protocolVersion=PROTOCOL_VERSION,
            taskId="task-1",
            requestId="request-1",
            toolCallId="call-1",
            tool="grep",
            argumentsFingerprint="fingerprint",
            status="success",
            content="Authorization: Bearer secret-value\nauth/login.py:42: email.lower()",
            durationMs=35,
        ),
    )
    ledger.complete_round("success", "定位到 email 未判空。", ("auth/login.py:42",))
    ledger.checkpoint("completed", "已定位 500 根因。", ("email.lower() 前未判空。",), "修改空值校验。")

    events = [json.loads(line) for line in writer.path_for("task-1").read_text(encoding="utf-8").splitlines()]
    assert [event["type"] for event in events] == ["thinking", "tool_call", "tool_result", "thinking", "checkpoint"]
    assert events[1]["payload"]["argumentsFingerprint"] != "email.lower"
    assert "secret-value" not in writer.path_for("task-1").read_text(encoding="utf-8")
    assert events[2]["payload"]["outputPreview"] == "Authorization: Bearer [REDACTED]\nauth/login.py:42: email.lower()"

    context = ledger.context()
    assert context.current_goal is None
    assert context.last_result is not None
    assert context.last_result.summary == "定位到 email 未判空。"
    assert context.open_items == ("修改空值校验。",)
    assert "auth/login.py:42" in context.render()


def test_rejects_a_new_round_until_the_current_round_is_completed() -> None:
    ledger = ExecutionLedger("task-1", TraceWriter())
    ledger.start_round("定位问题。", "读取代码。")

    try:
        ledger.start_round("修改代码。", "写入文件。")
    except ValueError as error:
        assert str(error) == "Complete the active ReAct round before starting another one"
    else:
        raise AssertionError("Expected the active round to block a second round")
