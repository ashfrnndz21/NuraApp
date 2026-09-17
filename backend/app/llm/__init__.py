"""Model calls: the one place `app/llm/` package for the client Nura hands a request through
and the prompts asked of it (`backend/CLAUDE.md`).

`app.llm.client` builds the Anthropic client every Claude-backed adapter shares
(`app.ingestion.claude_extract.ClaudeExtractor` today; the feed's searcher and compressor
when they land). `app.llm.prompts` loads a prompt by name from files under `app/llm/prompts/`,
never a string held in an adapter's own module. Both exist only so a caller never constructs
the SDK's client or writes a prompt inline — an adapter asks this package for either, and a
new region-pinned provider or a changed prompt is a change here, not at every call site.

Demo-only (ADR 0017). Every caller of this package today runs only with `NURA_DEMO_MODE=1`,
on demo or test data — Anthropic's first-party API does not process in SG or MY. This package
is the client and prompt plumbing; the residency refusal itself stays where each adapter is
built (`app.ingestion.extract_provider.extractor_for`), so it is enforced once per adapter,
not duplicated here.
"""

from __future__ import annotations
