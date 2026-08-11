"""Workspace-only skill path resolution and usage attribution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from nanobot.agent.skills import SkillsLoader

_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class SkillReference:
    name: str
    path: Path
    source: Literal["workspace"] = "workspace"


def resolve_workspace_skill(
    workspace: Path | str,
    skill_name: str,
    *,
    builtin_skills_dir: Path | str | None = None,
) -> SkillReference | None:
    """Resolve a direct workspace ``<skill>/SKILL.md`` without symlink escape."""
    if not _SKILL_NAME.fullmatch(skill_name):
        return None
    skills_root = Path(workspace).expanduser().resolve() / "skills"
    candidate = skills_root / skill_name / "SKILL.md"
    return _valid_workspace_skill(skills_root, candidate, builtin_skills_dir)


def skill_reference_from_path(
    workspace: Path | str,
    path: Path | str | None,
    *,
    builtin_skills_dir: Path | str | None = None,
    path_base: Path | str | None = None,
) -> SkillReference | None:
    """Map a successfully-read path to a Workspace skill, if and only if safe."""
    if not isinstance(path, (Path, str)):
        return None
    workspace_root = Path(workspace).expanduser().resolve()
    skills_root = workspace_root / "skills"
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(path_base or workspace_root).expanduser().resolve() / candidate
    return _valid_workspace_skill(skills_root, candidate, builtin_skills_dir)


def attribute_read_file(
    workspace: Path | str,
    tool_name: str,
    params: dict[str, Any] | None,
    *,
    succeeded: bool,
    builtin_skills_dir: Path | str | None = None,
    path_base: Path | str | None = None,
) -> SkillReference | None:
    """Attribute only successful ``read_file`` reads of a Workspace SKILL.md."""
    if not succeeded or tool_name != "read_file" or not isinstance(params, dict):
        return None
    path = params.get("path", params.get("file_path"))
    return skill_reference_from_path(
        workspace,
        path,
        builtin_skills_dir=builtin_skills_dir,
        path_base=path_base,
    )


def always_workspace_skills(workspace: Path | str) -> list[SkillReference]:
    """Return valid always-on skills using the original SkillsLoader semantics."""
    workspace_root = Path(workspace).expanduser().resolve()
    loader = SkillsLoader(workspace_root)
    workspace_names = {
        entry["name"]
        for entry in loader.list_skills(filter_unavailable=True)
        if entry["source"] == "workspace"
    }
    always_names = workspace_names.intersection(loader.get_always_skills())
    references: list[SkillReference] = []
    for name in always_names:
        reference = resolve_workspace_skill(workspace_root, name)
        if reference is not None:
            references.append(reference)
    return sorted(references, key=lambda item: item.name)


def _valid_workspace_skill(
    skills_root: Path,
    candidate: Path,
    builtin_skills_dir: Path | str | None,
) -> SkillReference | None:
    if not candidate.exists() or not candidate.is_file() or candidate.name != "SKILL.md":
        return None
    root = skills_root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    # The resolved location must be exactly <skills>/<name>/SKILL.md.  This
    # rejects a symlinked skill directory or SKILL.md even if it points back
    # into the workspace tree.
    if resolved.parent.parent != root or candidate.parent.is_symlink() or candidate.is_symlink():
        return None
    if builtin_skills_dir is not None:
        builtin = Path(builtin_skills_dir).expanduser().resolve()
        try:
            resolved.relative_to(builtin)
        except ValueError:
            pass
        else:
            return None
    name = resolved.parent.name
    if not _SKILL_NAME.fullmatch(name):
        return None
    return SkillReference(name=name, path=resolved)


__all__ = [
    "SkillReference",
    "always_workspace_skills",
    "attribute_read_file",
    "resolve_workspace_skill",
    "skill_reference_from_path",
]
