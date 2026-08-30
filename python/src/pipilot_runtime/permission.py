"""Task-scoped permission state used before a tool operation is executed."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PermissionLevel = Literal["read-only", "workspace-write", "high-risk"]
PermissionStatus = Literal["allowed", "requires_confirmation", "denied"]
RequestedPermission = Literal["workspace-write", "high-risk"]


@dataclass(frozen=True)
class ToolOperation:
    """Minimal operation metadata required for a permission decision."""

    tool: str
    target_path: Path | None = None
    command: str | None = None


@dataclass(frozen=True)
class PermissionDecision:
    """An allow, deny, or user-confirmation outcome for one tool call."""

    status: PermissionStatus
    permission: PermissionLevel
    reason: str


@dataclass(frozen=True)
class PendingPermission:
    tool_call_id: str
    permission: RequestedPermission
    reason: str


@dataclass
class TaskPermissionState:
    workspace_write_granted: bool = False
    pending: PendingPermission | None = None


class PermissionManager:
    """Enforces read-only defaults and task-scoped, explicit escalation."""

    _READ_ONLY_TOOLS = frozenset({"read", "grep", "find", "ls"})
    _WORKSPACE_WRITE_TOOLS = frozenset({"edit", "write"})
    _HIGH_RISK_COMMAND_TERMS = ("git push", "deploy", "rm ", "remove-item", "del ", "format ", "curl |", "wget ")
    _READ_ONLY_COMMAND_PREFIXES = ("git status", "git diff", "rg ", "grep ", "ls", "dir", "get-content", "cat ", "pwd")

    def __init__(self, workspace_root: Path) -> None:
        self._workspace_root = workspace_root.resolve()
        self._states: dict[str, TaskPermissionState] = {}

    def request(self, task_id: str, tool_call_id: str, operation: ToolOperation) -> PermissionDecision:
        """Return whether one pending tool operation may proceed."""

        required_permission, reason = self._classify(operation)
        if required_permission == "workspace-write" and operation.target_path is not None:
            if not self._is_workspace_path(operation.target_path):
                return PermissionDecision("denied", "workspace-write", "Write target is outside the current workspace.")

        if required_permission == "read-only":
            return PermissionDecision("allowed", "read-only", reason)

        state = self._states.setdefault(task_id, TaskPermissionState())
        if state.pending is not None:
            return PermissionDecision("denied", required_permission, "Another permission request is already pending for this task.")
        if required_permission == "workspace-write" and state.workspace_write_granted:
            return PermissionDecision("allowed", "workspace-write", reason)

        state.pending = PendingPermission(tool_call_id=tool_call_id, permission=required_permission, reason=reason)
        return PermissionDecision("requires_confirmation", required_permission, reason)

    def respond(self, task_id: str, granted: bool) -> PermissionDecision:
        """Apply the user's response to the current task's pending request."""

        state = self._states.get(task_id)
        if state is None or state.pending is None:
            return PermissionDecision("denied", "read-only", "This task has no pending permission request.")

        pending = state.pending
        state.pending = None
        if not granted:
            return PermissionDecision("denied", pending.permission, "The user denied this operation.")
        if pending.permission == "workspace-write":
            state.workspace_write_granted = True
            return PermissionDecision("allowed", "workspace-write", "Workspace writes are allowed for this task.")
        return PermissionDecision("allowed", "high-risk", "The user approved this high-risk operation once.")

    def clear(self, task_id: str) -> None:
        """Discard all grants and pending requests when a task ends or is cancelled."""

        self._states.pop(task_id, None)

    def has_workspace_write(self, task_id: str) -> bool:
        """Expose current task-scoped write state for later Runtime integration."""

        state = self._states.get(task_id)
        return state is not None and state.workspace_write_granted

    def _classify(self, operation: ToolOperation) -> tuple[PermissionLevel, str]:
        if operation.tool in self._READ_ONLY_TOOLS:
            return "read-only", f"{operation.tool} is read-only."
        if operation.tool in self._WORKSPACE_WRITE_TOOLS:
            return "workspace-write", f"{operation.tool} can modify the workspace."
        if operation.tool in {"bash", "powershell"}:
            command = (operation.command or "").strip().lower()
            if any(term in command for term in self._HIGH_RISK_COMMAND_TERMS):
                return "high-risk", "The command may create an external or destructive side effect."
            if any(command.startswith(prefix) for prefix in self._READ_ONLY_COMMAND_PREFIXES):
                return "read-only", "The command is classified as read-only."
            return "high-risk", "Unknown shell commands require high-risk confirmation."
        return "high-risk", f"Unknown tool {operation.tool} requires high-risk confirmation."

    def _is_workspace_path(self, target_path: Path) -> bool:
        resolved_target = (target_path if target_path.is_absolute() else self._workspace_root / target_path).resolve()
        return resolved_target == self._workspace_root or self._workspace_root in resolved_target.parents
