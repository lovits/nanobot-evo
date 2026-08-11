"""Evaluate whether repository-analysis runs selected appropriate tools."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

READ_ONLY_TOOLS = {"read_file", "list_dir", "find_files", "grep", "exec"}
MUTATING_TOOLS = {
    "write_file",
    "edit_file",
    "apply_patch",
    "delete_file",
    "move_file",
}
MUTATING_COMMAND = re.compile(
    r"(?:^|[;&|]\s*|\bsudo\s+)"
    r"(?:pip(?:3)?\s+install|uv\s+(?:add|remove|sync)|poetry\s+(?:add|remove|install)|"
    r"rm\b|mv\b|cp\b|touch\b|mkdir\b|git\s+(?:checkout|switch|reset|clean|commit)|"
    r"npm\s+(?:install|uninstall)|bun\s+(?:add|remove|install))",
    re.IGNORECASE,
)


def _canonical_call(event: dict[str, Any]) -> str:
    return json.dumps(
        {"name": event.get("name"), "params": event.get("params")},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def classify_call(event: dict[str, Any], seen: set[str]) -> tuple[bool, str]:
    """Return whether one call was appropriate and the supporting reason."""
    name = str(event.get("name", ""))
    params = event.get("params")
    params = params if isinstance(params, dict) else {}
    canonical = _canonical_call(event)

    if canonical in seen:
        return False, "duplicate_call"
    seen.add(canonical)

    if name in MUTATING_TOOLS:
        return False, "mutating_tool_for_read_only_task"
    if name not in READ_ONLY_TOOLS:
        return False, "unrelated_tool"
    if event.get("status") != "success":
        return False, "tool_execution_failed"

    if name in {"read_file", "list_dir"}:
        raw_path = params.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return False, "missing_path"
        path = Path(raw_path)
        if name == "read_file" and (not path.exists() or not path.is_file()):
            return False, "read_file_target_is_not_a_file"
        if name == "list_dir" and (not path.exists() or not path.is_dir()):
            return False, "list_dir_target_is_not_a_directory"

    if name == "exec":
        command = params.get("cmd")
        if not isinstance(command, str) or not command.strip():
            return False, "missing_command"
        if MUTATING_COMMAND.search(command):
            return False, "mutating_command_for_read_only_task"

    return True, "appropriate"


def evaluate_trajectory_files(paths: list[Path]) -> dict[str, Any]:
    per_source: list[dict[str, Any]] = []
    total_calls = 0
    correct_calls = 0
    reasons: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []

    for path in paths:
        source_total = 0
        source_correct = 0
        source_reasons: Counter[str] = Counter()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            seen: set[str] = set()
            for event in row.get("tool_events", []):
                correct, reason = classify_call(event, seen)
                source_total += 1
                total_calls += 1
                source_reasons[reason] += 1
                reasons[reason] += 1
                if correct:
                    source_correct += 1
                    correct_calls += 1
                else:
                    failures.append(
                        {
                            "source": str(path),
                            "line": line_number,
                            "trace_id": row.get("trace_id"),
                            "tool": event.get("name"),
                            "params": event.get("params"),
                            "reason": reason,
                        }
                    )
        per_source.append(
            {
                "source": str(path),
                "calls": source_total,
                "correct": source_correct,
                "accuracy": source_correct / source_total if source_total else None,
                "reasons": dict(source_reasons),
            }
        )

    return {
        "metric": "observed_tool_call_selection_accuracy",
        "definition": "appropriate observed calls / all observed calls",
        "scope": (
            "Checks tool family, read-only task contract, file/directory target type, "
            "execution success, and exact duplicate calls. It does not measure omitted "
            "necessary calls."
        ),
        "calls": total_calls,
        "correct": correct_calls,
        "accuracy": correct_calls / total_calls if total_calls else None,
        "reasons": dict(reasons),
        "per_source": per_source,
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trajectory",
        type=Path,
        action="append",
        required=True,
        help="Path to a NanoEvo trajectories.jsonl file; repeat for multiple skills.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate_trajectory_files(args.trajectory)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
