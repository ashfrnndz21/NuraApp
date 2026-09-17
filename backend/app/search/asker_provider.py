"""Which asker a deployment runs on.

`NURA_ASKER=rule` (the default) is today's behaviour, unchanged: `RuleBasedAsker`, a rule-based
retriever over templates (`app.search.ask.recall_stream`), behind the port. `NURA_ASKER=claude`
is the agent (`app.llm.ask_agent.ClaudeAsker`) — a real adapter behind the same port, not a
fixture — but Anthropic's first-party API does not process in SG or MY, and no in-region
provider exists yet, so it may only be built where every word it will ever be shown is demo or
test data: a declared demo (`NURA_DEMO_MODE=1`), the runtime-feature exception ADR 0017 sets
out — or the owner's own dev run on his own laptop, by his own choice (ADR 0017 addendum).
Anywhere else naming `claude` refuses to start rather than silently send a family's ask out of
region (`app.llm.residency.allow_external_model`, the one gate every Claude-backed adapter
calls). A name this build does not have refuses to start too.

When an in-region provider exists, it is a third name chosen here, behind the same port;
nothing above this module changes.
"""

from __future__ import annotations

from app.delivery.feed.claude_adapters import ClaudeSearcher
from app.llm.ask_agent import ClaudeAsker
from app.llm.client import client_for
from app.llm.residency import allow_external_model
from app.search.asker import Asker, RuleBasedAsker
from app.settings import Settings

RULE = "rule"
FIXTURE = "fixture"  # the name every other provider's default answers to; the rule-based asker here
CLAUDE = "claude"


class NoAsker(RuntimeError):
    """The deployment names an asker this build does not have."""


class ClaudeAskerOutsideDemo(RuntimeError):
    """`NURA_ASKER=claude` was named outside a declared demo or the owner's own dev run
    (`app.llm.residency.allow_external_model`, ADR 0017 and its addendum)."""


def asker_for(settings: Settings) -> Asker:
    if settings.asker in (RULE, FIXTURE):
        return RuleBasedAsker()
    if settings.asker == CLAUDE:
        allow_external_model(
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
            refusal=ClaudeAskerOutsideDemo,
            what="NURA_ASKER=claude",
        )
        searcher = ClaudeSearcher(
            api_key=settings.anthropic_api_key,
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
        )
        return ClaudeAsker(client_for(settings), searcher=searcher)
    raise NoAsker(
        f"no asker named {settings.asker!r}; only {RULE!r} and {CLAUDE!r} are built. Set "
        "NURA_ASKER=rule for a local run"
    )
