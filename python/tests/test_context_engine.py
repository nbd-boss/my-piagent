from pathlib import Path

from pipilot_runtime.context import ContextEngine, UserTask


def test_builds_initial_context_in_fixed_order_with_rule_sources(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    working_directory = workspace / "packages" / "api"
    working_directory.mkdir(parents=True)
    (workspace / ".git").mkdir()
    (workspace / "AGENTS.md").write_text("Use Python.", encoding="utf-8")
    (workspace / "packages" / "AGENTS.md").write_text("Run focused tests.", encoding="utf-8")
    user_task = UserTask("修复登录接口。", ("不要修改数据库结构。",))

    context = ContextEngine(working_directory).build_initial_context(user_task)

    rules, task = context.blocks
    assert (rules.name, task.name) == ("AGENTS.md", "UserTask")
    assert rules.sources == ("AGENTS.md", "packages/AGENTS.md")
    assert "### AGENTS.md\nUse Python." in rules.content
    assert "### packages/AGENTS.md\nRun focused tests." in rules.content
    assert task.sources == ("user_message", "steer", "host:execution_scope")
    assert context.render().index("## AGENTS.md") < context.render().index("## User task")


def test_records_that_no_agents_file_was_found(tmp_path: Path) -> None:
    context = ContextEngine(tmp_path).build_initial_context(UserTask("解释认证流程。"))

    rules = context.blocks[0]
    assert rules.sources == ()
    assert rules.content == "## AGENTS.md\nNo project rules file was found."


def test_rejects_a_working_directory_outside_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    try:
        ContextEngine(outside, workspace).build_initial_context(UserTask("解释认证流程。"))
    except ValueError as error:
        assert str(error) == "working_directory must be inside workspace_root"
    else:
        raise AssertionError("Expected an outside working directory to be rejected")
