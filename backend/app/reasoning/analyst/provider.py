"""Which `Analyst` a deployment runs on (`NURA_ANALYST`, mirroring `app.search.narrator_
provider.narrator_for`): `rule` (the default) is `RuleAnalyst`, unchanged; `claude` is
`ClaudeAnalyst`, gated by `app.llm.residency.allow_external_model` the same way every other
Claude-backed adapter here is — it may only be built on a declared demo (`NURA_DEMO_MODE=1`)
or a declared dev run (`NURA_DEV_CODE_SENDER=1`) on the owner's own laptop, never the public
deployment. A name this build does not have refuses to start.
"""

from __future__ import annotations

from app.drugs.registry import DrugRegistry
from app.llm.client import client_for
from app.llm.residency import allow_external_model
from app.reasoning.analyst.claude_adapter import ClaudeAnalyst
from app.reasoning.analyst.port import Analyst
from app.reasoning.analyst.rule import RuleAnalyst
from app.settings import Settings

RULE = "rule"
CLAUDE = "claude"


class NoAnalyst(RuntimeError):
    """The deployment names an `Analyst` this build does not have."""


class ClaudeAnalystOutsideDemo(RuntimeError):
    """NURA_ANALYST=claude outside a declared demo (NURA_DEMO_MODE=1) or a declared dev run
    (NURA_DEV_CODE_SENDER=1): Anthropic's first-party API processes outside SG and MY, so this
    adapter may only be built where every word it will be shown is demo or test data, or the
    person shown it is the one choosing to show it (ADR 0017)."""


def analyst_for(settings: Settings, *, registry: DrugRegistry | None = None) -> Analyst:
    if settings.analyst == RULE:
        return RuleAnalyst(registry=registry)
    if settings.analyst == CLAUDE:
        allow_external_model(
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
            refusal=ClaudeAnalystOutsideDemo,
            what="NURA_ANALYST=claude",
        )
        return ClaudeAnalyst(client=client_for(settings), registry=registry)
    raise NoAnalyst(
        f"no Health Analyst named {settings.analyst!r}; only {RULE!r} and {CLAUDE!r} are "
        "built. Set NURA_ANALYST=rule for a local run"
    )


__all__ = ["CLAUDE", "RULE", "ClaudeAnalystOutsideDemo", "NoAnalyst", "analyst_for"]
