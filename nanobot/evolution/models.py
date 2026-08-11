"""Serializable immutable data transfer objects for NanoEvo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from os import path as os_path
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION, PROJECT_SCOPE_HASH_LENGTH


class ToolEventStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class ReviewTrigger(StrEnum):
    PERIODIC = "periodic"
    OBJECTIVE_FAILURE = "objective_failure"
    MANUAL = "manual"


class ReviewDecision(StrEnum):
    NO_CHANGE = "no_change"
    PROPOSE_PATCH = "propose_patch"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    INVALID = "invalid"
    CONFLICT = "conflict"
    RESTORED = "restored"


def utc_now() -> str:
    """Return a UTC ISO-8601 timestamp suitable for JSON persistence."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Return an opaque, namespaced identifier without embedding user data."""
    return f"{prefix}{uuid4().hex}"


def new_trace_id() -> str:
    return new_id("tr_")


def new_review_id() -> str:
    return new_id("rv_")


def new_proposal_id() -> str:
    return new_id("pr_")


def project_scope_hash(workspace: str | Path | None) -> str | None:
    """Return a stable, non-reversible workspace fingerprint.

    The normalized path exists only in this function's local scope. Callers
    receive the truncated SHA-256 digest and must never persist the raw path.
    """
    if workspace is None:
        return None
    raw = str(workspace).strip()
    if not raw:
        return None
    normalized = os_path.normcase(str(Path(raw).expanduser().resolve(strict=False)))
    return sha256(normalized.encode("utf-8")).hexdigest()[:PROJECT_SCOPE_HASH_LENGTH]


def _optional_text(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    return None if value is None else str(value)


@dataclass(frozen=True, slots=True)
class EvolutionToolEvent:
    call_id: str
    name: str
    params: dict[str, Any]
    status: ToolEventStatus
    result_excerpt: str | None
    error: str | None
    iteration: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "params": self.params,
            "status": self.status.value,
            "result_excerpt": self.result_excerpt,
            "error": self.error,
            "iteration": self.iteration,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvolutionToolEvent:
        params = data.get("params")
        return cls(
            call_id=str(data["call_id"]),
            name=str(data["name"]),
            params=dict(params) if isinstance(params, Mapping) else {},
            status=ToolEventStatus(str(data["status"])),
            result_excerpt=_optional_text(data, "result_excerpt"),
            error=_optional_text(data, "error"),
            iteration=int(data["iteration"]),
        )


@dataclass(frozen=True, slots=True)
class SkillTrajectory:
    schema_version: int
    trace_id: str
    created_at: str
    turn_id: str
    session_key: str | None
    channel: str
    chat_id: str
    task: str
    used_skills: tuple[str, ...]
    tool_events: tuple[EvolutionToolEvent, ...]
    final_response_excerpt: str | None
    stop_reason: str | None
    error: str | None
    iterations: int
    prompt_tokens: int
    completion_tokens: int
    objective_failure: bool
    project_scope_hash: str | None

    def __post_init__(self) -> None:
        """Canonicalize attribution so persisted evidence is deterministic."""
        object.__setattr__(self, "used_skills", tuple(sorted(set(self.used_skills))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "created_at": self.created_at,
            "turn_id": self.turn_id,
            "session_key": self.session_key,
            "channel": self.channel,
            "chat_id": self.chat_id,
            "task": self.task,
            "used_skills": list(self.used_skills),
            "tool_events": [event.to_dict() for event in self.tool_events],
            "final_response_excerpt": self.final_response_excerpt,
            "stop_reason": self.stop_reason,
            "error": self.error,
            "iterations": self.iterations,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "objective_failure": self.objective_failure,
            "project_scope_hash": self.project_scope_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SkillTrajectory:
        events = data.get("tool_events")
        skills = data.get("used_skills")
        return cls(
            schema_version=int(data.get("schema_version", EVOLUTION_SCHEMA_VERSION)),
            trace_id=str(data["trace_id"]),
            created_at=str(data["created_at"]),
            turn_id=str(data["turn_id"]),
            session_key=_optional_text(data, "session_key"),
            channel=str(data["channel"]),
            chat_id=str(data["chat_id"]),
            task=str(data["task"]),
            used_skills=tuple(str(skill) for skill in skills)
            if isinstance(skills, list | tuple)
            else (),
            tool_events=(
                tuple(
                    EvolutionToolEvent.from_dict(event)
                    for event in events
                    if isinstance(event, Mapping)
                )
                if isinstance(events, list | tuple)
                else ()
            ),
            final_response_excerpt=_optional_text(data, "final_response_excerpt"),
            stop_reason=_optional_text(data, "stop_reason"),
            error=_optional_text(data, "error"),
            iterations=int(data["iterations"]),
            prompt_tokens=int(data["prompt_tokens"]),
            completion_tokens=int(data["completion_tokens"]),
            objective_failure=bool(data["objective_failure"]),
            project_scope_hash=_optional_text(data, "project_scope_hash"),
        )


@dataclass(frozen=True, slots=True)
class ReviewRequest:
    review_id: str
    skill_name: str
    trigger: ReviewTrigger
    trajectory_ids: tuple[str, ...]
    user_feedback: str | None
    source_channel: str
    source_chat_id: str
    requested_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "skill_name": self.skill_name,
            "trigger": self.trigger.value,
            "trajectory_ids": list(self.trajectory_ids),
            "user_feedback": self.user_feedback,
            "source_channel": self.source_channel,
            "source_chat_id": self.source_chat_id,
            "requested_at": self.requested_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReviewRequest:
        ids = data.get("trajectory_ids")
        return cls(
            review_id=str(data["review_id"]),
            skill_name=str(data["skill_name"]),
            trigger=ReviewTrigger(str(data["trigger"])),
            trajectory_ids=tuple(str(item) for item in ids)
            if isinstance(ids, list | tuple)
            else (),
            user_feedback=_optional_text(data, "user_feedback"),
            source_channel=str(data["source_channel"]),
            source_chat_id=str(data["source_chat_id"]),
            requested_at=str(data["requested_at"]),
        )


@dataclass(frozen=True, slots=True)
class SkillPatch:
    old_text: str
    new_text: str

    def to_dict(self) -> dict[str, Any]:
        return {"old_text": self.old_text, "new_text": self.new_text}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SkillPatch:
        return cls(old_text=str(data["old_text"]), new_text=str(data["new_text"]))


@dataclass(frozen=True, slots=True)
class SkillProposal:
    schema_version: int
    proposal_id: str
    review_id: str | None
    skill_name: str
    base_hash: str
    evidence_trace_ids: tuple[str, ...]
    reason: str
    patch: SkillPatch
    status: ProposalStatus
    created_at: str
    decided_at: str | None
    applied_at: str | None
    restored_at: str | None
    validation_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "review_id": self.review_id,
            "skill_name": self.skill_name,
            "base_hash": self.base_hash,
            "evidence_trace_ids": list(self.evidence_trace_ids),
            "reason": self.reason,
            "patch": self.patch.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "applied_at": self.applied_at,
            "restored_at": self.restored_at,
            "validation_error": self.validation_error,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SkillProposal:
        evidence = data.get("evidence_trace_ids")
        patch = data.get("patch")
        return cls(
            schema_version=int(data.get("schema_version", EVOLUTION_SCHEMA_VERSION)),
            proposal_id=str(data["proposal_id"]),
            review_id=_optional_text(data, "review_id"),
            skill_name=str(data["skill_name"]),
            base_hash=str(data["base_hash"]),
            evidence_trace_ids=(
                tuple(str(item) for item in evidence) if isinstance(evidence, list | tuple) else ()
            ),
            reason=str(data["reason"]),
            patch=SkillPatch.from_dict(patch) if isinstance(patch, Mapping) else SkillPatch("", ""),
            status=ProposalStatus(str(data["status"])),
            created_at=str(data["created_at"]),
            decided_at=_optional_text(data, "decided_at"),
            applied_at=_optional_text(data, "applied_at"),
            restored_at=_optional_text(data, "restored_at"),
            validation_error=_optional_text(data, "validation_error"),
        )


@dataclass(frozen=True, slots=True)
class SkillReviewState:
    skill_name: str
    trajectory_count: int
    last_reviewed_count: int
    review_running: bool
    review_pending: bool
    active_review_id: str | None
    last_reviewed_at: str | None
    last_decision: ReviewDecision | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "trajectory_count": self.trajectory_count,
            "last_reviewed_count": self.last_reviewed_count,
            "review_running": self.review_running,
            "review_pending": self.review_pending,
            "active_review_id": self.active_review_id,
            "last_reviewed_at": self.last_reviewed_at,
            "last_decision": self.last_decision.value if self.last_decision else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SkillReviewState:
        decision = data.get("last_decision")
        return cls(
            skill_name=str(data["skill_name"]),
            trajectory_count=int(data["trajectory_count"]),
            last_reviewed_count=int(data["last_reviewed_count"]),
            review_running=bool(data["review_running"]),
            review_pending=bool(data["review_pending"]),
            active_review_id=_optional_text(data, "active_review_id"),
            last_reviewed_at=_optional_text(data, "last_reviewed_at"),
            last_decision=ReviewDecision(str(decision)) if decision is not None else None,
        )


@dataclass(frozen=True, slots=True)
class EvolutionState:
    schema_version: int
    skills: dict[str, SkillReviewState]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "skills": {name: state.to_dict() for name, state in self.skills.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvolutionState:
        raw_skills = data.get("skills")
        skills = (
            {
                str(name): SkillReviewState.from_dict(state)
                for name, state in raw_skills.items()
                if isinstance(state, Mapping)
            }
            if isinstance(raw_skills, Mapping)
            else {}
        )
        return cls(
            schema_version=int(data.get("schema_version", EVOLUTION_SCHEMA_VERSION)), skills=skills
        )


@dataclass(frozen=True, slots=True)
class SkillVersionRecord:
    skill_name: str
    content_hash: str
    proposal_id: str
    created_at: str
    content_file: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "content_hash": self.content_hash,
            "proposal_id": self.proposal_id,
            "created_at": self.created_at,
            "content_file": self.content_file,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SkillVersionRecord:
        return cls(
            skill_name=str(data["skill_name"]),
            content_hash=str(data["content_hash"]),
            proposal_id=str(data["proposal_id"]),
            created_at=str(data["created_at"]),
            content_file=str(data["content_file"]),
        )
