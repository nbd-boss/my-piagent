from pathlib import Path

from pipilot_runtime.context import UserTask
from pipilot_runtime.routing import DeterministicMockClassifier, IntentRouter, RouteInput
from pipilot_runtime.task_memory import TaskMemory


def test_persists_a_routed_task_for_a_later_runtime_instance(tmp_path: Path) -> None:
    route = IntentRouter(DeterministicMockClassifier()).decide(RouteInput(userMessage="修复登录校验并添加测试"))
    TaskMemory(tmp_path).record_request("task/1", UserTask("修复登录校验并添加测试"), route)

    snapshot = TaskMemory(tmp_path).load("task/1")

    assert snapshot is not None
    assert snapshot.task_id == "task/1"
    assert snapshot.intent == "change"
    assert snapshot.status == "routed"


def test_marks_an_existing_task_as_cancelled(tmp_path: Path) -> None:
    memory = TaskMemory(tmp_path)
    route = IntentRouter(DeterministicMockClassifier()).decide(RouteInput(userMessage="Explain the authentication flow"))
    memory.record_request("task-1", UserTask("Explain the authentication flow"), route)

    memory.mark_cancelled("task-1")

    snapshot = memory.load("task-1")
    assert snapshot is not None
    assert snapshot.status == "cancelled"


def test_persists_user_task_with_follow_ups_and_host_scope(tmp_path: Path) -> None:
    memory = TaskMemory(tmp_path)
    route = IntentRouter(DeterministicMockClassifier()).decide(RouteInput(userMessage="修复登录校验"))
    user_task = UserTask(
        "修复登录校验",
        ("不要修改数据库结构。", "只运行相关测试。"),
        "所有相对路径均以当前工作区为根目录。",
    )

    memory.record_request("task-1", user_task, route)

    snapshot = memory.load("task-1")
    assert snapshot is not None
    assert snapshot.user_task == user_task
    assert "用户补充：不要修改数据库结构。" in snapshot.latest_request
