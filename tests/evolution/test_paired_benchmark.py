from pathlib import Path

import pytest

from experiments.nanoevo.run_experiment import evaluate_response
from experiments.nanoevo.run_paired_benchmark import (
    build_pair,
    evolved_content,
    prepare_version_workspace,
    quality_pass,
    summarize_pairs,
)


def test_evolved_content_applies_recorded_patch() -> None:
    result = {
        "approval": {
            "status": "applied",
            "patch": {"old_text": "slow", "new_text": "batched"},
        }
    }

    assert evolved_content("use slow inspection", result) == "use batched inspection"


def test_evolved_content_rejects_ambiguous_patch() -> None:
    result = {
        "approval": {
            "status": "applied",
            "patch": {"old_text": "same", "new_text": "new"},
        }
    }

    with pytest.raises(ValueError, match="exactly once"):
        evolved_content("same same", result)


def test_prepare_version_workspace_refuses_reuse(tmp_path: Path) -> None:
    root = tmp_path / "v0"
    skill_file = prepare_version_workspace(root, "demo", "---\nname: demo\n---\n")

    assert skill_file.is_file()
    with pytest.raises(FileExistsError):
        prepare_version_workspace(root, "demo", "changed")


def test_quality_pass_requires_complete_grounded_answer() -> None:
    run = {"stop_reason": "completed", "error": None}
    metrics = {
        "required_term_recall": 1.0,
        "grounded_path_rate": 1.0,
        "cited_paths": {"src/a.py": True, "tests/test_a.py": True},
    }

    assert quality_pass(metrics, run)
    assert not quality_pass({**metrics, "required_term_recall": 0.5}, run)


def test_response_evaluation_ignores_ambiguous_bare_filenames(tmp_path: Path) -> None:
    (tmp_path / "src" / "demo").mkdir(parents=True)
    (tmp_path / "src" / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()

    metrics = evaluate_response(
        "Inspect `src/demo/__init__.py`, `tests/`, and `__init__.py`.",
        tmp_path,
        ["demo"],
    )

    assert metrics["cited_paths"] == {
        "src/demo/__init__.py": True,
        "tests/": True,
    }
    assert metrics["grounded_path_rate"] == 1.0


def test_summary_only_uses_quality_valid_pairs() -> None:
    valid = {
        "quality_pass": True,
        "token_reduction_pct": 50.0,
        "tool_call_reduction_pct": 25.0,
        "v0_total_tokens": 100,
        "v1_total_tokens": 50,
        "v0_tool_calls": 4,
        "v1_tool_calls": 3,
    }
    invalid = {
        **valid,
        "quality_pass": False,
        "token_reduction_pct": 99.0,
        "tool_call_reduction_pct": 99.0,
    }

    summary = summarize_pairs([valid, invalid])

    assert summary["quality_valid_pairs"] == 1
    assert summary["token_reduction_pct"]["mean"] == 50.0


def test_build_pair_counts_every_tool_attempt() -> None:
    common = {
        "repository": "demo",
        "repetition": 1,
        "quality_pass": True,
        "usage": {"total_tokens": 100},
    }
    pair = build_pair(
        pair_id="demo:1",
        order="AB",
        v0={**common, "tools_used": ["read_file", "read_file"]},
        v1={**common, "usage": {"total_tokens": 75}, "tools_used": ["read_file"]},
    )

    assert pair["token_reduction_pct"] == 25.0
    assert pair["tool_call_reduction_pct"] == 50.0
