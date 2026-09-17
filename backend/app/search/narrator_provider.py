"""Which narrator a deployment runs on.

`NURA_NARRATOR=fixture` (the default) is today's behaviour, unchanged
(`app.search.narrate.FixtureNarrator`): the catalogue's own label for every step, every time.
`NURA_NARRATOR=claude` is the Claude-backed narrator (`app.search.claude_narrate.
ClaudeNarrator`) — a real adapter behind the same port, not a fixture — but Anthropic's
first-party API does not process in SG or MY, and no in-region provider exists yet, so it may
only be built where every word it will ever be shown is demo or test data: a declared demo
(`NURA_DEMO_MODE=1`), the runtime-feature exception ADR 0017 sets out (mirroring `app.
ingestion.extract_provider.extractor_for`, which holds the same rule for the document
extractor). Anywhere else — a laptop dev run included — naming `claude` refuses to start
rather than silently send a real family's trace out of region. A name this build does not
have refuses to start too.

When an in-region provider exists, it is a third name chosen here, behind the same port;
nothing above this module changes.
"""

from __future__ import annotations

from app.llm.client import client_for
from app.search.claude_narrate import ClaudeNarrator
from app.search.narrate import FixtureNarrator, Narrator
from app.settings import Settings

FIXTURE = "fixture"
CLAUDE = "claude"


class NoNarrator(RuntimeError):
    """The deployment names a narrator this build does not have."""


class ClaudeNarratorOutsideDemo(RuntimeError):
    """NURA_NARRATOR=claude outside a declared demo (NURA_DEMO_MODE=1): Anthropic's
    first-party API processes outside SG and MY, so this adapter may only be built where
    every word it will be shown is demo or test data (ADR 0017)."""


def narrator_for(settings: Settings) -> Narrator:
    if settings.narrator == FIXTURE:
        return FixtureNarrator()
    if settings.narrator == CLAUDE:
        if not settings.demo_mode:
            raise ClaudeNarratorOutsideDemo(
                "NURA_NARRATOR=claude runs only on a declared demo (NURA_DEMO_MODE=1): "
                "Anthropic's first-party API does not process in SG or MY, no in-region "
                "provider exists yet, and a demo is the only deployment where every word "
                "shown is demo or test data (ADR 0017). Use NURA_NARRATOR=fixture (the "
                "default) anywhere else."
            )
        return ClaudeNarrator(client_for(settings))
    raise NoNarrator(
        f"no narrator named {settings.narrator!r}; only {FIXTURE!r} and {CLAUDE!r} are "
        "built. Set NURA_NARRATOR=fixture for a local run"
    )
