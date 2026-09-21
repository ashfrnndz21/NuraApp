# Build spec — the redesign's "One record" scenes and the conversation surface

Written against `docs/design/experience-blueprint.html` (25 scenes, `redesign` branch) and the engine
as it stands on `build-spec` (branched from `origin/redesign`). Every section below is grounded in a
file the engine already has; anything the blueprint implies that does not yet exist is marked
**PROPOSED** or **GAP**, never presented as already built. File paths are relative to `backend/` or
`web/` under `~/Projects/nura` unless stated otherwise.

---

## 0. Owner decisions still open

These block real work starting; each names the options, a recommendation, and what waits on it.

### (a) Country first — Malaysia or Singapore

**Not actually either/or in the engine.** `app/regions.py` already pins every Person/Profile to
`Region.SG` or `Region.MY` at creation, one backend per region, health data never crossing
(`guard_region`). Region-derived facts already exist for both:

| Fact | SG | MY | Cite |
|---|---|---|---|
| Ambulance number | 995 | 999 | `app/safety/emergency_card.py:89` `EMERGENCY_NUMBER = {Region.SG: "995", Region.MY: "999"}` |
| Currency | SGD | MYR | `app/insurance/ledger.py` `CURRENCY_BY_REGION`, read off `context.region` |
| Timezone | Asia/Singapore | Asia/Kuala_Lumpur | `app/regions.py:24-27` |
| Government scheme policy type | MediShield Life | MySalam | `PolicyType.GOVERNMENT_SCHEME` docstring, `app/insurance/policy.py:75-85` |
| Drug register | NPRA+HSA-shaped reg. numbers, 233 products | same table | `backend/tests/fixtures/drugs/registry.json` `_about` |
| Strings | `en`/`ms`/`zh` all three ship today | same | `web/src/strings/{en,ms,zh}.ts` |

The blueprint's worked examples (Sunway Medical Centre, ringgit, "999") are MY-flavoured — they
already match a real, working region binding, not a choice still to make in code.

**Recommendation:** build and demo against `Region.MY` (matches the blueprint's own examples and
the fuller MY drug-register/currency wiring already in the fixtures); SG stays a parallel, already-
supported deployment with its own numbers. This blocks nothing — it only decides which region's
fixtures the demo data (open item c) is written in.

### (b) Clips: embed or link out

The existing `ClipMedia`/`GuideClip` components (`web/src/screens/tabs.tsx:257-316`) already embed:
a poster button that, on tap, fetches a still and — "where the publisher's licence allows one" — an
excerpt video, played in-page (`<video>` element, never a redirect). The blueprint's `.poster`/`.pl`
play-button scenes (`connected`, `registry`) draw the same pattern. **No open question in the
engine** — the existing licensing gate (`clip?.excerpt` presence) already decides embed-vs-poster-
only per clip. Recommend: keep it, extend it to the medicine-registry and connected-item scenes
exactly as built for Home's learning cards. Blocks nothing.

### (c) Real redacted test papers

**Genuinely missing.** The fixture extractor (`app/ingestion/extract.py` `FixtureExtractor`) reads
from `tests/fixtures/paper/`, keyed by `sha256_of(data)` of a *specific* file's bytes — so a new
scene (a 48-page policy, a multi-lab blood test with a synonym mismatch, a discharge letter, a
pharmacy receipt) needs its own fixture bytes and a matching JSON extraction to test against.
**None of the "One record" scenes' underlying papers exist as fixtures today.** This blocks section
3 (inbox), 4 (matching), 5 (policy passport) test-writing directly — every acceptance test in
§11 needs at least: one multi-lab blood test pair (Jan/Sep, mismatched analyte names), one 40+ page
MY medical policy, one prescription + clinic letter with a genuine dose conflict, one pharmacy
receipt with a different name on it. **Recommendation:** the owner (or counsel) supplies redacted
real papers, or Nura's own team hand-builds synthetic ones shaped like real MY papers (panel
hospital wording, NPRA layout) with a clinician sign-off on any printed range, the same discipline
already used for `backend/tests/fixtures/labs/ranges.json` (cites NCEP/ADA/KDIGO/WHO tables).
Do not start the matching-engine tests without at least the lab-pair fixture.

### (d) Backgrounds: drawn CSS atmosphere or licensed photography

The blueprint's `.atmos` (three blurred gradient blobs, `linear-gradient` + `filter:blur(64px)`) is
pure CSS, no image asset, no licence, already inline in `experience-blueprint.html:50-56` and cheap
on a weak phone (see §10). **Recommendation:** keep it exactly as drawn — it is free, on-brand, and
the CSP/offline-PWA constraint (brief, "fonts must be bundled... no runtime request") argues against
adding an external photography dependency at all. No further owner input needed unless the owner
wants a different mood; this is the lowest-risk open item.

### (e) The model behind a public launch

ADR 0017 (`docs/adr/0017-claude-runtime-features-demo-only.md`) is unambiguous and current: a
Claude-backed adapter (`ClaudeExtractor`, `ClaudeNarrator`, `ClaudeAsker`, `ClaudeAnalyst`,
`ClaudeSearcher`/`Compressor`, `ClaudeEstimator`) may build only when `NURA_DEMO_MODE=1` or
`NURA_DEV_CODE_SENDER=1` (`app/llm/residency.py` `allow_external_model`) — gated at every adapter's
own construction site, not a single global switch. A real deployment cannot start any of them: no
in-region Claude/Anthropic endpoint exists for SG or MY today. **This spec's scenes 1–6 all assume
a Claude-backed read** (extraction, ask, analyst, matching's own reasoning where it goes beyond
rules) is available — which is true only in a declared demo or the owner's own dev laptop, never on
a public deployment. **Blocks:** any public-launch timeline for the "One record" scenes as designed;
does not block building and testing them under demo/dev mode, which is what §11's work packages
assume. Flagging, not deciding — retiring or amending ADR 0017 needs an in-region provider, which is
outside this spec's scope.

---

## 1. The conversation block protocol

### What exists today (ground truth, not the blueprint's vocabulary)

The blueprint's prose — `status`, `headline`, `text`, `looked_at`, `tabs`, `rows`, `card`, `actions`,
`sheet`, `note`, `refusal`, `done` — **is not a schema that exists in the codebase.** Grepped
repo-wide for `"looked_at"`, `"block protocol"`: no hits relevant to this surface. The real,
current SSE vocabulary for `/ask/stream` and `/conversations/{id}/turns/stream`
(`app/channels/api/timeline.py`) is five event types, all `data: {json}\n\n` (the `_sse` helper,
`timeline.py:97-101`):

| Event `type` | Emitted at | Payload |
|---|---|---|
| `step` | `timeline.py:354-361` (`_step_event_now`) | `{key, label, name}` — one per tool call, `AskStep.key`/`.count` from `app/llm/ask_agent.py:787` |
| `step_label` | `timeline.py:382` (`_narrate_step_later`, background task) | `{key, label}` — only sent if the narrator actually rephrased; never blocks `step`/`answer` (the whole point of `sse_pump.py`'s fan-in) |
| `answer_delta` | `timeline.py:468` | `{text}` — `AnswerDelta.text`, one per `answer.lines[i]` |
| `answer` | `timeline.py:414, 479` | `{answer: AnswerOut}` — final, includes `proposals: ProposalOut[]` |
| `refusal` | `timeline.py:113` | `{status, ...body}` |

Ingestion's own streams (`/photos/stream`, `/imports/stream`, `app/channels/api/capture.py`) use a
**different, hand-rolled** generator (not `sse_pump.py`) with `type: "step"` (`ImportStepKey`:
`STORED, READING, FOUND, RED_FLAG_CHECKED, LINKED, READY`) and a final `type: "card"`. Feed's
`/find/stream` uses `type: "step"` / `type: "results"`. **Three different ad-hoc envelopes exist
today, none matching the blueprint's twelve-name vocabulary.**

The web side is worse-aligned than the backend: `web/src/ui/kit/Conversation.tsx`'s `StepTrace`/
`TraceSteps` renders an **accumulating checklist** — a growing `<ol>` of steps, each ticked with a
green checkmark as it completes (`trace-tick`/`trace-spin`, lines 52-70). This is the *opposite* of
the blueprint's "ONE status line that changes in place with a light sweep... never an accumulating
checklist" (`docs/design/README.md` rule 2, and `think()` in the blueprint's own JS, line 171: one
`.status` span, replaced, never appended). **This is the single largest UI-behaviour change in this
spec** — every screen currently using `StepTrace`/`ThinkingIndicator`/`LookedAt` needs its
step-rendering swapped, not just restyled.

### A single protocol (PROPOSED), and the additive migration to it

Rather than inventing twelve new SSE event types, define **one envelope every "Nura speaks" surface
streams**, additive over what exists — new event `type`s the client can start rendering while the
old ones still work, one deprecation generation apart:

```
type: "status"    { text: string }                          // replaces accumulating step lists
type: "headline"  { text: string }                           // maps to existing answer.headline where present, else first answer line
type: "text"      { delta: string }                           // = today's "answer_delta", renamed for reuse outside ask
type: "looked_at" { chips: [{ kind: string, id: string, label: string }] }   // NEW — today only reconstructed client-side from step.name (Ask.tsx)
type: "tabs"       { tabs: [{ id: string, label: string }] }   // NEW — used by policy passport, registry
type: "rows"       { rows: [{ title, sub?, value?, unit?, flag?: {kind,label}, range?: {low, high, marker} }] }  // NEW, generalises `lab()`/`item()` in the blueprint's own JS
type: "card"       { headline, body: string[], cite? }        // exists already, ingestion-only (capture.py) — generalise
type: "actions"    { actions: [{ label, kind: "navigate"|"sheet"|"confirm", target }] }  // exists as answer.proposals (ask_agent.py Proposal), generalise the shape
type: "sheet"      { title, sub?, lines: string[], cta: [string,string,string], footnote? }  // NEW — draft/confirm flow, closest existing analogue is app/drafts.py's ConfirmSubject/*Draft, not yet streamed
type: "note"       { text: string }                           // = boundary_lines() today, already computed server-side, never streamed as its own event
type: "refusal"    { status: number, ...body }                // exists verbatim (timeline.py:113) — unchanged
type: "done"       {}                                          // NEW — today the stream simply ends; an explicit terminal event lets the client tell "still working" from "finished with nothing to add"
```

**Mapping table — old → new:**

| Today | Becomes | Note |
|---|---|---|
| `step` / `step_label` (ask) | `status` | Collapse the narrated-step pair into one line that replaces in place; `step.label` -> the status text, `step_label`'s rephrase replaces the same line rather than appending a row |
| `step` (ingestion `ImportStepKey`) | `status` | Same collapse; `STORED`/`READING`/`FOUND`/`RED_FLAG_CHECKED`/`LINKED`/`READY` become five `status` lines, in order — matches the blueprint's `inbox` scene's `Reading N of 7…` pattern (blueprint line 207) |
| `answer_delta` | `text` | Rename only; payload shape (`{text}` vs `{delta}`) needs a one-field rename, trivial |
| `answer` | split into `headline` + `text`(final) + `rows` (if the answer has structured lines) + `card` | `AnswerOut` today is one flat object; this is the actual schema work — `AnswerOut`/`Answer` (`app/search/ask.py:220-244`) needs a `headline: str | None` and a way to mark some `AnswerLine`s as `rows` vs prose, which does not exist yet |
| `answer.proposals[]` | `actions` | Shape is already close: `Proposal(kind, label)` -> `{label, kind: "navigate"|"sheet"|"confirm", target}` needs a `target` added — proposals today carry no navigation target (`ProposalOut`'s own docstring: "it still needs a yes through the existing confirm flow" — aspirational) |
| (nothing) | `looked_at` | **New.** Today the client (`Ask.tsx`) reconstructs "What Nura looked at" from accumulated `step.name` values after the fact — an explicit event removes that reconstruction |
| (nothing) | `tabs`, `rows` | **New**, needed for policy passport and registry; no backend concept of a tabbed or tabular answer exists today (`AnswerOut` is prose + citations only) |
| (nothing) | `sheet` | **New** on the wire; the *confirm* mechanics it would drive already exist server-side (`app/drafts.py`, 22 `ConfirmSubject`s, one-time-use digest via `app/keys/confirm.py`) — only the *streaming of a sheet's content* (its `lines` arriving word-by-word) is new |
| `boundary_lines()` (computed, attached to every `Answer`) | `note` | Today the boundary line already travels inside the answer payload (`ask_agent.py:843,880,895`); making it its own event lets a screen show it once per screen rather than embedded per-answer, matching "the safety line appears ONCE per screen" |
| (stream just ends) | `done` | **New**, trivial — one more event after the last real one |

### Where the plain-words / boundary gate runs, exactly (unchanged by this migration)

Confirmed server-side, before any byte reaches the client, on every path:

- Ask: `app/llm/ask_agent.py:1007` (`_answer_from_payload`, per-line `verified()`), `:966-975`
  (`_plain_words_findings`, repair round), `:1014` (re-check after `_boundary_rewrite`), `:1023`
  (`_has_conclusion_language`) — all run **inside the round loop**, before the function ever reaches
  the `AnswerDelta` yield loop at `:887-888`. Nothing partially-verified is ever streamed.
- Rule-based fallback: `app/search/ask.py:904` (`words.verified` over every group) and `:931`
  (`boundary_lines`), both before `recall_stream`'s single `Answer` yield (it never streams deltas).
- Narrator: `app/llm/narrate.py:300` (`verified()`) before a `step_label` is queued.
- Feed cards: `app/delivery/feed/items.py:252-256` (`changes_treatment` -> `TreatmentChangingCard`,
  raised, never written) and `:202-208`/`:259-262` (`failures_in` -> `NotPlainWords`, raised) inside
  `create_item`, for any `deliver_to is DeliverTo.PATIENT` card.

**This migration adds nothing here** — the gate stays exactly where it is; the protocol change only
touches *how the already-verified text is chunked onto the wire*, never *what is allowed through*.

### Backwards-compatible migration order (PROPOSED)

1. Add `status`/`text`/`done` alongside existing events on `/ask/stream` only (additive; old client
   code keeps working off `step`/`answer_delta`/`answer`). Swap `Conversation.tsx`'s `StepTrace` for
   a single in-place status line consuming `status` — this is the change that actually fixes the
   "accumulating checklist" defect, and can ship alone before anything else in this table.
2. Add `looked_at` to `/ask/stream`, remove the client-side reconstruction in `Ask.tsx`.
3. Add `rows`/`tabs`/`card` to a *new* stream only (policy passport, registry — net-new screens, no
   back-compat burden).
4. Add `actions`/`sheet` last, once `target` semantics for a proposal are designed (needs the
   `ConfirmSubject` wiring described in §5/§6, since `propose_action`'s three kinds are not
   currently wired to any real confirm flow — `ask_agent.py:206-229`'s `propose_action` tool only
   appends a label today).
5. Only once every consuming screen is migrated, retire `step`/`answer_delta`/`answer` from new
   code (never delete the wire types outright without an API version bump — WhatsApp and any other
   channel consuming the same event stream would break silently).

---

## 2. Streaming extraction

### What exists (ground truth)

`ClaudeExtractor.extract()` (`app/ingestion/claude_extract.py:283-311`) is **one blocking call**:

```python
message = await self._client.messages.create(
    model=MODEL, max_tokens=MAX_TOKENS, system=_SYSTEM_PROMPT,
    messages=[...], output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
)
```

`MODEL = "claude-opus-5"`, `MAX_TOKENS = 8192`. No `.stream()`, no `stream=True`, no iteration over
deltas anywhere in this file. The **whole PDF goes in as one base64 `document` content block in one
call** (`_content_block`, lines 169-181) — there is no page-by-page loop; the model is only asked to
*self-report* which page a field came from (`ExtractedField.span.page`), inside its one JSON answer.
`json.loads(text)` parses the whole response only after it returns in full (line 325). A page count
that overruns `MAX_TOKENS` truncates silently to `Extraction.nothing()` (module comment,
lines 72-74) — there is no chunk/retry-per-page fallback today.

### The gap the blueprint's `reading`/`policy` scenes assume

The blueprint's own build-status note on scene `reading` already says this plainly: *"Stream the
model's answer so rows land as they are read; today it answers in one piece after about 15
seconds"* (blueprint line 202). And scene `policy`'s progress ("Reading page 4 of 48"... "page 48 of
48") is **currently impossible to report honestly** — a single blocking call has no intermediate
state to report from. Per the brief's own rule ("every status line is a stage the backend really
reports"), this progress cannot ship as shown until the extraction is actually restructured.

### PROPOSED: from one blocking call to a streamed, page-aware one

1. **Anthropic streaming with partial JSON.** Replace `messages.create(...)` with
   `self._client.messages.stream(...)` (the SDK's streaming context manager), consuming
   `input_json_delta` events to accumulate the structured-output JSON incrementally. A `Field`
   object (subject/attribute/value/unit/confidence/span) is only emitted to the caller **once its
   JSON object closes and validates against `_FIELD_SCHEMA`** — never a half-written field. This
   is the `rows` land-as-they-are-read behaviour the blueprint's `reading` scene shows.
2. **Page-by-page reading for long PDFs**, so `"page N of M"` is a real number, not invented: split
   a PDF's pages into `document` content blocks sent as **separate, sequential** `messages.create`
   (or `.stream`) calls, each covering a page range small enough to stay well under `MAX_TOKENS`
   (today's ceiling is already the failure mode for a 48-page policy in one call). Each call's
   completion is one real `status` event (§1): `Reading page {n} of {m}…`. This directly replaces
   the blueprint's invented-looking-but-should-be-real progress line.
3. **Failure modes**, each mapped to an honest status/refusal rather than silence:
   - A page's call returns `stop_reason == "refusal"` -> today's `Extraction.nothing()` path,
     unchanged, surfaced as a `refusal` event for that page only (other pages continue).
   - A page's call hits `max_tokens` -> today's truncation path; PROPOSED: retry that one page at a
     smaller field-count ceiling before giving up on it, rather than silently truncating the whole
     document (today's per-file, not per-page, granularity makes a partial doc a total loss).
   - `APIStatusError` (network/rate-limit) -> unchanged (`claude_extract.py:329-338`), but now scoped
     to one page's retry, not the whole document.
   - JSON parse failure on one page's accumulated stream -> `Extraction.nothing()` for that page,
     never for pages already successfully parsed.
4. **No database transaction open during a model call.** Cite the concrete precedent of the defect
   already found and partially mitigated elsewhere in this codebase:
   `app/delivery/feed/background.py:227-248` opens a SQLite savepoint (`_own_session` ->
   `unit_of_work` -> `session.begin_nested()`, `db.py:305`) that **stays open across**
   `run_job`'s two blocking model calls (`app/delivery/feed/search.py:406-408` and `:461-463`, both
   wrapped in `asyncio.to_thread` because `Searcher.search`/`Compressor.compress` are synchronous
   ports). `db.py:371-401` documents why this matters on SQLite specifically: every transaction is
   `BEGIN IMMEDIATE`, and a second writer waits up to `SQLITE_LOCK_WAIT_SECONDS = 30` before
   failing "database is locked" — a `JOB_DEADLINE_SECONDS = 60` job can hold that lock twice as
   long as another writer is willing to wait. **The streamed extractor must not repeat this
   defect**: each page's model call must happen *outside* any open transaction — read what's needed
   (hints, prior pages' fields) before the call, `await` the call with no session open, then open a
   short transaction only to persist the page's validated fields. `review_artifact_stream`
   (`app/ingestion/review.py:375-460`) already yields per-stage (`ImportStepKey`) rather than
   holding one long transaction across the whole card — the streamed extractor should follow that
   existing shape, not `background.py`'s.

---

## 3. The inbox

### What exists (ground truth) — smaller than the blueprint's scene implies

- **No job/queue table for ingestion exists.** Grepped `app/ingestion/` and
  `app/channels/api/` for `batch|queue|fingerprint|dedup`: zero matches. (`SearchJob` in
  `app/delivery/feed/` and the pharmacist drug-label review queue in `app/channels/api/review.py`
  are both unrelated subsystems.)
- **No "kept -> sorted -> read -> matched" state vocabulary exists anywhere.** The only states today
  are per-field `FieldState` (`PROPOSED, CONFIRMED, CORRECTED, REJECTED`, `app/ingestion/models.py`)
  and per-card `confirmed_at is None` (open) / not (closed).
- **No cross-upload fingerprint/dedup.** `sha256_of(data)` (`app/ingestion/objects.py:37-38`) is
  used only as an **object-store key** (`photos/<profile_id>/<sha256>`,
  `imports/<profile_id>/<sha256>`) — identical bytes reuse the same storage key, but a new
  `Artifact` row and a new review card are still created every time (`store_photo`/`store_pdf`
  call `store_artifact` unconditionally). **There is no "have I already read this exact document"
  check before a model call is paid for** — the blueprint's `inbox` scene claims exactly this
  ("caught by its fingerprint before any reading is paid for") and it is not built.
- **No resumability after restart for a photo/PDF extraction.** Resumability exists only for
  chunked *consult audio* uploads (`app/ingestion/chunks.py`, `ConsultUpload`) — an unrelated
  feature. If the process restarts mid-`review_artifact`, the attempt is simply lost; the bytes
  already in the object store remain, but nothing records "extraction attempted, not finished."
- **No batch upload endpoint.** Every `capture.py` route (`/photos`, `/photos/stream`, `/imports`,
  `/imports/stream`) takes exactly one file per call. **The client already has a batch pattern**,
  though: `web/src/capture/batch.ts`'s `PaperBatch` picks many photos/PDFs at once into a grid
  (`Picked[]`), then sends them **one at a time, in the order picked**, client-side, through the
  existing single-file `/stream` routes — each item's `Outcome` (`waiting|sending|card|notHealth|
  refused|notSent`) tracked in a Preact signal. This is a real, working client-side sequencer; it
  is not a server-side job queue, and it has no fingerprint check, no cross-restart resumability,
  and no per-profile serialization beyond "the tab that opened it."

### PROPOSED: the inbox job model

A genuinely new server-side concept, close to what the blueprint shows but scoped to what a
per-profile background queue actually needs:

**Table `ingestion_job`** (new, `app/ingestion/models.py`):

| Column | Type | Notes |
|---|---|---|
| `id` | UUID pk | |
| `profile_id` | UUID FK | `ProfileScoped` |
| `artifact_sha256` | str(64) | the fingerprint — **the new thing**: checked before storage, not just used as a storage key |
| `state` | enum | `KEPT, SORTED, READ, MATCHED, IN, NEEDS_YOU, SAME, FAILED` — matches blueprint's flag values (`In`, `Needs you`, `Same paper`) plus the working states it animates through |
| `document_kind` | `DocumentKind \| None` | filled at `SORTED` |
| `review_card_id` | UUID FK, nullable | filled at `READ` |
| `created_at`, `updated_at` | datetime | |
| `error` | str, nullable | filled on `FAILED` |

**One-at-a-time per profile**: a single background worker per profile (extend
`background.ensure_learning_scheduled`'s in-process claim pattern,
`app/delivery/feed/background.py:119-138`, but persisted — its own docstring already flags its
in-memory `_runs` dict as not surviving a restart or a second process; the inbox job table's
`state` column is exactly what closes that gap for ingestion specifically).

**Fingerprint duplicate check before any model call**: on `POST /profiles/{id}/imports/batch`
(new route, PROPOSED), for each file compute `sha256_of(data)` and look up an existing
`ingestion_job` (any state) with the same `artifact_sha256` **for this profile** before creating a
new row or touching the extractor — a hit short-circuits straight to `SAME`, no model call, no new
`Artifact`. This is the one piece of the blueprint's `inbox` claim ("caught by its fingerprint
before any reading is paid for") that is currently false and needs building.

**Resumability after restart**: a worker on start scans `ingestion_job` rows in
`KEPT`/`SORTED`/`READ` (i.e. claimed but not finished) for this profile and resumes from that
state, rather than restarting the whole extraction — this needs each stage's output persisted
(`document_kind` at `SORTED`, the review card at `READ`) rather than held only in a generator's
local variables, unlike `review_artifact_stream` today.

**Scopes/audit**: every job write goes through `audited_write(session, IngestionJob, context,
Scope.RECORDS, ...)` (the existing door, `app/audit/access.py:133`), same as any other row; the
external-model-reach audit line (ADR 0017 point 3, `EXTERNAL_MODEL_PROCESSOR`) still fires once per
model call, unchanged.

**Batch summary**: PROPOSED response shape once all jobs in a batch reach a terminal state:
`{ total, in, needs_you, same, failed }` — the blueprint's closing line ("I read seven papers. Five
are in. Two need *you.*") is a template over these four counts, streamed as a `headline` (§1) once
the last job in the batch finishes.

**API routes (PROPOSED, additive)**:
```
POST /profiles/{id}/imports/batch        -> [] of ingestion_job (202, work starts in background)
GET  /profiles/{id}/imports/batch/{id}    -> batch status + per-job state (poll or SSE)
GET  /profiles/{id}/imports/batch/{id}/stream  -> SSE: one `status`/`rows` update per job state change, `done` at batch end
```

---

## 4. The matching engine

**Rules decide, never a model** — this is already the house style: `RuleAnalyst` does all record
reads and finding-generation itself (`app/reasoning/analyst/rule.py`); `ClaudeAnalyst` only
rephrases an already-rule-built report and is re-validated candidate-by-candidate
(`claude_adapter.py:137-218`). The matching engine below follows the same shape: a
`ClaudeExtractor` reads a paper's *fields*; a rule-only matcher decides the *verdict*.

### The six verdicts, precisely, per fact type

No matching-engine code exists yet (**GAP** — this whole section is PROPOSED). Definitions below are
written to be directly testable against `Fact.valid_from`/`valid_to`/`supersedes_id`
(`app/memory/models.py:222-278`), the only append-only-history primitive that exists today.

| Verdict | Condition (PROPOSED rule, per fact type) |
|---|---|
| **New** | No existing `Fact` with the same `(subject, attribute)` (lab: same canonical analyte code) and an overlapping `valid_from`/`valid_to` window for this profile. Write a new `Fact`, `confidence_state=EXTRACTED`. |
| **Same** | Incoming field's `(subject, attribute, value, unit)` matches an existing `Fact` **and** the new artifact's `sha256` differs from the one already on file for an equal-or-near-identical value+date (the blueprint's "same blood test, as a photo... skipped" — a second capture of a paper already read). Write nothing; cite both artifacts on the existing fact for provenance completeness. |
| **Newer** | Same `(subject, attribute)`, a later `valid_from` than the current fact's, and a materially different value. Close the old fact (`valid_to = new.valid_from`), append the new one with `supersedes_id` pointing at the old — never overwrite (`Fact` is otherwise `frozen(..., except_for={"superseded_at"})`, `app/memory/models.py:529`, so this must go through the existing supersession write path, not a raw UPDATE). |
| **Conflict** | Two facts (or an incoming field and an existing fact) for the **same subject/attribute claim the same validity window** with **different values** — e.g. two doses for the same medicine line both claiming to be current. Never auto-resolved; always routed to a person's yes (see below). |
| **Replaces** | A structurally distinct object (a policy, a full document) supersedes an *entire* prior one of the same kind for the same profile — not a field-level change. Uses `Policy.supersedes_id` (`app/insurance/policy.py`, already exists for policies) as the model; extend the same shape to any "whole document replaces a whole document" case. |
| **Not yours?** | The name printed on the paper (extracted as a field, e.g. `subject="person", attribute="name_on_paper"`) does not match the profile's own name within tolerance (see below). Never auto-filed; always a question. |

### Analyte identity across labs — synonym table

**What exists**: 10 canonical analytes with a canonical unit and an mg/dL<->mmol/L (or equivalent)
factor already defined, in `backend/tests/fixtures/labs/ranges.json` `analytes`:

```
total_cholesterol, ldl, hdl, triglycerides, hba1c, creatinine, egfr, potassium, haemoglobin, tsh
```

Each carries `{subject, attribute, unit, factors: {other_unit: multiplier}, bands: [...]}` — e.g.
`ldl: {unit: "mg/dL", factors: {"mmol/L": 38.67}, bands: [{upper: 100, source: "ncep-atp3-2001"}]}`.
This is exactly the shape needed, but the file's own header **already flags itself**: *"these
numbers stand in until a clinical reviewer signs off a licensed table... needs a clinician's
sign-off (LDL target, TSH age bands)."*

**What does not exist**: any table mapping a lab's own printed name for an analyte (e.g. "LDL",
"LDL-C", "LDL Cholesterol", "Low-density lipoprotein cholesterol") to the ten canonical
`attribute` codes above. `ranges.json`'s `labs` key holds *lab-specific range overrides*, not
*name synonyms* — a different problem. **This synonym table does not exist and is the first thing
the matching engine needs**, before it can decide "New" vs "Newer" across two labs that print the
same analyte differently.

**PROPOSED first 40 analytes to cover** (the existing 10, marked *existing*, plus 30 more common on
a MY/SG chronic-disease panel — **every row below NEEDS CLINICAL REVIEW**, unit factors are
standard published conversions, not yet signed off for this product):

| Canonical code | Common synonyms on a printed report | Canonical unit | mg/dL<->mmol/L (or stated) factor |
|---|---|---|---|
| `total_cholesterol`* | Total Cholesterol, Cholesterol Total, TC | mg/dL | ×0.02586 -> mmol/L |
| `ldl`* | LDL, LDL-C, LDL Cholesterol, Low-Density Lipoprotein | mg/dL | ×0.02586 |
| `hdl`* | HDL, HDL-C, HDL Cholesterol, High-Density Lipoprotein | mg/dL | ×0.02586 |
| `triglycerides`* | TG, Trig, Triglyceride | mg/dL | ×0.01129 |
| `hba1c`* | HbA1c, Glycated Haemoglobin, A1C | % | (also reported as mmol/mol — IFCC; needs a second factor, NEEDS CLINICAL REVIEW) |
| `creatinine`* | Creat, Serum Creatinine, Cr | umol/L | ×0.0113 -> mg/dL |
| `egfr`* | eGFR, GFR, Estimated GFR | mL/min/1.73m2 | n/a (already normalised) |
| `potassium`* | K, K+, Serum Potassium | mmol/L | ×1.0 -> mEq/L |
| `haemoglobin`* | Hb, Hgb, Haemoglobin | g/dL | ×10 -> g/L |
| `tsh`* | TSH, Thyroid Stimulating Hormone, Thyrotropin | mIU/L | ×1.0 -> uIU/mL |
| `fasting_glucose` | FBG, Fasting Blood Glucose, Fasting Sugar | mg/dL | ×0.0555 -> mmol/L |
| `sodium` | Na, Na+, Serum Sodium | mmol/L | ×1.0 -> mEq/L |
| `chloride` | Cl, Cl-, Serum Chloride | mmol/L | ×1.0 -> mEq/L |
| `urea` | Urea, BUN, Blood Urea Nitrogen | mmol/L | ×2.801 -> mg/dL |
| `uric_acid` | Uric Acid, Urate | umol/L | ×0.0168 -> mg/dL |
| `alt` | ALT, SGPT, Alanine Aminotransferase | U/L | n/a |
| `ast` | AST, SGOT, Aspartate Aminotransferase | U/L | n/a |
| `alp` | ALP, Alkaline Phosphatase | U/L | n/a |
| `ggt` | GGT, Gamma-GT | U/L | n/a |
| `bilirubin_total` | Total Bilirubin, TBIL | umol/L | ×0.0585 -> mg/dL |
| `albumin` | Albumin, Alb | g/L | ×0.1 -> g/dL |
| `total_protein` | Total Protein, TP | g/L | ×0.1 -> g/dL |
| `calcium` | Ca, Serum Calcium | mmol/L | ×4.008 -> mg/dL |
| `phosphate` | Phosphate, Phosphorus, PO4 | mmol/L | ×3.097 -> mg/dL |
| `magnesium` | Mg, Serum Magnesium | mmol/L | ×2.431 -> mg/dL |
| `white_cell_count` | WBC, White Blood Cell Count, Leukocytes | ×10^9/L | n/a |
| `platelet_count` | Platelets, PLT, Thrombocyte Count | ×10^9/L | n/a |
| `haematocrit` | Hct, PCV, Packed Cell Volume | % | n/a |
| `mcv` | MCV, Mean Corpuscular Volume | fL | n/a |
| `crp` | CRP, C-Reactive Protein | mg/L | n/a |
| `esr` | ESR, Erythrocyte Sedimentation Rate | mm/hr | n/a |
| `vitamin_d` | Vitamin D, 25-OH Vitamin D, 25(OH)D | nmol/L | ×0.4 -> ng/mL |
| `vitamin_b12` | B12, Vitamin B12, Cobalamin | pmol/L | ×1.355 -> pg/mL |
| `folate` | Folate, Folic Acid | nmol/L | ×0.4413 -> ng/mL |
| `ferritin` | Ferritin, Serum Ferritin | ug/L | ×1.0 -> ng/mL |
| `iron` | Iron, Serum Iron | umol/L | ×5.585 -> ug/dL |
| `psa` | PSA, Prostate Specific Antigen | ug/L | ×1.0 -> ng/mL |
| `free_t4` | Free T4, FT4 | pmol/L | ×0.0777 -> ng/dL |
| `hs_troponin` | High-Sensitivity Troponin, hs-cTnT, hs-cTnI | ng/L | n/a |
| `nt_probnp` | NT-proBNP | pg/mL | n/a |
| `inr` | INR, International Normalised Ratio | ratio | n/a (warfarin monitoring — high relevance given `warfarin` is already in the drug register) |

*(rows marked `*` are the 10 already in `ranges.json`; the other 30 are new, **every factor in this
table NEEDS CLINICAL REVIEW** before any is used to decide a verdict on a real person's data — the
existing file's own header sets this bar and it should not be lowered for the new rows.)*

### Plausibility bounds — "question it, never drop it"

**PROPOSED, no code exists.** Per analyte, a wide sanity band (not the clinical reference range —
a *physiologically-possible* band) beyond which a value is flagged `unreadable`-adjacent rather than
either silently accepted or silently dropped: e.g. an LDL read as "40,000 mg/dL" is almost certainly
a decimal-point OCR error, not a real value. On a bounds violation: write the fact with
`confidence_state=EXTRACTED` as usual but attach a `Check` verdict alongside — same shape as
`ReviewField.needs_confirm` (`confidence < CONFIDENCE_THRESHOLD or unreadable`,
`app/ingestion/models.py:170-173`) already forces a human look; extend that same mechanism to a
bounds check rather than building a second one.

### Plausibility, name-on-paper tolerance

**PROPOSED.** Fuzzy string match (e.g. token-set Levenshtein) between the paper's printed name field
and `Person.display_name`, with a tolerance for common variants already anticipated in the strings
file (`Record.matchByNameOnly: string[]` exists in `web/src/strings/types.ts:757` — client-side
copy already assumes a "matched by name only" state exists, confirming this was designed for, not
yet wired). Below the tolerance: file as usual. Above it: **Not yours?** verdict, always a question,
never auto-accepted or auto-rejected — matches the blueprint's `matching` scene exactly
("Pharmacy receipt... The name on it is Mei Tan... Yours?").

### Never overwrite

Already the house pattern for `Policy` (`supersedes_id`/`superseded_at`,
`app/insurance/policy.py`) and for `Fact` itself (`supersedes_id`, `frozen(..., except_for=
{"superseded_at"})`). The matching engine's **Newer** and **Replaces** verdicts must go through
this existing write shape — close with `valid_to`/`superseded_at`, write a new row with
`supersedes_id`, never `UPDATE` a kept row's `value` column. This is enforced at the DB layer today
for every table listed with `frozen(...)` in `app/memory/models.py:526-529` — any matching-engine
write path must use the existing supersession helpers, not raw SQLAlchemy assignment.

### Citation on everything

Already available on every `Fact`: `artifact_id`/`event_id` (provenance, `CheckConstraint
"artifact_id IS NOT NULL OR event_id IS NOT NULL"`) plus, per extracted field, `Span{x0,y0,x1,y1,
page}` (`app/ingestion/extract.py:123-138`). The matching engine only needs to **carry this through**
into whatever it writes — no new citation mechanism needed, just discipline about not dropping
`Span`/`artifact_id` when a matched fact is created.

### Which verdicts need the person's yes

| Verdict | Needs a yes? | Mechanism |
|---|---|---|
| New | No | Auto-filed, `confidence_state=EXTRACTED` |
| Same | No | Nothing written |
| Newer | No, unless value is a medicine dose (see below) | Auto-filed with supersession |
| **Conflict** | **Always** | New `ConfirmSubject` (extend `app/drafts.py`'s 22-member enum), one yes settles which value is current |
| **EVERY medicine change** | **Always** | Existing pattern: a dose change already writes as `ChangeKind.DOSE_CHANGE` with `supersedes_id` on the person's `confirmation_id` (`app/medicines/service.py:472-479`) — the matching engine's medicine-line verdicts must route through `app.medicines.service`, never write a `MedicationLine` directly |
| **High-risk medicines** | **Double-confirmed** | `refuse_dose_without_label_photo()` already hooks `before_fact_write` for every writer (`app/safety/high_risk.py:216-253`) and requires a label-photo artifact, not a loose pill photo — the matching engine gets this for free by writing through the same hook, but the blueprint's "double-confirmed" (two separate yeses) is **not** what exists: today it is one yes plus a mandatory label photo, not two sequential confirmations. **PROPOSED**: add a second explicit confirm step (e.g. "Are you sure?" restated) specifically for a high-risk-class dose change, since one photo requirement is not the same UX as two yeses. |
| Replaces (whole document) | Case-by-case — a policy replacement already auto-supersedes without a yes today (`Policy.supersedes_id` is set by staff/import, not gated on a confirm in the code read) — **PROPOSED**: require a yes here too, for consistency with Conflict/medicine handling |
| Not yours? | **Always** | Routes to a filing decision, never auto-accepted |

### Audit entries

Every write above goes through `audited_write(session, Fact, context, scope_for_subject(subject),
...)` (`app/audit/access.py:133`, existing, unchanged) — the matching engine adds no new audit
mechanism, it only needs to call the existing door for every fact/medicine-line/policy write it
produces, exactly as `app/medicines/service.py` and `app/insurance/policy.py` already do.

---

## 5. The policy passport

### What exists today — much flatter than the blueprint's scene

`Policy` (`app/insurance/policy.py:93-127`), 14 flat fields:

```
id, insurer_name, policy_reference, policy_type, covered, covers,
start_date, renewal_date, premium_due_date, status, guarantee_letter,
supersedes_id, superseded_at, set_by_person_id, confirmation_id, set_at
```

`PolicyType` (`policy.py:75-85`): `HOSPITAL, OUTPATIENT, CRITICAL_ILLNESS, GOVERNMENT_SCHEME`.
**No `LIFE`, no `PERSONAL_ACCIDENT`, no `TAKAFUL` member exists.**

Checked against the blueprint's fixed schema, field by field:

| Blueprint field | Status |
|---|---|
| Identity (insurer, reference) | **Exists** — `insurer_name`, `policy_reference` |
| Insured persons | **Partial/GAP** — `covered` is one free-text string ("Pa and Mum"), not a structured list of profiles/people |
| Period, renewal | **Exists** — `start_date`, `renewal_date` |
| Limits (annual/lifetime/per-disability) | **GAP** — no `limit_cents`/`sum_insured` field at all |
| Deductible / co-insurance | **GAP** — no field |
| Room and board | **GAP** — would today only ever appear inside the free-text `covers` string |
| Waiting periods | **GAP** — no field |
| Panel hospitals | **GAP** — only `guarantee_letter: bool` (whether the insurer works by GL at all, not a hospital list) |
| Benefits[] | **GAP** — only free-text `covers` |
| Exclusions[] | **GAP** — no field |
| how_to_claim (cashless/GL vs pay-and-claim, hotline, documents, time limit) | **GAP** — claims are a separate `InsuranceClaim` flow (status machine), not a policy-level field describing the process |
| Beneficiaries (life) | **GAP** — and moot until `LIFE` exists as a `PolicyType` |
| Takaful | **GAP** — no distinction anywhere |
| `{quote, page}` citation per item | **GAP** — no field on `Policy` carries a source page/quote at all. (Contrast: `app/insurance/benchmarks.py`'s `BenchmarkEntry` *does* carry `publisher`/`url`/`fetched_at` — a citation shape exists in the codebase, just not on `Policy`.) |

This is the single largest schema gap in this spec: today's `Policy` is a **person-typed summary**
("what he told the system his policy says," `covers`'s own docstring: "never a coverage Nura
decided") — the blueprint's `policy` scene is a **document-read** (a 48-page PDF parsed into a fixed
shape with page citations on every line). These are different features sharing a name.

### PROPOSED migration(s)

1. **Extend `PolicyType`**: add `LIFE`, `PERSONAL_ACCIDENT`; add a `takaful: bool` field (a takaful
   plan is structurally the same shape with different terminology/legal basis in MY, not a fifth
   `PolicyType`).
2. **New table `PolicyDetail`** (one-to-one with `Policy`, keeps `Policy` itself untouched for
   backward compatibility with the existing ledger/claims flow): structured fields for limits
   (`annual_limit_cents`, `lifetime_limit_cents`, `per_disability_limit_cents`),
   `deductible_cents`, `co_insurance_percent`, `room_and_board_cents_per_night`,
   `waiting_periods: list[WaitingPeriod]` (`{condition: str, months: int, cite: Citation}`),
   `panel_hospitals: list[str]`, `benefits: list[BenefitLine]` (`{title, detail, cite}`),
   `exclusions: list[ExclusionLine]` (`{title, detail, cite}`), `how_to_claim:
   list[ClaimStep]` (`{step, detail, cite}`), `beneficiaries: list[Beneficiary]` (life only,
   `{name, relationship, share_percent}` — **PII**, treat under the same care as identity-card
   numbers per CLAUDE.md's "never store identity-card numbers outside the insurance module" rule).
3. **`Citation` shape** (new, shared type): `{quote: str, page: int, artifact_id: uuid}` — every
   `PolicyDetail` line item carries one, following the same `Span{page,...}` discipline
   `app/ingestion/extract.py` already applies to lab fields.
4. **Extraction**: the deep policy read is the same streamed, page-by-page `ClaudeExtractor` change
   from §2, with a policy-specific prompt/schema (new `app/llm/prompts/extract_policy.txt`,
   following the existing `load_prompt` convention, `app/llm/prompts.py`) that targets
   `PolicyDetail`'s shape rather than the generic lab/medicine field schema.

### The money scope

Already correct and needs no change: `insurance_policy`/`insurance_claim` subjects already sit
under `Scope.MONEY` (`app/keys/scopes.py:92-97`), not `Scope.RECORDS` — "a clinic key holds RECORDS
and must not see a policy or a claim number a chief typed" (comment, `scopes.py:96-97`). Any new
`PolicyDetail` fields inherit the same scope by staying attached to the same `Policy` row.

### Display rules

Already the house voice, confirmed in the blueprint's own scene copy: *"Your policy says this... The
insurer decides what is paid. This is not financial advice."* This matches `plain-words.md`'s
glossary line: `"Guarantee letter, GL, coverage" -> "Your insurance letter. 'Your insurance letter
is ready.'"` and the existing `cost_expectation.py` module docstring's explicit rule: never a
made-up midpoint, never a "covered" percentage invented (`cost_expectation.py` lines 20-26, already
enforced code, not just a style rule).

### "Claimed so far" from the ledger

Already built, unchanged: `insurance_ledger()` (`app/insurance/ledger.py:133-230`) sums
`claimed_amount_cents`/`paid_by_insurer_cents`/`paid_by_patient_cents` across this year's claims,
grouped by policy (`PolicyTotal`). The policy passport's "claimed so far" tile is a direct read of
`PolicyTotalOut.claimed_said` (`insurance_schemas.py:138-146`) for the policy in view — no new
computation needed, just a UI binding.

### Renewal and waiting-period-ending reminders into the feed

`renewal_date`/`premium_due_date` already exist on `Policy` and could drive a `CardType.NOTICE` or
new `CardType.RENEWAL` card through the existing `compose.py` `refresh()` pipeline
(`app/delivery/feed/compose.py:200-344`), the same way `_memos`/`_visit` cards are built today.
Waiting-period-ending needs `PolicyDetail.waiting_periods` (proposed above) to exist first — no
current field to compute it from.

---

## 6. The medicine registry

### What exists (strong ground here — closer to built than insurance)

`MedicationLine` (`app/medicines/models.py:84-165`) — key fields: `generic, brand, strength, form,
registration_no, drug_class, high_risk, product_kind, dose (JSON), prescriber, source_kind,
status (ACTIVE|HELD|STOPPED), change_kind (NEW_LINE|DOSE_CHANGE), started_at, stopped_at,
supersedes_id, confidence, confidence_state`.

**Identity** is already computed exactly as the blueprint implies: `_one_product()`
(`app/medicines/service.py:184-217`) treats `(generic, strength, form)` as the identity triple —
more than one distinct triple among registry matches is ambiguous (`NotIdentified`).

**Brand -> generic**: `FixtureRegistry` (`app/drugs/fixture.py`), data file
`backend/tests/fixtures/drugs/registry.json` — **233 products, 25 interaction pairs, 50
monographs**, NPRA/HSA-shaped registration numbers, across cardiovascular, diabetes, lipid,
analgesic, gastro, respiratory, plus supplements and TCM remedies. Confirmed real example row:
`{"registration_no": "MAL19970001A", "brand": "Norvasc", "generic": "amlodipine", "strength":
"5 mg", "form": "tablet", ...}` — so "Norvasc and amlodipine resolve to one medicine" (blueprint
scene copy) is **already true today**, not aspirational. The port is `DrugRegistry`
(`app/drugs/registry.py`), a second (licensed) adapter is a drop-in behind the same
`identify()`/`interactions()`/`monograph()` protocol — no caller changes needed to swap it.

**Same-medicine-twice detection**: exists at three levels already:
1. Registry-level: `FixtureRegistry.interactions()` synthesizes a `Severity.DUPLICATE`
   (`text_id="same_kind_twice"`) pairing for any two generics sharing a `drug_class`.
2. Analyst-level: `RuleAnalyst._medicine_candidates()` (`app/reasoning/analyst/rule.py:261-289`)
   groups active lines by `drug_class`; ≥2 distinct generics in one class -> an `InsightKind.
   MEDICINE` insight, `ask_who=PHARMACIST` — **already the blueprint's "Ask your pharmacist"
   pattern, already routed to the pharmacist, never a verdict**, exactly as specified.
3. Line-list level: `LineView.duplicate_of` computed at read time in `active_lines()`.

**Dose change between papers -> confirm**: already built as a supersession write
(`ChangeKind.DOSE_CHANGE`, `supersedes_id`, `service.py:472-479`), on the person's
`confirmation_id`, never automatic — and already rendered as a question, not a fact: `story.py`'s
`medication_story()` swaps in template line *"Your new pack says a different amount from before.
Ask {doctor} about the new amount"* whenever `change_kind is DOSE_CHANGE` (strings.py:550-561).

**High-risk labelling**: `app/safety/high_risk.py` — 5 hand-named classes (`anticoagulant,
insulin, cardiac_glycoside, antimetabolite, opioid`), enforced via a `before_fact_write` hook
(`high_risk.py:252-253`) that runs for **every** writer, not just the medicines module — a
WhatsApp-sourced or voice-sourced dose write is caught the same way as a photo-sourced one.

**Supplements**: modelled the same way as any other medicine line (`fish oil`, `vitamin k`,
`potassium chloride` etc. are already in the registry as `product_kind` distinct from prescription
medicines) — no separate data model needed, just a UI filter on `product_kind`.

### What is genuinely missing

- **One merged registry view across sources with a sources chip per medicine.** Today
  `MedicationLine` rows exist; there is no endpoint that assembles "this generic, across every
  paper/pill-photo/receipt that touched it" into one card with a `sources: [{kind, artifact_id}]`
  chip list — the blueprint's `med(...)` card helper (blueprint line 213: `['3 papers','matching']`)
  has no backend equivalent yet. **PROPOSED**: `GET /profiles/{id}/medicines/{line}/sources`,
  aggregating every `Fact`/`Supply`/`Event` whose provenance touches this line's `fact_id` chain.
- **Now / All / Changes three-view tabbing**: no client screen groups medicines this way today
  (`web/src/screens/record/Medicines.tsx` exists but was not read in this pass for its exact
  grouping — flag for the builder to confirm against the blueprint's three-tab split before
  assuming it needs to be built from scratch).
- **"Show my pharmacist" sheet**: no dedicated summary-sheet endpoint exists; the data
  (`active_lines()`) already supports building one — this is a rendering gap, not a data gap.

### Explicitly NO interaction judgement

Already the house rule, already enforced in code, not just documentation: `FixtureRegistry.
interactions()` returns `review_state=awaiting_review` for a pair the fixture has not been
clinically checked against yet ("still flagged, never silent, queued for the pharmacist review
queue... the first time it is actually raised for a person" — `fixture.py` `_about`), and the
registry's own docstring is explicit that **Nura lists, a pharmacist judges**. Nothing in this
spec proposes changing that boundary; the registry surface's job is completeness and citation, not
a verdict on whether two medicines are safe together.

---

## 7. Connectedness

### What is stored vs derived

**Stored** (already exists, no change needed): `Fact.artifact_id`/`event_id` (provenance),
`Fact.supersedes_id` (history chain), `MedicationLine.source_artifact_id`/`source_event_id`,
`FeedItem.why: dict` (JSON — the reason a card exists, `Why` dataclass,
`app/delivery/feed/items.py:164-199`, kinds include `fact_ids`, `event_id`, `artifact_id`,
`visit_id`, `flag_id`, `source_id`, `rule`, `topic`).

**Derived at read time, not stored** (also already the pattern): `LineView.duplicate_of`
(computed in `active_lines()`), the analyst's `Evidence` tuples on an `Insight` (computed fresh each
report run, not persisted as a graph edge).

**GAP**: there is no general-purpose "neighbours of this item" query. Provenance today is a tree
rooted at one `Fact`/`FeedItem` pointing *backward* to its source artifact/event — there is no
index that lets a screen ask, forward, "what medicines/visits/policy items relate to *this* lab
result" the way the blueprint's `connected` scene's five-row list does (From/Related/Kept for/Your
policy/In your week). Each of those five rows today would need its own bespoke query against a
different table (`Fact` for "From", `MedicationLine` for "Related", `Appointment`/`ProviderNote`
for "Kept for", `Policy`/`PolicySummaryOut` for "Your policy", `InsightReport` for "In your week") —
**PROPOSED**: a thin `connections_for(subject_kind, subject_id)` service function that fans out to
each of those five existing reads and returns a uniform `[{label, title, target_kind, target_id}]`
list, rather than a new stored graph — keeps "nothing stored that could be derived and go stale."

### The item-detail screen contract (PROPOSED — no such screen exists client-side today)

Grepped `web/src/` for `*detail*`/`*item*`: no generic detail screen exists. Every current screen is
purpose-built per entity kind (`Medicines.tsx`, `Ledger.tsx`, `Timeline.tsx`, ...). PROPOSED
contract, one screen genuinely reusable across kinds:

```
GET /profiles/{id}/items/{kind}/{item_id}
  -> { headline, value?, unit?, flag?, history: Row[], connections: Connection[], clip?: ClipRef }
```

where `kind` is one of `result | medicine | visit | policy_item | receipt`. Rendering follows the
`headline`/`rows`/`card`/`actions` shapes already proposed in §1's protocol — this screen is the
first genuinely new consumer of that protocol, not a retrofit onto an existing one.

### Content-in-context placement rules

Which feed card kinds attach to which item kinds, reusing `CardType` (`app/delivery/feed/models.py`
lines 43-102: `FLAG, NOW, READING, VISIT, VISIT_LOGISTICS, MEMO, REORDER, NOTICE, RECALL_ACTION,
GATE, STORY, LEARNING, QUESTION, DUTY, CLIP, RECAP, LOCAL, SEASONAL, FOOD`) and the existing "why"
mechanism (`why_lines()`, `app/delivery/feed/why_sheet.py:22-43` — already correctly scope-gates a
why-reason, withheld line vs shown line, per reader):

| Item kind | Attaches | Existing mechanism to reuse |
|---|---|---|
| A lab result | `CLIP` (an explainer), `LEARNING` | `clipOf(item)` already exists (`web/src/feed/model.ts`, referenced by `GuideClip`/`ClipMedia`) |
| A medicine line | `REORDER`, `CLIP` (story/how-to-take) | `story.py`'s `medication_story()` already produces the per-medicine explainer content this would attach |
| A visit | `VISIT_LOGISTICS`, `QUESTION` (filed questions) | Already built: `app/reasoning/visits/planner.py`, `questionsOpen`/`briefOpen` in `nav.ts`'s `VisitList` |
| A policy item | `NOTICE` (renewal/waiting-period-ending, §5) | New — needs `PolicyDetail` from §5 first |
| A receipt | (none proposed — receipts feed the ledger and medicine cost chips, not a card kind of their own) | |

This table is the "content shown in context, not only in the feed" requirement — every row reuses
an existing card-building or story-building function; nothing here proposes a new content-generation
mechanism, only new *attachment points* for content that already exists.

---

## 8. Every non-happy state

Per screen, what the engine already honestly says (cited) vs what is undecided (PROPOSED).

| Screen | Empty | Loading | Partial | Unreadable page | Refusal | API down | Offline |
|---|---|---|---|---|---|---|---|
| Inbox (§3) | PROPOSED: "No papers yet" tile, no precedent screen exists | `status` stream (§1) | PROPOSED: batch summary must show partial counts even if some jobs still running — `{in, needs_you, same, failed, still_reading}` | `ReviewField.unreadable` already exists (`models.py`), routes to `type_field` (type it in) — reuse unchanged | `type: "refusal"` event, unchanged, already flows through `Notice` component (`web/src/ui/components.tsx:160-175`, `role="alert"`, `data-testid="notice"`) | `Notice` renders `t().errors.network` for an `Unreachable` error — same pattern, reuse | `web/src/offline/queue.ts` + `web/src/strings` `held: {held, tapped, sent}` — existing "taps held, then sent once" pattern (E00-08), reuse for a batch upload queued offline |
| Matching (§4) | PROPOSED: "Nothing changed" state, no precedent | `status` stream | PROPOSED: partial matching (some fields matched, one still Conflict) — show settled rows immediately, unsettled ones last, matches blueprint's own `matching` scene layout | Bounds-violation fields (§4) reuse `needs_confirm` | Same `Notice` pattern | Same | Same held-queue pattern for a conflict resolution tapped offline |
| Policy passport (§5) | `s.insurance.none`/`noneOther` already exists in strings (`me.ts` `insurance.none`) — reuse, do not invent new copy | `status` stream, page-by-page (§2) | A policy partially read (some pages failed) — PROPOSED: show tabs for sections that did parse, a `note` for the page(s) that did not, never block the whole passport on one bad page | Same `unreadable` pattern extended to `PolicyDetail` line items | Same `Notice` | Same | Read-only cached view of last-read passport via existing `web/src/offline/feedCache.ts`-style pattern — PROPOSED extension, no policy-specific cache exists yet |
| Registry (§6) | Existing `record.papersNone`/`papersNoneOther` copy pattern, reuse | N/A — registry reads are not streamed today (no model call at read time) | N/A | N/A — registry is a computed view over confirmed facts, not itself extracting | N/A | Same `Notice` | Registry is a plain synchronous read — no offline-specific case beyond ordinary offline queueing of a confirm |
| Connected/item-detail (§7) | PROPOSED: no precedent, needs one (e.g. "Nothing connects here yet") | N/A (plain read) | PROPOSED: some connection rows may fail to resolve (e.g. a policy scope withheld) — render withheld rows exactly as `why_sheet.py` already renders a withheld why-line, never blank | N/A | Same `Notice` | Same | Same |
| Conversation/Ask (§1) | Existing `talk.working`/`talk.failed`/`talk.tryAgain` strings | `status` stream | Existing: `answer_delta` already renders as it arrives, never waits for the whole answer | N/A | `type: "refusal"` — exact match already | Same `Notice` | `web/src/screens/Ask.tsx` — needs check: does an Ask sent offline queue like a batch upload does? **Flag for builder**: not confirmed in this research pass; the existing `queue.ts` pattern may not currently cover Ask specifically. |
| A helper key without the scope | Section named as withheld, never blank | — | — | — | — | — | — |

**A helper key without the scope**: already correctly built and must not be re-invented — `why_sheet.
py`'s `withheld` line pattern, `InsightReport`'s `withheld: list[str]` naming which section keys
were dropped (service.py `_narrowed_for`), and `insurance/relevance.py`'s two-tier
(full/narrow) pre-visit brief with a **named** narrow-tier line rather than an absent section, are
three independent, already-correct implementations of "section named as withheld, never blank."
Any new screen in this spec (policy passport, registry, connected) must follow the same pattern,
not silently omit a tab/row a key cannot see.

**Very long text, ms/zh lengths, large type, reduced motion, desktop width**: no screen-specific
research was done in this pass (out of scope of the files listed in the task) — existing app-wide
mechanisms exist and should be reused unchanged: `prefers-reduced-motion` handling already exists in
`web/src/ui/{warm,feed,tokens,design}.css` and in the blueprint's own JS (`RM` flag, `sleep()`
short-circuits to 0ms, `@media(prefers-reduced-motion:reduce)` disables all `.phone` animations,
blueprint line 139) — **the redesign's screens must gate every new animation the same way, not add a
second reduced-motion mechanism.**

---

## 9. Navigation

**The five-tab structure already exists and matches the blueprint's dock exactly** —
`web/src/nav.ts`: `Tab = "home" | "health" | "connect" | "services" | "profile"`,
`tabsFor()` builds the `TabItem[]` filtered by scope (`connect` needs `Scope.FAMILY`, `services`
needs `Scope.VISITS`; `home`/`health`/`profile` always shown). This is a 1:1 match with the
blueprint's `TABS` const (`home/health/family(labelled Connect)/visits(labelled Services)/
profile`) — **no navigation redesign needed at the tab-bar level**, only placement of new screens
within it.

| New screen | Tab | Where under it | Cite |
|---|---|---|---|
| Inbox (§3) | Health | New `RecordAt` entry (`{name: "inbox"}`), alongside existing `papers`/`medicines`/`timeline` | `web/src/record/places.ts` — `HubEntry` type already lists `"papers" | "medicines" | "routine" | "timeline" | "trends" | "providers" | "changes" | "ledger"`; add `"inbox"` |
| Matching results (§4) | Health | Reached from Inbox's summary action, not its own tab entry — matches blueprint's `inbox -> matching` flow (`go: 'matching'`) | |
| Policy passport (§5) | Health | New `RecordAt` entry `{name: "policy"}`, beside the existing `{name: "ledger"}` — `Ledger.tsx` already exists in `web/src/screens/record/`, `Policy.tsx` does not | `web/src/screens/record/` listing: `Day.tsx, Ledger.tsx, Medicines.tsx, Papers.tsx, Record.tsx, Timeline.tsx, parts.tsx` — no `Policy.tsx` |
| Medicine registry (§6) | Health | Existing `{name: "medicines"}` entry — this is a richer *rendering* of data `Medicines.tsx` already reads, not a new nav entry | |
| Item-detail (§7) | Wherever it is opened from (no tab of its own) | `{name: "item", kind, itemId}` — a route reachable from any row in any of the above, deep-linkable | PROPOSED, follows the same `go({name: "record", at})` pattern already used everywhere in `nav.ts`/`places.ts` |
| Profile's existing "Insurance" row | Profile | Already exists (`me.insurance` string, `insurance_schemas.py` API) — becomes a shortcut into the same Health-tab policy passport, not a second implementation | `web/src/strings/types.ts` `me.insurance: string` |

**Back behaviour**: unchanged from the existing pattern — every screen in `web/src/nav.ts`/
`record/places.ts` already uses `go({name: "record", at})` with a `back` prop wired to `Shell`
(`Shell tab="services" ... topBar={{variant:"board", title, back:true}}`, `VisitsScreen` as the
model). New screens should follow this exactly, not invent a new back stack.

**Deep links**: the existing `RecordAt` union is already how every Record-hub screen is
addressed (`{name:"medicines", index}`, `{name:"trends", analyte}`, etc.) — new entries
(`inbox`, `policy`, `item`) slot into the same union, inheriting whatever deep-link mechanism
already resolves a `RecordAt` to a URL (not traced in this pass — flag for the builder to confirm
`flow.ts`'s URL scheme covers a new `RecordAt` member without additional plumbing).

---

## 10. Accessibility and performance

**Contrast on glass over the animated ground**: the blueprint's own tokens
(`--c:#fbf6f0` text on `--g:rgba(255,255,255,.10)` fill over the `.atmos` gradient) need a checked
contrast ratio against the *darkest* point of the moving gradient (`#1f1731`, the ground's bottom
stop), not just against the glass fill — text-on-glass-on-gradient is a three-layer contrast
problem, and the brief's own >=4.5:1 rule must be checked against the worst-case composite, which a
static Figma comp would not catch. **PROPOSED**: a contrast-check test in `web/tests/e2e/a11y.spec.
ts` (already exists) computing the composite colour at the gradient's darkest stop, not sampling
mid-gradient.

**Streamed text and `aria-live`**: the existing `Conversation.tsx` components already use
`aria-live` in five files (`Conversation.tsx`, `Ask.tsx`, `Feed.tsx`, `family/Thread.tsx`,
`onboarding/parts.tsx`) — not read in detail this pass. **PROPOSED policy** for the new `status`/
`text` events (§1): `status` region `aria-live="polite"`, updated in place (never appended) so a
screen reader announces the *replacement*, not a growing list — this is the accessibility
consequence of fixing the "accumulating checklist" defect, not a separate concern. `text` deltas
should **not** each trigger their own announcement (would be unusable word-by-word); batch to
sentence or paragraph boundaries for the live region, independent of the visual word-by-word reveal.

**Focus in sheets**: the blueprint's `openSheet()` (blueprint line 181) does not appear to manage
focus (no `focus()` call visible in the reveal). **PROPOSED**: on `sheet` open, move focus to the
sheet's heading (`<h3>`); on close, return focus to the control that opened it — standard modal
focus-trap discipline, not yet present in the blueprint's own reference JS, so the real
implementation must add it rather than copy the blueprint verbatim here.

**`backdrop-filter` cost and the fallback**: `backdrop-filter:blur(18px)` (`.glass`) and
`blur(24px)` (`.sheet`) are already used elsewhere in the shipped app (`web/src/ui/{warm,base,
design}.css` all reference `backdrop-filter`) — this is not a new cost the redesign introduces, it
is already paid. **PROPOSED**: confirm (not traced this pass) whether those existing stylesheets
already carry a `@supports not (backdrop-filter: blur(1px))` fallback (a solid, slightly darker fill
instead of blur) for a weak phone/older Android WebView — if not, add one, since the redesign adds
*more* glass surfaces (every row, every card), multiplying whatever cost already exists.

**The orb's cost**: `conic-gradient` + `filter:blur(5-15px)` + a 7s/2.2s CSS `animation: spin` — pure
CSS, GPU-composited on any modern mobile browser, cheap. The larger cost is **many small blurred
elements simultaneously** (three atmos blobs + orb + every glass card's own backdrop-filter) on one
screen — **PROPOSED**: cap simultaneous `backdrop-filter` layers per screen (e.g. never blur behind
more than the visible viewport's cards; use a plain translucent fill, no blur, for off-screen/
below-the-fold cards) rather than relying on the browser to skip work for elements outside the
viewport, which is not guaranteed.

---

## 11. Work packages, dependency order

| # | Package | Depends on | Rough hours | Independent safety review needed? | Acceptance test |
|---|---|---|---|---|---|
| 1 | Conversation protocol step 1: single in-place `status` line replacing `StepTrace`'s accumulating checklist, on `/ask/stream` only | none | 12–16h | No (pure rendering change, no new data touched) | `web/tests/e2e/*.spec.ts` extended: a multi-step ask shows exactly one status line on screen at any time, never more than one `data-testid="thinking"` node simultaneously present |
| 2 | Fixture papers for the matching-engine tests (open item c) | Owner/counsel supplies redacted papers, or team hand-builds MY-shaped synthetics with clinical sign-off | 8–20h (mostly waiting on the owner, not build time) | **Yes** — any synthetic lab/policy fixture with printed ranges needs the same clinical review `ranges.json` already flags for itself | New fixtures load through `FixtureExtractor` and `FixtureRegistry` without schema errors; at least one lab-pair fixture with a genuine analyte-name mismatch exists |
| 3 | Analyte synonym table (§4), 40 rows | Package 2's fixtures (to test against) | 16–24h build + **clinical review timeline outside this estimate** | **Yes — every row NEEDS CLINICAL REVIEW** before use on real data | `tests/conformance`-style test: every synonym in the table resolves to exactly one of the 40 canonical codes; every canonical code round-trips its unit factor without loss |
| 4 | Matching engine core: six verdicts, supersession writes, audit | Package 3 | 40–60h | **Yes** — writes medicine and lab facts that reach a person | Given two fixture lab reports for the same profile with one analyte's value changed, the engine produces exactly one `Newer` verdict, closes the old fact with `valid_to`, writes the new one with `supersedes_id`, and both remain queryable |
| 5 | Streamed extraction (§2): partial-JSON rows + page-by-page PDF reads, no open transaction during a model call | none (independent of matching) | 24–32h | **Yes** — extraction feeds every downstream medical/financial fact | A 40+ page fixture PDF streams `status` events with real, increasing page numbers; killing the process mid-read and restarting resumes rather than restarting from page 1 (once package 6's job table exists) or at minimum fails cleanly per-page, not for the whole document |
| 6 | Inbox job model (§3): table, fingerprint dedup, resumability, batch API | Package 5 (extraction must emit per-stage status for the job table to track) | 32–40h | No additional review beyond package 4/5's (writes go through the same audited doors) | Uploading the same file's bytes twice for one profile produces one `SAME`-state job and one model call, not two; killing the worker mid-batch and restarting resumes unfinished jobs from their last persisted state |
| 7 | Policy passport schema (§5): `PolicyDetail` table, `Citation` shape, policy-specific extraction prompt | Package 5 | 32–40h | **Yes** — money and coverage facts a person may act on | Given a fixture policy PDF, every benefit/exclusion/how-to-claim line in the output carries a `{quote, page}` citation traceable to the source artifact |
| 8 | Medicine registry merged view + sources chip + Now/All/Changes screen | none (mostly a read-side aggregation over existing data) | 20–28h | No (no new writes — read-only aggregation over already-safety-gated data) | Given a profile with a medicine on 3 different source papers, the registry view lists all 3 as sources on one card, never as 3 separate medicine cards |
| 9 | Connectedness: `connections_for()` fan-out + item-detail screen | Packages 6, 7, 8 (needs inbox/policy/registry data to link to) | 24–32h | No (read-only, reuses existing scope-gated reads) | Opening an item-detail screen for a lab result with a withheld-scope policy connection shows a named withheld row, never a blank or missing row |
| 10 | Conversation protocol steps 2–5: `looked_at`, `rows`/`tabs`/`card` on new screens, `actions`/`sheet` with real `target` wiring | Packages 7, 8, 9 (policy/registry are the first real consumers of `rows`/`tabs`) | 40–56h | **Yes for the `sheet`/`actions` wiring** — this is where a proposal becomes a real confirm-gated write | A policy passport's four tabs (Covers/Not covered/How to use it/Claims) render from `tabs`+`rows` events, not client-hardcoded copy; a `propose_action` with `kind:"message_provider"` opens a `sheet` that streams real drafted text and a working three-state Copy button |
| 11 | Non-happy-state coverage pass (§8) across every new screen | All of the above | 16–24h | No | Each cell in §8's table has a corresponding e2e test asserting the exact fallback copy/testid, not just "doesn't crash" |
| 12 | Accessibility/performance pass (§10): contrast test at gradient's darkest stop, `aria-live` policy on `status`/`text`, sheet focus trap, `backdrop-filter` fallback audit | All screen work (9-11) | 16–20h | No | `a11y.spec.ts` passes with the new screens included; a `prefers-reduced-motion` run of every new screen shows all content immediately with zero animation |

**Total, excluding waiting on owner/counsel/clinical-review turnaround**: roughly 280–380 build
hours. The critical path is 2 -> 3 -> 4 (fixtures -> synonym table -> matching engine) and 5 -> 6
(streaming -> inbox), both gated on non-engineering turnaround (owner-supplied fixtures, clinical
sign-off) that this estimate cannot compress.
