"""Deterministic safety gates for skill patch proposals."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from nanobot.evolution.attribution import SkillReference, resolve_workspace_skill
from nanobot.evolution.constants import MAX_PATCH_CHARS
from nanobot.evolution.models import (
    ProposalStatus,
    ReviewRequest,
    SkillPatch,
    SkillProposal,
    SkillTrajectory,
)

_ABSOLUTE_PATH = re.compile(
    r"(?m)(?:^|[\s`'\"])(?:/(?:[^/\s`'\"]+/)+[^/\s`'\"]+|"
    r"[A-Za-z]:[\\/][^\s`'\"]+)"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|authorization|cookie|password|private[_-]?key|secret|token)"
    r"\s*[:=]\s*\S+"
)


class PolicyViolationError(ValueError):
    """A proposal violates a non-LLM safety or evidence rule."""


class PatchPolicy:
    def __init__(
        self,
        workspace: Path | str,
        *,
        builtin_skills_dir: Path | str | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.builtin_skills_dir = builtin_skills_dir

    def validate_target(self, skill_name: str) -> SkillReference:
        reference = resolve_workspace_skill(
            self.workspace,
            skill_name,
            builtin_skills_dir=self.builtin_skills_dir,
        )
        if reference is None:
            raise PolicyViolationError("Target must be an existing Workspace Skill")
        return reference

    def validate_evidence(
        self,
        skill_name: str,
        evidence: list[SkillTrajectory],
        request: ReviewRequest,
    ) -> None:
        if not evidence:
            raise PolicyViolationError("At least one persisted trajectory is required")
        requested_ids = set(request.trajectory_ids)
        if any(item.trace_id not in requested_ids for item in evidence):
            raise PolicyViolationError("Evidence is outside this review request")
        if len({item.trace_id for item in evidence}) != len(evidence):
            raise PolicyViolationError("Duplicate trajectory evidence is not allowed")
        if any(skill_name not in item.used_skills for item in evidence):
            raise PolicyViolationError("Every trajectory must be attributed to the target Skill")

    def validate_patch(self, current: str, patch: SkillPatch) -> str:
        if not patch.old_text:
            raise PolicyViolationError("old_text must not be empty")
        if not patch.new_text.strip():
            raise PolicyViolationError("new_text must not be empty")
        if patch.old_text == patch.new_text:
            raise PolicyViolationError("Patch must change the Skill")
        if len(patch.old_text) + len(patch.new_text) > MAX_PATCH_CHARS:
            raise PolicyViolationError("Patch exceeds the V1 size limit")
        if current.count(patch.old_text) != 1:
            raise PolicyViolationError("old_text must match exactly once")
        if _ABSOLUTE_PATH.search(patch.new_text):
            raise PolicyViolationError("Patch must not add absolute paths")
        if "[REDACTED]" in patch.new_text or _SECRET_ASSIGNMENT.search(patch.new_text):
            raise PolicyViolationError("Patch must not contain secrets or redaction markers")

        updated = current.replace(patch.old_text, patch.new_text, 1)
        self.validate_document(current, updated)
        return updated

    def validate_document(self, current: str, updated: str) -> None:
        current_frontmatter = self._frontmatter(current)
        updated_frontmatter = self._frontmatter(updated)
        current_name = current_frontmatter.get("name")
        updated_name = updated_frontmatter.get("name")
        if not isinstance(current_name, str) or not current_name.strip():
            raise PolicyViolationError("Current Skill frontmatter must contain name")
        if updated_name != current_name:
            raise PolicyViolationError("Patch must not change the Skill name")

    @staticmethod
    def find_duplicate(
        proposals: list[SkillProposal],
        *,
        skill_name: str,
        patch: SkillPatch,
    ) -> SkillProposal | None:
        return next(
            (
                proposal
                for proposal in proposals
                if proposal.status is ProposalStatus.PENDING
                and proposal.skill_name == skill_name
                and proposal.patch == patch
            ),
            None,
        )

    @staticmethod
    def _frontmatter(document: str) -> dict[str, object]:
        if not document.startswith("---\n"):
            raise PolicyViolationError("Skill must retain YAML frontmatter")
        closing = document.find("\n---\n", 4)
        if closing == -1:
            raise PolicyViolationError("Skill must retain valid YAML frontmatter")
        try:
            payload = yaml.safe_load(document[4:closing])
        except yaml.YAMLError as exc:
            raise PolicyViolationError("Skill frontmatter is invalid YAML") from exc
        if not isinstance(payload, dict):
            raise PolicyViolationError("Skill frontmatter must be a mapping")
        return {str(key): value for key, value in payload.items()}


__all__ = ["PatchPolicy", "PolicyViolationError"]
