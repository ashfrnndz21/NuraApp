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
| `NURA_ASKER` | No adapter yet — a companion PR adds one; `make dev` passes it through regardless, so unset already means whatever lands as the default | `Asker` |

Any one on its own, or all four together. Leave the rest unset — an unset switch stays
`fixture`, today's behaviour, unchanged.

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
