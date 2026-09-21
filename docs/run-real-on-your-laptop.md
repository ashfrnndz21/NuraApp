# Running the real Claude adapters on your own laptop

A dev run (`make dev`) answers everything from fixtures by default — no key needed, nothing
you type ever leaves your machine. This page is for the one thing more: turning on the real
document reader, the real feed search and compression, or the real trace narrator, against
your own documents, with your own Anthropic key, on your own laptop only. This never turns
anything on for `nura-sg` or any other hosted deployment — those stay on `NURA_DEMO_MODE=1`
and the fixtures regardless of what you export here (`docs/deploy-demo.md` §5).

Why this is allowed here and nowhere else: Anthropic's first-party API does not process in
Singapore or Malaysia, and no in-region provider exists yet (ADR 0017). A real deployment's
data must never leave the region for this. A dev run is different — you are the data subject,
choosing for yourself to run your own papers through your own key (ADR 0017's 2026-09-17
addendum, `app/llm/residency.py`). Nothing here changes that standing rule for anyone else's
data.

## What each switch turns on

| Switch | Turns on | Port |
|---|---|---|
| `NURA_EXTRACTOR=claude` | The real photo/PDF reader (`app.ingestion.claude_extract.ClaudeExtractor`) | `Extractor` |
| `NURA_SEARCHER=claude` | The feed's real web search, over the allowlist only | `Searcher` |
| `NURA_COMPRESSOR=claude` | The feed's real plain-words card, grounded on the fetched page | `Compressor` |
| `NURA_NARRATOR=claude` | The trace narrator rephrasing a step's own catalogue label | `Narrator` |
| `NURA_ASKER=claude` | The agent asker deciding for itself what to look at (`app.llm.ask_agent.ClaudeAsker`) | `Asker` |
| `NURA_ANALYST=claude` | The Health Analyst choosing and rephrasing from the rule read (`app.reasoning.analyst.claude_adapter.ClaudeAnalyst`) | `Analyst` |
| `NURA_DRAFTER=claude` | The navigation drafter, checked against `RuleDrafter`'s own guards (T3) | `Drafter` |
| `NURA_ESTIMATOR=claude` | The cost estimator's one grounded fetch of a benchmark's own page (T3) | `Estimator` |

Any of these on its own, or several together. Leave the rest unset — an unset switch stays
`fixture` (or `rule`), today's behaviour, unchanged.

## The model each task runs on

`backend/CLAUDE.md` forbids hard-coding a model in a caller: `app.llm.models` is the one
table every switch above actually reads its model from (ADR 0018), the cheapest model that
still keeps the task's behaviour. Reading a paper and Ask stay on the dearest model — a
mistake there reaches a family directly; the searcher stays off Haiku 4.5 because its server
tools (`web_search_20260209`/`web_fetch_20260209`) need Sonnet 5 or above.

| Task | Default model | Override |
|---|---|---|
| `extract` (the document reader) | `claude-opus-5` | `NURA_MODEL_EXTRACT` |
| `ask` (Ask) | `claude-opus-5` | `NURA_MODEL_ASK` |
| `analyst` (the Health Analyst) | `claude-sonnet-5` | `NURA_MODEL_ANALYST` |
| `search` (the feed searcher) | `claude-sonnet-5` | `NURA_MODEL_SEARCH` |
| `estimate` (the cost estimator) | `claude-sonnet-5` | `NURA_MODEL_ESTIMATE` |
| `draft` (the navigation drafter) | `claude-sonnet-5` | `NURA_MODEL_DRAFT` |
| `compress` (the feed compressor) | `claude-haiku-4-5-20251001` | `NURA_MODEL_COMPRESS` |
| `clip` (the clip maker's script step) | `claude-haiku-4-5-20251001` | `NURA_MODEL_CLIP` |
| `narrate` (the trace narrator) | `claude-haiku-4-5-20251001` | `NURA_MODEL_NARRATE` |

An override names one of the model ids this build actually knows how to call
(`app.llm.models.ALLOWED_MODELS`); naming anything else refuses to start rather than fail on
the adapter's first real call. Export only the ones you want to move — everything else keeps
its own default:

```sh
export NURA_MODEL_COMPRESS=claude-opus-5   # e.g. to try the compressor on the dearest model
```

## The run cap

A background feed run only ever executes the plan's first `NURA_MAX_JOBS_PER_RUN` jobs
(default 6), in the broker's own order; the rest are left due for a later run, ordinarily the
next day's — the run-level half of the same cost fix (ADR 0018). The feed response's own
`jobs.deferred` says how many were held back. Raise or lower it the same way:

```sh
export NURA_MAX_JOBS_PER_RUN=3
```

The searcher's own server-tool use is capped too (`SEARCH_TOOL_MAX_USES` on
`web_search`/`web_fetch`, `app.delivery.feed.claude_adapters`), so one job cannot itself fan
out into many searches the way the live incident that prompted this page did.

## Watching what it costs, live

`GET /dev/model-calls` (dev runs only — the same `NURA_DEV_CODE_SENDER=1` gate every other
`/dev/*` door needs) reads back this process's own running count of external model calls, by
task and model — counts only, never content, never a token count:

```sh
curl http://127.0.0.1:8000/dev/model-calls
```

The server log also prints a feed run's own delta once, right after it finishes: `feed: N
external model calls this run (search/claude-sonnet-5=2, compress/claude-haiku-…=4)`.

## The exact lines to export

In the same shell you run `make dev` from, before you run it:

```sh
export NURA_ANTHROPIC_API_KEY=<your key, from the Anthropic console>
export NURA_EXTRACTOR=claude
export NURA_SEARCHER=claude
export NURA_COMPRESSOR=claude
export NURA_NARRATOR=claude
```

Only export the switches for the adapters you actually want real; the rest can stay unset.
`ANTHROPIC_API_KEY` (no `NURA_` prefix) works the same way if that is what you already have
set for the `anthropic` SDK elsewhere on this machine — `NURA_ANTHROPIC_API_KEY` wins if both
are set. Then, as usual:

```sh
make dev
```

The server log says, once per adapter you turned on, that a declared dev run is sending bytes
to the Anthropic API outside the region — that line is expected, not an error.

## What this costs you

Every document you upload, every feed search and compression, and every rephrased trace step
you make with one of these switches on is billed to the key you exported above, at Anthropic's
own rates. Turning a switch off (unset it, or set it back to `fixture`) stops the billing for
that adapter; the fixture answers again, free, from `backend/tests/fixtures/`.

## Turning it off again

Unset the switch (`unset NURA_EXTRACTOR`, and so on), or close the shell you exported it in —
these are ordinary shell environment variables, never written to this repo or to a config
file. The next `make dev` from a fresh shell is back on fixtures alone.
