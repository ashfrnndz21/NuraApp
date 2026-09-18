"""Which drafter a deployment runs on, for care navigation's drafted messages (T3).

`NURA_DRAFTER=rule` (the default) is `RuleDrafter`: the catalogue's own templates, filled
from the need's own who/what/when, unchanged. `NURA_DRAFTER=claude` is the Claude-backed
drafter (`app.llm.navigation_draft.ClaudeDrafter`) — Anthropic's first-party API does not
process in SG or MY, so, exactly like the trace narrator and the agent asker before it, it
may only be built on a declared demo (`NURA_DEMO_MODE=1`) or a declared dev run
(`NURA_DEV_CODE_SENDER=1`) on the owner's own laptop (`app.llm.residency.allow_external_model`,
ADR 0017). Anywhere else naming `claude` refuses to start rather than silently send a real
family's need out of region. A name this build does not have refuses to start too.
"""

from __future__ import annotations

from app.llm.client import client_for
from app.llm.navigation_draft import ClaudeDrafter
from app.llm.residency import allow_external_model
from app.reasoning.navigation.models import Drafter
from app.reasoning.navigation.rule_drafter import RuleDrafter
from app.settings import Settings

RULE = "rule"
CLAUDE = "claude"


class NoDrafter(RuntimeError):
    """The deployment names a drafter this build does not have."""


class ClaudeDrafterOutsideDemo(RuntimeError):
    """NURA_DRAFTER=claude outside a declared demo or a declared dev run: Anthropic's
    first-party API processes outside SG and MY (ADR 0017)."""


def drafter_for(settings: Settings) -> Drafter:
    if settings.drafter == RULE:
        return RuleDrafter()
    if settings.drafter == CLAUDE:
        allow_external_model(
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
            refusal=ClaudeDrafterOutsideDemo,
            what="NURA_DRAFTER=claude",
        )
        return ClaudeDrafter(client_for(settings))
    raise NoDrafter(
        f"no drafter named {settings.drafter!r}; only {RULE!r} and {CLAUDE!r} are built. "
        "Set NURA_DRAFTER=rule for a local run"
    )
