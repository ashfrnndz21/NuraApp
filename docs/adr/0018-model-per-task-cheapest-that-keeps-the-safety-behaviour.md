# ADR 0018 — Model per task, cheapest that keeps the safety behaviour

**Date** 2026-09-21 · **Status** accepted · **Decided by** the owner · **Stories** RE-07, E02, E03-05, T3

## Context

Every Claude-backed adapter hard-coded its own model id as a literal: `MODEL = "claude-
opus-5"` in the feed searcher and compressor (`app.delivery.feed.claude_adapters`), the clip
maker's script step (`app.delivery.feed.clipmaker`), the document extractor (`app.ingestion.
claude_extract`), the cost estimator (`app.insurance.cost_expectation`), Ask
(`app.llm.ask_agent`), the trace narrator (`app.llm.narrate`) and the navigation drafter
(`app.llm.navigation_draft`); the Health Analyst alone ran the older `claude-sonnet-4-5`
(`app.reasoning.analyst.claude_adapter`). Every one of them defaulted to the most expensive
model whether the task needed it or not.

Live, one feed run for one person made about 48 Opus calls with web search and produced one
card, and drained two credit top-ups. The owner's own words: "use lower cost models where
needed" and "don't use this wastefully." `backend/CLAUDE.md` already forbids hard-coding a
provider or a model in a caller — every model id above was exactly that defect, just not yet
named as one.

## Decision

1. **One table, one place: `app.llm.models`.** `Task` names what a call is *for*
   (`extract`, `ask`, `analyst`, `search`, `compress`, `clip`, `narrate`, `draft`,
   `estimate`) — never which model answers it. `DEFAULT_MODELS` maps each task to the
   cheapest model that still keeps the task's behaviour; `model_table_for` resolves it once,
   at startup, folding in an env override per task (`NURA_MODEL_EXTRACT`,
   `NURA_MODEL_ASK`, `NURA_MODEL_ANALYST`, `NURA_MODEL_SEARCH`, `NURA_MODEL_COMPRESS`,
   `NURA_MODEL_CLIP`, `NURA_MODEL_NARRATE`, `NURA_MODEL_DRAFT`, `NURA_MODEL_ESTIMATE`) and
   checking every id — default or override — against `ALLOWED_MODELS`, the ids this build
   actually knows how to call. An id outside that list refuses to start (`UnknownModel`),
   the same `MissingSetting`-style posture every other setting in `app.settings` is held to,
   rather than let an adapter's first real call fail on a typo.
2. **`Settings.models` carries the resolved table down**, the way every other setting
   already reaches its adapter: each `*_for` factory (`searcher_for`, `compressor_for`,
   `extractor_for`, `narrator_for`, `asker_for`, `drafter_for`, `analyst_for`,
   `estimator_for`) reads its own task's model from `settings.models.for_task(Task.X)` and
   passes it into the adapter's constructor as `model=`. No adapter reads an environment
   variable or names a model id itself; the module-level `MODEL` constant each adapter kept
   is now only the default a direct construction (chiefly a test) falls back to when it does
   not pass `model=`, itself sourced from `DEFAULT_MODELS`, never a second hard-coded string.
3. **The assignment, cheapest first:**
   - **Opus 5** (`claude-opus-5`) — reading a paper (`extract`) and Ask (`ask`). A misread
     field or a wrong answer reaches a family directly; quality and safety matter most here,
     so this task keeps the dearest model rather than save on the calls where a mistake
     costs the most.
   - **Sonnet 5** (`claude-sonnet-5`) — the Health Analyst (`analyst`, replacing the older
     `claude-sonnet-4-5`: it only chooses and rephrases from `RuleAnalyst`'s own already-read
     candidates, never a first read of its own), the feed searcher (`search` — it calls the
     server tools `web_search_20260209`/`web_fetch_20260209`, which Haiku 4.5 does not
     support, so it cannot move down; Sonnet 5 is the cheapest model that still supports
     them), the cost estimator (`estimate` — one grounded fetch and a handful of typed
     numbers) and the navigation drafter (`draft` — a short message from a few named fields,
     checked against `RuleDrafter`'s own guards before it is trusted).
   - **Haiku 4.5** (`claude-haiku-4-5-20251001`) — the feed compressor (`compress` —
     rewriting an already-fetched page's text into plain words), the clip maker's script step
     (`clip` — 4-6 spoken lines from evidence already on the record plus one fetched page)
     and the narrator (`narrate` — rephrasing a step that already happened, never deciding
     anything). All three are short rewrites over text Nura already has, not open-ended
     reasoning, so the cheapest model keeps the behaviour.
4. **The run itself is capped, not only the model.** `Settings.max_jobs_per_run`
   (`NURA_MAX_JOBS_PER_RUN`, default 6) bounds how many of a day's self-searches one
   background run actually executes: the plan's first N jobs, in the broker's own order
   (`app.delivery.feed.compose.plan_learning_jobs`), run; the rest are left untouched, due
   for a later run — ordinarily the next day's (`app.delivery.feed.background._run`). The
   feed searcher's own server-tool use is capped too (`SEARCH_TOOL_MAX_USES = 3` on
   `web_search`/`web_fetch`), so one job cannot fan out into many searches the way the live
   incident's one job did. The cheaper model and the run cap are two different halves of the
   same fix: the model decides what one call costs, the cap decides how many calls one run
   can make.
5. **A call counter, for a live check to read back.** `app.llm.call_counter` is a lightweight
   per-process count of external model calls by task and model — counts only, never content,
   never a token count. Every adapter's own call site calls `record_call(task, model)` right
   where it calls the SDK. A feed run logs its own delta once, and `GET /dev/model-calls`
   (dev runs only, `settings.dev_code_sender`, the same gate `app.channels.api.dev_clock`
   already holds every other `/dev/*` door to) reads the process's running total back over
   HTTP, so an operator watching a live check can say exactly how many calls it made rather
   than estimate from a log line's prose.

## Consequences

- Every hard-coded `MODEL = "claude-…"` literal in a Claude-backed adapter is gone; the
  model an adapter calls with is always the argument its `*_for` factory passed it, sourced
  from `Settings.models`. `tests/test_model_selection.py` asserts, per factory, that the
  constructed adapter carries its own task's model — `searcher._model`,
  `compressor._model`, `extractor._model`, `estimator._model`, `narrator._model`,
  `drafter._model`, `analyst._model`, and `asker._model` alongside its own
  `ClaudeSearcher`'s `_model` for Ask's own tool use.
- `tests/test_claude_feed_adapters.py` and `tests/test_narrator.py` had asserted the old,
  uniform `"claude-opus-5"` on every call; both are updated to the task's new default
  (Sonnet 5 for the searcher, Haiku 4.5 for the compressor and the narrator) — the same
  live-shape assertions (`output_config.format.schema`, never the `json_schema`-wrapper
  shape a 400 was hit on live 2026-09-18), now also pinning the right model.
- `app.insurance.cost_expectation.ESTIMATE_SCHEMA` carried that same wrapper bug —
  `{"name", "schema", "strict"}` instead of the flat schema `output_config.format.schema`
  actually reads — caught only because this task touched the file for the model swap and
  there was no `test_the_structured_output_schema_is_one_the_api_accepts`-style test on this
  adapter to have caught it sooner. Fixed alongside the model change, with the same
  regression-style comment `SEARCH_SCHEMA`'s docstring carries.
- `tests/test_feed_background.py::
  test_a_plan_bigger_than_the_run_cap_runs_only_the_first_n_and_defers_the_rest` exercises
  the run cap end to end: four distinct medicines queue more jobs than the default cap, only
  six run, the rest are left with no `last_run_at` at all, and `RunRecord.deferred` /
  `FeedJobsOut.deferred` both say how many.
- `docs/run-real-on-your-laptop.md` carries the model table, the env overrides and the run
  cap, so a laptop run's own cost is visible before it is made, not discovered after.

## Alternatives considered

- **Pass an explicit `model=` at every call site instead of a table.** Leaves the actual
  assignment (which task gets which model, and why) scattered across eight files again, and
  gives `backend/CLAUDE.md`'s "no hard-coded model in a caller" nothing to point at as the
  one place that decides. Rejected.
- **One model for every task, chosen once.** The searcher's own server tools need a model
  that supports them (ruling out Haiku 4.5 for that one task); Ask and extraction carry more
  risk per mistake than a rewrite of text Nura already has. A single model either overpays
  on the cheap tasks or underpays on the risky ones. Rejected.
- **Leave the run uncapped and rely on the cheaper models alone.** The live incident was a
  fan-out — about 48 calls behind one card — not only a choice of the dearest model; a
  cheaper model still multiplied by an unbounded run is still an unbounded bill. Rejected;
  the run cap and the per-call `max_uses` cap are both kept, alongside the model table.
- **A full token-and-cost ledger instead of a call counter.** Reasonable for a hosted
  deployment with a bill to reconcile, but out of scope for a laptop and a demo's own clock;
  a call counter is enough for an operator to see a fan-out coming, without carrying any of
  a person's content or token counts. Rejected for now; a later, hosted deployment may want
  the fuller ledger.
