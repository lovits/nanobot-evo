from __future__ import annotations

from types import SimpleNamespace

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.command.router import CommandContext, CommandRouter
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


def _context(raw: str) -> CommandContext:
    message = InboundMessage(
        channel="cli",
        sender_id="user",
        chat_id="direct",
        content=raw,
    )
    return CommandContext(
        msg=message,
        session=None,
        key=message.session_key,
        raw=raw,
    )


async def test_evolve_status_uses_existing_command_router(tmp_path) -> None:
    host = ExtensionHost(tmp_path)
    install_skill_evolution(
        host,
        SimpleNamespace(enabled=True, review_model_preset=None),
    )

    response = await host.commands.dispatch(_context("/evolve"))

    assert response is not None
    assert response.content == ("NanoEvo status\nTracked skills: 0\nPending proposals: 0")


async def test_evolve_rejects_unknown_action_without_model_call(tmp_path) -> None:
    host = ExtensionHost(tmp_path)
    install_skill_evolution(
        host,
        SimpleNamespace(enabled=True, review_model_preset=None),
    )

    response = await host.commands.dispatch(_context("/evolve unknown"))

    assert response is not None
    assert response.content.startswith("Usage: /evolve")
