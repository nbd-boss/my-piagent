"""Durable task snapshots used for recovery after a Runtime restart."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import cast

from .context import UserTask
from .routing import RouteDecision


@dataclass(frozen=True)
class TaskSnapshot:
    """Minimal durable state needed to resume a task safely."""

    task_id: str
    user_task: UserTask
    intent: str
    execution_class: str | None
    status: str

    @property
    def latest_request(self) -> str:
        """Keep the task-status API focused on the complete user request."""

        return self.user_task.routing_input()

    @classmethod
    def from_payload(cls, payload: object) -> TaskSnapshot:
        """Validate an on-disk task snapshot before using it."""

        if not isinstance(payload, dict):
            raise ValueError("Task snapshot must be a JSON object")

        record = cast(Mapping[str, object], payload)
        fields = ("task_id", "user_task", "intent", "execution_class", "status")
        values = {field: record.get(field) for field in fields}
        required_string_fields = ("task_id", "intent", "status")
        if any(not isinstance(values[field], str) for field in required_string_fields):
            raise ValueError("Task snapshot required fields must be strings")
        if values["execution_class"] is not None and not isinstance(values["execution_class"], str):
            raise ValueError("Task snapshot execution_class must be a string or null")
        user_task = cls._parse_user_task(values["user_task"])

        return cls(
            task_id=cast(str, values["task_id"]),
            user_task=user_task,
            intent=cast(str, values["intent"]),
            execution_class=values["execution_class"],
            status=cast(str, values["status"]),
        )

    @staticmethod
    def _parse_user_task(payload: object) -> UserTask:
        if not isinstance(payload, dict):
            raise ValueError("Task snapshot user_task must be an object")

        record = cast(Mapping[str, object], payload)
        original_request = record.get("original_request")
        follow_ups = record.get("follow_ups")
        execution_scope = record.get("execution_scope")
        if not isinstance(original_request, str) or not isinstance(execution_scope, str):
            raise ValueError("Task snapshot user_task text fields must be strings")
        if not isinstance(follow_ups, list):
            raise ValueError("Task snapshot user_task follow_ups must be a list of strings")
        raw_follow_ups = cast(list[object], follow_ups)
        if any(not isinstance(item, str) for item in raw_follow_ups):
            raise ValueError("Task snapshot user_task follow_ups must be a list of strings")

        try:
            return UserTask(original_request, tuple(cast(str, item) for item in raw_follow_ups), execution_scope)
        except ValueError as error:
            raise ValueError(f"Task snapshot user_task is invalid: {error}") from error


class TaskMemory:
    """Stores one atomic JSON snapshot per task without UI dependencies."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory

    def record_request(self, task_id: str, user_task: UserTask, route: RouteDecision) -> TaskSnapshot:
        snapshot = TaskSnapshot(
            task_id=task_id,
            user_task=user_task,
            intent=route.intent,
            execution_class=route.execution_class,
            status="routed",
        )
        self._write(snapshot)
        return snapshot

    def mark_cancelled(self, task_id: str) -> TaskSnapshot | None:
        snapshot = self.load(task_id)
        if snapshot is None:
            return None

        cancelled = replace(snapshot, status="cancelled")
        self._write(cancelled)
        return cancelled

    def load(self, task_id: str) -> TaskSnapshot | None:
        if self._directory is None:
            return None

        path = self._path_for(task_id)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        try:
            return TaskSnapshot.from_payload(payload)
        except ValueError as error:
            raise ValueError(f"Invalid task snapshot for {task_id}: {error}") from error

    def _write(self, snapshot: TaskSnapshot) -> None:
        if self._directory is None:
            return

        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._path_for(snapshot.task_id)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(snapshot), sort_keys=True), encoding="utf-8")
        temporary.replace(target)

    def _path_for(self, task_id: str) -> Path:
        if self._directory is None:
            raise RuntimeError("Task storage is disabled")
        safe_task_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in task_id)
        return self._directory / f"{safe_task_id}.json"
