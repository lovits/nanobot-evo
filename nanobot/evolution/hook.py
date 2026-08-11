"""Turn-scoped observation hook for redacted Workspace Skill trajectories."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from nanobot.agent.hook import (
    AgentHook,
    AgentHookContext,
    AgentRunHookContext,
    AgentTurnHookContext,
    AgentTurnHookFactory,
)
from nanobot.agent.tools.context import RequestContext, current_request_context
from nanobot.evolution.attribution import (
    always_workspace_skills,
    attribute_read_file,
)
from nanobot.evolution.constants import (
    EVOLUTION_SCHEMA_VERSION,
    MAX_FINAL_RESPONSE_CHARS,
    MAX_TOOL_RESULT_CHARS,
)
from nanobot.evolution.models import (
    EvolutionToolEvent,
    SkillTrajectory,
    ToolEventStatus,
    new_trace_id,
    project_scope_hash,
    utc_now,
)
from nanobot.evolution.redaction import (
    redact_params,
    redact_text,
    redact_tool_result,
)
from nanobot.providers.base import ToolCallRequest

TrajectoryCallback = Callable[[SkillTrajectory], Awaitable[None]]
_NORMAL_STOP_REASONS = {"completed"}


class SkillEvolutionHook(AgentHook):
    """Observe one normal agent turn without changing its execution semantics."""

    def __init__(
        self,
        *,
        agent_workspace: Path,
        turn: AgentTurnHookContext,
        request: RequestContext,
        on_trajectory: TrajectoryCallback,
    ) -> None:
        super().__init__()
        self._agent_workspace = agent_workspace
        self._turn = turn
        self._request = request
        self._on_trajectory = on_trajectory
        self._used_skills = {
            reference.name for reference in always_workspace_skills(agent_workspace)
        }
        self._tool_events: list[EvolutionToolEvent] = []
        self._last_iteration = -1
        self._run_context: AgentRunHookContext | None = None
        self._emitted = False

    async def before_iteration(self, context: AgentHookContext) -> None:
        self._last_iteration = max(self._last_iteration, context.iteration)

    async def after_execute_tool(
        self,
        context: AgentHookContext,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
        result: Any,
    ) -> None:
        safe_params = params if isinstance(params, dict) else {}
        reference = attribute_read_file(
            self._agent_workspace,
            tool_call.name,
            safe_params,
            succeeded=True,
            path_base=self._request.workspace,
        )
        if reference is not None:
            self._used_skills.add(reference.name)
        self._tool_events.append(
            EvolutionToolEvent(
                call_id=str(tool_call.id),
                name=str(tool_call.name),
                params=redact_params(safe_params),
                status=ToolEventStatus.SUCCESS,
                result_excerpt=redact_tool_result(result, MAX_TOOL_RESULT_CHARS),
                error=None,
                iteration=context.iteration,
            )
        )

    async def on_execute_tool_error(
        self,
        context: AgentHookContext,
        tool_call: ToolCallRequest,
        tool: Any,
        params: Any,
        error: Any,
    ) -> None:
        safe_params = params if isinstance(params, dict) else {}
        self._tool_events.append(
            EvolutionToolEvent(
                call_id=str(tool_call.id),
                name=str(tool_call.name),
                params=redact_params(safe_params),
                status=ToolEventStatus.ERROR,
                result_excerpt=None,
                error=redact_text(error, MAX_TOOL_RESULT_CHARS),
                iteration=context.iteration,
            )
        )

    async def after_run(self, context: AgentRunHookContext) -> None:
        self._run_context = context

    async def on_error(self, context: AgentRunHookContext) -> None:
        self._run_context = context

    async def on_finally(self, context: AgentRunHookContext) -> None:
        if self._emitted:
            return
        self._emitted = True
        run = self._run_context or context
        if not self._used_skills:
            return
        self._merge_runner_events(run)
        stop_reason = run.stop_reason
        objective_failure = (
            run.error is not None
            or run.exception is not None
            or stop_reason not in _NORMAL_STOP_REASONS
            or any(event.status is ToolEventStatus.ERROR for event in self._tool_events)
            or any(event.get("status") == "error" for event in run.tool_events)
        )
        usage = run.usage
        trajectory = SkillTrajectory(
            schema_version=EVOLUTION_SCHEMA_VERSION,
            trace_id=new_trace_id(),
            created_at=utc_now(),
            turn_id=self._request.turn_id or new_trace_id(),
            session_key=self._request.session_key,
            channel=self._turn.channel,
            chat_id=self._turn.chat_id,
            task=redact_text(
                self._request.original_user_text or "",
                MAX_FINAL_RESPONSE_CHARS,
            ),
            used_skills=tuple(self._used_skills),
            tool_events=tuple(self._tool_events),
            final_response_excerpt=(
                redact_text(run.final_content, MAX_FINAL_RESPONSE_CHARS)
                if run.final_content is not None
                else None
            ),
            stop_reason=stop_reason,
            error=(
                redact_text(run.error, MAX_TOOL_RESULT_CHARS) if run.error is not None else None
            ),
            iterations=max(0, self._last_iteration + 1),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            objective_failure=objective_failure,
            project_scope_hash=project_scope_hash(self._request.workspace),
        )
        await self._on_trajectory(trajectory)

    def _merge_runner_events(self, run: AgentRunHookContext) -> None:
        """Retain runner-boundary failures that happen before tool hooks fire."""
        observed = [(event.name, event.status.value) for event in self._tool_events]
        for index, event in enumerate(run.tool_events):
            name = str(event.get("name", ""))
            status = "error" if event.get("status") == "error" else "success"
            match = (name, status)
            if match in observed:
                observed.remove(match)
                continue
            detail = event.get("detail")
            self._tool_events.append(
                EvolutionToolEvent(
                    call_id=f"runner_{index}",
                    name=name,
                    params={},
                    status=ToolEventStatus(status),
                    result_excerpt=(
                        redact_text(detail, MAX_TOOL_RESULT_CHARS)
                        if status == "success" and detail is not None
                        else None
                    ),
                    error=(
                        redact_text(detail, MAX_TOOL_RESULT_CHARS)
                        if status == "error" and detail is not None
                        else None
                    ),
                    iteration=max(0, self._last_iteration),
                )
            )


def make_skill_evolution_hook_factory(
    *,
    agent_workspace: Path,
    on_trajectory: TrajectoryCallback,
) -> AgentTurnHookFactory:
    """Build hooks only for ordinary turns with a bound request identity."""

    def factory(turn: AgentTurnHookContext) -> AgentHook | None:
        if turn.ephemeral:
            return None
        request = current_request_context()
        if request is None or request.turn_id is None:
            return None
        return SkillEvolutionHook(
            agent_workspace=agent_workspace,
            turn=turn,
            request=request,
            on_trajectory=on_trajectory,
        )

    return factory


__all__ = [
    "SkillEvolutionHook",
    "TrajectoryCallback",
    "make_skill_evolution_hook_factory",
]
