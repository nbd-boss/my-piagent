"""Structured ReAct state projected from durable trace events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Literal

from .trace import TraceWriter
from .types import ToolRequest, ToolResult

RoundStatus = Literal["pending", "success", "failed", "blocked"]
CheckpointStatus = Literal["completed", "blocked", "verifying", "verified"]


@dataclass(frozen=True)
class ToolCallRecord:
    """The factual result of one tool call, without raw arguments or long output."""

    tool_call_id: str
    tool: str
    arguments_fingerprint: str
    status: Literal["requested", "success", "failed", "cancelled"]
    duration_ms: int | None = None
    exit_code: int | None = None
    output_reference: str | None = None
    error_category: str | None = None
    output_preview: str | None = None


@dataclass(frozen=True)
class ReActResult:
    """A bounded, evidence-backed result of one ReAct round."""

    status: RoundStatus
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReActRound:
    """One visible goal-action-result loop, linked to its tool calls."""

    round_id: str
    goal: str
    action: str
    tool_calls: tuple[ToolCallRecord, ...] = ()
    result: ReActResult | None = None


@dataclass(frozen=True)
class TaskCheckpoint:
    """A stable milestone rather than a mandatory workflow step."""

    status: CheckpointStatus
    summary: str
    facts: tuple[str, ...]
    next_goal: str | None = None


@dataclass(frozen=True)
class ExecutionContext:
    """The small execution-state projection suitable for the next model turn."""

    current_goal: str | None
    last_result: ReActResult | None
    latest_checkpoint: TaskCheckpoint | None
    open_items: tuple[str, ...]

    def render(self) -> str:
        """Render only the execution facts that can affect the next decision."""

        sections = ["## Execution state"]
        if self.current_goal is not None:
            sections.append(f"### Current goal\n{self.current_goal}")
        if self.last_result is not None:
            evidence = "".join(f"\n- {reference}" for reference in self.last_result.evidence_refs)
            sections.append(f"### Last result\n{self.last_result.summary}{evidence}")
        if self.latest_checkpoint is not None:
            facts = "".join(f"\n- {fact}" for fact in self.latest_checkpoint.facts)
            sections.append(f"### Latest checkpoint\n{self.latest_checkpoint.summary}{facts}")
        if self.open_items:
            sections.append("### Open items\n" + "\n".join(f"- {item}" for item in self.open_items))
        return "\n\n".join(sections)


@dataclass
class ExecutionLedger:
    """Own the structured state and Trace projection for one active task."""

    task_id: str
    trace_writer: TraceWriter
    rounds: list[ReActRound] = field(default_factory=list)
    checkpoints: list[TaskCheckpoint] = field(default_factory=list)

    def start_round(self, goal: str, action: str) -> ReActRound:
        """Start a visible decision/action round and record its public decision."""

        if self._active_round() is not None:
            raise ValueError("Complete the active ReAct round before starting another one")
        round_ = ReActRound(round_id=f"round-{len(self.rounds) + 1}", goal=goal, action=action)
        self.rounds.append(round_)
        self.trace_writer.append(self.task_id, round_.round_id, "thinking", {"goal": goal, "nextAction": action})
        return round_

    def record_tool_call(self, request: ToolRequest) -> ToolCallRecord:
        """Record a tool request with only a deterministic arguments fingerprint."""

        round_ = self._require_active_round()
        record = ToolCallRecord(
            tool_call_id=request.tool_call_id,
            tool=request.tool,
            arguments_fingerprint=self._arguments_fingerprint(request.arguments),
            status="requested",
        )
        self._replace_round(replace(round_, tool_calls=(*round_.tool_calls, record)))
        self.trace_writer.append(
            self.task_id,
            round_.round_id,
            "tool_call",
            {"toolCallId": record.tool_call_id, "tool": record.tool, "argumentsFingerprint": record.arguments_fingerprint},
        )
        return record

    def record_tool_result(self, result: ToolResult) -> ToolCallRecord | None:
        """Record a Host result and attach it to the matching active round when present."""

        record = self._find_tool_call(result.tool_call_id)
        active_round = self._active_round()
        round_id = active_round.round_id if active_round is not None else "unlinked"
        payload: dict[str, object] = {
            "toolCallId": result.tool_call_id,
            "tool": result.tool,
            "status": result.status,
            "durationMs": result.duration_ms,
            "exitCode": result.exit_code,
            "outputReference": result.output_reference,
            "errorCategory": result.error_category,
            "outputPreview": self._preview(result.content),
        }
        self.trace_writer.append(self.task_id, round_id, "tool_result", payload)
        if record is None:
            return None

        updated = replace(
            record,
            status=result.status,
            duration_ms=result.duration_ms,
            exit_code=result.exit_code,
            output_reference=result.output_reference,
            error_category=result.error_category,
            output_preview=self._preview(result.content),
        )
        self._replace_tool_call(updated)
        return updated

    def complete_round(self, status: RoundStatus, summary: str, evidence_refs: tuple[str, ...] = ()) -> ReActRound:
        """Close the active round with an evidence-backed result summary."""

        round_ = self._require_active_round()
        result = ReActResult(status=status, summary=summary, evidence_refs=evidence_refs)
        completed = replace(round_, result=result)
        self._replace_round(completed)
        self.trace_writer.append(
            self.task_id,
            completed.round_id,
            "thinking",
            {"result": {"status": status, "summary": summary, "evidenceRefs": list(evidence_refs)}},
        )
        return completed

    def checkpoint(
        self,
        status: CheckpointStatus,
        summary: str,
        facts: tuple[str, ...],
        next_goal: str | None = None,
    ) -> TaskCheckpoint:
        """Record a completed, blocked, or verification milestone."""

        checkpoint = TaskCheckpoint(status=status, summary=summary, facts=facts, next_goal=next_goal)
        self.checkpoints.append(checkpoint)
        round_id = self.rounds[-1].round_id if self.rounds else "checkpoint"
        self.trace_writer.append(
            self.task_id,
            round_id,
            "checkpoint",
            {
                "status": status,
                "summary": summary,
                "facts": list(facts),
                "nextGoal": next_goal,
            },
        )
        return checkpoint

    def context(self) -> ExecutionContext:
        """Select the active goal, latest result and checkpoint for the next turn."""

        active = self._active_round()
        completed = next((round_ for round_ in reversed(self.rounds) if round_.result is not None), None)
        checkpoint = self.checkpoints[-1] if self.checkpoints else None
        open_items = ()
        if active is not None:
            open_items = (active.goal,)
        elif checkpoint is not None and checkpoint.next_goal is not None:
            open_items = (checkpoint.next_goal,)
        return ExecutionContext(
            current_goal=active.goal if active is not None else None,
            last_result=completed.result if completed is not None else None,
            latest_checkpoint=checkpoint,
            open_items=open_items,
        )

    def _active_round(self) -> ReActRound | None:
        if not self.rounds or self.rounds[-1].result is not None:
            return None
        return self.rounds[-1]

    def _require_active_round(self) -> ReActRound:
        round_ = self._active_round()
        if round_ is None:
            raise ValueError("No active ReAct round")
        return round_

    def _find_tool_call(self, tool_call_id: str) -> ToolCallRecord | None:
        for round_ in reversed(self.rounds):
            for record in round_.tool_calls:
                if record.tool_call_id == tool_call_id:
                    return record
        return None

    def _replace_tool_call(self, updated: ToolCallRecord) -> None:
        for index, round_ in enumerate(self.rounds):
            if any(record.tool_call_id == updated.tool_call_id for record in round_.tool_calls):
                records = tuple(updated if record.tool_call_id == updated.tool_call_id else record for record in round_.tool_calls)
                self.rounds[index] = replace(round_, tool_calls=records)
                return
        raise ValueError(f"Unknown tool call: {updated.tool_call_id}")

    def _replace_round(self, updated: ReActRound) -> None:
        for index, round_ in enumerate(self.rounds):
            if round_.round_id == updated.round_id:
                self.rounds[index] = updated
                return
        raise ValueError(f"Unknown ReAct round: {updated.round_id}")

    @staticmethod
    def _arguments_fingerprint(arguments: dict[str, object]) -> str:
        return hashlib.sha256(json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _preview(content: str) -> str:
        return content[:1_000]
