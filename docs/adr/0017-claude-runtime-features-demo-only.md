# ADR 0017 — Claude-backed runtime features run only in a declared demo, on demo data

**Date** 2026-09-17 · **Status** accepted · **Decided by** the operator · **Stories** E02

## Context

E02's document extractor (`app.ingestion.claude_extract.ClaudeExtractor`) reads a photo or a
PDF with Anthropic's first-party API. The trace narrator (`app.llm.narrate.
ClaudeNarrator`) rephrases a step's own catalogue label the same demo-only way. Two more
runtime features are coming behind the same kind of adapter: the feed's searcher and
compressor (`app.delivery.feed.compress.Searcher`, `pdpa-data-map.md` §5). All four send bytes
or text outside the region to get an answer a rule cannot: reading a page, rephrasing a step
already taken, searching the web, compressing a result.

Anthropic's first-party API processes in the US or globally. It does not process in SG or
MY, and no in-region provider exists yet. The standing rule is unamended and does not bend
for these features: `pdpa-data-map.md` §5 says health data and identifier rows never leave
the region, no analytics vendor receives health data, and no model is trained on it.

An earlier version of the document extractor cited ADR 0008 (demo mode) as authority for
sending artefact bytes to a US endpoint. It is not: ADR 0008 authorises a deployment running
on the fixtures — "the photo and PDF reader" among them — so that the owner can open Nura on
his phone before the real providers exist. It says nothing about where a *real* adapter's
bytes may go, and its own "Consequences" section says free text can still carry real
information even inside a demo. Citing it that way let a real adapter's residency story ride
on a decision that was about fixtures, not about processors. This ADR is the actual decision;
the extractor's and the searcher's own module docstrings cite it, not ADR 0008.

## Decision

1. **A Claude-backed runtime feature may run only where every byte or word it is shown is
   demo or test data.** In practice that is exactly one declaration: `NURA_DEMO_MODE=1`
   (ADR 0008). A dev run alone (`NURA_DEV_CODE_SENDER=1`) is not enough — a laptop's own test
   papers are not "demo or test data" the way a wiped, banner-carrying, test-numbers-only
   deployment is. `extractor_for` (`app.ingestion.extract_provider`) enforces this at the one
   place the adapter is built; a later Claude-backed feature enforces it the same way, at its
   own construction site, not by relying on this ADR to be read.
2. **This is a runtime-feature exception, not a residency policy.** It does not amend
   `pdpa-data-map.md` §5: a real family's papers, on a real deployment, still never leave the
   region. It exists because a demo, by ADR 0008's own six promises, holds nothing that
   claims to be real: no real phone number, a nightly wipe, a banner on every screen. What a
   demo does not fully close off — free text a person could type real information into — is
   accepted for the demo generally in ADR 0008 and is not reopened here.
3. **Every Claude-backed adapter's bytes reaching Anthropic is audited as a reach outside the
   region**, distinct from an ordinary read or write of the row it produces, so the trail
   itself says a page went to a third party rather than leaving that to be inferred from
   which extractor was configured (`app.ingestion.review.review_artifact`,
   `EXTERNAL_MODEL_PROCESSOR`). The demo-only processor is named beside the recording
   pattern's own third parties (`docs/trust/recording-consent.md` §3), so a person reading
   either page finds the same fact.
4. **Model calls go through `app/llm/`** (`backend/CLAUDE.md`): one client factory
   (`app.llm.client.client_for`) every Claude-backed adapter shares, and prompts as files
   under `app/llm/prompts/`, never a string in an adapter's own module. A region-pinned
   provider, when one exists, is a new function there and a new name `extractor_for` (or the
   searcher's and compressor's own provider functions) choose — nothing above `app/llm/`
   needs to change.
5. **An in-region provider replaces the exception, not the port.** When one exists, it is a
   third adapter behind `Extractor` (or `Searcher`/`Compressor`), chosen the same way, and
   this ADR's declaration requirement no longer gates it. This ADR is retired, not amended,
   on that day.

## Consequences

- The document extractor's and the extractor provider's module docstrings cite this ADR for
  the residency exception; ADR 0008 is cited only for what it actually decided (the demo
  declaration, the fixtures it gates).
- A deployment that is not a declared demo cannot name `NURA_EXTRACTOR=claude` (or, later,
  a Claude-backed searcher or compressor) and start. `tests/test_claude_extractor.py` holds
  this for the extractor.
- Every call that reaches Anthropic writes an audit line naming the reach, in the same unit
  of work as the card it produces, so a reader of the trail can tell a Claude-backed read
  from a fixture read without inspecting deployment configuration.
- `docs/trust/recording-consent.md` names Anthropic as the demo-only processor for these
  features, beside the questions counsel still has open for the speech and model providers a
  real deployment will use.

## Alternatives considered

- **Read ADR 0008 as covering this.** It does not name a residency exception, and its own
  text says free text can still carry real information — extending it to authorise sending
  artefact bytes to a US endpoint was the defect this ADR fixes. Rejected.
- **Gate on `NURA_EXTRACTOR=claude` alone, with no demo requirement.** Lets a real deployment
  set the extractor name without also being a demo, sending a real family's paper to a
  first-party US endpoint. Rejected; the check is on the demo declaration, not the adapter
  name.
- **Wait for an in-region provider before building any Claude-backed feature.** Leaves E02's
  document extraction, and the feed's search and compression, without a real adapter to test
  the port against, and the owner's demo without real reading behind it. Rejected for Phase 0
  and the demo's timeline; the exception is narrow and auditable instead.
