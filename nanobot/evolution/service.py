"""Application service coordinating evidence, review, approval, and recovery."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.hook import AgentHook, AgentTurnHookContext
from nanobot.agent.model_runtime import ModelRuntimeResolver
from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.evolution.constants import (
    EVOLUTION_SCHEMA_VERSION,
    REVIEW_EVERY_N_TRAJECTORIES,
    REVIEW_INTERVAL_OPTIONS,
    REVIEW_TIMEOUT_SECONDS,
    REVIEW_TRAJECTORY_WINDOW,
)
from nanobot.evolution.hook import make_skill_evolution_hook_factory
from nanobot.evolution.models import (
    EvolutionState,
    ProposalStatus,
    ReviewRequest,
    ReviewTrigger,
    SkillProposal,
    SkillReviewState,
    SkillTrajectory,
    new_review_id,
    utc_now,
)
from nanobot.evolution.patching import SkillPatcher
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.reviewer import ReviewOutcome, SkillReviewer
from nanobot.evolution.store import EvolutionStore

BackgroundScheduler = Callable[[Coroutine[Any, Any, Any]], None]


@dataclass(frozen=True, slots=True)
class EvolutionStatusView:
    states: tuple[SkillReviewState, ...]
    pending_proposals: tuple[SkillProposal, ...]


class SkillEvolutionService:
    """Keep the evolution loop separate from normal AgentLoop semantics."""

    def __init__(
        self,
        *,
        workspace: Path,
        store: EvolutionStore,
        policy: PatchPolicy,
        reviewer: SkillReviewer,
        runtime_resolver: ModelRuntimeResolver,
        schedule_background: BackgroundScheduler,
        bus: MessageBus,
        review_model_preset: str | None = None,
        review_every_n_trajectories: int = REVIEW_EVERY_N_TRAJECTORIES,
    ) -> None:
        if review_every_n_trajectories not in REVIEW_INTERVAL_OPTIONS:
            choices = ", ".join(str(value) for value in REVIEW_INTERVAL_OPTIONS)
            raise ValueError(
                f"review_every_n_trajectories must be one of: {choices}"
            )
        self.workspace = workspace
        self.store = store
        self.policy = policy
        self.reviewer = reviewer
        self.runtime_resolver = runtime_resolver
        self.schedule_background = schedule_background
        self.bus = bus
        self.review_model_preset = review_model_preset
        self.review_every_n_trajectories = review_every_n_trajectories
        self.patcher = SkillPatcher(store, policy)
        self._pending_requests: dict[str, ReviewRequest] = {}
        self._hook_factory = make_skill_evolution_hook_factory(
            agent_workspace=workspace,
            on_trajectory=self.record_trajectory,
        )

    def create_hook(self, turn: AgentTurnHookContext) -> AgentHook | None:
        return self._hook_factory(turn)

    async def record_trajectory(self, trajectory: SkillTrajectory) -> None:
        self.store.append_trajectory(trajectory)
        if len(trajectory.used_skills) != 1:
            return

        skill_name = trajectory.used_skills[0]
        state = self.store.load_state()
        skill_state = self._skill_state(state, skill_name)
        skill_state = replace(
            skill_state,
            trajectory_count=skill_state.trajectory_count + 1,
        )
        trigger = self._trigger_for(trajectory, skill_state)
        request: ReviewRequest | None = None
        if trigger is not None:
            request = self._build_request(
                skill_name=skill_name,
                trigger=trigger,
                source_channel=trajectory.channel,
                source_chat_id=trajectory.chat_id,
                user_feedback=None,
            )
            if skill_state.review_running:
                skill_state = replace(skill_state, review_pending=True)
                self._pending_requests[skill_name] = request
                request = None
            else:
                skill_state = replace(
                    skill_state,
                    review_running=True,
                    active_review_id=request.review_id,
                )
        self._save_skill_state(state, skill_state)
        if request is not None:
            self._start_review(request)

    async def request_review(
        self,
        *,
        skill_name: str,
        source_channel: str,
        source_chat_id: str,
        user_feedback: str | None,
    ) -> ReviewRequest:
        self.policy.validate_target(skill_name)
        feedback = user_feedback.strip() if user_feedback else None
        state = self.store.load_state()
        skill_state = self._skill_state(state, skill_name)
        progress = max(0, skill_state.trajectory_count - skill_state.last_reviewed_count)
        if feedback is None and progress < self.review_every_n_trajectories:
            remaining = self.review_every_n_trajectories - progress
            raise ValueError(
                "Review requires user feedback or the periodic trajectory threshold; "
                f"{remaining} more attributed trajectory record(s) required"
            )
        request = self._build_request(
            skill_name=skill_name,
            trigger=ReviewTrigger.MANUAL,
            source_channel=source_channel,
            source_chat_id=source_chat_id,
            user_feedback=feedback,
        )
        if skill_state.review_running:
            self._pending_requests[skill_name] = request
            self._save_skill_state(
                state,
                replace(skill_state, review_pending=True),
            )
        else:
            self._save_skill_state(
                state,
                replace(
                    skill_state,
                    review_running=True,
                    active_review_id=request.review_id,
                ),
            )
            self._start_review(request)
        return request

    def approve_proposal(self, proposal_id: str) -> SkillProposal:
        proposal = self.store.load_proposal(proposal_id)
        if proposal is None or proposal.review_id is None:
            raise KeyError(f"Unknown review-backed proposal: {proposal_id}")
        review = self.store.load_review(proposal.review_id)
        request_data = review.get("request") if review is not None else None
        if not isinstance(request_data, dict):
            raise KeyError(f"Missing ReviewRequest for proposal: {proposal_id}")
        request = ReviewRequest.from_dict(request_data)
        evidence = self.store.trajectories_by_id(proposal.evidence_trace_ids)
        return self.patcher.approve(
            proposal_id,
            request=request,
            evidence=evidence,
        )

    def reject_proposal(self, proposal_id: str) -> SkillProposal:
        return self.patcher.reject(proposal_id)

    def restore_skill(self, skill_name: str) -> SkillProposal:
        return self.patcher.restore(skill_name)

    def switch_skill_version(self, skill_name: str, target_hash: str) -> str:
        return self.patcher.switch_version(skill_name, target_hash)

    def get_status(self) -> EvolutionStatusView:
        state = self.store.load_state()
        return EvolutionStatusView(
            states=tuple(state.skills[name] for name in sorted(state.skills)),
            pending_proposals=tuple(self.store.list_proposals(ProposalStatus.PENDING)),
        )

    async def wait_until_idle(
        self,
        skill_name: str,
        *,
        timeout_seconds: float = REVIEW_TIMEOUT_SECONDS + 10,
    ) -> None:
        """Wait for the tracked review queue without exposing loop internals."""
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while self._skill_state(
            self.store.load_state(),
            skill_name,
        ).review_running:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    f"Evolution review did not finish within {timeout_seconds:g} seconds"
                )
            await asyncio.sleep(0.1)

    def _build_request(
        self,
        *,
        skill_name: str,
        trigger: ReviewTrigger,
        source_channel: str,
        source_chat_id: str,
        user_feedback: str | None,
    ) -> ReviewRequest:
        trajectories = self.store.list_trajectories(
            skill_name=skill_name,
            limit=REVIEW_TRAJECTORY_WINDOW,
        )
        if not trajectories:
            raise KeyError(f"No persisted trajectory for Skill: {skill_name}")
        return ReviewRequest(
            review_id=new_review_id(),
            skill_name=skill_name,
            trigger=trigger,
            trajectory_ids=tuple(item.trace_id for item in trajectories),
            user_feedback=user_feedback.strip()
            if user_feedback and user_feedback.strip()
            else None,
            source_channel=source_channel,
            source_chat_id=source_chat_id,
            requested_at=utc_now(),
        )

    def _start_review(self, request: ReviewRequest) -> None:
        self.store.save_review(
            request.review_id,
            {
                "schema_version": EVOLUTION_SCHEMA_VERSION,
                "status": "running",
                "request": request.to_dict(),
            },
        )
        self.schedule_background(self._run_review(request))

    async def _run_review(self, request: ReviewRequest) -> None:
        runtime = self.runtime_resolver.current()
        if self.review_model_preset:
            try:
                runtime = self.runtime_resolver.resolve_preset(self.review_model_preset)
            except Exception:
                logger.exception(
                    "Evolution review preset '{}' is invalid; using current runtime",
                    self.review_model_preset,
                )
        outcome = await self.reviewer.run(request, runtime=runtime)
        self.store.save_review(
            request.review_id,
            {
                "schema_version": EVOLUTION_SCHEMA_VERSION,
                "status": "completed",
                "request": request.to_dict(),
                "decision": outcome.decision.value,
                "proposal_id": (
                    outcome.proposal.proposal_id if outcome.proposal is not None else None
                ),
                "final_content": outcome.final_content,
                "stop_reason": outcome.stop_reason,
                "error": outcome.error,
                "usage": outcome.usage,
                "completed_at": utc_now(),
            },
        )
        await self._notify_outcome(request, outcome)
        self._finish_review(request, outcome)

    async def _notify_outcome(
        self,
        request: ReviewRequest,
        outcome: ReviewOutcome,
    ) -> None:
        if outcome.proposal is None:
            return
        proposal = outcome.proposal
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=request.source_channel,
                chat_id=request.source_chat_id,
                content=(
                    f"Skill evolution proposal {proposal.proposal_id} is pending for "
                    f"{proposal.skill_name}.\n"
                    f"Reason: {proposal.reason}\n"
                    f"Approve: /evolve approve {proposal.proposal_id}\n"
                    f"Reject: /evolve reject {proposal.proposal_id}"
                ),
            )
        )

    def _finish_review(
        self,
        request: ReviewRequest,
        outcome: ReviewOutcome,
    ) -> None:
        state = self.store.load_state()
        skill_state = self._skill_state(state, request.skill_name)
        pending = self._pending_requests.pop(request.skill_name, None)
        if pending is None:
            updated = replace(
                skill_state,
                last_reviewed_count=skill_state.trajectory_count,
                review_running=False,
                review_pending=False,
                active_review_id=None,
                last_reviewed_at=utc_now(),
                last_decision=outcome.decision,
            )
            self._save_skill_state(state, updated)
            return

        updated = replace(
            skill_state,
            last_reviewed_count=skill_state.trajectory_count,
            review_running=True,
            review_pending=False,
            active_review_id=pending.review_id,
            last_reviewed_at=utc_now(),
            last_decision=outcome.decision,
        )
        self._save_skill_state(state, updated)
        self._start_review(pending)

    def _trigger_for(
        self,
        trajectory: SkillTrajectory,
        state: SkillReviewState,
    ) -> ReviewTrigger | None:
        if trajectory.objective_failure:
            return ReviewTrigger.OBJECTIVE_FAILURE
        if (
            state.trajectory_count - state.last_reviewed_count
            >= self.review_every_n_trajectories
        ):
            return ReviewTrigger.PERIODIC
        return None

    @staticmethod
    def _skill_state(
        state: EvolutionState,
        skill_name: str,
    ) -> SkillReviewState:
        return state.skills.get(
            skill_name,
            SkillReviewState(
                skill_name=skill_name,
                trajectory_count=0,
                last_reviewed_count=0,
                review_running=False,
                review_pending=False,
                active_review_id=None,
                last_reviewed_at=None,
                last_decision=None,
            ),
        )

    def _save_skill_state(
        self,
        state: EvolutionState,
        skill_state: SkillReviewState,
    ) -> None:
        skills = dict(state.skills)
        skills[skill_state.skill_name] = skill_state
        self.store.save_state(EvolutionState(EVOLUTION_SCHEMA_VERSION, skills))


__all__ = [
    "BackgroundScheduler",
    "EvolutionStatusView",
    "SkillEvolutionService",
]
