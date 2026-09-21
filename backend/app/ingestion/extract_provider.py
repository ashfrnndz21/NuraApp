"""Which reader a deployment runs on.

`NURA_EXTRACTOR=fixture` (the default) is the paper fixtures (`app.ingestion.extract.
FixtureExtractor`) over `NURA_PAPER_FIXTURES`, the only one a dev run or a laptop test may
build (`app.fixtures.check_fixtures`). `NURA_EXTRACTOR=claude` is the Claude-backed reader
(`app.ingestion.claude_extract.ClaudeExtractor`) — a real adapter behind the same port, not a
fixture — but Anthropic's first-party API does not process in SG or MY, and no in-region
provider exists yet, so it may only be built where every document it will ever be shown is
demo or test data, or the person shown it is the one choosing to show it: a declared demo
(`NURA_DEMO_MODE=1`) or a declared dev run (`NURA_DEV_CODE_SENDER=1`) on the owner's own
laptop, the runtime-feature exception ADR 0017 sets out (not ADR 0008, which is the demo
declaration itself and does not reach to residency). Anywhere else — the public deployment
above all — naming `claude` refuses to start rather than silently send a real person's paper
out of region. `app.llm.residency.allow_external_model` is the one gate this and every other
Claude-backed adapter's construction site shares. A name this build does not have refuses to
start too.

When an in-region provider exists, it is a third name chosen here, behind the same port;
nothing above this module changes.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.claude_extract import ClaudeExtractor
from app.ingestion.extract import Extractor, FixtureExtractor
from app.llm.client import client_for
from app.llm.models import Task
from app.llm.residency import allow_external_model
from app.settings import MissingSetting, Settings

FIXTURE = "fixture"
CLAUDE = "claude"


class NoExtractor(RuntimeError):
    """The deployment names an extractor this build does not have."""


class ClaudeExtractorOutsideDemo(RuntimeError):
    """NURA_EXTRACTOR=claude outside a declared demo (NURA_DEMO_MODE=1) or a declared dev run
    (NURA_DEV_CODE_SENDER=1): Anthropic's first-party API processes outside SG and MY, so this
    adapter may only be built where every document it will be shown is demo or test data, or
    the person shown it is the one choosing to show it (ADR 0017)."""


def extractor_for(settings: Settings) -> Extractor:
    if settings.extractor == FIXTURE:
        if settings.paper_fixtures is None:
            raise MissingSetting(
                "NURA_PAPER_FIXTURES is not set and there is no other extractor yet"
            )
        return FixtureExtractor(Path(settings.paper_fixtures))
    if settings.extractor == CLAUDE:
        allow_external_model(
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
            refusal=ClaudeExtractorOutsideDemo,
            what="NURA_EXTRACTOR=claude",
        )
        return ClaudeExtractor(client_for(settings), model=settings.models.for_task(Task.EXTRACT))
    raise NoExtractor(
        f"no extractor named {settings.extractor!r}; only {FIXTURE!r} and {CLAUDE!r} are "
        "built. Set NURA_EXTRACTOR=fixture for a local run"
    )
