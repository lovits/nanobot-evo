"""Aggregate completed NanoEvo V0/V1 benchmark artifacts without dropping regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _reduction(before: int, after: int) -> float | None:
    return (before - after) / before * 100 if before else None


def _summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    v0_tokens = sum(int(pair["v0_total_tokens"]) for pair in pairs)
    v1_tokens = sum(int(pair["v1_total_tokens"]) for pair in pairs)
    v0_calls = sum(int(pair["v0_tool_calls"]) for pair in pairs)
    v1_calls = sum(int(pair["v1_tool_calls"]) for pair in pairs)
    completed_runs = sum(
        run.get("stop_reason") == "completed" and not run.get("error")
        for pair in pairs
        for run in (pair["v0"], pair["v1"])
    )
    return {
        "pairs": len(pairs),
        "real_llm_runs": len(pairs) * 2,
        "completed_runs": completed_runs,
        "tokens": {
            "v0": v0_tokens,
            "v1": v1_tokens,
            "reduction_pct": _reduction(v0_tokens, v1_tokens),
            "improved_pairs": sum(pair["v1_total_tokens"] < pair["v0_total_tokens"] for pair in pairs),
        },
        "tool_calls": {
            "v0": v0_calls,
            "v1": v1_calls,
            "reduction_pct": _reduction(v0_calls, v1_calls),
            "improved_pairs": sum(pair["v1_tool_calls"] < pair["v0_tool_calls"] for pair in pairs),
        },
    }


def summarize_result_files(paths: list[Path]) -> dict[str, Any]:
    skills: dict[str, Any] = {}
    all_pairs: list[dict[str, Any]] = []
    model: str | None = None
    for path in paths:
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("status") != "completed":
            raise ValueError(f"Benchmark is not completed: {path}")
        if model is None:
            model = result.get("model")
        elif result.get("model") != model:
            raise ValueError("All benchmark artifacts must use the same model")
        pairs = result.get("pairs")
        if not isinstance(pairs, list) or not pairs:
            raise ValueError(f"Benchmark has no pairs: {path}")
        skill_name = str(result["skill_name"])
        skills[skill_name] = {
            "source": str(path),
            **_summarize_pairs(pairs),
        }
        all_pairs.extend(pairs)
    return {
        "schema_version": 1,
        "model": model,
        "aggregation": "ratio_of_sums_all_pairs_no_regression_filtering",
        "skills": skills,
        "overall": _summarize_pairs(all_pairs),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = summarize_result_files(args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
