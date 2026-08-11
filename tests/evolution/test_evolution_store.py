from __future__ import annotations

from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import (
    EvolutionState,
    ProposalStatus,
    SkillPatch,
    SkillProposal,
    SkillReviewState,
    SkillTrajectory,
    SkillVersionRecord,
)
from nanobot.evolution.store import EvolutionStore


def _trajectory(trace_id: str, turn_id: str, skill: str) -> SkillTrajectory:
    return SkillTrajectory(
        EVOLUTION_SCHEMA_VERSION,
        trace_id,
        "2026-07-26T00:00:00Z",
        turn_id,
        None,
        "cli",
        "direct",
        "inspect repository",
        (skill,),
        (),
        "done",
        "completed",
        None,
        1,
        2,
        3,
        False,
        None,
    )


def _proposal(proposal_id: str = "pr_1") -> SkillProposal:
    return SkillProposal(
        EVOLUTION_SCHEMA_VERSION,
        proposal_id,
        "rv_1",
        "repo-analysis",
        "base",
        ("tr_1", "tr_2"),
        "reason",
        SkillPatch("old", "new"),
        ProposalStatus.PENDING,
        "now",
        None,
        None,
        None,
        None,
    )


def test_appends_jsonl_and_filters_recent_trajectories(tmp_path) -> None:
    store = EvolutionStore(tmp_path)
    store.append_trajectory(_trajectory("tr_1", "turn_1", "repo-analysis"))
    store.append_trajectory(_trajectory("tr_2", "turn_2", "other"))
    store.append_trajectory(_trajectory("tr_3", "turn_3", "repo-analysis"))

    lines = store.trajectories_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [
        item.trace_id for item in store.list_trajectories(skill_name="repo-analysis", limit=1)
    ] == ["tr_3"]
    assert [item.trace_id for item in store.trajectories_by_id(("tr_3", "tr_1"))] == [
        "tr_1",
        "tr_3",
    ]

    with store.trajectories_file.open("a", encoding="utf-8") as handle:
        handle.write("{interrupted\n")
    assert len(store.list_trajectories()) == 3


def test_round_trips_proposals_reviews_and_state(tmp_path) -> None:
    store = EvolutionStore(tmp_path)
    proposal = _proposal()
    store.save_proposal(proposal)
    store.save_review("rv_1", {"decision": "no_change"})
    state = EvolutionState(
        EVOLUTION_SCHEMA_VERSION,
        {"repo-analysis": SkillReviewState("repo-analysis", 2, 0, False, False, None, None, None)},
    )
    store.save_state(state)

    assert store.load_proposal("pr_1") == proposal
    assert store.load_review("rv_1") == {"decision": "no_change"}
    assert store.load_state() == state
    assert store.update_proposal("pr_1", status=ProposalStatus.REJECTED).status is (
        ProposalStatus.REJECTED
    )


def test_persists_permanent_skill_versions(tmp_path) -> None:
    store = EvolutionStore(tmp_path)
    record = SkillVersionRecord(
        "repo-analysis",
        "abc123",
        "pr_1",
        "2026-07-26T00:00:00Z",
        "20260726T000000Z_abc123.md",
    )

    store.save_skill_version(record, "old skill")

    assert store.list_skill_versions("repo-analysis") == [record]
    assert store.load_skill_version_content(record) == "old skill"
