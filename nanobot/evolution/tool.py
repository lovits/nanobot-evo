"""Narrow tools exposed only to the isolated skill review agent."""

from __future__ import annotations

import json
from dataclasses import dataclass

from nanobot.agent.tools.base import Tool, ToolResult, tool_parameters
from nanobot.agent.tools.schema import ArraySchema, StringSchema, tool_parameters_schema
from nanobot.evolution.constants import (
    EVOLUTION_SCHEMA_VERSION,
    REVIEW_FINAL_EXCERPT_BUDGET,
)
from nanobot.evolution.models import (
    ProposalStatus,
    ReviewRequest,
    SkillPatch,
    SkillProposal,
    SkillTrajectory,
    new_proposal_id,
    utc_now,
)
from nanobot.evolution.patching import content_hash
from nanobot.evolution.policy import PatchPolicy, PolicyViolationError
from nanobot.evolution.redaction import truncate_text
from nanobot.evolution.store import EvolutionStore

_REVIEW_TASK_CHARS = 300
_REVIEW_ERROR_CHARS = 240
_REVIEW_TOOL_EVENTS = 12


def _trajectory_review_view(
    trajectories: list[SkillTrajectory],
) -> list[dict[str, object]]:
    """Project full stored traces into a bounded view that covers every trace."""
    final_chars = min(
        3_000,
        max(400, REVIEW_FINAL_EXCERPT_BUDGET // max(1, len(trajectories))),
    )
    views: list[dict[str, object]] = []
    for trajectory in trajectories:
        events = [
            {
                "name": event.name,
                "status": event.status.value,
                "error": (truncate_text(event.error, _REVIEW_ERROR_CHARS) if event.error else None),
            }
            for event in trajectory.tool_events[:_REVIEW_TOOL_EVENTS]
        ]
        views.append(
            {
                "trace_id": trajectory.trace_id,
                "turn_id": trajectory.turn_id,
                "project_scope_hash": trajectory.project_scope_hash,
                "task": truncate_text(trajectory.task, _REVIEW_TASK_CHARS),
                "used_skills": list(trajectory.used_skills),
                "objective_failure": trajectory.objective_failure,
                "stop_reason": trajectory.stop_reason,
                "error": (
                    truncate_text(trajectory.error, _REVIEW_ERROR_CHARS)
                    if trajectory.error
                    else None
                ),
                "tool_event_count": len(trajectory.tool_events),
                "tool_events": events,
                "final_response_excerpt": (
                    truncate_text(trajectory.final_response_excerpt, final_chars)
                    if trajectory.final_response_excerpt
                    else None
                ),
            }
        )
    return views


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(
            "Read the bound review input.",
            enum=["read_skill", "read_trajectories"],
        ),
        required=["action"],
    )
)
class ReviewEvidenceTool(Tool):
    """Read only the Skill and trajectories bound to one ReviewRequest."""

    def __init__(
        self,
        *,
        store: EvolutionStore,
        policy: PatchPolicy,
        request: ReviewRequest,
    ) -> None:
        self._store = store
        self._policy = policy
        self._request = request

    @property
    def name(self) -> str:
        return "review_evidence"

    @property
    def description(self) -> str:
        return (
            "Read the existing Workspace Skill or the redacted trajectories "
            "authorized for this review. It cannot access arbitrary files."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, action: str, **kwargs) -> str:
        if action == "read_skill":
            reference = self._policy.validate_target(self._request.skill_name)
            return reference.path.read_text(encoding="utf-8")
        if action == "read_trajectories":
            trajectories = self._store.trajectories_by_id(self._request.trajectory_ids)
            return json.dumps(
                _trajectory_review_view(trajectories),
                ensure_ascii=False,
                indent=2,
            )
        return ToolResult.error(f"Unsupported review_evidence action: {action}")


@dataclass(slots=True)
class ProposalBuilder:
    """Create at most one policy-compliant Pending Proposal for a review."""

    store: EvolutionStore
    policy: PatchPolicy
    request: ReviewRequest
    created: SkillProposal | None = None

    def propose(
        self,
        *,
        skill: str,
        old_text: str,
        new_text: str,
        reason: str,
        evidence_trace_ids: list[str],
    ) -> SkillProposal:
        if self.created is not None:
            raise PolicyViolationError("This review already created its one Proposal")
        if skill != self.request.skill_name:
            raise PolicyViolationError("Review may patch only its bound Skill")
        if not reason.strip():
            raise PolicyViolationError("Proposal reason must not be empty")
        evidence_ids = tuple(dict.fromkeys(evidence_trace_ids))
        evidence = self.store.trajectories_by_id(evidence_ids)
        if len(evidence) != len(evidence_ids):
            raise PolicyViolationError("Every evidence_trace_id must exist")

        reference = self.policy.validate_target(skill)
        current = reference.path.read_text(encoding="utf-8")
        patch = SkillPatch(old_text=old_text, new_text=new_text)
        self.policy.validate_evidence(skill, evidence, self.request)
        self.policy.validate_patch(current, patch)
        duplicate = self.policy.find_duplicate(
            self.store.list_proposals(ProposalStatus.PENDING),
            skill_name=skill,
            patch=patch,
        )
        if duplicate is not None:
            self.created = duplicate
            return duplicate

        proposal = SkillProposal(
            schema_version=EVOLUTION_SCHEMA_VERSION,
            proposal_id=new_proposal_id(),
            review_id=self.request.review_id,
            skill_name=skill,
            base_hash=content_hash(current),
            evidence_trace_ids=evidence_ids,
            reason=reason.strip(),
            patch=patch,
            status=ProposalStatus.PENDING,
            created_at=utc_now(),
            decided_at=None,
            applied_at=None,
            restored_at=None,
            validation_error=None,
        )
        self.store.save_proposal(proposal)
        self.created = proposal
        return proposal


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema("Only patch is allowed.", enum=["patch"]),
        skill=StringSchema("Existing Workspace Skill name."),
        old_text=StringSchema("Exact existing text to replace."),
        new_text=StringSchema("Generalizable replacement text."),
        reason=StringSchema("How the cited traces prove this Skill defect."),
        evidence_trace_ids=ArraySchema(
            StringSchema("Persisted trace ID."),
            min_items=1,
            max_items=10,
        ),
        required=[
            "action",
            "skill",
            "old_text",
            "new_text",
            "reason",
            "evidence_trace_ids",
        ],
    )
)
class SkillManageTool(Tool):
    """Propose one patch; never approve, apply, create, delete, or rename."""

    def __init__(self, builder: ProposalBuilder) -> None:
        self._builder = builder

    @property
    def name(self) -> str:
        return "skill_manage"

    @property
    def description(self) -> str:
        return (
            "Create one trace-grounded Pending Patch for the existing Workspace "
            "Skill bound to this review. The user must approve it separately."
        )

    async def execute(
        self,
        action: str,
        skill: str,
        old_text: str,
        new_text: str,
        reason: str,
        evidence_trace_ids: list[str],
        **kwargs,
    ) -> str:
        if action != "patch":
            return ToolResult.error("skill_manage only supports action='patch'")
        try:
            proposal = self._builder.propose(
                skill=skill,
                old_text=old_text,
                new_text=new_text,
                reason=reason,
                evidence_trace_ids=evidence_trace_ids,
            )
        except PolicyViolationError as exc:
            return ToolResult.error(f"Proposal rejected by deterministic policy: {exc}")
        return json.dumps(
            {
                "proposal_id": proposal.proposal_id,
                "status": proposal.status.value,
                "skill": proposal.skill_name,
            },
            ensure_ascii=False,
        )


__all__ = ["ProposalBuilder", "ReviewEvidenceTool", "SkillManageTool"]
