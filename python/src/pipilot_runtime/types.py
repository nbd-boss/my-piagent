"""Versioned messages shared by the TypeScript Host and Python Runtime."""

from __future__ import annotations

from typing import Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    """Raised when a JSONL message does not satisfy the PiCode protocol."""


class ProtocolMessage(BaseModel):
    """Fields every cross-process message must include."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    protocol_version: int = Field(alias="protocolVersion")
    task_id: str = Field(alias="taskId", min_length=1)
    request_id: str = Field(alias="requestId", min_length=1)
    type: str


class HostHello(ProtocolMessage):
    type: str = "host_hello"


class UserMessage(ProtocolMessage):
    type: str = "user_message"
    content: str = Field(min_length=1)


class Steer(ProtocolMessage):
    type: str = "steer"
    content: str = Field(min_length=1)


class PermissionResponse(ProtocolMessage):
    type: str = "permission_response"
    granted: bool


class Cancel(ProtocolMessage):
    type: str = "cancel"
    reason: str | None = None


class ToolResult(ProtocolMessage):
    type: str = "tool_result"
    tool_call_id: str = Field(alias="toolCallId", min_length=1)
    tool: str | None = None
    arguments_fingerprint: str | None = Field(default=None, alias="argumentsFingerprint")
    status: Literal["success", "failed", "cancelled"]
    content: str = ""
    duration_ms: int | None = Field(default=None, alias="durationMs", ge=0)
    truncated: bool | None = None
    output_reference: str | None = Field(default=None, alias="outputReference")
    exit_code: int | None = Field(default=None, alias="exitCode")
    error_category: Literal["permission", "invalid_request", "execution", "cancelled", "timeout", "conflict"] | None = Field(
        default=None,
        alias="errorCategory",
    )


class TaskStatus(ProtocolMessage):
    type: str = "task_status"


HostMessage: TypeAlias = HostHello | UserMessage | Steer | PermissionResponse | Cancel | ToolResult | TaskStatus


class RuntimeReady(ProtocolMessage):
    type: str = "runtime_ready"
    capabilities: list[str]


class AssistantDelta(ProtocolMessage):
    type: str = "assistant_delta"
    delta: str


class RouteDecided(ProtocolMessage):
    type: str = "route_decided"
    intent: Literal["question", "inspect", "change", "review", "run", "ambiguous"]
    execution_class: Literal["high_frequency", "long_task_agent"] | None = Field(alias="executionClass")
    clarification_question: str | None = Field(default=None, alias="clarificationQuestion")
    reason: str | None = None

    @model_validator(mode="after")
    def validate_execution_boundary(self) -> RouteDecided:
        if self.intent == "ambiguous":
            if self.execution_class is not None:
                raise ValueError("Ambiguous routes must not select an execution class")
            if self.clarification_question is None:
                raise ValueError("Ambiguous routes require a clarification question")
        else:
            if self.execution_class is None:
                raise ValueError("Non-ambiguous routes require an execution class")
            if self.clarification_question is not None:
                raise ValueError("Non-ambiguous routes must not include a clarification question")
        return self


class PlanUpdated(ProtocolMessage):
    type: str = "plan_updated"
    summary: str


class ToolRequest(ProtocolMessage):
    type: str = "tool_request"
    tool_call_id: str = Field(alias="toolCallId", min_length=1)
    tool: str = Field(min_length=1)
    arguments: dict[str, object]


class PermissionRequired(ProtocolMessage):
    type: str = "permission_required"
    permission: Literal["workspace-write", "high-risk"]
    reason: str = Field(min_length=1)


class VerificationUpdated(ProtocolMessage):
    type: str = "verification_updated"
    status: Literal["pending", "passed", "failed", "skipped"]
    summary: str


class TaskFinished(ProtocolMessage):
    type: str = "task_finished"
    status: Literal["success", "partial", "unverified", "blocked", "failed", "cancelled"]
    summary: str


class RuntimeError(ProtocolMessage):
    type: str = "runtime_error"
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    fatal: bool = False


class TaskState(ProtocolMessage):
    type: str = "task_state"
    found: bool
    latest_request: str | None = Field(default=None, alias="latestRequest")
    intent: str | None = None
    execution_class: str | None = Field(default=None, alias="executionClass")
    status: str | None = None


RuntimeMessage: TypeAlias = (
    RuntimeReady
    | AssistantDelta
    | RouteDecided
    | PlanUpdated
    | ToolRequest
    | PermissionRequired
    | VerificationUpdated
    | TaskFinished
    | RuntimeError
    | TaskState
)


HOST_MESSAGE_TYPES: dict[str, type[ProtocolMessage]] = {
    "host_hello": HostHello,
    "user_message": UserMessage,
    "steer": Steer,
    "permission_response": PermissionResponse,
    "cancel": Cancel,
    "tool_result": ToolResult,
    "task_status": TaskStatus,
}


def parse_host_message(payload: object) -> HostMessage:
    """Validate one Host-to-Runtime message and its protocol version."""

    if not isinstance(payload, dict):
        raise ProtocolError("Protocol message must be a JSON object")

    record = cast(dict[str, object], payload)
    message_type = record.get("type")
    if not isinstance(message_type, str):
        raise ProtocolError("Protocol message type must be a string")

    model = HOST_MESSAGE_TYPES.get(message_type)
    if model is None:
        raise ProtocolError(f"Unsupported Host message type: {message_type}")

    message = model.model_validate(record)
    if message.protocol_version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Unsupported protocol version {message.protocol_version}; expected {PROTOCOL_VERSION}",
        )

    return cast(HostMessage, message)
