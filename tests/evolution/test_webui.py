from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from nanobot.bus.queue import MessageBus
from nanobot.config.schema import Config
from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import (
    EvolutionToolEvent,
    ProposalStatus,
    ReviewRequest,
    ReviewTrigger,
    SkillPatch,
    SkillProposal,
    SkillTrajectory,
    ToolEventStatus,
)
from nanobot.evolution.patching import content_hash
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.reviewer import SkillReviewer
from nanobot.evolution.service import SkillEvolutionService
from nanobot.evolution.store import EvolutionStore
from nanobot.evolution.webui import EvolutionWebUIController


@dataclass
class CapturedResponse:
    payload: dict
    status_code: int = 200


@dataclass
class Request:
    headers: dict[str, str]


class ClosingScheduler:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, coroutine) -> None:
        self.count += 1
        coroutine.close()


def _json_response(payload: dict, *, status: int = 200) -> CapturedResponse:
    return CapturedResponse(payload, status)


def _write_skill(workspace: Path) -> tuple[Path, str]:
    path = workspace / "skills" / "repo-analysis" / "SKILL.md"
    path.parent.mkdir(parents=True)
    content = (
        "---\nname: repo-analysis\ndescription: Analyze Python repositories\n---\n"
        "1. Inspect source files.\n"
    )
    path.write_text(content, encoding="utf-8")
    return path, content


def _trajectory(index: int, workspace: Path) -> SkillTrajectory:
    event = EvolutionToolEvent(
        f"call_{index}",
        "read_file",
        {"path": "[REDACTED]"},
        ToolEventStatus.ERROR if index == 11 else ToolEventStatus.SUCCESS,
        None,
        "read failed" if index == 11 else None,
        0,
    )
    return SkillTrajectory(
        EVOLUTION_SCHEMA_VERSION,
        f"tr_{index}",
        f"2026-07-26T00:00:{index:02d}Z",
        f"turn_{index}",
        f"websocket:session-{index}",
        "websocket",
        f"chat-{index}",
        f"Analyze {workspace}/repositories/example-{index} with token=secret",
        ("repo-analysis",),
        (event,),
        "done",
        "completed",
        None,
        1,
        10,
        2,
        index == 11,
        f"scope_{index}",
    )


def _service(workspace: Path) -> tuple[SkillEvolutionService, ClosingScheduler]:
    store = EvolutionStore(workspace)
    policy = PatchPolicy(workspace)
    scheduler = ClosingScheduler()
    service = SkillEvolutionService(
        workspace=workspace,
        store=store,
        policy=policy,
        reviewer=SkillReviewer(workspace=workspace, store=store, policy=policy),
        runtime_resolver=None,
        schedule_background=scheduler,
        bus=MessageBus(),
    )
    return service, scheduler


def _controller(
    workspace: Path,
    *,
    service: SkillEvolutionService | None,
    config: Config | None = None,
    authorized: bool = True,
    saved: list[Config] | None = None,
) -> EvolutionWebUIController:
    current = config or Config()
    return EvolutionWebUIController(
        workspace=workspace,
        service=service,
        disabled_skills=None,
        check_api_token=lambda _request: authorized,
        json_response=_json_response,
        load_config_fn=lambda: current,
        save_config_fn=lambda value: saved.append(value) if saved is not None else None,
    )


def _review_request() -> ReviewRequest:
    return ReviewRequest(
        "rv_1",
        "repo-analysis",
        ReviewTrigger.PERIODIC,
        ("tr_1", "tr_2"),
        None,
        "webui",
        "skill-evolution",
        "2026-07-26T00:01:00Z",
    )


def _proposal(original: str, *, proposal_id: str = "pr_1") -> SkillProposal:
    return SkillProposal(
        EVOLUTION_SCHEMA_VERSION,
        proposal_id,
        "rv_1",
        "repo-analysis",
        content_hash(original),
        ("tr_1", "tr_2"),
        "Two independent repositories need packaging inspection",
        SkillPatch(
            "1. Inspect source files.",
            "1. Inspect pyproject.toml before source files.",
        ),
        ProposalStatus.PENDING,
        "2026-07-26T00:02:00Z",
        None,
        None,
        None,
        None,
    )


def test_disabled_overview_is_read_only_and_marks_builtin_skills_protected(tmp_path) -> None:
    _write_skill(tmp_path)
    controller = _controller(tmp_path, service=None)

    payload = controller.overview_payload()

    workspace_skill = next(item for item in payload["skills"] if item["name"] == "repo-analysis")
    builtin = next(item for item in payload["skills"] if item["source"] == "builtin")
    assert payload["enabled"] is False
    assert payload["runtime_active"] is False
    assert payload["restart_required"] is False
    assert payload["review_every_n_trajectories"] == 10
    assert payload["review_interval_options"] == [5, 10, 20, 100]
    assert workspace_skill["review_threshold"] == 10
    assert workspace_skill["evolvable"] is True
    assert builtin["state"] == "protected"
    assert builtin["evolvable"] is False
    assert not (tmp_path / ".nanobot" / "evolution").exists()


def test_detail_limits_and_sanitizes_evidence(tmp_path) -> None:
    _write_skill(tmp_path)
    service, _ = _service(tmp_path)
    for index in range(1, 13):
        service.store.append_trajectory(_trajectory(index, tmp_path))
    controller = _controller(tmp_path, service=service)

    payload = controller.skill_detail_payload("repo-analysis")

    assert len(payload["evidence"]) == 10
    serialized = json.dumps(payload)
    assert str(tmp_path) not in serialized
    assert "session_key" not in serialized
    assert "chat_id" not in serialized
    assert "token=secret" not in serialized
    assert payload["evidence"][1]["tool_errors"] == 1


async def test_authentication_invalid_header_and_disabled_actions(tmp_path) -> None:
    _write_skill(tmp_path)
    unauthorized = _controller(tmp_path, service=None, authorized=False)
    denied = await unauthorized.dispatch(Request({}), "/api/webui/evolution")
    assert denied.status_code == 401

    controller = _controller(tmp_path, service=None)
    malformed = await controller.dispatch(
        Request({"X-Nanobot-Evolution-Values": "%7Bbroken"}),
        "/api/webui/evolution/config/update",
    )
    assert malformed.status_code == 400

    unavailable = await controller.dispatch(
        Request({}),
        "/api/webui/evolution/skills/repo-analysis/review",
    )
    assert unavailable.status_code == 503
    assert unavailable.payload["error"]["retryable"] is True


async def test_config_update_persists_but_requires_gateway_restart(tmp_path) -> None:
    _write_skill(tmp_path)
    config = Config.model_validate(
        {
            "modelPresets": {
                "review": {
                    "provider": "custom",
                    "model": "review-model",
                }
            }
        }
    )
    saved: list[Config] = []
    controller = _controller(tmp_path, service=None, config=config, saved=saved)
    values = quote(
        json.dumps(
            {
                "enabled": True,
                "review_every_n_trajectories": 20,
                "review_model_preset": "review",
            }
        ),
        safe="",
    )

    response = await controller.dispatch(
        Request({"X-Nanobot-Evolution-Values": values}),
        "/api/webui/evolution/config/update",
    )

    assert response.status_code == 200
    assert response.payload["enabled"] is True
    assert response.payload["runtime_active"] is False
    assert response.payload["restart_required"] is True
    assert response.payload["review_every_n_trajectories"] == 20
    assert saved == [config]
    assert config.evolution.review_every_n_trajectories == 20
    assert config.evolution.review_model_preset == "review"


async def test_config_update_applies_review_interval_to_active_runtime(tmp_path) -> None:
    _write_skill(tmp_path)
    service, _ = _service(tmp_path)
    config = Config.model_validate(
        {
            "evolution": {
                "enabled": True,
                "reviewEveryNTrajectories": 10,
            }
        }
    )
    controller = _controller(tmp_path, service=service, config=config)
    values = quote(
        json.dumps({"review_every_n_trajectories": 5}),
        safe="",
    )

    response = await controller.dispatch(
        Request({"X-Nanobot-Evolution-Values": values}),
        "/api/webui/evolution/config/update",
    )

    assert response.status_code == 200
    assert response.payload["review_every_n_trajectories"] == 5
    assert response.payload["restart_required"] is False
    assert service.review_every_n_trajectories == 5


async def test_review_uses_service_and_builtin_review_is_rejected(tmp_path) -> None:
    path, original = _write_skill(tmp_path)
    service, scheduler = _service(tmp_path)
    service.store.append_trajectory(_trajectory(1, tmp_path))
    controller = _controller(tmp_path, service=service)
    feedback = quote(json.dumps({"feedback": "Check repository-root paths"}), safe="")

    response = await controller.dispatch(
        Request({"X-Nanobot-Evolution-Values": feedback}),
        "/api/webui/evolution/skills/repo-analysis/review",
    )

    assert response.status_code == 200
    assert response.payload["state"] == "reviewing"
    assert scheduler.count == 1
    assert path.read_text(encoding="utf-8") == original

    builtin_name = next(
        item["name"]
        for item in controller.overview_payload()["skills"]
        if item["source"] == "builtin"
    )
    rejected = await controller.dispatch(
        Request({}),
        f"/api/webui/evolution/skills/{quote(builtin_name, safe='')}/review",
    )
    assert rejected.status_code == 422


async def test_review_without_feedback_or_periodic_threshold_is_rejected(tmp_path) -> None:
    _write_skill(tmp_path)
    service, scheduler = _service(tmp_path)
    await service.record_trajectory(_trajectory(1, tmp_path))
    controller = _controller(tmp_path, service=service)

    response = await controller.dispatch(
        Request({}),
        "/api/webui/evolution/skills/repo-analysis/review",
    )

    assert response.status_code == 409
    assert "requires user feedback" in response.payload["error"]["message"]
    assert scheduler.count == 0


def test_detail_exposes_latest_failed_review_reason(tmp_path) -> None:
    _write_skill(tmp_path)
    service, _ = _service(tmp_path)
    request = _review_request()
    service.store.save_review(
        request.review_id,
        {
            "review_id": request.review_id,
            "request": request.to_dict(),
            "status": "completed",
            "decision": "failed",
            "error": "Provider returned an invalid response",
            "completed_at": "2026-07-26T00:02:00Z",
        },
    )

    detail = _controller(tmp_path, service=service).skill_detail_payload("repo-analysis")

    assert detail["latest_review"] == {
        "review_id": request.review_id,
        "status": "completed",
        "trigger": "periodic",
        "decision": "failed",
        "reason": "Provider returned an invalid response",
        "requested_at": "2026-07-26T00:01:00Z",
        "completed_at": "2026-07-26T00:02:00Z",
    }


async def test_approve_version_compare_switch_reject_and_conflict_use_existing_service(tmp_path) -> None:
    path, original = _write_skill(tmp_path)
    service, _ = _service(tmp_path)
    trajectories = [_trajectory(1, tmp_path), _trajectory(2, tmp_path)]
    for trajectory in trajectories:
        service.store.append_trajectory(trajectory)
    request = _review_request()
    service.store.save_review("rv_1", {"request": request.to_dict()})
    service.store.save_proposal(_proposal(original))
    controller = _controller(tmp_path, service=service)

    approved = await controller.dispatch(
        Request({}),
        "/api/webui/evolution/proposals/pr_1/approve",
    )

    assert approved.status_code == 200
    assert approved.payload["status"] == "applied"
    assert approved.payload["backup_created"] is True
    assert "pyproject.toml" in path.read_text(encoding="utf-8")
    detail = controller.skill_detail_payload("repo-analysis")
    assert detail["versions"][0]["is_current"] is True
    assert len(detail["versions"]) == 2
    original_hash = content_hash(original)
    evolved_hash = content_hash(path.read_text(encoding="utf-8"))

    compared = await controller.dispatch(
        Request(
            {
                "X-Nanobot-Evolution-Values": quote(
                    json.dumps(
                        {
                            "base_hash": original_hash,
                            "target_hash": evolved_hash,
                        }
                    ),
                    safe="",
                )
            }
        ),
        "/api/webui/evolution/skills/repo-analysis/versions/compare",
    )
    assert compared.status_code == 200
    assert "-1. Inspect source files." in compared.payload["diff"]
    assert "+1. Inspect pyproject.toml before source files." in compared.payload["diff"]

    switched = await controller.dispatch(
        Request(
            {
                "X-Nanobot-Evolution-Values": quote(
                    json.dumps({"content_hash": original_hash}),
                    safe="",
                )
            }
        ),
        "/api/webui/evolution/skills/repo-analysis/versions/switch",
    )
    assert switched.status_code == 200
    assert switched.payload["status"] == "switched"
    assert path.read_text(encoding="utf-8") == original

    service.store.save_proposal(_proposal(original, proposal_id="pr_reject"))
    rejected = await controller.dispatch(
        Request({}),
        "/api/webui/evolution/proposals/pr_reject/reject",
    )
    assert rejected.status_code == 200
    assert rejected.payload["status"] == "rejected"

    service.store.save_proposal(_proposal(original, proposal_id="pr_conflict"))
    path.write_text(original + "\nUser edit.\n", encoding="utf-8")
    conflict = await controller.dispatch(
        Request({}),
        "/api/webui/evolution/proposals/pr_conflict/approve",
    )
    assert conflict.status_code == 409
    assert conflict.payload["error"]["code"] == "evolution_base_hash_conflict"
    assert path.read_text(encoding="utf-8").endswith("User edit.\n")
