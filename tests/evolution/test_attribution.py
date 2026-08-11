from __future__ import annotations

from nanobot.evolution.attribution import (
    always_workspace_skills,
    attribute_read_file,
    resolve_workspace_skill,
)


def _write_skill(workspace, name: str, *, always: bool = False):
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: test\nalways: {str(always).lower()}\n---\nBody\n",
        encoding="utf-8",
    )
    return skill_file


def test_attributes_only_successful_workspace_skill_reads(tmp_path) -> None:
    skill_file = _write_skill(tmp_path, "repo-analysis")

    reference = attribute_read_file(
        tmp_path,
        "read_file",
        {"path": "skills/repo-analysis/SKILL.md"},
        succeeded=True,
    )

    assert reference is not None
    assert reference.name == "repo-analysis"
    assert reference.path == skill_file.resolve()
    assert (
        attribute_read_file(
            tmp_path,
            "read_file",
            {"path": skill_file},
            succeeded=False,
        )
        is None
    )
    assert (
        attribute_read_file(
            tmp_path,
            "write_file",
            {"path": skill_file},
            succeeded=True,
        )
        is None
    )


def test_rejects_builtin_outside_and_symlink_targets(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    builtin = tmp_path / "builtin"
    workspace.mkdir()
    builtin_file = _write_skill(builtin, "repo-analysis")

    assert (
        resolve_workspace_skill(
            workspace,
            "repo-analysis",
            builtin_skills_dir=builtin / "skills",
        )
        is None
    )

    linked = workspace / "skills" / "repo-analysis"
    linked.parent.mkdir(parents=True)
    linked.symlink_to(builtin_file.parent, target_is_directory=True)
    assert resolve_workspace_skill(workspace, "repo-analysis") is None


def test_lists_only_always_workspace_skills(tmp_path) -> None:
    _write_skill(tmp_path, "always-on", always=True)
    _write_skill(tmp_path, "on-demand")

    assert [item.name for item in always_workspace_skills(tmp_path)] == ["always-on"]


def test_relative_project_path_cannot_masquerade_as_agent_workspace_skill(
    tmp_path,
) -> None:
    agent_workspace = tmp_path / "agent"
    project_workspace = tmp_path / "project"
    _write_skill(agent_workspace, "repo-analysis")
    _write_skill(project_workspace, "repo-analysis")

    assert (
        attribute_read_file(
            agent_workspace,
            "read_file",
            {"path": "skills/repo-analysis/SKILL.md"},
            succeeded=True,
            path_base=project_workspace,
        )
        is None
    )
