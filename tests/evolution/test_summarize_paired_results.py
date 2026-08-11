import json
from pathlib import Path

import pytest

from experiments.nanoevo.summarize_paired_results import summarize_result_files


def _run(tokens: int, calls: int) -> dict:
    return {
        "usage": {"total_tokens": tokens},
        "tools_used": ["read_file"] * calls,
        "stop_reason": "completed",
        "error": None,
    }


def test_summary_keeps_positive_and_negative_pairs(tmp_path: Path) -> None:
    artifact = tmp_path / "skill.json"
    artifact.write_text(
        json.dumps(
            {
                "status": "completed",
                "skill_name": "demo",
                "model": "real-model",
                "pairs": [
                    {
                        "v0_total_tokens": 100,
                        "v1_total_tokens": 50,
                        "v0_tool_calls": 4,
                        "v1_tool_calls": 2,
                        "v0": _run(100, 4),
                        "v1": _run(50, 2),
                    },
                    {
                        "v0_total_tokens": 100,
                        "v1_total_tokens": 150,
                        "v0_tool_calls": 4,
                        "v1_tool_calls": 6,
                        "v0": _run(100, 4),
                        "v1": _run(150, 6),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = summarize_result_files([artifact])

    assert result["overall"]["tokens"] == {
        "v0": 200,
        "v1": 200,
        "reduction_pct": 0.0,
        "improved_pairs": 1,
    }
    assert result["overall"]["tool_calls"]["improved_pairs"] == 1


def test_summary_rejects_incomplete_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "running.json"
    artifact.write_text(
        json.dumps({"status": "running", "skill_name": "demo"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not completed"):
        summarize_result_files([artifact])
