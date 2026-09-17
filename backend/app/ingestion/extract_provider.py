"""Which reader a deployment runs on.

`NURA_EXTRACTOR=fixture` (the default) is the paper fixtures (`app.ingestion.extract.
FixtureExtractor`) over `NURA_PAPER_FIXTURES`, the only one a dev run or a laptop test may
build (`app.fixtures.check_fixtures`). `NURA_EXTRACTOR=claude` is the Claude-backed reader
(`app.ingestion.claude_extract.ClaudeExtractor`) — a real adapter behind the same port, not a
fixture — but Anthropic's first-party API does not process in SG or MY (ADR 0008), so it may
only be built where every document it will ever be shown is test data by declaration: a demo
(`NURA_DEMO_MODE=1`). Anywhere else — a laptop dev run included — naming `claude` refuses to
start rather than silently send a real person's paper out of region. A name this build does
not have refuses to start too.

When an in-region provider exists, it is a third name chosen here, behind the same port;
nothing above this module changes.
"""

from __future__ import annotations

import os
from pathlib import Path

from anthropic import AsyncAnthropic

from app.ingestion.claude_extract import ClaudeExtractor
from app.ingestion.extract import Extractor, FixtureExtractor
from app.settings import MissingSetting, Settings

FIXTURE = "fixture"
CLAUDE = "claude"


class NoExtractor(RuntimeError):
    """The deployment names an extractor this build does not have."""


class ClaudeExtractorOutsideDemo(RuntimeError):
    """NURA_EXTRACTOR=claude outside a declared demo (NURA_DEMO_MODE=1): Anthropic's
    first-party API processes outside SG and MY, so this adapter may only be built where
    every document it will be shown is test data by declaration."""


def extractor_for(settings: Settings) -> Extractor:
    if settings.extractor == FIXTURE:
        if settings.paper_fixtures is None:
            raise MissingSetting("NURA_PAPER_FIXTURES is not set and there is no other extractor yet")
        return FixtureExtractor(Path(settings.paper_fixtures))
    if settings.extractor == CLAUDE:
        if not settings.demo_mode:
            raise ClaudeExtractorOutsideDemo(
                "NURA_EXTRACTOR=claude runs only on a declared demo (NURA_DEMO_MODE=1): "
                "Anthropic's first-party API does not process in SG or MY (ADR 0008), and a "
                "demo is the only deployment where every document is test data by "
                "declaration. Use NURA_EXTRACTOR=fixture (the default) anywhere else."
            )
        if settings.anthropic_api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise MissingSetting(
                "NURA_EXTRACTOR=claude needs NURA_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) "
                "set; from the platform's secrets, never the repo"
            )
        return ClaudeExtractor(AsyncAnthropic(api_key=settings.anthropic_api_key))
    raise NoExtractor(
        f"no extractor named {settings.extractor!r}; only {FIXTURE!r} and {CLAUDE!r} are "
        "built. Set NURA_EXTRACTOR=fixture for a local run"
    )
