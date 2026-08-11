"""Run a counterbalanced V0/V1 benchmark for one evolved Workspace Skill."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.nanoevo.run_experiment import (
    ExperimentCaptureHook,
    evaluate_response,
    prepare_repository,
)
from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.config.loader import load_config, resolve_config_env_vars
from nanobot.providers.image_generation import image_gen_provider_configs
from nanobot.security.workspace_access import WORKSPACE_SCOPE_METADATA_KEY

HERE = Path(__file__).resolve().parent
DEFAULT_REPOSITORIES = HERE / "benchmark_repositories.json"


def evolved_content(base: str, result: dict[str, Any]) -> str:
    approval = result.get("approval")
    if not isinstance(approval, dict) or approval.get("status") != "applied":
        raise ValueError("Evolution result must contain an applied approval")
    patch = approval.get("patch")
    if not isinstance(patch, dict):
        raise ValueError("Evolution result approval has no patch")
    old_text = patch.get("old_text")
    new_text = patch.get("new_text")
    if not isinstance(old_text, str) or not isinstance(new_text, str):
        raise ValueError("Evolution patch must contain string old_text and new_text")
    if base.count(old_text) != 1:
        raise ValueError("Evolution patch old_text must match the baseline exactly once")
    return base.replace(old_text, new_text, 1)


def prepare_version_workspace(root: Path, skill_name: str, content: str) -> Path:
    if root.exists():
        raise FileExistsError(f"Benchmark workspace already exists: {root}")
    skill_file = root / "skills" / skill_name / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def quality_pass(metrics: dict[str, Any], run: dict[str, Any]) -> bool:
    grounded = metrics.get("grounded_path_rate")
    cited_paths = metrics.get("cited_paths")
    return bool(
        run.get("stop_reason") == "completed"
        and not run.get("error")
        and metrics.get("required_term_recall", 0) >= 1.0
        and grounded == 1.0
        and isinstance(cited_paths, dict)
        and len(cited_paths) >= 2
    )


async def run_turn(
    loop: AgentLoop,
    *,
    version: str,
    skill_name: str,
    skill_file: Path,
    repo: Path,
    required_terms: list[str],
    repetition: int,
) -> dict[str, Any]:
    capture = ExperimentCaptureHook()
    prompt = (
        f"Perform a targeted analysis of the Python repository at {repo}. First read and "
        f"follow the Workspace Skill at {skill_file}. Explain only the "
        "repository purpose, package layout, primary runtime path, and test layout. Prefer "
        "batched inspection over reading files one by one. Use direct repository evidence, "
        "cite at least two relative paths, and do not modify files or install dependencies."
    )
    chat_id = f"nanoevo-paired-{skill_name}-{repo.name}-{repetition}-{version}"
    started = time.perf_counter()
    response = await loop._process_message(
        InboundMessage(
            channel="websocket",
            sender_id="benchmark",
            chat_id=chat_id,
            content=prompt,
            session_key_override=f"websocket:{chat_id}",
            metadata={
                WORKSPACE_SCOPE_METADATA_KEY: {
                    "project_path": str(repo),
                    "access_mode": "full",
                }
            },
        ),
        hooks=[capture],
        ephemeral=True,
        run_extra_hooks_for_ephemeral=True,
    )
    content = response.content if response is not None else ""
    metrics = evaluate_response(content, repo, required_terms)
    run = {
        "version": version,
        "repository": repo.name,
        "repetition": repetition,
        "content": content,
        "tools_used": capture.tools_used,
        "tool_calls": capture.tool_calls,
        "usage": capture.usage,
        "latency_seconds": time.perf_counter() - started,
        "stop_reason": capture.stop_reason,
        "error": capture.error,
        "metrics": metrics,
    }
    run["quality_pass"] = quality_pass(metrics, run)
    return run


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _stdev(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else None


def bootstrap_mean_ci(values: list[float], *, samples: int = 10_000) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(20260804)
    means = sorted(
        statistics.fmean(rng.choices(values, k=len(values))) for _ in range(samples)
    )
    lower = means[math.floor(0.025 * (samples - 1))]
    upper = means[math.ceil(0.975 * (samples - 1))]
    return [lower, upper]


def summarize_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [pair for pair in pairs if pair["quality_pass"]]
    token_reductions = [pair["token_reduction_pct"] for pair in valid]
    call_reductions = [pair["tool_call_reduction_pct"] for pair in valid]
    token_deltas = [pair["v1_total_tokens"] - pair["v0_total_tokens"] for pair in valid]
    call_deltas = [pair["v1_tool_calls"] - pair["v0_tool_calls"] for pair in valid]
    return {
        "pairs": len(pairs),
        "quality_valid_pairs": len(valid),
        "quality_valid_rate": len(valid) / len(pairs) if pairs else None,
        "token_reduction_pct": {
            "mean": _mean(token_reductions),
            "median": _median(token_reductions),
            "stdev": _stdev(token_reductions),
            "bootstrap_95_ci": bootstrap_mean_ci(token_reductions),
            "improved_pairs": sum(value > 0 for value in token_reductions),
        },
        "tool_call_reduction_pct": {
            "mean": _mean(call_reductions),
            "median": _median(call_reductions),
            "stdev": _stdev(call_reductions),
            "bootstrap_95_ci": bootstrap_mean_ci(call_reductions),
            "improved_pairs": sum(value > 0 for value in call_reductions),
        },
        "paired_delta": {
            "total_tokens_mean": _mean(token_deltas),
            "tool_calls_mean": _mean(call_deltas),
        },
    }


def build_pair(
    *,
    pair_id: str,
    order: str,
    v0: dict[str, Any],
    v1: dict[str, Any],
) -> dict[str, Any]:
    v0_tokens = int(v0["usage"].get("total_tokens", 0))
    v1_tokens = int(v1["usage"].get("total_tokens", 0))
    v0_calls = len(v0["tools_used"])
    v1_calls = len(v1["tools_used"])
    return {
        "pair_id": pair_id,
        "order": order,
        "repository": v0["repository"],
        "repetition": v0["repetition"],
        "quality_pass": bool(v0["quality_pass"] and v1["quality_pass"]),
        "v0_total_tokens": v0_tokens,
        "v1_total_tokens": v1_tokens,
        "token_reduction_pct": (
            (v0_tokens - v1_tokens) / v0_tokens * 100 if v0_tokens else 0.0
        ),
        "v0_tool_calls": v0_calls,
        "v1_tool_calls": v1_calls,
        "tool_call_reduction_pct": (
            (v0_calls - v1_calls) / v0_calls * 100 if v0_calls else 0.0
        ),
        "v0": v0,
        "v1": v1,
    }


async def run(args: argparse.Namespace) -> Path:
    started_at = datetime.now(timezone.utc).isoformat()
    benchmark_root = args.workspace.expanduser().resolve()
    if benchmark_root.exists():
        raise FileExistsError(f"Benchmark root already exists: {benchmark_root}")
    benchmark_root.mkdir(parents=True)

    source = args.skill_source.expanduser().resolve()
    source_file = source if source.is_file() else source / "SKILL.md"
    baseline = source_file.read_text(encoding="utf-8")
    if args.evolved_skill_source is not None:
        evolved_source = args.evolved_skill_source.expanduser().resolve()
        evolved_file = evolved_source if evolved_source.is_file() else evolved_source / "SKILL.md"
        evolved = evolved_file.read_text(encoding="utf-8")
    else:
        if args.evolution_result is None:
            raise ValueError("Provide --evolution-result or --evolved-skill-source")
        evolution_result = json.loads(args.evolution_result.read_text(encoding="utf-8"))
        evolved = evolved_content(baseline, evolution_result)

    v0_workspace = benchmark_root / "workspace-v0"
    v1_workspace = benchmark_root / "workspace-v1"
    prepare_version_workspace(v0_workspace, args.skill_name, baseline)
    prepare_version_workspace(v1_workspace, args.skill_name, evolved)

    manifest = json.loads(args.repositories.read_text(encoding="utf-8"))
    repository_root = benchmark_root / "repositories"
    repositories = [
        (spec, prepare_repository(repository_root, spec)) for spec in manifest["repositories"]
    ]

    loops: dict[str, AgentLoop] = {}
    for version, workspace in (("v0", v0_workspace), ("v1", v1_workspace)):
        config = resolve_config_env_vars(load_config(args.config))
        config.agents.defaults.workspace = str(workspace)
        config.agents.defaults.max_tool_iterations = args.max_tool_iterations
        config.evolution.enabled = False
        loops[version] = AgentLoop.from_config(
            config,
            image_generation_provider_configs=image_gen_provider_configs(config),
        )

    pairs: list[dict[str, Any]] = []

    def write_result(status: str) -> Path:
        result = {
            "schema_version": 1,
            "status": status,
            "started_at": started_at,
            "finished_at": (
                datetime.now(timezone.utc).isoformat() if status == "completed" else None
            ),
            "skill_name": args.skill_name,
            "model": loops["v0"].model,
            "baseline_source": str(source_file),
            "evolution_result": str(args.evolution_result) if args.evolution_result else None,
            "evolved_skill_source": str(evolved_file) if args.evolved_skill_source else None,
            "repeats": args.repeats,
            "repositories": manifest["repositories"],
            "pairs": pairs,
            "summary": summarize_pairs(pairs),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return args.output

    try:
        for repo_index, (spec, repo) in enumerate(repositories):
            for repetition in range(1, args.repeats + 1):
                order = "AB" if (repo_index + repetition) % 2 == 0 else "BA"
                runs: dict[str, dict[str, Any]] = {}
                for version in (("v0", "v1") if order == "AB" else ("v1", "v0")):
                    runs[version] = await run_turn(
                        loops[version],
                        version=version,
                        skill_name=args.skill_name,
                        skill_file=(
                            (v0_workspace if version == "v0" else v1_workspace)
                            / "skills"
                            / args.skill_name
                            / "SKILL.md"
                        ),
                        repo=repo,
                        required_terms=spec["required_terms"],
                        repetition=repetition,
                    )
                pair_id = f"{args.skill_name}:{repo.name}:{repetition}"
                pairs.append(
                    build_pair(pair_id=pair_id, order=order, v0=runs["v0"], v1=runs["v1"])
                )
                write_result("running")
    finally:
        await asyncio.gather(*(loop.close_mcp() for loop in loops.values()))

    return write_result("completed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skill-name", required=True)
    parser.add_argument("--skill-source", type=Path, required=True)
    version_source = parser.add_mutually_exclusive_group(required=True)
    version_source.add_argument("--evolution-result", type=Path)
    version_source.add_argument("--evolved-skill-source", type=Path)
    parser.add_argument("--repositories", type=Path, default=DEFAULT_REPOSITORIES)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-tool-iterations", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
