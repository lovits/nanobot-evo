"""Authenticated WebUI facade for the NanoEvo control plane."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from difflib import unified_diff
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from nanobot.config.loader import load_config, save_config
from nanobot.evolution.constants import (
    REVIEW_EVERY_N_TRAJECTORIES,
    REVIEW_INTERVAL_OPTIONS,
)
from nanobot.evolution.models import (
    ProposalStatus,
    ReviewRequest,
    SkillProposal,
    SkillTrajectory,
)
from nanobot.evolution.patching import content_hash
from nanobot.evolution.policy import PolicyViolationError
from nanobot.evolution.redaction import redact_text, truncate_text
from nanobot.evolution.store import EvolutionStore
from nanobot.webui.http_utils import case_insensitive_header
from nanobot.webui.skills_api import webui_skills_payload

if TYPE_CHECKING:
    from nanobot.evolution.service import SkillEvolutionService

_VALUES_HEADER = "X-Nanobot-Evolution-Values"
_VALUES_HEADER_MAX_BYTES = 8 * 1024
_EVIDENCE_LIMIT = 10
_TASK_EXCERPT_CHARS = 300
_ABSOLUTE_PATH = re.compile(
    r"(?<![\w.-])(?:/[^\s`'\"<>]+)+|(?<![\w.-])[A-Za-z]:[\\/][^\s`'\"<>]+"
)

JsonResponse = Callable[..., Any]
ConfigLoader = Callable[[], Any]
ConfigSaver = Callable[[Any], None]


class EvolutionWebUIController:
    """Map authenticated HTTP requests onto the existing evolution service."""

    def __init__(
        self,
        *,
        workspace: Path,
        service: SkillEvolutionService | None,
        disabled_skills: set[str] | None,
        check_api_token: Callable[[Any], bool],
        json_response: JsonResponse,
        load_config_fn: ConfigLoader = load_config,
        save_config_fn: ConfigSaver = save_config,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.service = service
        self.disabled_skills = set(disabled_skills or ())
        self._check_api_token = check_api_token
        self._json_response = json_response
        self._load_config = load_config_fn
        self._save_config = save_config_fn

    async def dispatch(self, request: Any, path: str) -> Any | None:
        if not path.startswith("/api/webui/evolution"):
            return None
        if not self._check_api_token(request):
            return self._error(401, "unauthorized", "Unauthorized")

        try:
            return await self._dispatch_authenticated(request, path)
        except EvolutionUnavailableError as exc:
            return self._error(503, "evolution_unavailable", str(exc), retryable=True)
        except PolicyViolationError as exc:
            return self._error(422, "evolution_policy_violation", str(exc))
        except KeyError as exc:
            message = str(exc).strip("'")
            status = 409 if message.startswith("No persisted trajectory") else 404
            code = "evolution_state_conflict" if status == 409 else "evolution_not_found"
            return self._error(status, code, message)
        except (json.JSONDecodeError, TypeError) as exc:
            return self._error(400, "invalid_evolution_values", str(exc))
        except ValueError as exc:
            return self._error(409, "evolution_state_conflict", str(exc))

    async def _dispatch_authenticated(self, request: Any, path: str) -> Any:
        if path == "/api/webui/evolution":
            return self._json_response(self.overview_payload())
        if path == "/api/webui/evolution/config/update":
            return self._handle_config_update(request)

        proposal_match = re.fullmatch(
            r"/api/webui/evolution/proposals/([^/]+)/(approve|reject)",
            path,
        )
        if proposal_match:
            return self._handle_proposal_action(
                unquote(proposal_match.group(1)),
                proposal_match.group(2),
            )

        skill_action = re.fullmatch(
            r"/api/webui/evolution/skills/([^/]+)/versions/(compare|switch)",
            path,
        )
        if skill_action:
            name = _decode_name(skill_action.group(1))
            if skill_action.group(2) == "compare":
                return self._handle_version_compare(request, name)
            return self._handle_version_switch(request, name)

        skill_action = re.fullmatch(
            r"/api/webui/evolution/skills/([^/]+)/(review|restore)",
            path,
        )
        if skill_action:
            name = _decode_name(skill_action.group(1))
            if skill_action.group(2) == "review":
                return await self._handle_review(request, name)
            return self._handle_restore(name)

        skill_detail = re.fullmatch(r"/api/webui/evolution/skills/([^/]+)", path)
        if skill_detail:
            return self._json_response(self.skill_detail_payload(_decode_name(skill_detail.group(1))))
        return self._error(404, "evolution_route_not_found", "Evolution route not found")

    def overview_payload(self) -> dict[str, Any]:
        config = self._load_config()
        review_threshold = config.evolution.review_every_n_trajectories
        store = self._read_store()
        proposals = store.list_proposals() if store is not None else []
        skills = [
            self._skill_summary(
                entry,
                store=store,
                proposals=proposals,
                review_threshold=review_threshold,
            )
            for entry in self._skill_entries()
        ]
        return {
            "schema_version": 1,
            **self._runtime_payload(config),
            "review_every_n_trajectories": review_threshold,
            "review_interval_options": list(REVIEW_INTERVAL_OPTIONS),
            "review_model_preset": config.evolution.review_model_preset,
            "review_model_presets": sorted(config.model_presets),
            "summary": {
                "total": len(skills),
                "evolvable": sum(bool(skill["evolvable"]) for skill in skills),
                "protected": sum(not bool(skill["evolvable"]) for skill in skills),
                "reviewing": sum(bool(skill["review_running"]) for skill in skills),
                "pending_proposals": sum(
                    int(skill["pending_proposal_count"]) for skill in skills
                ),
            },
            "skills": skills,
        }

    def skill_detail_payload(self, name: str) -> dict[str, Any]:
        entry = next((item for item in self._skill_entries() if item["name"] == name), None)
        if entry is None:
            raise KeyError(f"Unknown Skill: {name}")

        store = self._read_store()
        review_threshold = self._load_config().evolution.review_every_n_trajectories
        proposals = store.list_proposals() if store is not None else []
        skill = self._skill_summary(
            entry,
            store=store,
            proposals=proposals,
            review_threshold=review_threshold,
        )
        if entry.get("source") != "workspace" or store is None:
            return {
                "skill": {**skill, "backup_available": False},
                "evidence": [],
                "latest_review": None,
                "pending_proposal": None,
                "versions": [],
            }

        trajectories = store.list_trajectories(skill_name=name, limit=_EVIDENCE_LIMIT)
        pending = next(
            (
                proposal
                for proposal in reversed(proposals)
                if proposal.skill_name == name and proposal.status is ProposalStatus.PENDING
            ),
            None,
        )
        versions = store.list_skill_versions(name)
        current_hash = self._current_version_hash(name)
        version_payloads = [
            {
                "content_hash": current_hash,
                "proposal_id": "current",
                "created_at": "",
                "is_current": True,
            }
        ] if current_hash else []
        seen = {current_hash} if current_hash else set()
        for version in reversed(versions):
            if version.content_hash in seen:
                continue
            seen.add(version.content_hash)
            version_payloads.append(
                {
                    "content_hash": version.content_hash,
                    "proposal_id": version.proposal_id,
                    "created_at": version.created_at,
                    "is_current": False,
                }
            )
        return {
            "skill": {
                **skill,
                "backup_available": bool(versions),
            },
            "evidence": [self._trajectory_payload(item) for item in reversed(trajectories)],
            "latest_review": self._latest_review_payload(store, name),
            "pending_proposal": (
                self._proposal_payload(pending, store) if pending is not None else None
            ),
            "versions": version_payloads,
        }

    @staticmethod
    def _latest_review_payload(
        store: EvolutionStore,
        skill_name: str,
    ) -> dict[str, Any] | None:
        reviews = store.list_reviews(skill_name=skill_name)
        if not reviews:
            return None
        review = reviews[-1]
        request = review.get("request")
        request = request if isinstance(request, Mapping) else {}
        decision = review.get("decision")
        error = review.get("error")
        reason = str(error).strip() if error else ""
        return {
            "review_id": str(review.get("review_id") or request.get("review_id") or ""),
            "status": str(review.get("status") or "unknown"),
            "trigger": str(request.get("trigger") or "manual"),
            "decision": str(decision) if decision is not None else None,
            "reason": reason or None,
            "requested_at": str(request.get("requested_at") or ""),
            "completed_at": (
                str(review["completed_at"]) if review.get("completed_at") is not None else None
            ),
        }

    def _skill_summary(
        self,
        entry: Mapping[str, Any],
        *,
        store: EvolutionStore | None,
        proposals: list[SkillProposal],
        review_threshold: int = REVIEW_EVERY_N_TRAJECTORIES,
    ) -> dict[str, Any]:
        name = str(entry["name"])
        evolvable = entry.get("source") == "workspace"
        state = store.load_state().skills.get(name) if store is not None else None
        trajectories = (
            store.list_trajectories(skill_name=name, limit=_EVIDENCE_LIMIT)
            if store is not None and evolvable
            else []
        )
        skill_proposals = [item for item in proposals if item.skill_name == name]
        pending_count = sum(item.status is ProposalStatus.PENDING for item in skill_proposals)
        progress = (
            max(0, state.trajectory_count - state.last_reviewed_count)
            if state is not None
            else len(trajectories)
        )
        latest = skill_proposals[-1] if skill_proposals else None
        return {
            "name": name,
            "description": str(entry.get("description") or name),
            "source": str(entry.get("source") or "unknown"),
            "available": bool(entry.get("available")),
            "evolvable": evolvable,
            "protection_reason": (
                None
                if evolvable
                else "NanoEvo V1 only modifies existing Workspace Skills"
            ),
            "state": self._display_state(
                evolvable=evolvable,
                available=bool(entry.get("available")),
                reviewing=bool(state and state.review_running),
                pending_count=pending_count,
                latest=latest,
            ),
            "trajectory_count": progress,
            "review_threshold": review_threshold,
            "remaining_trajectories": max(0, review_threshold - progress),
            "review_running": bool(state and state.review_running),
            "last_reviewed_at": state.last_reviewed_at if state is not None else None,
            "last_decision": (
                state.last_decision.value if state is not None and state.last_decision else None
            ),
            "pending_proposal_count": pending_count,
            "current_version": self._current_version(name) if evolvable else None,
        }

    def _trajectory_payload(self, trajectory: SkillTrajectory) -> dict[str, Any]:
        task = redact_text(trajectory.task, _TASK_EXCERPT_CHARS)
        task = task.replace(str(self.workspace), "[WORKSPACE]")
        task = _ABSOLUTE_PATH.sub("[PATH]", task)
        return {
            "trace_id": trajectory.trace_id,
            "created_at": trajectory.created_at,
            "turn_id": trajectory.turn_id,
            "project_scope_hash": trajectory.project_scope_hash,
            "task_excerpt": truncate_text(task, _TASK_EXCERPT_CHARS),
            "tool_calls": len(trajectory.tool_events),
            "tool_errors": sum(event.status.value == "error" for event in trajectory.tool_events),
            "iterations": trajectory.iterations,
            "objective_failure": trajectory.objective_failure,
            "stop_reason": trajectory.stop_reason,
        }

    def _proposal_payload(
        self,
        proposal: SkillProposal,
        store: EvolutionStore,
    ) -> dict[str, Any]:
        evidence = store.trajectories_by_id(proposal.evidence_trace_ids)
        review_request = self._review_request(proposal, store)
        eligible = False
        if review_request is not None:
            try:
                self._policy().validate_evidence(
                    proposal.skill_name,
                    evidence,
                    review_request,
                )
            except PolicyViolationError:
                pass
            else:
                eligible = True
        return {
            "proposal_id": proposal.proposal_id,
            "skill_name": proposal.skill_name,
            "reason": proposal.reason,
            "status": proposal.status.value,
            "created_at": proposal.created_at,
            "base_hash": proposal.base_hash,
            "evidence_trace_ids": list(proposal.evidence_trace_ids),
            "patch": proposal.patch.to_dict(),
            "evidence_gates": {
                "trace_count": len(evidence),
                "eligible": eligible,
            },
        }

    async def _handle_review(self, request: Any, name: str) -> Any:
        service = self._require_service()
        values = self._values(request, required=False)
        feedback = values.get("feedback")
        if feedback is not None and not isinstance(feedback, str):
            raise TypeError("feedback must be a string")
        review = await service.request_review(
            skill_name=name,
            source_channel="webui",
            source_chat_id="skill-evolution",
            user_feedback=feedback,
        )
        return self._json_response(
            {"ok": True, "review_id": review.review_id, "state": "reviewing"}
        )

    def _handle_proposal_action(self, proposal_id: str, action: str) -> Any:
        if not proposal_id or "/" in proposal_id or "\\" in proposal_id:
            raise KeyError("Unknown Proposal")
        service = self._require_service()
        proposal = (
            service.approve_proposal(proposal_id)
            if action == "approve"
            else service.reject_proposal(proposal_id)
        )
        if proposal.status is ProposalStatus.CONFLICT:
            return self._error(
                409,
                "evolution_base_hash_conflict",
                proposal.validation_error or "SKILL.md changed after proposal creation",
            )
        if proposal.status is ProposalStatus.INVALID:
            return self._error(
                422,
                "evolution_policy_violation",
                proposal.validation_error or "Proposal failed validation",
            )
        return self._json_response(
            {
                "ok": True,
                "proposal_id": proposal.proposal_id,
                "status": proposal.status.value,
                "backup_created": proposal.status is ProposalStatus.APPLIED,
            }
        )

    def _handle_restore(self, name: str) -> Any:
        proposal = self._require_service().restore_skill(name)
        return self._json_response(
            {
                "ok": True,
                "proposal_id": proposal.proposal_id,
                "status": proposal.status.value,
            }
        )

    def _handle_version_compare(self, request: Any, name: str) -> Any:
        values = self._values(request, required=True)
        base_hash = self._version_hash(values, "base_hash")
        target_hash = self._version_hash(values, "target_hash")
        store = self._read_store()
        if store is None:
            raise KeyError(f"No Skill versions available for: {name}")
        base = self._version_content(store, name, base_hash)
        target = self._version_content(store, name, target_hash)
        diff = "".join(
            unified_diff(
                base.splitlines(keepends=True),
                target.splitlines(keepends=True),
                fromfile=base_hash[:12],
                tofile=target_hash[:12],
            )
        )
        return self._json_response(
            {
                "base_hash": base_hash,
                "target_hash": target_hash,
                "diff": diff,
            }
        )

    def _handle_version_switch(self, request: Any, name: str) -> Any:
        values = self._values(request, required=True)
        target_hash = self._version_hash(values, "content_hash")
        selected = self._require_service().switch_skill_version(name, target_hash)
        return self._json_response(
            {
                "ok": True,
                "status": "switched",
                "content_hash": selected,
            }
        )

    def _handle_config_update(self, request: Any) -> Any:
        values = self._values(request, required=True)
        unknown = set(values) - {
            "enabled",
            "review_every_n_trajectories",
            "review_model_preset",
        }
        if unknown:
            raise TypeError(f"unknown evolution field: {sorted(unknown)[0]}")
        if not values:
            raise TypeError("evolution values must not be empty")

        config = self._load_config()
        if "enabled" in values:
            if not isinstance(values["enabled"], bool):
                raise TypeError("enabled must be a boolean")
            config.evolution.enabled = values["enabled"]
        if "review_every_n_trajectories" in values:
            threshold = values["review_every_n_trajectories"]
            if (
                not isinstance(threshold, int)
                or isinstance(threshold, bool)
                or threshold not in REVIEW_INTERVAL_OPTIONS
            ):
                choices = ", ".join(str(value) for value in REVIEW_INTERVAL_OPTIONS)
                raise TypeError(
                    f"review_every_n_trajectories must be one of: {choices}"
                )
            config.evolution.review_every_n_trajectories = threshold
        if "review_model_preset" in values:
            preset = values["review_model_preset"]
            if preset is not None and not isinstance(preset, str):
                raise TypeError("review_model_preset must be a string or null")
            preset = preset.strip() if isinstance(preset, str) else None
            if preset and preset not in config.model_presets:
                raise TypeError(f"unknown review model preset: {preset}")
            config.evolution.review_model_preset = preset or None
        self._save_config(config)
        if self.service is not None:
            self.service.review_every_n_trajectories = (
                config.evolution.review_every_n_trajectories
            )
        return self._json_response(
            {
                "ok": True,
                **self._runtime_payload(config),
                "review_every_n_trajectories": (
                    config.evolution.review_every_n_trajectories
                ),
                "review_model_preset": config.evolution.review_model_preset,
            }
        )

    def _runtime_payload(self, config: Any) -> dict[str, bool]:
        runtime_active = self.service is not None
        configured_preset = config.evolution.review_model_preset
        runtime_preset = (
            getattr(self.service, "review_model_preset", None)
            if self.service is not None
            else None
        )
        restart_required = config.evolution.enabled != runtime_active
        if runtime_active and configured_preset != runtime_preset:
            restart_required = True
        configured_threshold = config.evolution.review_every_n_trajectories
        runtime_threshold = (
            getattr(self.service, "review_every_n_trajectories", None)
            if self.service is not None
            else None
        )
        if runtime_active and configured_threshold != runtime_threshold:
            restart_required = True
        return {
            "enabled": bool(config.evolution.enabled),
            "runtime_active": runtime_active,
            "restart_required": restart_required,
        }

    def _skill_entries(self) -> list[dict[str, Any]]:
        payload = webui_skills_payload(
            self.workspace,
            disabled_skills=self.disabled_skills,
        )
        return list(payload["skills"])

    def _read_store(self) -> EvolutionStore | None:
        if self.service is not None:
            return self.service.store
        root = self.workspace / ".nanobot" / "evolution"
        return EvolutionStore(self.workspace) if root.is_dir() else None

    def _policy(self) -> Any:
        if self.service is not None:
            return self.service.policy
        from nanobot.evolution.policy import PatchPolicy

        return PatchPolicy(self.workspace)

    def _current_version(self, skill_name: str) -> str | None:
        current = self._current_version_hash(skill_name)
        return current[:8] if current else None

    def _current_version_hash(self, skill_name: str) -> str | None:
        try:
            reference = self._policy().validate_target(skill_name)
            return content_hash(reference.path.read_text(encoding="utf-8"))
        except (OSError, PolicyViolationError):
            return None

    def _version_content(
        self,
        store: EvolutionStore,
        skill_name: str,
        version_hash: str,
    ) -> str:
        reference = self._policy().validate_target(skill_name)
        current = reference.path.read_text(encoding="utf-8")
        if content_hash(current) == version_hash:
            return current
        record = next(
            (
                item
                for item in reversed(store.list_skill_versions(skill_name))
                if item.content_hash == version_hash
            ),
            None,
        )
        if record is None:
            raise KeyError(f"Unknown Skill version: {version_hash}")
        return store.load_skill_version_content(record)

    @staticmethod
    def _version_hash(values: Mapping[str, Any], field: str) -> str:
        value = values.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise TypeError(f"{field} must be a full SHA-256 hash")
        return value

    @staticmethod
    def _review_request(
        proposal: SkillProposal,
        store: EvolutionStore,
    ) -> ReviewRequest | None:
        if proposal.review_id is None:
            return None
        review = store.load_review(proposal.review_id)
        request = review.get("request") if isinstance(review, Mapping) else None
        return ReviewRequest.from_dict(request) if isinstance(request, Mapping) else None

    @staticmethod
    def _display_state(
        *,
        evolvable: bool,
        available: bool,
        reviewing: bool,
        pending_count: int,
        latest: SkillProposal | None,
    ) -> str:
        if not evolvable:
            return "protected"
        if not available:
            return "unavailable"
        if latest is not None and latest.status is ProposalStatus.CONFLICT:
            return "conflict"
        if pending_count:
            return "proposal_pending"
        if reviewing:
            return "reviewing"
        if latest is not None and latest.status is ProposalStatus.APPLIED:
            return "updated"
        return "collecting"

    def _require_service(self) -> SkillEvolutionService:
        if self.service is None:
            raise EvolutionUnavailableError("NanoEvo is not active; save config and restart Gateway")
        return self.service

    def _values(self, request: Any, *, required: bool) -> dict[str, Any]:
        raw = case_insensitive_header(getattr(request, "headers", {}), _VALUES_HEADER)
        if not raw:
            if required:
                raise TypeError(f"missing {_VALUES_HEADER}")
            return {}
        if len(raw.encode("utf-8")) > _VALUES_HEADER_MAX_BYTES:
            raise TypeError("evolution values header is too large")
        decoded = json.loads(unquote(raw))
        if not isinstance(decoded, dict):
            raise TypeError("evolution values must be a JSON object")
        return dict(decoded)

    def _error(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> Any:
        return self._json_response(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                }
            },
            status=status,
        )


class EvolutionUnavailableError(RuntimeError):
    """The Gateway was started without an active evolution service."""


def _decode_name(raw_name: str) -> str:
    name = unquote(raw_name).strip()
    if not name or "/" in name or "\\" in name:
        raise KeyError("Unknown Skill")
    return name


__all__ = ["EvolutionWebUIController"]
