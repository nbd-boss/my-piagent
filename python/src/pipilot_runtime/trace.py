"""Append-only, redacted JSONL traces for visible Agent execution events."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

TraceEventType = Literal["thinking", "tool_call", "tool_result", "checkpoint"]

_SENSITIVE_FIELD_NAMES = {"api_key", "apikey", "authorization", "password", "secret", "token"}
_SENSITIVE_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|password|secret|token)\b\s*([:=])\s*[^\s,;]+")
_BEARER_TOKEN = re.compile(r"(?i)bearer\s+[^\s,;]+")


@dataclass(frozen=True)
class TraceEvent:
    """One persisted event from the visible ReAct execution process."""

    task_id: str
    round_id: str
    timestamp: str
    type: TraceEventType
    payload: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "roundId": self.round_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "payload": self.payload,
        }


class TraceWriter:
    """Write task-local JSONL traces while removing obvious secret values."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._events: dict[str, list[TraceEvent]] = {}

    def append(self, task_id: str, round_id: str, event_type: TraceEventType, payload: Mapping[str, object]) -> TraceEvent:
        """Append one event in memory and, when configured, to its task trace file."""

        event = TraceEvent(
            task_id=task_id,
            round_id=round_id,
            timestamp=datetime.now(UTC).isoformat(),
            type=event_type,
            payload=self._redact_mapping(payload),
        )
        self._events.setdefault(task_id, []).append(event)
        if self._directory is not None:
            self._directory.mkdir(parents=True, exist_ok=True)
            with self.path_for(task_id).open("a", encoding="utf-8") as trace_file:
                trace_file.write(json.dumps(event.to_payload(), ensure_ascii=False, separators=(",", ":")) + "\n")
        return event

    def events(self, task_id: str) -> tuple[TraceEvent, ...]:
        """Return the in-memory events for diagnostics and focused tests."""

        return tuple(self._events.get(task_id, ()))

    def path_for(self, task_id: str) -> Path:
        """Return the task-local trace path without allowing path traversal."""

        if self._directory is None:
            raise RuntimeError("Trace persistence is disabled")
        safe_task_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in task_id)
        return self._directory / f"{safe_task_id}.jsonl"

    def _redact_mapping(self, value: Mapping[str, object]) -> dict[str, object]:
        return {key: self._redact_value(key, item) for key, item in value.items()}

    def _redact_value(self, key: str, value: object) -> object:
        if key.lower() in _SENSITIVE_FIELD_NAMES:
            return "[REDACTED]"
        if isinstance(value, Mapping):
            return self._redact_mapping(cast(Mapping[str, object], value))
        if isinstance(value, list):
            return [self._redact_value("", item) for item in cast(list[object], value)]
        if isinstance(value, str):
            without_assignments = _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)
            return _BEARER_TOKEN.sub("Bearer [REDACTED]", without_assignments)
        return value
