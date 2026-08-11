"""Hash-guarded application and restoration of approved Workspace Skill patches."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

from nanobot.evolution.models import (
    ProposalStatus,
    ReviewRequest,
    SkillProposal,
    SkillTrajectory,
    SkillVersionRecord,
    utc_now,
)
from nanobot.evolution.policy import PatchPolicy, PolicyViolationError
from nanobot.evolution.store import EvolutionStore, atomic_write_text


def content_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def _version_filename(content: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}_{content_hash(content)[:12]}.md"


class SkillPatcher:
    """Apply one approved local patch without exposing general file mutation."""

    def __init__(
        self,
        store: EvolutionStore,
        policy: PatchPolicy,
    ) -> None:
        self.store = store
        self.policy = policy

    def approve(
        self,
        proposal_id: str,
        *,
        request: ReviewRequest,
        evidence: list[SkillTrajectory],
    ) -> SkillProposal:
        proposal = self._pending_proposal(proposal_id)
        reference = self.policy.validate_target(proposal.skill_name)
        current = reference.path.read_text(encoding="utf-8")
        if content_hash(current) != proposal.base_hash:
            return self.store.update_proposal(
                proposal_id,
                status=ProposalStatus.CONFLICT,
                decided_at=utc_now(),
                validation_error="SKILL.md changed after the proposal was created",
            )

        try:
            self.policy.validate_evidence(proposal.skill_name, evidence, request)
            updated = self.policy.validate_patch(current, proposal.patch)
        except PolicyViolationError as exc:
            return self.store.update_proposal(
                proposal_id,
                status=ProposalStatus.INVALID,
                decided_at=utc_now(),
                validation_error=str(exc),
            )

        decided_at = utc_now()
        self.store.update_proposal(
            proposal_id,
            status=ProposalStatus.APPROVED,
            decided_at=decided_at,
            validation_error=None,
        )
        self._backup(proposal, current)
        atomic_write_text(reference.path, updated)
        return self.store.update_proposal(
            proposal_id,
            status=ProposalStatus.APPLIED,
            decided_at=decided_at,
            applied_at=utc_now(),
        )

    def reject(self, proposal_id: str) -> SkillProposal:
        self._pending_proposal(proposal_id)
        return self.store.update_proposal(
            proposal_id,
            status=ProposalStatus.REJECTED,
            decided_at=utc_now(),
        )

    def restore(self, skill_name: str) -> SkillProposal:
        reference = self.policy.validate_target(skill_name)
        versions = self.store.list_skill_versions(skill_name)
        candidates: list[tuple[SkillVersionRecord, SkillProposal]] = []
        for record in versions:
            proposal = self.store.load_proposal(record.proposal_id)
            if proposal is not None and proposal.status is ProposalStatus.APPLIED:
                candidates.append((record, proposal))
        if not candidates:
            raise KeyError(f"No applied version to restore for Skill: {skill_name}")

        record, proposal = candidates[-1]
        current = reference.path.read_text(encoding="utf-8")
        self._backup(
            replace(
                proposal,
                proposal_id=f"restore_{proposal.proposal_id}",
            ),
            current,
        )
        restored = self.store.load_skill_version_content(record)
        self.policy.validate_document(current, restored)
        atomic_write_text(reference.path, restored)
        return self.store.update_proposal(
            proposal.proposal_id,
            status=ProposalStatus.RESTORED,
            restored_at=utc_now(),
        )

    def switch_version(self, skill_name: str, target_hash: str) -> str:
        """Switch to one retained version while preserving the current content."""
        reference = self.policy.validate_target(skill_name)
        current = reference.path.read_text(encoding="utf-8")
        if content_hash(current) == target_hash:
            return target_hash

        record = next(
            (
                item
                for item in reversed(self.store.list_skill_versions(skill_name))
                if item.content_hash == target_hash
            ),
            None,
        )
        if record is None:
            raise KeyError(f"Unknown Skill version: {target_hash}")

        target = self.store.load_skill_version_content(record)
        self.policy.validate_document(current, target)
        self._backup_content(
            skill_name=skill_name,
            proposal_id=f"switch_{content_hash(current)[:12]}",
            content=current,
        )
        atomic_write_text(reference.path, target)
        return target_hash

    def _pending_proposal(self, proposal_id: str) -> SkillProposal:
        proposal = self.store.load_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"Unknown proposal: {proposal_id}")
        if proposal.status is not ProposalStatus.PENDING:
            raise ValueError(f"Proposal {proposal_id} is {proposal.status.value}, not pending")
        return proposal

    def _backup(self, proposal: SkillProposal, content: str) -> SkillVersionRecord:
        return self._backup_content(
            skill_name=proposal.skill_name,
            proposal_id=proposal.proposal_id,
            content=content,
        )

    def _backup_content(
        self,
        *,
        skill_name: str,
        proposal_id: str,
        content: str,
    ) -> SkillVersionRecord:
        record = SkillVersionRecord(
            skill_name=skill_name,
            content_hash=content_hash(content),
            proposal_id=proposal_id,
            created_at=utc_now(),
            content_file=_version_filename(content),
        )
        return self.store.save_skill_version(record, content)


__all__ = ["SkillPatcher", "content_hash"]
