"""Run the real-model NanoEvo experience/held-out experiment."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanobot.agent.hook import SDKCaptureHook
from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.config.loader import load_config, resolve_config_env_vars
from nanobot.providers.image_generation import image_gen_provider_configs
from nanobot.security.workspace_access import WORKSPACE_SCOPE_METADATA_KEY

HERE = Path(__file__).resolve().parent
REPOSITORIES_FILE = HERE / "repositories.json"
INITIAL_SKILL_FILE = HERE / "repo-analysis.SKILL.md"
_BACKTICK = re.compile(r"`([^`\n]+)`")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_PATH_SUFFIXES = {".c", ".md", ".py", ".pyi", ".toml"}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


class ExperimentCaptureHook(SDKCaptureHook):
    """Capture structured tool calls without changing the production SDK result."""

    def __init__(self) -> None:
        super().__init__()
        self.tool_calls: list[dict[str, Any]] = []

    async def after_execute_tool(
        self,
        context: Any,
        tool_call: Any,
        tool: Any,
        params: Any,
        result: Any,
    ) -> None:
        self.tool_calls.append(
            {
                "call_id": tool_call.id,
                "name": tool_call.name,
                "params": _json_safe(params),
                "status": "success",
                "result_excerpt": str(result)[:1000],
                "error": None,
            }
        )

    async def on_execute_tool_error(
        self,
        context: Any,
        tool_call: Any,
        tool: Any,
        params: Any,
        error: Any,
    ) -> None:
        self.tool_calls.append(
            {
                "call_id": tool_call.id,
                "name": tool_call.name,
                "params": _json_safe(params),
                "status": "error",
                "result_excerpt": "",
                "error": str(error)[:1000],
            }
        )


def _run_git(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def prepare_repository(root: Path, spec: dict[str, Any]) -> Path:
    target = root / str(spec["name"])
    if target.exists():
        if not (target / ".git").is_dir():
            raise RuntimeError(f"Refusing to reuse non-git directory: {target}")
        if _run_git("status", "--porcelain", cwd=target):
            raise RuntimeError(f"Refusing to overwrite dirty repository: {target}")
    else:
        target.mkdir(parents=True)
        _run_git("init", "--quiet", cwd=target)
        _run_git("remote", "add", "origin", str(spec["url"]), cwd=target)
    commit = str(spec["commit"])
    _run_git("fetch", "--quiet", "--depth", "1", "origin", commit, cwd=target)
    _run_git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=target)
    actual = _run_git("rev-parse", "HEAD", cwd=target)
    if actual != commit:
        raise RuntimeError(f"Commit mismatch for {target.name}: {actual} != {commit}")
    return target


def prepare_workspace(root: Path, *, skill_name: str, skill_source: Path) -> Path:
    skill_dir = root / "skills" / skill_name
    skill = skill_dir / "SKILL.md"
    if skill.exists() or (root / ".nanobot" / "evolution").exists():
        raise RuntimeError(
            f"Experiment workspace is not fresh: {root}. Choose another --workspace."
        )
    source = skill_source.expanduser().resolve()
    skill_dir.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        skill_dir.mkdir()
        shutil.copyfile(source, skill)
    else:
        source_skill = source / "SKILL.md"
        if not source_skill.is_file():
            raise FileNotFoundError(f"Skill source has no SKILL.md: {source}")
        shutil.copytree(source, skill_dir)
    return skill


def evaluate_response(content: str, repo: Path, required_terms: list[str]) -> dict[str, Any]:
    lowered = content.lower()
    term_results = {term: term.lower() in lowered for term in required_terms}
    path_candidates: list[tuple[str, str]] = []
    for raw in _BACKTICK.findall(content):
        candidate = raw.strip().strip(".,;")
        if " " in candidate or candidate.startswith(("/", "~")):
            continue
        normalized = _LINE_SUFFIX.sub("", candidate)
        looks_like_path = (
            "/" in normalized
            and (
                normalized.endswith("/")
                or Path(normalized).suffix.lower() in _PATH_SUFFIXES
            )
            or (repo / normalized).exists()
        )
        if looks_like_path:
            path_candidates.append((candidate, normalized))
    grounded = {
        candidate: (repo / normalized).exists()
        for candidate, normalized in dict.fromkeys(path_candidates)
    }
    grounded_rate = sum(grounded.values()) / len(grounded) if grounded else None
    return {
        "required_terms": term_results,
        "required_term_recall": sum(term_results.values()) / len(term_results),
        "cited_paths": grounded,
        "grounded_path_rate": grounded_rate,
    }


async def run_repo_turn(
    loop: AgentLoop,
    *,
    repo: Path,
    skill_file: Path,
    phase: str,
    required_terms: list[str],
    collect_evolution: bool,
) -> dict[str, Any]:
    capture = ExperimentCaptureHook()
    prompt = (
        f"Perform a targeted analysis of the Python repository at {repo}. First read and "
        f"follow the existing Workspace Skill at {skill_file}. Explain only the repository "
        "purpose, package layout, primary runtime path, and test layout. Prefer batched "
        "inspection over reading files one by one. Use direct repository evidence, cite "
        "relative paths, and do not modify files."
    )
    chat_id = f"nanoevo-{phase}-{repo.name}"
    response = await loop._process_message(
        InboundMessage(
            channel="websocket",
            sender_id="experiment",
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
        ephemeral=not collect_evolution,
        run_extra_hooks_for_ephemeral=not collect_evolution,
    )
    content = response.content if response is not None else ""
    return {
        "phase": phase,
        "repository": repo.name,
        "commit": _run_git("rev-parse", "HEAD", cwd=repo),
        "content": content,
        "tools_used": capture.tools_used,
        "tool_calls": capture.tool_calls,
        "usage": capture.usage,
        "stop_reason": capture.stop_reason,
        "error": capture.error,
        "metrics": evaluate_response(content, repo, required_terms),
    }


async def run(args: argparse.Namespace) -> Path:
    manifest = json.loads(REPOSITORIES_FILE.read_text(encoding="utf-8"))
    workspace = args.workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    skill_file = prepare_workspace(
        workspace,
        skill_name=args.skill_name,
        skill_source=args.skill_source,
    )
    repository_root = workspace / "repositories"
    experience = [
        (spec, prepare_repository(repository_root, spec)) for spec in manifest["experience"]
    ]
    held_spec = manifest["held_out"]
    held_repo = prepare_repository(repository_root, held_spec)

    config = resolve_config_env_vars(load_config(args.config))
    config.agents.defaults.workspace = str(workspace)
    config.agents.defaults.max_tool_iterations = args.max_tool_iterations
    config.evolution.enabled = True
    if args.review_model_preset:
        config.evolution.review_model_preset = args.review_model_preset
    loop = AgentLoop.from_config(
        config,
        image_generation_provider_configs=image_gen_provider_configs(config),
    )
    service = loop.skill_evolution
    results: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "skill_name": args.skill_name,
        "skill_source": str(args.skill_source.expanduser().resolve()),
        "model": loop.model,
        "review_model_preset": config.evolution.review_model_preset,
        "manifest": manifest,
        "baseline": None,
        "experience": [],
        "review": None,
        "evolution_applied": False,
        "evolved": None,
    }
    try:
        results["baseline"] = await run_repo_turn(
            loop,
            repo=held_repo,
            skill_file=skill_file,
            phase="baseline-held-out",
            required_terms=held_spec["required_terms"],
            collect_evolution=False,
        )
        for spec, repo in experience:
            results["experience"].append(
                await run_repo_turn(
                    loop,
                    repo=repo,
                    skill_file=skill_file,
                    phase="experience",
                    required_terms=spec["required_terms"],
                    collect_evolution=True,
                )
            )

        request = await service.request_review(
            skill_name=args.skill_name,
            source_channel="cli",
            source_chat_id="nanoevo-experiment",
            user_feedback=args.review_feedback,
        )
        await service.wait_until_idle(args.skill_name)
        review = service.store.load_review(request.review_id)
        results["review"] = review
        proposal_id = review.get("proposal_id") if review else None
        applied = False
        if proposal_id and args.approve:
            proposal = service.approve_proposal(str(proposal_id))
            results["approval"] = proposal.to_dict()
            applied = proposal.status.value == "applied"
        elif proposal_id:
            results["approval"] = {
                "status": "not_approved",
                "proposal_id": proposal_id,
            }

        results["evolution_applied"] = applied
        if applied:
            results["evolved"] = await run_repo_turn(
                loop,
                repo=held_repo,
                skill_file=skill_file,
                phase="evolved-held-out",
                required_terms=held_spec["required_terms"],
                collect_evolution=False,
            )
    finally:
        await loop.close_mcp()

    results["finished_at"] = datetime.now(timezone.utc).isoformat()
    baseline = results["baseline"]
    evolved = results["evolved"]
    if baseline is not None and evolved is not None:
        baseline_tool_calls = len(baseline["tools_used"])
        evolved_tool_calls = len(evolved["tools_used"])
        baseline_tokens = int(baseline["usage"].get("total_tokens", 0))
        evolved_tokens = int(evolved["usage"].get("total_tokens", 0))
        results["efficiency"] = {
            "tool_calls": {
                "baseline": baseline_tool_calls,
                "evolved": evolved_tool_calls,
                "change": evolved_tool_calls - baseline_tool_calls,
                "reduction_pct": (
                    (baseline_tool_calls - evolved_tool_calls) / baseline_tool_calls * 100
                    if baseline_tool_calls
                    else None
                ),
            },
            "total_tokens": {
                "baseline": baseline_tokens,
                "evolved": evolved_tokens,
                "change": evolved_tokens - baseline_tokens,
                "reduction_pct": (
                    (baseline_tokens - evolved_tokens) / baseline_tokens * 100
                    if baseline_tokens
                    else None
                ),
            },
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return args.output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run NanoEvo with real repositories and the configured real model.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="nanobot config.json; defaults to ~/.nanobot/config.json",
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skill-name", default="repo-analysis")
    parser.add_argument(
        "--max-tool-iterations",
        type=int,
        default=12,
        help="Per-turn tool-iteration budget shared by baseline and evolved runs.",
    )
    parser.add_argument(
        "--skill-source",
        type=Path,
        default=INITIAL_SKILL_FILE,
        help="Directory containing the market Skill or a path to its SKILL.md.",
    )
    parser.add_argument("--review-model-preset")
    parser.add_argument(
        "--review-feedback",
        help=(
            "Optional explicit review hypothesis grounded in the recorded trajectories. "
            "The deterministic evidence and patch policies remain authoritative."
        ),
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Pre-authorize applying a generated Pending Proposal for this experiment only.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
