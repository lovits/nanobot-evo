from __future__ import annotations

from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import (
    ProposalStatus,
    ReviewRequest,
    ReviewTrigger,
    SkillPatch,
    SkillProposal,
    SkillTrajectory,
)
from nanobot.evolution.patching import SkillPatcher, content_hash
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.store import EvolutionStore


def _write_skill(workspace) -> tuple[object, str]:
    path = workspace / "skills" / "repo-analysis" / "SKILL.md"
    path.parent.mkdir(parents=True)
    content = (
        "---\nname: repo-analysis\ndescription: Analyze Python repositories\n---\n"
        "1. Inspect source files.\n"
    )
    path.write_text(content, encoding="utf-8")
    return path, content


def _trajectory(trace_id: str, turn_id: str, scope: str) -> SkillTrajectory:
    return SkillTrajectory(
        EVOLUTION_SCHEMA_VERSION,
        trace_id,
        "now",
        turn_id,
        None,
        "cli",
        "direct",
        "task",
        ("repo-analysis",),
        (),
        None,
        "completed",
        None,
        1,
        0,
        0,
        False,
        scope,
    )


def _request() -> ReviewRequest:
    return ReviewRequest(
        "rv_1",
        "repo-analysis",
        ReviewTrigger.PERIODIC,
        ("tr_1", "tr_2"),
        None,
        "cli",
        "direct",
        "now",
    )


def _proposal(base_hash: str) -> SkillProposal:
    return SkillProposal(
        EVOLUTION_SCHEMA_VERSION,
        "pr_1",
        "rv_1",
        "repo-analysis",
        base_hash,
        ("tr_1", "tr_2"),
        "Two repositories omitted packaging metadata",
        SkillPatch(
            "1. Inspect source files.",
            "1. Inspect pyproject.toml before source files.",
        ),
        ProposalStatus.PENDING,
        "now",
        None,
        None,
        None,
        None,
    )


def _patcher(workspace) -> SkillPatcher:
    return SkillPatcher(EvolutionStore(workspace), PatchPolicy(workspace))


def test_approve_backs_up_and_applies_then_restore_recovers(tmp_path) -> None:
    path, original = _write_skill(tmp_path)
    patcher = _patcher(tmp_path)
    patcher.store.save_proposal(_proposal(content_hash(original)))
    evidence = [
        _trajectory("tr_1", "turn_1", "scope_a"),
        _trajectory("tr_2", "turn_2", "scope_b"),
    ]

    applied = patcher.approve("pr_1", request=_request(), evidence=evidence)

    assert applied.status is ProposalStatus.APPLIED
    assert "pyproject.toml" in path.read_text(encoding="utf-8")
    assert (
        patcher.store.load_skill_version_content(
            patcher.store.list_skill_versions("repo-analysis")[0]
        )
        == original
    )

    restored = patcher.restore("repo-analysis")
    assert restored.status is ProposalStatus.RESTORED
    assert path.read_text(encoding="utf-8") == original


def test_switches_between_any_retained_versions_and_preserves_current(tmp_path) -> None:
    path, original = _write_skill(tmp_path)
    patcher = _patcher(tmp_path)
    first = _proposal(content_hash(original))
    patcher.store.save_proposal(first)
    patcher.approve(
        first.proposal_id,
        request=_request(),
        evidence=[_trajectory("tr_1", "turn_1", "scope_a")],
    )
    evolved = path.read_text(encoding="utf-8")

    selected = patcher.switch_version("repo-analysis", content_hash(original))
    assert selected == content_hash(original)
    assert path.read_text(encoding="utf-8") == original

    selected = patcher.switch_version("repo-analysis", content_hash(evolved))
    assert selected == content_hash(evolved)
    assert path.read_text(encoding="utf-8") == evolved


def test_approve_marks_conflict_without_overwriting_user_edit(tmp_path) -> None:
    path, original = _write_skill(tmp_path)
    patcher = _patcher(tmp_path)
    patcher.store.save_proposal(_proposal(content_hash(original)))
    path.write_text(original + "\nUser edit.\n", encoding="utf-8")

    result = patcher.approve(
        "pr_1",
        request=_request(),
        evidence=[
            _trajectory("tr_1", "turn_1", "scope_a"),
            _trajectory("tr_2", "turn_2", "scope_b"),
        ],
    )

    assert result.status is ProposalStatus.CONFLICT
    assert path.read_text(encoding="utf-8").endswith("User edit.\n")
    assert patcher.store.list_skill_versions("repo-analysis") == []


def test_reject_never_modifies_skill(tmp_path) -> None:
    path, original = _write_skill(tmp_path)
    patcher = _patcher(tmp_path)
    patcher.store.save_proposal(_proposal(content_hash(original)))

    rejected = patcher.reject("pr_1")

    assert rejected.status is ProposalStatus.REJECTED
    assert path.read_text(encoding="utf-8") == original
