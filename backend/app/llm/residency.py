"""The one residency gate every Claude-backed adapter's construction site calls (ADR 0017),
so the rule is written once and every caller shares it, rather than each adapter carrying its
own copy that could drift from the others.

A Claude-backed adapter — the document extractor (`app.ingestion.claude_extract.
ClaudeExtractor`), the feed's searcher and compressor (`app.delivery.feed.claude_adapters`),
the trace narrator (`app.llm.narrate.ClaudeNarrator`) — sends bytes or words to Anthropic's
first-party API, which does not process in SG or MY; no in-region provider exists yet. It may
build in exactly two deployments:

1. **A declared demo** (`NURA_DEMO_MODE=1`, ADR 0008): every document or word it is ever
   shown is demo or test data by declaration, so the exception ADR 0017 sets out applies
   silently — that declaration is said elsewhere, on every screen.
2. **A declared dev run** (`NURA_DEV_CODE_SENDER=1`) on the owner's own laptop: the data
   subject is the owner himself, choosing for himself to run his own documents through his
   own key (ADR 0017 addendum, 2026-09-17). This is not the public deployment's posture —
   nothing changes there — so this path logs plainly, every time, rather than passing
   silently the way the demo declaration does.

Anywhere else — the public deployment above all — this gate refuses.
"""

from __future__ import annotations

import logging

log = logging.getLogger("nura.llm.residency")


def allow_external_model(
    *, demo_mode: bool, dev_run: bool, refusal: type[Exception], what: str
) -> None:
    """Raise `refusal` unless `demo_mode` or `dev_run` is set.

    `refusal` is the caller's own exception type (`ClaudeExtractorOutsideDemo`,
    `ClaudeNarratorOutsideDemo`, `ClaudeAdapterNotAvailable`, …) so each adapter's construction
    site keeps naming its own failure the way its own tests and callers already expect; only
    the decision of *when* to raise it lives here now. `what` names the adapter in the
    refusal message and the dev-run log line, e.g. `"NURA_EXTRACTOR=claude"` or `"the Claude
    searcher"`.
    """
    if demo_mode:
        return
    if dev_run:
        log.warning(
            "%s: a declared dev run (NURA_DEV_CODE_SENDER=1) sends these bytes to the "
            "Anthropic API outside the region — the owner's own laptop, his own documents, "
            "his own key, his own choice. Never the public deployment, which stays on "
            "NURA_DEMO_MODE=1 and the fixtures.",
            what,
        )
        return
    raise refusal(
        f"{what} runs only on a declared demo (NURA_DEMO_MODE=1) or a declared dev run "
        "(NURA_DEV_CODE_SENDER=1) on the owner's own laptop: Anthropic's first-party API "
        "does not process in SG or MY, and no in-region provider exists yet (ADR 0017)."
    )
