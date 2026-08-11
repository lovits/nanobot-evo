from pathlib import Path

from experiments.nanoevo.evaluate_tool_accuracy import classify_call


def test_read_file_requires_a_file(tmp_path: Path) -> None:
    target = tmp_path / "SKILL.md"
    target.write_text("test", encoding="utf-8")

    assert classify_call(
        {
            "name": "read_file",
            "params": {"path": str(target)},
            "status": "success",
        },
        set(),
    ) == (True, "appropriate")
    assert classify_call(
        {
            "name": "read_file",
            "params": {"path": str(tmp_path)},
            "status": "success",
        },
        set(),
    ) == (False, "read_file_target_is_not_a_file")


def test_read_only_repo_analysis_rejects_environment_mutation() -> None:
    assert classify_call(
        {
            "name": "exec",
            "params": {"cmd": "cd repo && pip install -e ."},
            "status": "success",
        },
        set(),
    ) == (False, "mutating_command_for_read_only_task")


def test_exact_duplicate_is_unnecessary(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("test", encoding="utf-8")
    event = {
        "name": "read_file",
        "params": {"path": str(target)},
        "status": "success",
    }
    seen: set[str] = set()

    assert classify_call(event, seen) == (True, "appropriate")
    assert classify_call(event, seen) == (False, "duplicate_call")
