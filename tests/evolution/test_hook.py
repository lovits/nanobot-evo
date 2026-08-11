from __future__ import annotations

from nanobot.agent.hook import AgentHookContext, AgentRunHookContext, AgentTurnHookContext
from nanobot.agent.tools.base import ToolResult
from nanobot.agent.tools.context import RequestContext, request_context
from nanobot.evolution.hook import SkillEvolutionHook, make_skill_evolution_hook_factory
from nanobot.evolution.models import ToolEventStatus
from nanobot.providers.base import ToolCallRequest


def _write_skill(workspace, name="repo-analysis", *, always=False):
    path = workspace / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"---\nname: {name}\ndescription: test\nalways: {str(always).lower()}\n---\nBody\n",
        encoding="utf-8",
    )
    return path


def _request(tmp_path) -> RequestContext:
    return RequestContext(
        channel="cli",
        chat_id="direct",
        session_key="cli:direct",
        original_user_text="Analyze token=private",
        turn_id="turn_1",
        workspace=tmp_path / "project",
    )


async def test_hook_records_redacted_successful_workspace_skill_use(tmp_path) -> None:
    skill_path = _write_skill(tmp_path)
    captured = []

    async def capture(trajectory):
        captured.append(trajectory)

    hook = SkillEvolutionHook(
        agent_workspace=tmp_path,
        turn=AgentTurnHookContext(channel="cli", chat_id="direct"),
        request=_request(tmp_path),
        on_trajectory=capture,
    )
    iteration = AgentHookContext(iteration=0, messages=[])
    await hook.before_iteration(iteration)
    await hook.after_execute_tool(
        iteration,
        ToolCallRequest(id="call_1", name="read_file", arguments={}),
        None,
        {"path": str(skill_path), "api_key": "private"},
        "token=private",
    )
    await hook.after_run(
        AgentRunHookContext(
            messages=[],
            final_content="done",
            usage={"prompt_tokens": 12, "completion_tokens": 3},
            stop_reason="completed",
        )
    )
    await hook.on_finally(AgentRunHookContext(messages=[]))

    assert len(captured) == 1
    trajectory = captured[0]
    assert trajectory.used_skills == ("repo-analysis",)
    assert trajectory.task == "Analyze token=[REDACTED]"
    assert trajectory.tool_events[0].params["api_key"] == "[REDACTED]"
    assert trajectory.tool_events[0].result_excerpt == "token=[REDACTED]"
    assert trajectory.objective_failure is False
    assert trajectory.iterations == 1


async def test_hook_marks_tool_error_as_objective_failure(tmp_path) -> None:
    _write_skill(tmp_path, always=True)
    captured = []

    async def capture(trajectory):
        captured.append(trajectory)

    hook = SkillEvolutionHook(
        agent_workspace=tmp_path,
        turn=AgentTurnHookContext(channel="cli", chat_id="direct"),
        request=_request(tmp_path),
        on_trajectory=capture,
    )
    iteration = AgentHookContext(iteration=1, messages=[])
    await hook.before_iteration(iteration)
    await hook.on_execute_tool_error(
        iteration,
        ToolCallRequest(id="call_1", name="shell", arguments={}),
        None,
        {"command": "python -m app"},
        ToolResult.error("password=private"),
    )
    await hook.after_run(
        AgentRunHookContext(
            messages=[],
            final_content="recovered",
            stop_reason="completed",
        )
    )
    await hook.on_finally(AgentRunHookContext(messages=[]))

    assert captured[0].objective_failure is True
    assert captured[0].tool_events[0].status is ToolEventStatus.ERROR
    assert captured[0].tool_events[0].error == "password=[REDACTED]"


async def test_hook_retains_runner_boundary_tool_failure(tmp_path) -> None:
    _write_skill(tmp_path, always=True)
    captured = []

    async def capture(trajectory):
        captured.append(trajectory)

    hook = SkillEvolutionHook(
        agent_workspace=tmp_path,
        turn=AgentTurnHookContext(channel="cli", chat_id="direct"),
        request=_request(tmp_path),
        on_trajectory=capture,
    )
    await hook.after_run(
        AgentRunHookContext(
            messages=[],
            final_content="recovered",
            stop_reason="completed",
            tool_events=[
                {
                    "name": "missing_tool",
                    "status": "error",
                    "detail": "token=private",
                }
            ],
        )
    )
    await hook.on_finally(AgentRunHookContext(messages=[]))

    assert captured[0].objective_failure is True
    assert captured[0].tool_events[0].name == "missing_tool"
    assert captured[0].tool_events[0].error == "token=[REDACTED]"


async def test_hook_skips_turn_without_workspace_skill_use(tmp_path) -> None:
    captured = []

    async def capture(trajectory):
        captured.append(trajectory)

    hook = SkillEvolutionHook(
        agent_workspace=tmp_path,
        turn=AgentTurnHookContext(channel="cli", chat_id="direct"),
        request=_request(tmp_path),
        on_trajectory=capture,
    )
    await hook.after_run(
        AgentRunHookContext(messages=[], final_content="done", stop_reason="completed")
    )
    await hook.on_finally(AgentRunHookContext(messages=[]))
    assert captured == []


def test_factory_requires_normal_bound_turn(tmp_path) -> None:
    async def capture(trajectory):
        return None

    factory = make_skill_evolution_hook_factory(
        agent_workspace=tmp_path,
        on_trajectory=capture,
    )

    assert factory(AgentTurnHookContext()) is None
    with request_context(_request(tmp_path)):
        assert factory(AgentTurnHookContext(ephemeral=True)) is None
        assert isinstance(factory(AgentTurnHookContext()), SkillEvolutionHook)
