# Design build 2, step 2 — the interaction map

**Status: draft for owner confirmation.** Builds on `design-build-2-reading.md` (step 1). Sources: the 26
scenes of `docs/design/experience-blueprint.html` (lines 193–251), the specification in
`docs/design/design-build-2.md` §1 (its own §4, §9–§15, §20–§23, §27, §28), the engine inventory in
`docs/design/audit-2026-09-22.md` §7.1 (event vocabularies), and the kit at `web/src/ui/kit/*`. Every kit
column below is a file that exists today; every "spec component" column is quoted from §27. This is step 2 of
the twelve-step plan in `design-build-2.md` §4.

**A finding that shapes every row below.** The blueprint's own engine (`show()`, line 258) implements *every*
scene change identically: `scr.innerHTML=''`, then the scene's render function runs. Mechanically, "Home →
Health" and "Who is this for → The cloud" are the same operation. This means the blueprint's code **cannot**
tell us which transitions should be `navigate` and which should be `expand-in-place`/`stream` — that judgement
has to come from the spec's own intent (§1, §11, §12), not from the reference's implementation. Every
`navigate` row below is justified from the spec and from what the moment *does* (crosses an entity boundary, a
capture/auth boundary, or a persistent-navigation boundary per §17), not from how the blueprint happens to be
coded. Two further things follow from step 1 and are stated once here rather than in every row: **no
shared-element transition exists anywhere in the blueprint's own code** (§12 is intent, not a captured
pattern), and **the composer never expands in place in the blueprint** (§9 is likewise intent). Rows that touch
either are marked accordingly.

---

## 1. The interaction map

Legend — **AI state**: idle / listening / thinking / responding / error (§28). **Card/screen state**:
collapsed / pressed / expanded / loading / complete / error (§28). **Transition**: expand-in-place /
shared-element / sheet / stream / navigate.

| # | Moment | Trigger | AI state | Card/screen state | Transition (reason if `navigate`) | What the UI shows while waiting | What can go wrong / the calm response | Kit today | Spec component (§27) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Welcome | App opens, first run | idle | complete | **navigate** to Sign in — no account or record exists yet; nothing on Welcome to expand | — (nothing async; orb is `.lg` breathing at rest) | n/a | `Orb` (`size="lg"`) | AIOrb |
| 2 | Sign in | Enters phone + the sent code, taps Continue | idle | loading→complete | **navigate** to onboarding — a verified identity is a new account object, not a detail of the welcome screen | (blueprint has no explicit wait copy here; real send/verify calls should use LoadingState, never a bare spinner) | Wrong/expired code → calm, specific: "That code didn't match. We can send a new one." (spec §23 pattern; not attested in blueprint, which never fails this step) | plain form fields (no kit component wraps sign-in today) | LoadingState, ErrorState |
| 3 | Who is this for — pick "Me" | Taps a chip | responding | complete | **expand-in-place / stream** — same screen, the conversation continues (`me()` bubble + a second `nura()` turn appended, line 197) | n/a (chip tap is instant; the *reply* streams via `nura()`) | — | `Conversation.tsx` (`MessageBubble`, `Exchange`-shaped) | AIComposer / ContextualAction |
| 4 | Who → The cloud | Taps Continue | idle→thinking | complete | **stream**, not navigate — one onboarding conversation; the blueprint's `go('cloud')` clears the DOM (see the finding above) but there is no entity-boundary reason to treat this as a new surface | n/a | — | — | AIComposer |
| 5 | The cloud — toggle a condition | Taps a bubble | idle | pressed→complete | in-place toggle, no transition | n/a (`.bub`→`.bub.on`, `scale(1.06)`, 350ms, line 122) | — | none (bespoke `.bub`; no kit equivalent) | InsightCard variant (tertiary) |
| 6 | The cloud — "Or just tell me" | Taps the alternate-entry button | listening→thinking | loading | **sheet** — a focused capture moment (§20) | `openSheet()` streams the person's own words back before writing (line 182) | Speech not understood → "I didn't catch that. Try again, or tap instead." (spec §23 pattern; not attested) | `Sheet` / `ActionSheet` | BottomSheet |
| 7 | Cloud → Add a paper | Taps "That is me" | idle | complete | **stream**, same reasoning as #4 | n/a | — | — | AIComposer |
| 8 | Add a paper — choose entry method | Taps Take a photo / Choose a file / Choose many | idle | collapsed→loading | **navigate** — hands off to a native camera/file picker (an OS-level surface) and a real upload call; a genuine boundary, not a detail view | n/a (the *next* scene carries the wait) | Picker cancelled → return to this screen unchanged, no error | plain rows (no icon-row kit component) | DocumentCard |
| 9 | Nura reads it | (passive — the AI's own turn after upload) | thinking→responding | loading→complete | **stream** | Four real backend stages, one line at a time, in place: *"Keeping your paper safe…", "Looking at your paper…", "Found a blood test…", "Checking it closely…"* (`t:[...]`, line 203) | Extraction fails/low confidence → per spec §23's shape: state what could not be read and what to do, never an HTTP code (not attested in blueprint, which never fails here) | `Conversation.tsx` (`ThinkingIndicator`/`StepTrace`), `StatusLine` | LoadingState |
| 10 | Reading → Report table | Taps "See the full table" | idle | expanded | **shared-element** — `design-build-2.md` step 8 names this exact pair ("Home insight → blood test table") as the model case for `ExpandableCard`; today the blueprint (and the app) `navigate` here | n/a | — | none (today: full navigate) | ExpandableCard |
| 11 | Report table — confirm "Looks right" | Taps the CTA | idle | complete | **navigate** to Insight — a genuinely new AI turn (connecting medicines + the next visit), not a deeper view of the same table; distinct from #10 | n/a | — | `ThreeStateButton` (label→busy→done pattern, `openSheet`'s CTA shape) | ContextualAction |
| 12 | Report table — "Check this one" (uncertain row) | Taps the flagged row | listening→responding | loading | **sheet** | `openSheet()` streams the uncertain line's own text (line 205) | — | `Sheet` | BottomSheet |
| 13 | Report table — "Fix a number" | Taps the button | idle | — | **not built** — the blueprint's own handler is a toast stub ("Tap any value to correct it", line 205) with no real edit flow behind it | n/a | n/a | `ReviewField` exists in the kit but nothing wires it here | ExpandableCard (inline edit) |
| 14 | Insight — "Keep these for my visit" | Taps the CTA | responding | complete | **navigate** to Home — task complete, returning to the hub | busy label "Keeping…" then done "Kept" (inline three-state handler, line 207) | — | `ThreeStateButton` | ContextualAction |
| 15 | Many papers at once (Inbox) | Sends a whole folder | thinking | loading | **stream** | A shared status counts through the batch ("Reading 2 of 7…") while each row's own flag cycles `Sorting → <kind> → Reading → Matching → <verdict>` independently (line 209) — two motion channels at once | A duplicate is caught by fingerprint before any read is paid for (audit §2 row 09 — package not yet built) | none dedicated; closest is `Conversation.tsx` + `Flag` per row | LoadingState, DocumentCard |
| 16 | Inbox → What changed (Matching) | Taps "See what changed" | idle | complete | **navigate** — a distinct verdict-review surface over the whole batch, not one paper's detail | n/a | — | — | InsightCard |
| 17 | Matching — "Settle the two that need you" | Taps the CTA | listening→responding | loading | **sheet** | `openSheet()` streams the conflict, e.g. "Your prescription … says 5 mg. The clinic letter … says 10 mg." (line 211) | — | `Sheet` | BottomSheet |
| 18 | Matching sheet → Registry | Confirms the dose in the sheet (`then:'registry'`) | idle | complete | **navigate** — the medicines record is the object of truth; landing there confirms the write took effect | busy "Updating…" then done "Updated" | Write fails → nothing overwritten; old value stays with an end date (audit §2 row 10: "Nothing is ever overwritten") — the calm framing already exists in copy, needs an ErrorState if the write itself fails | `ThreeStateButton` | ContextualAction |
| 19 | Policy passport — upload and read | (passive) | thinking | loading | **stream** | Real page-by-page progress: *"Reading page 4 of 48…"* through *"page 48 of 48…"*, each held 430ms (`hold:430`, line 213) — the most literal "honest loading state" in the file | Long document times out → per spec §23 shape (not attested; blueprint always finishes) | `Conversation.tsx` | LoadingState |
| 20 | Policy — switch tabs (Covers / Not covered / How to use it / Claims) | Taps a tab | idle | expanded | **expand-in-place** — content swaps inside the same card via `tabset()`'s own stagger (`70+90k`ms, line 189), not a route change | n/a | — | `TabBar` (tab switching; the segmented-content stagger itself has no kit equivalent) | ExpandableCard, BottomNavigation |
| 21 | Add a medicine — photo/type entry, clarify which statin | Shows a box, or types/speaks; picks a chip if ambiguous | listening→thinking→responding | loading→complete | **stream** | Real stages, e.g. *"Looking at your photo…", "Found a medicine box…", "Checking the licensed register…"* (line 217) | Box only names a family ("STATIN") → Nura asks which one rather than guessing (line 217) — the calm-refusal pattern already built into the reference | `Conversation.tsx`, bespoke `row()` (Sure/Need-you) | LoadingState, DocumentCard |
| 22 | Add a medicine → Registry | Taps "Add to my medicines" (or the dose-change sheet resolves) | responding | complete | **navigate** — same reasoning as #18 | busy "Adding…" then done "Added" | — | `ThreeStateButton` | ContextualAction |
| 23 | Medicine registry — switch tabs (Now / All / Changes) | Taps a tab | idle | expanded | **expand-in-place** (`tabset()`, same mechanism as #20) | n/a | — | `TabBar` | ExpandableCard, BottomNavigation |
| 24 | Registry — "Show my pharmacist" | Taps the CTA | listening→responding | loading | **sheet** | `openSheet()` streams the assembled list (line 224) | — | `Sheet` | BottomSheet |
| 25 | Everything connected — tap a related row (source, medicine, visit, policy, analyst mention) | Taps any of the five rows | idle | complete | **navigate today**; per spec §12 these could become shared-element expansions since each row already carries the target's identity (icon + label) — an explicit decision the owner should make, not inferred | n/a | — | — | ExpandableCard (candidate) |
| 26 | Home — headline + insight card (on load) | (passive, screen opens) | responding | complete | **stream** — the headline is composed from the day's top feed item (`s.does`, line 229), not fixed copy | word-by-word headline (`stream(...,85)`, line 228) | Nothing to surface today → per spec §22 shape (not attested; blueprint's Home is never empty) | `SoftText` (word reveal), `Hero`/bespoke `.big` | EditorialHeadline |
| 27 | Home — "See them in a table" | Taps the CTA on the insight card | idle | expanded | **shared-element** — the plan's own example (`design-build-2.md` step 8); today `navigate` | n/a | — | none today | ExpandableCard |
| 28 | Home — reminder row (evening tablet due) | Taps the row | idle | complete | **navigate** to Medicines — today's doses are a distinct, persistent object, not a deepening of the headline | n/a | — | — | ReminderCard |
| 29 | Home — feed row (a 30-second clip) | Taps the row | idle | complete | **navigate** to For you — a separate content surface (media), not health data | n/a | — | — | MediaCard |
| 30 | Home — composer tap | Taps the docked "Ask Nura anything" bar | listening | expanded | **navigate today; spec §9 requires expand-in-place** — no reference implementation exists anywhere in the blueprint (step 1, conclusion 1) | n/a | — | `AskBar` (docked pill only) | AIComposer |
| 31 | Ask — first turn | Types/speaks a question | listening→thinking→responding | loading→complete | **stream** | Real stages (e.g. *"Opening your policy letter…", "Reading the exclusions page…"*, line 230) then `looked()` sources before the answer | Falls back to keyword search silently in the real app today (audit §7.2, "Ask" row: 5 distinct failure paths, none surfaced to the UI) — should become an honest badge (audit §7.3: "an honest badge when the answer came from the fallback") | `Conversation.tsx` (`Exchange`, `LookedAt`) | LoadingState, InsightCard |
| 32 | Ask — follow-up turn | Asks a second question in the same thread | listening→thinking→responding | loading→complete | **stream** — same surface, the thread continues (no navigate) | Same shape as #31; sources for the second turn are a different set (`looked()` called again) | — | `Conversation.tsx` | InsightCard |
| 33 | Ask — action chip ("Draft a message to the insurer") | Taps the chip | listening→responding | loading | **sheet** | Streams the draft's lines, then Copy→Copying→Copied (line 230) | — | `Sheet`, `ThreeStateButton` | BottomSheet, ContextualAction |
| 34 | Ask — action chip ("Add to my visit questions") | Taps the chip | idle | complete | in-place confirmation (toast), no transition | n/a | — | (toast — no kit component named) | ContextualAction |
| 35 | Health (tab) | Taps the Health tab | idle | complete | **navigate** — bottom navigation is persistent infrastructure by design (§17), not a card expanding | n/a (static composed view — no `nura()` call in this scene, per step 1) | Nothing recorded yet → per spec §22 shape (not attested; blueprint's Health is pre-populated) | `TabBar` | BottomNavigation |
| 36 | Health — "Read it" (open the weekly Analyst) | Taps the CTA | idle | complete | **navigate** — the Analyst is a distinct, saved report covering the whole week, not an expansion of the summary card | n/a | — | — | InsightCard |
| 37 | Health — blood test row ("Look") | Taps the row | idle | complete | **navigate today** (`data-go="report"`); spec §11's own chain ("Blood pressure → week chart → daily values…") has **no reference instance in the blueprint at all** — the blood-pressure trend card on this same screen is not tappable in the blueprint's own code (no `data-go` on it) | n/a | — | — | ExpandableCard, TrendCard |
| 38 | Health Analyst — passive read | (screen opens) | thinking→responding | loading→complete | **stream** | Four stages (line 234), then `looked()`, then sections reveal **one at a time**, each preceded by its own 260ms wait (the sequential-loop pattern from step 1) | A section with nothing to say is left out entirely, never shown empty (line 234's own `s.see`) — the one place the blueprint demonstrates an omission rule instead of an EmptyState | `Conversation.tsx` | LoadingState, InsightCard |
| 39 | Analyst — "Turn these into visit questions" | Taps the CTA | idle | complete | in-place confirmation (toast), no transition | n/a | — | (toast) | ContextualAction |
| 40 | Analyst — "Ask about this" | Taps the CTA | idle | complete | **navigate** to Ask — leaving a fixed report for the open-ended conversational surface | n/a | — | — | AIComposer |
| 41 | Medicines — "I took it" | Taps the button | idle | pressed→complete | **in-place** state change — the button itself becomes the record (`.btn.light`→`.btn.done`, line 236); no AI turn at all | n/a (instant; no `nura()` call — correctly, recording a tap needs no reasoning) | Offline → held on the phone and written later (design-build-2.md §2 table, "Doses, taps, offline holding" — Ready) | bespoke `.dose` row (no kit equivalent) | ContextualAction |
| 42 | Medicines — "Take a photo" (unidentified tablet) | Taps the CTA | listening→responding | loading | **sheet** | `openSheet()` reads the strip back (line 236) | Reads printed text only, refuses to guess from colour/shape (line 236's own `s.does`) — a calm refusal, not a silent guess | `Sheet` | BottomSheet |
| 43 | Visits (tab) | Taps the Services tab | idle | complete | **navigate** — same reasoning as #35 | n/a | — | `TabBar` | BottomNavigation |
| 44 | Visits — "What might it cost?" | Taps the CTA | listening→responding | loading | **sheet** | Streams a cost expectation cited to past receipts (line 238) | Estimate needs a booked visit; today's engine has no unbooked-procedure estimator (audit §7.1, ESTIMATE row: "never exercised against the real shape") | `Sheet` | BottomSheet |
| 45 | Visits — "Draft the message" | Taps the CTA | listening→responding | loading | **sheet** | Streams the draft, then Copy→Copying→Copied | Never sends itself — stated in the sheet's own footer text (line 238) | `Sheet`, `ThreeStateButton` | BottomSheet, ContextualAction |
| 46 | Insurance — passive load | Navigated here from Visits' "Insurance · See" row | idle | complete | **navigate** — a distinct policy record, static composed view (no `nura()` call) | n/a | Real app today shows a genuine empty state here: *"Nura has no insurance written down for you yet"* (audit §2 row 11) — the one measured EmptyState instance in the whole codebase; the blueprint itself never shows an empty policy | — | EmptyState |
| 47 | Insurance — "Add a letter or receipt" | Taps the CTA | idle | loading | **navigate** to Reading — same capture boundary as #8 | (carried by the Reading scene) | — | — | DocumentCard |
| 48 | For you (feed) | Reached from Home's feed row, or a future tab | idle | complete | **navigate** — a separate content surface (media), static composed reveal | n/a | Today's real API returns text-only cards with no source — the blueprint's whole media promise is currently undrawable (audit §2, "For you" row: "no clip and no article exist to draw") | — | MediaCard |
| 49 | For you — tap Play on a clip | Taps the circular play button | idle→responding | loading→playing | **in-place** media-state change — no navigation | Caption streams under the poster at 210ms/word, the slowest word-pace measured (line 242) | Voice asset missing → real backend 404 by design (`GET /profiles/{id}/feed/{item}/voice`, audit §2, "Errors and blank frames"); the actual defect is the fallback firing silently ten times (`TooLongToSay`) rather than surfacing anything | `Poster`, `PlayerStrip` | MediaCard |
| 50 | Not feeling well — entry | Taps "Not well?" from Home's header | idle | complete | **navigate** — the safety surface must be reachable in one unambiguous tap from anywhere, regardless of scroll position (§17 style, applied to safety) | n/a | — | — | ContextualAction |
| 51 | Not feeling well — pick a symptom (e.g. "Chest pain") | Taps the chip | error (deliberately) | complete | **in-place** — background swap + card reveal in the same screen at 60ms (line 244), the fastest and least-transitioned moment measured; no `nura()`, no `think()`, no streaming | n/a — no wait is shown by design | Red-flag rules run on-device and server, no model in the loop (line 245's own `s.does`) — the one place a "what can go wrong" column does not apply, because nothing here is allowed to be uncertain | bespoke alarm card (no kit equivalent) | ErrorState (as "alarm", not failure) |
| 52 | Connect (tab) | Taps the Connect tab | idle | complete | **navigate** — same reasoning as #35 | n/a | Real app today shows three empty sections ("No call is on your calendar yet.", etc. — audit §2 row 24) where the blueprint shows three populated role rows | `TabBar` | BottomNavigation, EmptyState |
| 53 | Connect — "Let someone in" | Taps the CTA | listening→responding | loading | **sheet** | Streams the scope choice, then reads consent words in full before it is given (line 246's own `s.does`) | Consent withdrawal must be one tap (line 246) — not shown as a failure path but a reversibility guarantee | `Sheet` | BottomSheet |
| 54 | Connect — "See it as Mei" | Taps the CTA | idle | complete | **navigate** — switching the acting profile is an identity/permission change, not a view of the same record | n/a | — | — | AppShell |
| 55 | Mei's Home | (passive, same Home template, caregiver voice) | responding | complete | **stream** — structurally identical to #26's `stream()` call (step 1, conclusion 10); listed separately only because the words differ | word-by-word headline, caregiver-voiced (line 248) | — | `SoftText` | EditorialHeadline |
| 56 | Profile (tab) | Taps the Profile tab | idle | complete | **navigate** — same reasoning as #35; also the one scene the audit found **freezes WebKit on open** (audit §2, "Engines" note) — a defect, not a design choice | n/a | Synchronous loop blocks the render thread on Safari; on the owner's own iPhone this tab does not open at all (audit §2) | `TabBar` | BottomNavigation |

---

## 2. The three state machines of §28

### 2.1 AI state (idle / listening / thinking / responding / error)

| From → To | Triggering event (user or system) | Real backend event today | Under the AG-UI-shaped vocabulary (audit §7.4–7.5) |
|---|---|---|---|
| idle → listening | Person taps the mic/composer, or begins speaking | **None** — no capture-start event exists in any of the six vocabularies (audit §7.1) | Would need a client-local state, or a new lightweight `RUN_STARTED`-adjacent signal at capture start |
| listening → thinking | Capture ends / question submitted | The first `step{key,label,name}` (or `step{key,label}` for `find`) of whichever route fired (audit §7.1 table) — there is no dedicated "run started" event; the first step doubles as one | `RUN_STARTED` |
| thinking → thinking (stage change) | Backend emits the next reasoning stage | `step`/`step_label` events, in **four different payload shapes under the one name `step`** across routes (audit §7.1: ask/turns, find, insights, photos/imports) | One `step` shape, or `TOOL_CALL_START`/`RESULT` where the stage is really a tool call (today collapsed into a localised sentence, audit §7.1 "the identity is gone by the time it reaches the wire") |
| thinking → responding | Backend sends the terminal payload | One of **four mutually incompatible terminal events for one concept**: `answer`/`answer_sentence` (ask), `results` (find), `report` (insights, and again with a *different* payload shape on the paper-insight route), `card` (photos/imports, not-feeling-well) — audit §7.1 | `TEXT_MESSAGE_START/CONTENT/END`, or `STATE_SNAPSHOT`/`STATE_DELTA` for structured content |
| responding → idle | Content fully delivered, no further turns pending | **None** — no explicit "run finished" signal; the client infers completion from the terminal event arriving (audit §7.1: "`RUN_FINISHED` … today faked in one screen", referring to `insights.ts:120-125`) | `RUN_FINISHED` |
| thinking/responding → error | Backend raises a refusal, or the connection fails | `refusal` — present on 5 of 6 vocabularies; **absent on `…/papers/{id}/insight/stream` phase 3**, where "a refusal there kills the connection silently" (audit §7.1, a named defect) | `RUN_ERROR` |
| error → idle | Person dismisses or retries | Client-only; no backend event needed | Client-only |

### 2.2 Card state (collapsed / pressed / expanded / loading / complete / error)

| From → To | Triggering event | What drives it today |
|---|---|---|
| collapsed → pressed | Finger down on a tappable card | Real `<button>` `:active`, `scale(0.98)` over `--press` (90ms) — `motion.md` §3, applied via `.pill`/`.card-button`/`.list-row` etc. in `web/src/ui/base.css`/`warm.css` |
| pressed → expanded | Release on-target, and the target data is already available | Local navigation/toggle; no network wait |
| collapsed → loading | Tap opens a request whose data has not returned | `pendingSignal(key)` count > 0 (`web/src/api/client.ts`); `PendingCard` (`web/src/ui/kit/Pending.tsx`) draws `SkeletonCard` only after a 150ms CSS `animation-delay`, so a fast answer never flashes it (`motion.md` §1) |
| loading → complete | `pendingSignal(key)` returns to 0 with data | The terminal AI-state event above (`answer`/`report`/`card`/`results`), or a plain REST response settling |
| loading → error | The request settles as a failure | `refusal`, or a rejected fetch — surfaced today via **six different hand-written rejection strings**, one per stream wrapper (audit §7.1, "reject with six different hand-written strings for the one condition 'the terminal event never came'") — the concrete case for a single `ErrorState` |
| expanded → collapsed | Back, tap the same card again, or navigate away | Local only |
| complete → expanded | Tap a card whose data is already loaded (a progressive-disclosure drill, §11) | Local only — no network wait, which is why §11's chain has no "loading" beat once the parent screen has already fetched |

### 2.3 Media state (idle / loading / playing / paused / complete)

| From → To | Triggering event | What drives it today |
|---|---|---|
| idle → loading | Tap the poster's play button (`.pl`, scene 22) | Client-local; the blueprint calls `stream()` on the caption immediately rather than waiting on a real asset |
| loading → playing | Media begins actual playback | Blueprint approximates this with `.playing` on the poster, driving `.pg`'s 9-second linear progress-bar transition (line 126); the real backend equivalent is `GET /profiles/{id}/feed/{item}/voice` resolving with audio |
| playing → paused | Person taps pause | **Not modelled anywhere** — the blueprint's `.pl` button has no pause affordance or icon swap; a gap in the reference, not just the app |
| playing → complete | Progress finishes | 9s linear bar completes (blueprint); real media firing its `ended` event |
| complete → idle | Card scrolls back into view later, or replay is tapped | Local only |
| any → error | The voice asset is missing | Real, measured: `GET .../voice` 404s by design when no audio is prepared (`backend/app/channels/api/feed.py:223-234`, per audit §2) — the actual defect is that the server logged `TooLongToSay` **ten times** and every card silently fell back to the phone's own voice rather than surfacing an error state (audit §2, "Errors and blank frames") |

---

## 3. The §27 component list, mapped to the kit

| §27 component | Action | Kit today | File |
|---|---|---|---|
| `AppShell` | **rename/keep** — closest existing root composition | `Shell` | `web/src/screens/Shell.tsx` |
| `AmbientBackground` | **add** — no component wraps this today; it is static markup plus CSS | `<div class="atmosphere">` | `web/index.html:31`, CSS in `web/src/ui/base.css:77-145`, wash tokens in `web/src/ui/tokens.css:217-296` |
| `BottomNavigation` | **rename** — matches per `design-build-2.md` §2 ("Bottom navigation (§17) — Matches") | `TabBar` | `web/src/ui/kit/TabBar.tsx` |
| `AIOrb` | **rename + extend** — today only `idle`/`thinking` (via a `thinking` boolean prop); needs `listening`/`responding`/`error` | `Orb` | `web/src/ui/kit/Orb.tsx` |
| `AIComposer` | **rename + rebuild** — today a docked pill that navigates to a separate screen; needs the in-place expansion §9 asks for, which has no reference implementation anywhere (step 1) | `AskBar` | `web/src/ui/kit/AskBar.tsx` |
| `EditorialHeadline` | **merge** — `Hero` carries a greeting + one figure/state word (its own docstring: built for "How you feel today" and the caregiver "Steady" pattern), not a headline with one italicised accent word; `SoftText` is the closest existing word-reveal primitive to the blueprint's `stream()` | `Hero`, `SoftText` | `web/src/ui/kit/Hero.tsx`, `web/src/ui/kit/SoftText.tsx` |
| `InsightCard` | **merge** — no single component; spec §5 wants one `Card` with named variants and three tiers | `FeedCard`, `MemoCard`, `TintCard` | `web/src/ui/kit/FeedCard.tsx`, `web/src/ui/kit/MemoCard.tsx`, `web/src/ui/kit/Tint.tsx` |
| `ReminderCard` | **merge** — today a plain list row, not a card variant | `ListRow` | `web/src/ui/kit/Rows.tsx` |
| `MediaCard` | **merge** — three components stand in for one variant | `FeedCard`, `Poster`, `PlayerStrip` | `web/src/ui/kit/FeedCard.tsx`, `web/src/ui/kit/Poster.tsx`, `web/src/ui/kit/PlayerStrip.tsx` |
| `MetricCard` | **rename** | `MetricRow` | `web/src/ui/kit/Rows.tsx` |
| `TrendCard` | **add** — `Sparkline` exists but has no Week/Month toggle, no shaded personal-usual band, no count-up number (`design-build-2.md` §2 gap) | `Sparkline` | `web/src/ui/kit/Sparkline.tsx`, `web/src/ui/kit/sparkGeometry.ts` |
| `DocumentCard` | **merge** | `PaperTile`, `GlassTile` | `web/src/ui/kit/Tiles.tsx` |
| `ExpandableCard` | **add** — confirmed absent (`design-build-2.md` §2: "none") | — | — |
| `BottomSheet` | **merge** — two components for one concept; neither has a drag handle, interactive drag, or velocity-aware dismissal (`design-build-2.md` §2 gap) | `Sheet`, `ActionSheet` | `web/src/ui/kit/Sheet.tsx`, `web/src/ui/kit/ActionSheet.tsx` |
| `ContextualAction` | **merge** | `PillButton`, `ThreeStateButton`, `ArrowButton` | `web/src/ui/kit/PillButton.tsx`, `web/src/ui/kit/ThreeStateButton.tsx`, `web/src/ui/kit/Rows.tsx` |
| `LoadingState` | **merge** — four places do pieces of one job today (`design-build-2.md` §2: "No shared `LoadingState`/`EmptyState`/`ErrorState` primitives") | `PendingCard`, `Skeleton`, `StatusLine`, `ThinkingIndicator`/`StepTrace` | `web/src/ui/kit/Pending.tsx`, `web/src/ui/kit/Skeleton.tsx`, `web/src/ui/kit/StatusLine.tsx`, `web/src/ui/kit/Conversation.tsx` |
| `EmptyState` | **add** — none exists; per-screen copy today (e.g. the Insurance empty text found live, audit §2 row 11) | — | — |
| `ErrorState` | **add** — none exists; today six different hand-written rejection strings, one per stream wrapper (audit §7.1) | — | `web/src/api/nura.ts` (the six wrappers) |
| `MotionProvider` | **add** — no provider; three raw custom properties only, no spring family, no per-role tokens (`design-build-2.md` §2 gap; `motion.md` §title) | `--settle`, `--press`, `--wash-fade` | `web/src/ui/tokens.css` |

---

## Notes for the owner

- Every one of the 26 blueprint scenes appears at least once above (rows 1–9, 10–14, 15–18, 19–20, 21–24, 25,
  26–34, 35–42, 43–51, 52–56 cover welcome, signin, who, cloud, firstpaper, reading, report, insight, inbox,
  matching, policy, addmed, registry, connected, home, ask, health, analyst, meds, visits, insurance, feed,
  unwell, family, mei, profile in that order).
- Six rows are marked **not attested in the blueprint** (progressive-disclosure drill into a chart, #37; the
  in-place composer, #30; shared-element transitions generally, #10/#27/#25; the "Fix a number" edit flow, #13;
  media pause, in §2.3) — these are spec-derived design work, not extraction, and are flagged so the owner can
  confirm the intent rather than assume a reference exists.
- Three rows point at real, currently-shipping defects rather than design gaps: the WebKit freeze on Profile
  (#56), the silent Ask fallback to keyword search (#31), and the six incompatible rejection strings for one
  failure condition (§2.2, loading → error). None of these are design decisions to make; they are the audit's
  own findings, repeated here because they sit directly on interaction moments this map covers.
