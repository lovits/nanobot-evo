from __future__ import annotations

import pytest

from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import (
    ProposalStatus,
    ReviewRequest,
    ReviewTrigger,
    SkillPatch,
    SkillProposal,
    SkillTrajectory,
)
from nanobot.evolution.policy import PatchPolicy, PolicyViolationError


def _write_skill(workspace, content: str | None = None):
    path = workspace / "skills" / "repo-analysis" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        content
        or "---\nname: repo-analysis\ndescription: Analyze Python repositories\n---\n"
        "1. Inspect source files.\n",
        encoding="utf-8",
    )
    return path


def _trajectory(trace_id: str, turn_id: str, scope: str | None) -> SkillTrajectory:
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


def _request(trigger=ReviewTrigger.PERIODIC, feedback=None) -> ReviewRequest:
    return ReviewRequest(
        "rv_1",
        "repo-analysis",
        trigger,
        ("tr_1", "tr_2"),
        feedback,
        "cli",
        "direct",
        "now",
    )


def test_validates_existing_workspace_target_and_local_patch(tmp_path) -> None:
    path = _write_skill(tmp_path)
    policy = PatchPolicy(tmp_path)
    current = path.read_text(encoding="utf-8")

    assert policy.validate_target("repo-analysis").path == path.resolve()
    updated = policy.validate_patch(
        current,
        SkillPatch(
            "1. Inspect source files.",
            "1. Inspect pyproject.toml before source files.",
        ),
    )
    assert "pyproject.toml" in updated


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        (SkillPatch("missing", "new"), "exactly once"),
        (SkillPatch("1. Inspect source files.", ""), "must not be empty"),
        (
            SkillPatch("1. Inspect source files.", "Read /Users/example/private.py"),
            "absolute paths",
        ),
        (
            SkillPatch("1. Inspect source files.", "api_key=secret"),
            "secrets",
        ),
    ],
)
def test_rejects_unsafe_patches(tmp_path, patch, message) -> None:
    path = _write_skill(tmp_path)
    with pytest.raises(PolicyViolationError, match=message):
        PatchPolicy(tmp_path).validate_patch(path.read_text(encoding="utf-8"), patch)


def test_rejects_frontmatter_name_changes(tmp_path) -> None:
    path = _write_skill(tmp_path)
    with pytest.raises(PolicyViolationError, match="must not change"):
        PatchPolicy(tmp_path).validate_patch(
            path.read_text(encoding="utf-8"),
            SkillPatch("name: repo-analysis", "name: another-skill"),
        )


def test_one_attributed_trajectory_is_valid_evidence(tmp_path) -> None:
    _write_skill(tmp_path)
    policy = PatchPolicy(tmp_path)

    policy.validate_evidence(
        "repo-analysis",
        [_trajectory("tr_1", "turn_1", "scope_a")],
        _request(),
    )


def test_manual_feedback_allows_one_persisted_evidence(tmp_path) -> None:
    _write_skill(tmp_path)
    request = ReviewRequest(
        "rv_1",
        "repo-analysis",
        ReviewTrigger.MANUAL,
        ("tr_1",),
        "Always inspect pyproject.toml first",
        "cli",
        "direct",
        "now",
    )

    PatchPolicy(tmp_path).validate_evidence(
        "repo-analysis",
        [_trajectory("tr_1", "turn_1", "scope_a")],
        request,
    )


def test_finds_only_identical_pending_proposal() -> None:
    patch = SkillPatch("old", "new")
    proposal = SkillProposal(
        EVOLUTION_SCHEMA_VERSION,
        "pr_1",
        "rv_1",
        "repo-analysis",
        "base",
        ("tr_1", "tr_2"),
        "reason",
        patch,
        ProposalStatus.PENDING,
        "now",
        None,
        None,
        None,
        None,
    )

    assert (
        PatchPolicy.find_duplicate(
            [proposal],
            skill_name="repo-analysis",
            patch=patch,
        )
        == proposal
    )
