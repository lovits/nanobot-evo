"""Durable local persistence for NanoEvo evidence and control state."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from loguru import logger

from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import (
    EvolutionState,
    ProposalStatus,
    SkillProposal,
    SkillTrajectory,
    SkillVersionRecord,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, Mapping) else None


def atomic_write_text(path: Path, content: str) -> None:
    """Write one file durably without exposing a partially written target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


class EvolutionStore:
    """Filesystem store rooted under ``<workspace>/.nanobot/evolution``."""

    def __init__(self, workspace: Path | str) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.root = self.workspace / ".nanobot" / "evolution"
        self.trajectories_file = self.root / "trajectories.jsonl"
        self.state_file = self.root / "state.json"
        self.proposals_dir = self.root / "proposals"
        self.reviews_dir = self.root / "reviews"
        self.skill_history_dir = self.root / "skill-history"
        for directory in (
            self.root,
            self.proposals_dir,
            self.reviews_dir,
            self.skill_history_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def append_trajectory(self, trajectory: SkillTrajectory) -> None:
        """Append one complete JSON line and force it to disk."""
        line = json.dumps(
            trajectory.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self.trajectories_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def list_trajectories(
        self,
        *,
        skill_name: str | None = None,
        limit: int | None = None,
    ) -> list[SkillTrajectory]:
        if not self.trajectories_file.is_file():
            return []
        trajectories: list[SkillTrajectory] = []
        for line in self.trajectories_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed evolution trajectory line")
                continue
            if not isinstance(payload, Mapping):
                continue
            trajectory = SkillTrajectory.from_dict(payload)
            if skill_name is not None and skill_name not in trajectory.used_skills:
                continue
            trajectories.append(trajectory)
        if limit is not None:
            return trajectories[-max(0, limit) :]
        return trajectories

    def trajectories_by_id(self, trace_ids: tuple[str, ...]) -> list[SkillTrajectory]:
        wanted = set(trace_ids)
        return [
            trajectory for trajectory in self.list_trajectories() if trajectory.trace_id in wanted
        ]

    def save_review(self, review_id: str, payload: Mapping[str, Any]) -> None:
        _atomic_write_json(self.reviews_dir / f"{review_id}.json", payload)

    def load_review(self, review_id: str) -> dict[str, Any] | None:
        return _read_json(self.reviews_dir / f"{review_id}.json")

    def list_reviews(self, *, skill_name: str | None = None) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        for path in sorted(self.reviews_dir.glob("*.json")):
            payload = _read_json(path)
            if payload is None:
                continue
            request = payload.get("request")
            if skill_name is not None and (
                not isinstance(request, Mapping) or request.get("skill_name") != skill_name
            ):
                continue
            reviews.append(payload)
        return sorted(
            reviews,
            key=lambda item: str(
                item.get("completed_at")
                or (
                    item.get("request", {}).get("requested_at")
                    if isinstance(item.get("request"), Mapping)
                    else ""
                )
                or ""
            ),
        )

    def save_proposal(self, proposal: SkillProposal) -> None:
        _atomic_write_json(self._proposal_path(proposal.proposal_id), proposal.to_dict())

    def load_proposal(self, proposal_id: str) -> SkillProposal | None:
        payload = _read_json(self._proposal_path(proposal_id))
        return SkillProposal.from_dict(payload) if payload is not None else None

    def list_proposals(self, status: ProposalStatus | None = None) -> list[SkillProposal]:
        proposals: list[SkillProposal] = []
        for path in sorted(self.proposals_dir.glob("*.json")):
            payload = _read_json(path)
            if payload is None:
                continue
            proposal = SkillProposal.from_dict(payload)
            if status is None or proposal.status is status:
                proposals.append(proposal)
        return proposals

    def update_proposal(self, proposal_id: str, **changes: Any) -> SkillProposal:
        proposal = self.load_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal: {proposal_id}")
        updated = replace(proposal, **changes)
        self.save_proposal(updated)
        return updated

    def load_state(self) -> EvolutionState:
        payload = _read_json(self.state_file)
        if payload is None:
            return EvolutionState(EVOLUTION_SCHEMA_VERSION, {})
        return EvolutionState.from_dict(payload)

    def save_state(self, state: EvolutionState) -> None:
        _atomic_write_json(self.state_file, state.to_dict())

    def save_skill_version(
        self,
        record: SkillVersionRecord,
        content: str,
    ) -> SkillVersionRecord:
        directory = self.skill_history_dir / record.skill_name
        content_path = directory / record.content_file
        metadata_path = content_path.with_suffix(".json")
        atomic_write_text(content_path, content)
        _atomic_write_json(metadata_path, record.to_dict())
        return record

    def list_skill_versions(self, skill_name: str) -> list[SkillVersionRecord]:
        directory = self.skill_history_dir / skill_name
        records: list[SkillVersionRecord] = []
        for path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
            payload = _read_json(path)
            if payload is not None:
                records.append(SkillVersionRecord.from_dict(payload))
        return records

    def load_skill_version_content(self, record: SkillVersionRecord) -> str:
        path = self.skill_history_dir / record.skill_name / record.content_file
        return path.read_text(encoding="utf-8")

    def _proposal_path(self, proposal_id: str) -> Path:
        return self.proposals_dir / f"{proposal_id}.json"


__all__ = ["EvolutionStore", "atomic_write_text"]
