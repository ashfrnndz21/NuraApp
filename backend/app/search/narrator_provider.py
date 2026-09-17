"""Which narrator a deployment runs on.

`NURA_NARRATOR=fixture` (the default) is today's behaviour, unchanged
(`app.search.narrate.FixtureNarrator`): the catalogue's own label for every step, every time.
`NURA_NARRATOR=claude` is the Claude-backed narrator (`app.llm.narrate.
ClaudeNarrator`) — a real adapter behind the same port, not a fixture — but Anthropic's
first-party API does not process in SG or MY, and no in-region provider exists yet, so it may
only be built where every word it will ever be shown is demo or test data, or the person shown
it is the one choosing to show it: a declared demo (`NURA_DEMO_MODE=1`) or a declared dev run
(`NURA_DEV_CODE_SENDER=1`) on the owner's own laptop, the runtime-feature exception ADR 0017
sets out (mirroring `app.ingestion.extract_provider.extractor_for`, which holds the same rule
for the document extractor). Anywhere else — the public deployment above all — naming `claude`
refuses to start rather than silently send a real family's trace out of region. `app.llm.
residency.allow_external_model` is the one gate this and every other Claude-backed adapter's
construction site shares. A name this build does not have refuses to start too.

When an in-region provider exists, it is a third name chosen here, behind the same port;
nothing above this module changes.
"""

from __future__ import annotations

from app.llm.client import client_for
from app.llm.narrate import ClaudeNarrator
from app.llm.residency import allow_external_model
from app.search.narrate import FixtureNarrator, Narrator
from app.settings import Settings

FIXTURE = "fixture"
CLAUDE = "claude"


class NoNarrator(RuntimeError):
    """The deployment names a narrator this build does not have."""


class ClaudeNarratorOutsideDemo(RuntimeError):
    """NURA_NARRATOR=claude outside a declared demo (NURA_DEMO_MODE=1) or a declared dev run
    (NURA_DEV_CODE_SENDER=1): Anthropic's first-party API processes outside SG and MY, so this
    adapter may only be built where every word it will be shown is demo or test data, or the
    person shown it is the one choosing to show it (ADR 0017)."""


def narrator_for(settings: Settings) -> Narrator:
    if settings.narrator == FIXTURE:
        return FixtureNarrator()
    if settings.narrator == CLAUDE:
        allow_external_model(
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
            refusal=ClaudeNarratorOutsideDemo,
            what="NURA_NARRATOR=claude",
        )
        return ClaudeNarrator(client_for(settings))
    raise NoNarrator(
        f"no narrator named {settings.narrator!r}; only {FIXTURE!r} and {CLAUDE!r} are "
        "built. Set NURA_NARRATOR=fixture for a local run"
    )
