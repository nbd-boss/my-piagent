import pytest

from pipilot_runtime.context import UserTask


def test_preserves_original_request_and_appends_follow_up() -> None:
    task = UserTask("修复登录接口空邮箱导致 500，并补测试。")

    updated = task.with_follow_up("不要修改数据库结构。")

    assert updated.original_request == "修复登录接口空邮箱导致 500，并补测试。"
    assert updated.follow_ups == ("不要修改数据库结构。",)
    assert updated.routing_input() == "修复登录接口空邮箱导致 500，并补测试。\n\n用户补充：不要修改数据库结构。"


def test_renders_host_scope_separately_from_user_text() -> None:
    task = UserTask("解释认证流程").with_follow_up("不要修改代码。")

    assert task.render() == (
        "## User task\n解释认证流程\n\n"
        "## Follow-up constraints\n- 不要修改代码。\n\n"
        "## Execution scope (host-provided)\n所有相对路径均以当前工作区为根目录。"
    )


def test_rejects_empty_user_input() -> None:
    with pytest.raises(ValueError, match="original_request"):
        UserTask("  ")
