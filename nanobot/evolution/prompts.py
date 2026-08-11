"""Prompts for the isolated evidence review loop."""

from __future__ import annotations

import json

from nanobot.evolution.models import ReviewRequest

REVIEW_SYSTEM_PROMPT = """\
You review whether an existing Workspace Skill needs one small, reusable correction.

You are not editing code and you are not allowed to create a new Skill. Use only the
provided review_evidence and skill_manage tools.

Required process:
1. Call review_evidence(action="read_skill") exactly once.
2. Call review_evidence(action="read_trajectories") exactly once. The returned compact
   projection is deliberately shaped so every authorized trace remains visible.
   No read_file tool exists; never request arbitrary files or repeat evidence reads.
3. Separate Skill defects from model mistakes, repository-specific facts, environment
   failures, and stylistic preferences.
4. Propose a patch only when one or more attributed trajectories directly verify a
   reusable Skill defect. User feedback may focus the review but is not evidence itself.
5. If evidence is insufficient, return NO_CHANGE without calling skill_manage.
6. Otherwise call skill_manage exactly once with one exact old_text/new_text replacement.
7. Never add absolute paths, credentials, hidden reasoning, repository-specific answers,
   new permissions, or a changed Skill name.

The deterministic policy is authoritative. A rejected tool call means the proposal is
not allowed; do not try to bypass it.
"""


def build_review_messages(request: ReviewRequest) -> list[dict[str, str]]:
    payload = json.dumps(request.to_dict(), ensure_ascii=False, indent=2)
    user = (
        "Review this request. Use the tools to inspect its bound evidence.\n\n"
        f"{payload}\n\n"
        "Finish with either NO_CHANGE or a short summary of the Pending Proposal created."
    )
    return [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


__all__ = ["REVIEW_SYSTEM_PROMPT", "build_review_messages"]
