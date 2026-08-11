"""Slash-command adapter for the SkillEvolutionService."""

from __future__ import annotations

from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.evolution.service import SkillEvolutionService


def register_evolution_commands(
    router: CommandRouter,
    service: SkillEvolutionService,
) -> None:
    async def handle(ctx: CommandContext) -> OutboundMessage:
        try:
            content = await _dispatch(ctx, service)
        except (KeyError, ValueError) as exc:
            content = str(exc).strip("'")
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata=dict(ctx.msg.metadata or {}),
        )

    router.exact("/evolve", handle)
    router.prefix("/evolve ", handle)


async def _dispatch(
    ctx: CommandContext,
    service: SkillEvolutionService,
) -> str:
    args = ctx.args.strip()
    if not args:
        status = service.get_status()
        lines = [
            "NanoEvo status",
            f"Tracked skills: {len(status.states)}",
            f"Pending proposals: {len(status.pending_proposals)}",
        ]
        lines.extend(
            f"- {proposal.proposal_id}: {proposal.skill_name} — {proposal.reason}"
            for proposal in status.pending_proposals
        )
        return "\n".join(lines)

    action, _, remainder = args.partition(" ")
    action = action.lower()
    remainder = remainder.strip()
    if action == "review":
        skill, _, feedback = remainder.partition(" ")
        if not skill:
            raise ValueError("Usage: /evolve review <skill> [feedback]")
        request = await service.request_review(
            skill_name=skill,
            source_channel=ctx.msg.channel,
            source_chat_id=ctx.msg.chat_id,
            user_feedback=feedback or None,
        )
        return f"Review {request.review_id} scheduled for {skill}."
    if action == "approve":
        if not remainder or " " in remainder:
            raise ValueError("Usage: /evolve approve <proposal-id>")
        proposal = service.approve_proposal(remainder)
        return f"Proposal {proposal.proposal_id}: {proposal.status.value}."
    if action == "reject":
        if not remainder or " " in remainder:
            raise ValueError("Usage: /evolve reject <proposal-id>")
        proposal = service.reject_proposal(remainder)
        return f"Proposal {proposal.proposal_id}: {proposal.status.value}."
    if action == "restore":
        if not remainder or " " in remainder:
            raise ValueError("Usage: /evolve restore <skill>")
        proposal = service.restore_skill(remainder)
        return f"Restored {proposal.skill_name} from proposal {proposal.proposal_id}."
    raise ValueError(
        "Usage: /evolve [review <skill> [feedback] | approve <id> | reject <id> | restore <skill>]"
    )


__all__ = ["register_evolution_commands"]
