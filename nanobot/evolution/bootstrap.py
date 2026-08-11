"""Optional assembly of NanoEvo onto an existing AgentLoop."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.evolution.commands import register_evolution_commands
from nanobot.evolution.constants import REVIEW_EVERY_N_TRAJECTORIES
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.reviewer import SkillReviewer
from nanobot.evolution.service import SkillEvolutionService
from nanobot.evolution.store import EvolutionStore


def install_skill_evolution(
    loop: Any,
    config: Any,
) -> SkillEvolutionService | None:
    """Install the extension only when explicitly enabled."""
    if config is None or not bool(getattr(config, "enabled", False)):
        return None

    workspace = Path(loop.workspace).expanduser().resolve()
    store = EvolutionStore(workspace)
    policy = PatchPolicy(workspace)
    reviewer = SkillReviewer(
        workspace=workspace,
        store=store,
        policy=policy,
    )
    service = SkillEvolutionService(
        workspace=workspace,
        store=store,
        policy=policy,
        reviewer=reviewer,
        runtime_resolver=loop.runtime_resolver,
        schedule_background=loop.schedule_background,
        bus=loop.bus,
        review_model_preset=getattr(config, "review_model_preset", None),
        review_every_n_trajectories=getattr(
            config,
            "review_every_n_trajectories",
            REVIEW_EVERY_N_TRAJECTORIES,
        ),
    )
    loop.register_hook_factory(service.create_hook)
    register_evolution_commands(loop.commands, service)
    loop.skill_evolution = service
    return service


__all__ = ["install_skill_evolution"]
