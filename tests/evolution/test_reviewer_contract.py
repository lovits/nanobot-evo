from __future__ import annotations

from nanobot.evolution.models import ReviewRequest, ReviewTrigger
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.reviewer import SkillReviewer
from nanobot.evolution.store import EvolutionStore


def test_reviewer_exposes_only_evidence_and_proposal_tools(tmp_path) -> None:
    skill = tmp_path / "skills" / "repo-analysis" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: repo-analysis\ndescription: test\n---\nBody\n",
        encoding="utf-8",
    )
    reviewer = SkillReviewer(
        workspace=tmp_path,
        store=EvolutionStore(tmp_path),
        policy=PatchPolicy(tmp_path),
    )
    request = ReviewRequest(
        "rv_1",
        "repo-analysis",
        ReviewTrigger.MANUAL,
        (),
        None,
        "cli",
        "direct",
        "now",
    )

    registry, _ = reviewer.build_tools(request)

    assert set(registry.tool_names) == {"review_evidence", "skill_manage"}
    assert "shell" not in registry.tool_names
    assert "read_file" not in registry.tool_names
