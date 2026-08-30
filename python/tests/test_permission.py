from pathlib import Path

from pipilot_runtime.permission import PermissionManager, ToolOperation


def test_allows_read_only_operations_without_a_prompt(tmp_path: Path) -> None:
    decision = PermissionManager(tmp_path).request("task-1", "call-1", ToolOperation(tool="read"))

    assert decision.status == "allowed"
    assert decision.permission == "read-only"


def test_grants_workspace_write_only_to_the_current_task(tmp_path: Path) -> None:
    manager = PermissionManager(tmp_path)

    request = manager.request("task-1", "call-1", ToolOperation(tool="edit", target_path=tmp_path / "src" / "login.py"))
    granted = manager.respond("task-1", granted=True)

    assert request.status == "requires_confirmation"
    assert request.permission == "workspace-write"
    assert granted.status == "allowed"
    assert manager.has_workspace_write("task-1") is True
    assert manager.has_workspace_write("task-2") is False


def test_denies_a_write_outside_the_workspace(tmp_path: Path) -> None:
    manager = PermissionManager(tmp_path)
    outside_workspace = tmp_path.parent / "outside.py"

    decision = manager.request("task-1", "call-1", ToolOperation(tool="write", target_path=outside_workspace))

    assert decision.status == "denied"
    assert "outside" in decision.reason


def test_allows_relative_write_paths_inside_the_workspace(tmp_path: Path) -> None:
    decision = PermissionManager(tmp_path).request("task-1", "call-1", ToolOperation(tool="edit", target_path=Path("src/login.py")))

    assert decision.status == "requires_confirmation"


def test_high_risk_shell_commands_require_a_one_time_confirmation(tmp_path: Path) -> None:
    manager = PermissionManager(tmp_path)
    operation = ToolOperation(tool="bash", command="git push origin main")

    request = manager.request("task-1", "call-1", operation)
    granted = manager.respond("task-1", granted=True)
    repeated_request = manager.request("task-1", "call-2", operation)

    assert request.status == "requires_confirmation"
    assert request.permission == "high-risk"
    assert granted.status == "allowed"
    assert repeated_request.status == "requires_confirmation"


def test_clearing_a_task_removes_its_workspace_write_grant(tmp_path: Path) -> None:
    manager = PermissionManager(tmp_path)
    manager.request("task-1", "call-1", ToolOperation(tool="edit", target_path=tmp_path / "login.py"))
    manager.respond("task-1", granted=True)

    manager.clear("task-1")

    assert manager.has_workspace_write("task-1") is False
