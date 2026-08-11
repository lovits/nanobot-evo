"""Real-model reviewer built on the existing AgentRunner."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.evolution.constants import (
    REVIEW_MAX_ITERATIONS,
    REVIEW_MAX_TOOL_RESULT_CHARS,
    REVIEW_TIMEOUT_SECONDS,
)
from nanobot.evolution.models import (
    ReviewDecision,
    ReviewRequest,
    SkillProposal,
)
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.prompts import build_review_messages
from nanobot.evolution.store import EvolutionStore
from nanobot.evolution.tool import ProposalBuilder, ReviewEvidenceTool, SkillManageTool
from nanobot.utils.llm_runtime import LLMRuntime


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    decision: ReviewDecision
    proposal: SkillProposal | None
    final_content: str | None
    stop_reason: str | None
    error: str | None
    usage: dict[str, int]


class SkillReviewer:
    """Run an isolated review against the configured real LLM runtime."""

    def __init__(
        self,
        *,
        workspace,
        store: EvolutionStore,
        policy: PatchPolicy,
    ) -> None:
        self.workspace = workspace
        self.store = store
        self.policy = policy
        self.runner = AgentRunner()

    def build_tools(self, request: ReviewRequest) -> tuple[ToolRegistry, ProposalBuilder]:
        builder = ProposalBuilder(self.store, self.policy, request)
        registry = ToolRegistry()
        registry.register(
            ReviewEvidenceTool(
                store=self.store,
                policy=self.policy,
                request=request,
            )
        )
        registry.register(SkillManageTool(builder))
        return registry, builder

    async def run(
        self,
        request: ReviewRequest,
        *,
        runtime: LLMRuntime,
    ) -> ReviewOutcome:
        tools, builder = self.build_tools(request)
        spec = AgentRunSpec(
            initial_messages=build_review_messages(request),
            tools=tools,
            runtime=runtime,
            max_iterations=REVIEW_MAX_ITERATIONS,
            max_tool_result_chars=REVIEW_MAX_TOOL_RESULT_CHARS,
            concurrent_tools=False,
            fail_on_tool_error=False,
            workspace=self.workspace,
            session_key=f"evolution:{request.review_id}",
            finalize_on_max_iterations=True,
        )
        try:
            async with asyncio.timeout(REVIEW_TIMEOUT_SECONDS):
                result = await self.runner.run(spec)
        except TimeoutError:
            return ReviewOutcome(
                ReviewDecision.TIMED_OUT,
                None,
                None,
                "timed_out",
                f"Review exceeded {REVIEW_TIMEOUT_SECONDS} seconds",
                {},
            )
        except Exception as exc:
            return ReviewOutcome(
                ReviewDecision.FAILED,
                None,
                None,
                "error",
                f"{type(exc).__name__}: {exc}",
                {},
            )

        if builder.created is not None:
            decision = ReviewDecision.PROPOSE_PATCH
        elif result.error is not None:
            decision = ReviewDecision.FAILED
        else:
            decision = ReviewDecision.NO_CHANGE
        return ReviewOutcome(
            decision=decision,
            proposal=builder.created,
            final_content=result.final_content,
            stop_reason=result.stop_reason,
            error=result.error,
            usage=result.usage,
        )


__all__ = ["ReviewOutcome", "SkillReviewer"]
