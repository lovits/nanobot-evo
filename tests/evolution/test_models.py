from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import (
    EvolutionState,
    EvolutionToolEvent,
    ProposalStatus,
    ReviewDecision,
    ReviewRequest,
    ReviewTrigger,
    SkillPatch,
    SkillProposal,
    SkillReviewState,
    SkillTrajectory,
    SkillVersionRecord,
    ToolEventStatus,
    new_proposal_id,
    new_review_id,
    new_trace_id,
    project_scope_hash,
    utc_now,
)


def test_identifiers_and_time_are_opaque_and_utc() -> None:
    assert new_trace_id().startswith("tr_")
    assert new_review_id().startswith("rv_")
    assert new_proposal_id().startswith("pr_")
    assert utc_now().endswith("Z")


def test_scope_hash_is_stable_and_never_contains_the_path(tmp_path) -> None:
    scope = project_scope_hash(tmp_path / "project" / ".." / "project")
    assert scope == project_scope_hash(tmp_path / "project")
    assert scope is not None
    assert str(tmp_path) not in scope


def test_trajectory_round_trips_nested_events_and_is_frozen() -> None:
    trajectory = SkillTrajectory(
        schema_version=EVOLUTION_SCHEMA_VERSION,
        trace_id="tr_1",
        created_at="2026-07-26T00:00:00Z",
        turn_id="turn_1",
        session_key=None,
        channel="cli",
        chat_id="chat",
        task="inspect project",
        used_skills=("repo-analysis",),
        tool_events=(
            EvolutionToolEvent(
                call_id="call_1",
                name="read_file",
                params={"path": "README.md"},
                status=ToolEventStatus.SUCCESS,
                result_excerpt="ok",
                error=None,
                iteration=0,
            ),
        ),
        final_response_excerpt="done",
        stop_reason="complete",
        error=None,
        iterations=1,
        prompt_tokens=4,
        completion_tokens=2,
        objective_failure=False,
        project_scope_hash="a" * 16,
    )

    assert SkillTrajectory.from_dict(trajectory.to_dict()) == trajectory
    with pytest.raises(FrozenInstanceError):
        trajectory.channel = "other"  # type: ignore[misc]


def test_trajectory_canonicalizes_workspace_skill_attribution() -> None:
    trajectory = SkillTrajectory(
        EVOLUTION_SCHEMA_VERSION,
        "tr_1",
        "now",
        "turn",
        None,
        "cli",
        "chat",
        "task",
        ("zeta", "alpha", "zeta"),
        (),
        None,
        None,
        None,
        0,
        0,
        0,
        False,
        None,
    )

    assert trajectory.used_skills == ("alpha", "zeta")


def test_all_remaining_dtos_round_trip() -> None:
    review = ReviewRequest(
        "rv_1",
        "repo-analysis",
        ReviewTrigger.MANUAL,
        ("tr_1",),
        "check setup",
        "cli",
        "chat",
        "now",
    )
    proposal = SkillProposal(
        EVOLUTION_SCHEMA_VERSION,
        "pr_1",
        "rv_1",
        "repo-analysis",
        "hash",
        ("tr_1", "tr_2"),
        "repeatable omission",
        SkillPatch("old", "new"),
        ProposalStatus.PENDING,
        "now",
        None,
        None,
        None,
        None,
    )
    state = EvolutionState(
        EVOLUTION_SCHEMA_VERSION,
        {
            "repo-analysis": SkillReviewState(
                "repo-analysis", 10, 0, False, True, "rv_1", None, ReviewDecision.NO_CHANGE
            )
        },
    )
    version = SkillVersionRecord("repo-analysis", "hash", "pr_1", "now", "history.md")

    assert ReviewRequest.from_dict(review.to_dict()) == review
    assert SkillProposal.from_dict(proposal.to_dict()) == proposal
    assert EvolutionState.from_dict(state.to_dict()) == state
    assert SkillVersionRecord.from_dict(version.to_dict()) == version
