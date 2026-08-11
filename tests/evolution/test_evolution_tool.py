from __future__ import annotations

import json

from nanobot.agent.tools.base import ToolResult
from nanobot.evolution.constants import (
    EVOLUTION_SCHEMA_VERSION,
    REVIEW_MAX_TOOL_RESULT_CHARS,
)
from nanobot.evolution.models import (
    EvolutionToolEvent,
    ReviewRequest,
    ReviewTrigger,
    SkillTrajectory,
    ToolEventStatus,
)
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.store import EvolutionStore
from nanobot.evolution.tool import ProposalBuilder, ReviewEvidenceTool, SkillManageTool


def _setup(workspace):
    skill_path = workspace / "skills" / "repo-analysis" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\nname: repo-analysis\ndescription: Analyze repositories\n---\n"
        "1. Inspect source files.\n",
        encoding="utf-8",
    )
    store = EvolutionStore(workspace)
    for index, scope in enumerate(("scope_a", "scope_b"), 1):
        store.append_trajectory(
            SkillTrajectory(
                EVOLUTION_SCHEMA_VERSION,
                f"tr_{index}",
                "now",
                f"turn_{index}",
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
        )
    request = ReviewRequest(
        "rv_1",
        "repo-analysis",
        ReviewTrigger.PERIODIC,
        ("tr_1", "tr_2"),
        None,
        "cli",
        "direct",
        "now",
    )
    return skill_path, store, request


async def test_review_evidence_is_bound_to_skill_and_request(tmp_path) -> None:
    _, store, request = _setup(tmp_path)
    tool = ReviewEvidenceTool(
        store=store,
        policy=PatchPolicy(tmp_path),
        request=request,
    )

    assert "name: repo-analysis" in await tool.execute("read_skill")
    evidence = json.loads(await tool.execute("read_trajectories"))
    assert [item["trace_id"] for item in evidence] == ["tr_1", "tr_2"]


async def test_review_budget_can_return_large_marketplace_skill_in_full(tmp_path) -> None:
    skill_path, store, request = _setup(tmp_path)
    body = "Inspect representative files before expanding scope.\n" * 500
    skill_path.write_text(
        "---\nname: repo-analysis\ndescription: Analyze repositories\n---\n" + body,
        encoding="utf-8",
    )
    tool = ReviewEvidenceTool(
        store=store,
        policy=PatchPolicy(tmp_path),
        request=request,
    )

    raw = await tool.execute("read_skill")

    assert len(raw) > 16_000
    assert len(raw) < REVIEW_MAX_TOOL_RESULT_CHARS
    assert raw.endswith(body)


async def test_review_evidence_compacts_every_authorized_trace(tmp_path) -> None:
    _, store, request = _setup(tmp_path)
    for index in range(3, 11):
        store.append_trajectory(
            SkillTrajectory(
                EVOLUTION_SCHEMA_VERSION,
                f"tr_{index}",
                "now",
                f"turn_{index}",
                None,
                "cli",
                "direct",
                f"task {index}",
                ("repo-analysis",),
                (
                    EvolutionToolEvent(
                        f"call_{index}",
                        "read_file",
                        {"path": f"repository-{index}/file.py"},
                        ToolEventStatus.SUCCESS,
                        "x" * 4_000,
                        None,
                        0,
                    ),
                ),
                f"trace-{index} " + "y" * 4_000,
                "completed",
                None,
                1,
                0,
                0,
                False,
                f"scope_{index}",
            )
        )
    request = ReviewRequest(
        request.review_id,
        request.skill_name,
        request.trigger,
        tuple(f"tr_{index}" for index in range(1, 11)),
        request.user_feedback,
        request.source_channel,
        request.source_chat_id,
        request.requested_at,
    )
    tool = ReviewEvidenceTool(
        store=store,
        policy=PatchPolicy(tmp_path),
        request=request,
    )

    raw = await tool.execute("read_trajectories")
    evidence = json.loads(raw)

    assert len(raw) < REVIEW_MAX_TOOL_RESULT_CHARS
    assert [item["trace_id"] for item in evidence] == [f"tr_{index}" for index in range(1, 11)]
    assert evidence[-1]["final_response_excerpt"].startswith("trace-10")
    assert "params" not in evidence[-1]["tool_events"][0]


async def test_skill_manage_creates_pending_without_modifying_skill(tmp_path) -> None:
    skill_path, store, request = _setup(tmp_path)
    original = skill_path.read_text(encoding="utf-8")
    builder = ProposalBuilder(store, PatchPolicy(tmp_path), request)
    tool = SkillManageTool(builder)

    result = await tool.execute(
        action="patch",
        skill="repo-analysis",
        old_text="1. Inspect source files.",
        new_text="1. Inspect pyproject.toml before source files.",
        reason="Both repositories missed their declared entry point.",
        evidence_trace_ids=["tr_1", "tr_2"],
    )

    assert json.loads(result)["status"] == "pending"
    assert builder.created is not None
    assert skill_path.read_text(encoding="utf-8") == original


async def test_skill_manage_accepts_single_attributed_evidence(tmp_path) -> None:
    _, store, request = _setup(tmp_path)
    tool = SkillManageTool(ProposalBuilder(store, PatchPolicy(tmp_path), request))

    result = await tool.execute(
        action="patch",
        skill="repo-analysis",
        old_text="1. Inspect source files.",
        new_text="1. Inspect pyproject.toml before source files.",
        reason="One task failed.",
        evidence_trace_ids=["tr_1"],
    )

    assert not isinstance(result, ToolResult)
    assert json.loads(result)["status"] == "pending"
    assert len(store.list_proposals()) == 1
