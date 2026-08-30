"""Minimal Python Runtime used to establish the cross-process contract."""

from __future__ import annotations

from pathlib import Path

from .clarification import PendingClarification
from .context import ContextEngine, InitialContext, UserTask
from .execution import CheckpointStatus, ExecutionContext, ExecutionLedger, RoundStatus
from .model_provider import ModelProvider
from .recovery import RecoveryGuard
from .routing import DeterministicMockClassifier, IntentRouter, ModelRouteClassifier, RouteClassifier, RouteInput
from .task_memory import TaskMemory, TaskSnapshot
from .trace import TraceWriter
from .types import (
    PROTOCOL_VERSION,
    AssistantDelta,
    Cancel,
    HostHello,
    HostMessage,
    RuntimeError,
    RuntimeMessage,
    RuntimeReady,
    RouteDecided,
    Steer,
    TaskState,
    TaskStatus,
    TaskFinished,
    ToolRequest,
    ToolResult,
    UserMessage,
)


class PiPilotRuntime:
    """Owns Agent state; the TypeScript process remains a UI and tool host."""

    def __init__(
        self,
        state_directory: Path | None = None,
        classifier: RouteClassifier | None = None,
        model_provider: ModelProvider | None = None,
        context_engine: ContextEngine | None = None,
        trace_directory: Path | None = None,
    ) -> None:
        if classifier is not None and model_provider is not None:
            raise ValueError("Provide either a route classifier or a model provider, not both")
        self._handshake_complete = False
        route_classifier = classifier or (
            ModelRouteClassifier(model_provider) if model_provider is not None else DeterministicMockClassifier()
        )
        self._intent_router = IntentRouter(route_classifier)
        self._task_memory = TaskMemory(state_directory)
        self._pending_clarifications: dict[str, PendingClarification] = {}
        self._recovery_guard = RecoveryGuard()
        self._user_tasks: dict[str, UserTask] = {}
        self._context_engine = context_engine or ContextEngine()
        self._initial_contexts: dict[str, InitialContext] = {}
        self._trace_writer = TraceWriter(trace_directory)
        self._executions: dict[str, ExecutionLedger] = {}

    def handle(self, message: HostMessage) -> list[RuntimeMessage]:
        """Handle one Host message without depending on TUI or process I/O."""

        if isinstance(message, HostHello):
            self._handshake_complete = True
            return [
                RuntimeReady(
                    protocolVersion=PROTOCOL_VERSION,
                    taskId=message.task_id,
                    requestId=message.request_id,
                    capabilities=["streaming", "cancellation", "protocol-v1"],
                ),
            ]

        if not self._handshake_complete:
            return [self._error(message, "handshake_required", "Send host_hello before task messages", fatal=True)]

        if isinstance(message, UserMessage):
            user_task = UserTask(message.content)
            self._user_tasks[message.task_id] = user_task
            self._initial_contexts[message.task_id] = self._context_engine.build_initial_context(user_task)
            self._executions[message.task_id] = ExecutionLedger(message.task_id, self._trace_writer)
            return self._route_request(message, user_task)

        if isinstance(message, Steer):
            pending = self._pending_clarifications.get(message.task_id)
            if pending is None:
                return [
                    self._error(
                        message,
                        "no_pending_clarification",
                        "This task is not waiting for clarification.",
                    ),
                ]
            user_task = self._user_tasks.get(message.task_id)
            if user_task is None:
                return [self._error(message, "user_task_missing", "This task has no user request to extend.")]
            updated_task = user_task.with_follow_up(message.content)
            self._user_tasks[message.task_id] = updated_task
            self._initial_contexts[message.task_id] = self._context_engine.build_initial_context(updated_task)
            return self._route_request(message, updated_task, pending)

        if isinstance(message, Cancel):
            self._pending_clarifications.pop(message.task_id, None)
            self._user_tasks.pop(message.task_id, None)
            self._initial_contexts.pop(message.task_id, None)
            self._task_memory.mark_cancelled(message.task_id)
            self._recovery_guard.clear(message.task_id)
            return [
                TaskFinished(
                    protocolVersion=PROTOCOL_VERSION,
                    taskId=message.task_id,
                    requestId=message.request_id,
                    status="cancelled",
                    summary=message.reason or "Task cancelled by user.",
                ),
            ]

        if isinstance(message, ToolResult):
            execution = self._executions.get(message.task_id)
            if execution is not None:
                execution.record_tool_result(message)
            recovery = self._recovery_guard.observe(message)
            if recovery.should_block:
                return [
                    self._error(
                        message,
                        "repeated_tool_failure",
                        "Stopped repeated tool call after the same parameters produced the same failure twice.",
                    ),
                ]
            return []

        if isinstance(message, TaskStatus):
            snapshot = self._task_memory.load(message.task_id)
            if snapshot is None:
                return [
                    TaskState(
                        protocolVersion=PROTOCOL_VERSION,
                        taskId=message.task_id,
                        requestId=message.request_id,
                        found=False,
                    ),
                ]

            return [
                TaskState(
                    protocolVersion=PROTOCOL_VERSION,
                    taskId=message.task_id,
                    requestId=message.request_id,
                    found=True,
                    latestRequest=snapshot.latest_request,
                    intent=snapshot.intent,
                    executionClass=snapshot.execution_class,
                    status=snapshot.status,
                ),
            ]

        return [
            self._error(
                message,
                "unsupported_message",
                f"Runtime does not handle {message.type} during the protocol foundation phase",
            ),
        ]

    def load_task(self, task_id: str) -> TaskSnapshot | None:
        """Load the latest durable task state when storage is configured."""

        return self._task_memory.load(task_id)

    def initial_context_for_task(self, task_id: str) -> InitialContext | None:
        """Return the latest Python-built initial context for an active task."""

        return self._initial_contexts.get(task_id)

    def start_react_round(self, task_id: str, goal: str, action: str) -> str:
        """Start a visible ReAct round for the future Agent Loop."""

        return self._execution_for(task_id).start_round(goal, action).round_id

    def record_tool_request(self, task_id: str, request: ToolRequest) -> None:
        """Record the tool request before the TypeScript Host executes it."""

        self._execution_for(task_id).record_tool_call(request)

    def complete_react_round(
        self,
        task_id: str,
        status: RoundStatus,
        summary: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        """Complete the active round using a public, evidence-backed summary."""

        self._execution_for(task_id).complete_round(status, summary, evidence_refs)

    def checkpoint(
        self,
        task_id: str,
        status: CheckpointStatus,
        summary: str,
        facts: tuple[str, ...],
        next_goal: str | None = None,
    ) -> None:
        """Write a task milestone without constraining future Agent actions."""

        self._execution_for(task_id).checkpoint(status, summary, facts, next_goal)

    def execution_context_for_task(self, task_id: str) -> ExecutionContext | None:
        """Return the compact execution-state projection for the next turn."""

        execution = self._executions.get(task_id)
        return execution.context() if execution is not None else None

    def _execution_for(self, task_id: str) -> ExecutionLedger:
        execution = self._executions.get(task_id)
        if execution is None:
            raise ValueError(f"No active execution for task {task_id}")
        return execution

    def _route_request(
        self,
        message: UserMessage | Steer,
        user_task: UserTask,
        pending: PendingClarification | None = None,
    ) -> list[RuntimeMessage]:
        request = user_task.routing_input()
        route = self._intent_router.decide(RouteInput(userMessage=request))
        events: list[RuntimeMessage] = [
            RouteDecided(
                protocolVersion=PROTOCOL_VERSION,
                taskId=message.task_id,
                requestId=message.request_id,
                intent=route.intent,
                executionClass=route.execution_class,
                clarificationQuestion=route.clarification_question,
                reason=route.reason,
            ),
        ]

        if route.intent == "ambiguous":
            attempt_count = (pending.attempts if pending is not None else 0) + 1
            if attempt_count >= 2:
                self._pending_clarifications.pop(message.task_id, None)
                events.extend(
                    [
                        AssistantDelta(
                            protocolVersion=PROTOCOL_VERSION,
                            taskId=message.task_id,
                            requestId=message.request_id,
                            delta="仍无法确定任务范围，请重新描述希望我分析、修改或执行的具体内容。",
                        ),
                        TaskFinished(
                            protocolVersion=PROTOCOL_VERSION,
                            taskId=message.task_id,
                            requestId=message.request_id,
                            status="blocked",
                            summary="Task could not be clarified after two attempts.",
                        ),
                    ],
                )
                return events

            self._pending_clarifications[message.task_id] = PendingClarification(
                original_request=pending.original_request if pending is not None else request,
                question=route.clarification_question or "Please clarify the task.",
                attempts=attempt_count,
            )
            events.append(
                AssistantDelta(
                    protocolVersion=PROTOCOL_VERSION,
                    taskId=message.task_id,
                    requestId=message.request_id,
                    delta=route.clarification_question or "Please clarify the task.",
                ),
            )
            return events

        self._pending_clarifications.pop(message.task_id, None)
        self._task_memory.record_request(message.task_id, user_task, route)
        events.extend(
            [
                AssistantDelta(
                    protocolVersion=PROTOCOL_VERSION,
                    taskId=message.task_id,
                    requestId=message.request_id,
                    delta=f"PiCode Runtime received: {request}",
                ),
                TaskFinished(
                    protocolVersion=PROTOCOL_VERSION,
                    taskId=message.task_id,
                    requestId=message.request_id,
                    status="success",
                    summary="Intent route decided; Agent Loop is not connected yet.",
                ),
            ],
        )
        return events

    @staticmethod
    def _error(message: HostMessage, code: str, text: str, fatal: bool = False) -> RuntimeError:
        return RuntimeError(
            protocolVersion=PROTOCOL_VERSION,
            taskId=message.task_id,
            requestId=message.request_id,
            code=code,
            message=text,
            fatal=fatal,
        )
