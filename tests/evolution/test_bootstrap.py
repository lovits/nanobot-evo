from __future__ import annotations

from types import SimpleNamespace

from nanobot.bus.queue import MessageBus
from nanobot.command.router import CommandRouter
from nanobot.evolution.bootstrap import install_skill_evolution


class ExtensionHost:
    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self.runtime_resolver = object()
        self.bus = MessageBus()
        self.commands = CommandRouter()
        self.factories = []

    def register_hook_factory(self, factory) -> None:
        self.factories.append(factory)

    def schedule_background(self, coroutine) -> None:
        coroutine.close()


def test_disabled_bootstrap_is_a_noop_and_creates_no_state(tmp_path) -> None:
    host = ExtensionHost(tmp_path)

    service = install_skill_evolution(
        host,
        SimpleNamespace(enabled=False, review_model_preset=None),
    )

    assert service is None
    assert host.factories == []
    assert not (tmp_path / ".nanobot" / "evolution").exists()
    assert not host.commands.is_dispatchable_command("/evolve")


def test_enabled_bootstrap_registers_hook_and_commands(tmp_path) -> None:
    host = ExtensionHost(tmp_path)

    service = install_skill_evolution(
        host,
        SimpleNamespace(
            enabled=True,
            review_model_preset=None,
            review_every_n_trajectories=20,
        ),
    )

    assert service is not None
    assert host.skill_evolution is service
    assert service.review_every_n_trajectories == 20
    assert len(host.factories) == 1
    assert host.commands.is_dispatchable_command("/evolve")
    assert (tmp_path / ".nanobot" / "evolution").is_dir()
