from __future__ import annotations

import pytest

from nanobot.bus.queue import MessageBus
from nanobot.evolution.constants import EVOLUTION_SCHEMA_VERSION
from nanobot.evolution.models import SkillTrajectory
from nanobot.evolution.policy import PatchPolicy
from nanobot.evolution.reviewer import SkillReviewer
from nanobot.evolution.service import SkillEvolutionService
from nanobot.evolution.store import EvolutionStore


class ClosingScheduler:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, coroutine) -> None:
        self.count += 1
        coroutine.close()


def _service(tmp_path, *, review_every_n_trajectories=10):
    store = EvolutionStore(tmp_path)
    policy = PatchPolicy(tmp_path)
    scheduler = ClosingScheduler()
    service = SkillEvolutionService(
        workspace=tmp_path,
        store=store,
        policy=policy,
        reviewer=SkillReviewer(workspace=tmp_path, store=store, policy=policy),
        runtime_resolver=None,
        schedule_background=scheduler,
        bus=MessageBus(),
        review_every_n_trajectories=review_every_n_trajectories,
    )
    return service, scheduler


def _trajectory(index: int, *, failed=False, skills=("repo-analysis",)):
    return SkillTrajectory(
        EVOLUTION_SCHEMA_VERSION,
        f"tr_{index}",
        "now",
        f"turn_{index}",
        None,
        "cli",
        "direct",
        "task",
        skills,
        (),
        None,
        "completed",
        None,
        1,
        0,
        0,
        failed,
        f"scope_{index}",
    )


def _write_skill(tmp_path) -> None:
    path = tmp_path / "skills" / "repo-analysis" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: repo-analysis\ndescription: Analyze Python repositories\n---\n"
        "Inspect source files.\n",
        encoding="utf-8",
    )


async def test_manual_review_requires_feedback_before_periodic_threshold(tmp_path) -> None:
    _write_skill(tmp_path)
    service, scheduler = _service(tmp_path)
    await service.record_trajectory(_trajectory(1))

    with pytest.raises(ValueError, match="requires user feedback"):
        await service.request_review(
            skill_name="repo-analysis",
            source_channel="webui",
            source_chat_id="skill-evolution",
            user_feedback=None,
        )

    assert scheduler.count == 0


async def test_feedback_allows_early_manual_review_with_persisted_evidence(tmp_path) -> None:
    _write_skill(tmp_path)
    service, scheduler = _service(tmp_path)
    await service.record_trajectory(_trajectory(1))

    review = await service.request_review(
        skill_name="repo-analysis",
        source_channel="webui",
        source_chat_id="skill-evolution",
        user_feedback="The dependency instructions are incomplete",
    )

    assert review.user_feedback == "The dependency instructions are incomplete"
    assert scheduler.count == 1


async def test_tenth_single_skill_trajectory_schedules_one_review(tmp_path) -> None:
    service, scheduler = _service(tmp_path)
    for index in range(1, 10):
        await service.record_trajectory(_trajectory(index))
    assert scheduler.count == 0

    await service.record_trajectory(_trajectory(10))

    assert scheduler.count == 1
    state = service.store.load_state().skills["repo-analysis"]
    assert state.trajectory_count == 10
    assert state.review_running is True


async def test_configured_fifth_trajectory_schedules_review(tmp_path) -> None:
    service, scheduler = _service(tmp_path, review_every_n_trajectories=5)
    for index in range(1, 5):
        await service.record_trajectory(_trajectory(index))
    assert scheduler.count == 0

    await service.record_trajectory(_trajectory(5))

    assert scheduler.count == 1


async def test_objective_failure_schedules_immediately(tmp_path) -> None:
    service, scheduler = _service(tmp_path)

    await service.record_trajectory(_trajectory(1, failed=True))

    assert scheduler.count == 1


async def test_multi_skill_trajectory_never_auto_schedules(tmp_path) -> None:
    service, scheduler = _service(tmp_path)

    await service.record_trajectory(
        _trajectory(1, failed=True, skills=("repo-analysis", "python-debug"))
    )

    assert scheduler.count == 0
    assert service.store.load_state().skills == {}
    assert len(service.store.list_trajectories()) == 1
