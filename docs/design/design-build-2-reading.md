# Design build 2, step 1 — the reference, read as an experience

**Status: draft for owner confirmation.** This reads `docs/design/experience-blueprint.html`'s 26 scenes
(`SC` array, lines 193–251) as interactions, not screenshots, against the 26 captured frames at
`/private/tmp/claude-501/-Users-ashleyfernandez-SingleIDContext/e8f60261-760e-4178-a18b-74e3888c414c/scratchpad/shots/blueprint-ref/01.png`–`26.png`
and the specification in `docs/design/design-build-2.md` §1. Every timing and function name below is quoted
from the blueprint's own script (lines 158–263) or its `<style>` block (lines 9–141); nothing is invented.
This is step 1 of the twelve-step plan in `design-build-2.md` §4.

## How the blueprint actually moves (the primitives, cited once, used throughout)

| Primitive | Where | What it does | Timing |
|---|---|---|---|
| `stream(el,text,id,per=62)` | line 171 | Reveals text word by word; each word is a `<span class="w">`, animated by `win` (line 109–110: opacity 0→1, `blur(5px)`→0, `translateY(2px)`→0). A `*word*` becomes `.ser` (Instrument Serif italic) — the one emphasised word per headline (spec §4). | 62ms between words (headline default), 36ms for body paragraphs (`nura()`, line 173); ends with a 220ms hold; word entrance itself is 500ms ease (line 109 `win`). |
| `think(slot,lines,id,hold=1050)` | line 172 | Drives the orb's `.think` class and swaps one status line in place per array entry — never a stack. | Each line holds 1050ms by default, exits via `.out`/`sout` (220ms, line 105–107) before the next line writes in via `sin` (350ms, line 104–107). The line's own text shimmers continuously with `sweep` (1.5s linear, line 104–106). |
| `nura(c,id,{t,head,body,hold})` | line 173 | The one function every AI turn goes through: optional thinking lines (`t`) → removes the thinking slot → streams a headline (`head`) → streams body paragraphs (`body`). This is the composite that "AI understands → AI surfaces → AI explains" (spec §1) is built from. | Composed from `think`/`stream` above. |
| `reveal(nodes,id,gap=120)` | line 174 | The card/row stagger. Each node is `.rv` at rest (opacity 0, `blur(6px)`, `translateY(10px)`, line 112) and gets `.in` after `gap`ms, one at a time, then a final 300ms settle. | Default 120ms; measured per scene below — it ranges 80ms (a 7-row inbox) to 320ms (a two-card answer), i.e. denser lists stagger faster. |
| `tabset(...)` | line 189 | Segmented tabs (Covers/Not covered/…, Now/All/Changes); switching tabs re-triggers a stagger via `setTimeout(...,70+k*90)` (line 189) — not `reveal`, a second, parallel stagger mechanism for tab content. | 70ms + 90ms/row. |
| `.orb` / `.orb.lg` / `.orb.think` | lines 97–102 | The living orb: a conic-gradient spinning at 7s (base), a highlight blur. `.lg` (Welcome only) adds `breathe` (4.5s ease-in-out, scale to 1.05 at the midpoint). `.think` speeds the spin to 2.2s — the *only* CSS state change from idle. | 7s / 2.2s / 4.5s. |
| `.sheet` | lines 130–132 | Bottom sheet: `translateY(105%)`→`translateY(0)`, `cubic-bezier(.2,.8,.2,1)`. | 550ms. |
| `openSheet()` | line 182 | Streams its lines in via `stream`, reveals its action row via `.rv.in`, and its CTA is a three-state button (label → busy label with `.busy` opacity → done label with `.done` colour and a check icon) — the Copy/Copying/Copied, Adding/Added pattern used seven times across the 26 scenes. | Lines stream at the `stream` default (58ms/word here); the busy hold before "done" is a flat `sleep(900–1100ms)` in each call site, not a real async wait — the blueprint is a storyboard, so this is simulated, not measured, latency. |
| Reduced motion | line 140 | `@media (prefers-reduced-motion:reduce){.phone *,.phone *::before{animation:none!important;transition:none!important}}`, plus `RM` (line 161) makes every `sleep()` resolve instantly (line 164) so content still appears, just without the word-by-word and stagger pacing. | 0ms. |

**What the blueprint does not show.** There is no `:active`/press rule anywhere in its CSS (grepped the full
`<style>` block) — spec §7's "scale 1→0.985" tactile press is not modelled in the reference at all; it is a
spec requirement with no reference implementation to measure against. Likewise the orb has exactly two CSS
states (idle spin, `.think` faster spin) plus a size variant (`.lg`, breathing) — not the five states spec §8
names. The five-state orb is the *specification's* model; the blueprint demonstrates two of its five in motion
and asserts the concept of a "living" presence, not a full state machine.

---

## Scene by scene

| # | Scene | User does | AI does | What moves, and how (cited) | What stays | Emotional beat |
|---|---|---|---|---|---|---|
| 01 | Welcome | Nothing yet; watches, then taps **Start**. | Nothing — no account, no data (per the blueprint's own note, `s.does`). | Orb (`.lg`, breathing 4.5s) appears alone; `stream()` writes the headline at 90ms/word, then the subline at 50ms/word; the **Start** button reveals after both finish (`acts()` then `.in`). | The orb itself carries into every later scene as the AI's one recurring mark. | Arrival: the orb is the *first* thing on screen, before any UI chrome — "someone to talk to," not a product. |
| 02 | Sign in | Reads a question, sees the number field then the code field appear. | Asks one question at a time, not a form. | `stream($('#sl'),...,80)` writes the question; both fields are `.rv` and reveal together via `reveal([...],id,260)` — a slower 260ms gap than most lists, so each field is felt as its own beat, not a batch. | The glass field pattern (`.field.glass`) recurs at 03 (name), and later in `.field` for phone-number-style entry. | Calm procedure: no password anywhere; the pacing gives each field room. |
| 03 | Who is this for | Taps a chip (Me/My parent/Someone else), then reads Nura's reply. | Asks, listens (chip choice = the "answer"), replies with a second `nura()` turn including thinking (`t:['Setting up your papers']`) then a headline and one body line. | This is the first scene to show a full **conversation shape**: Nura bubble → chip row (`reveal([ch],id)`) → `me()` bubble (the person's own reply, right-aligned, `.me` class) → a second `nura()` turn. | The `me()`/`nura()` bubble alternation is the template for every later conversational scene (09, 10, 16, 23). | Being met: "Good to meet you, Tan" — the first personalised sentence in the product. |
| 04 | The cloud | Taps bubbles to select conditions (`.bub`→`.bub.on`, `scale(1.06)`, line 122, 350ms transition), or opens a sheet to say it in one sentence instead. | Counts what was tapped and writes it back as a sentence ("I have written 2 things down") — grammatical, not "2 items". | Bubbles `bob` continuously (6s ease-in-out alternate, translateY −7px) even at rest — the only *ambient*, non-event-triggered motion on a data-entry screen. The sheet path re-streams the person's own words back before writing them down. | The bubble-cloud metaphor is unique to this scene; nothing later reuses it. | Low friction: tapping is optional, speaking in your own words is offered as an equal path. |
| 05 | Add a paper | Picks one of three entry rows, or "I have no papers today". | Nothing yet — this is a pure choice screen. | Three rows reveal via `reveal([...c.children],id,160)`; skipping is a plain action with no penalty framing. | The icon-row-with-subline pattern recurs at 09 (paper kind icons) and throughout. | Permission to skip, stated once, not repeated. |
| 06 | Nura reads it | Shows one paper (a `me()` bubble with a doc icon). | Thinks through four real stages in place, then states the finding as a headline, then the rows. | `nura(scr,id,{t:['Keeping your paper safe','Looking at your paper','Found a blood test','Checking it closely'],head:...})` — one status line changing in place (not a stack), `sweep`-shimmered; then the headline streams with one italic word (*paper*); then a 3-chip summary (`reveal(...,170)`); then five rows (`reveal(...,260)`). | The four-stage think → headline → rows sequence is the template `report`, `insight`, `analyst` and `policy` all reuse with different stage lists. | Trust building in real time — the audit (§2, row 06) independently calls this "the best screen in the app" because the stages are the backend's own, not invented. |
| 07 | The report table | Reads the table, taps "Looks right" or "Fix a number", or checks the uncertain row. | Presents one table (`lab()`, line 177) instead of 25 stacked cards; flags exactly one row as uncertain. | Rows reveal at `reveal(...,110)` — the fastest list-stagger measured (five rows, each with a range bar `.bar`/`u`/`s`), because the table reads as one object, not five separate arrivals. Tapping "Check this one" opens `openSheet()` with the uncertain line's own text. | The table/row pattern (`lab()`) is scene 07's alone; 09's `item()` and 10's verdict rows are its plainer sibling for lists that are not lab values. | Confidence: one thing needs a yes, not twenty-five. |
| 08 | What it means for you | Reads Nura's questions for the doctor, taps "Keep these for my visit". | Connects the paper just confirmed to medicines and the next visit, unprompted — no user action requested this. | `nura()` with three thinking stages, then a `looked(scr,[...])` chip row (what was consulted, shown before the answer), then one glass card with three questions, `reveal(...,300)`. The keep button is a `ThreeState`-shaped inline handler (label → "Keeping…" busy → "Kept" done) before navigating home. | `looked()` (line 176) — the "Looked at" chip row — is reused verbatim at 09/16/18/23 wherever Nura cites sources. | The moment the spec calls out by name (§10, §11): the record volunteering a connection the person did not ask for. |
| 09 | Many papers at once | Sends a whole folder at once (one `me()` bubble). | Works through seven papers as a visible queue — one orb, one status counting through them, each row's own flag changing live. | `$('#ibs').textContent` is rewritten per paper ("Reading 2 of 7…"); each row's `.flag` text and class cycle through `Sorting → <kind> → Reading → Matching → <verdict>` on a 230ms `sleep` per step — the only scene where **each row animates independently while a shared status line also animates**, i.e. two motion channels at once. | The per-row state-cycling pattern is unique to this scene (a literal queue-of-jobs UI); nothing later shows concurrent per-item progress. | Being trusted with volume: seven papers, one summary at the end ("I read seven. Five are in. Two need you."). |
| 10 | What changed in your record | Reads six verdict rows, opens a sheet to settle a dose conflict. | States a plain verdict per item (New/Same/Newer/Conflict/Replaces/Yours?) — never silent, never a raw diff. | Rows reveal at `reveal(...,230)`; a trend card (inline `<svg class="spark">`, hand-drawn polyline, no `Sparkline` abstraction in the blueprint) appears after the rows; the sheet for the conflicting dose uses the same `openSheet()` three-state CTA as 08. | The six-verdict vocabulary (New/Same/Newer/Conflict/Replaces/Yours?) is this scene's own; §28's card states (collapsed/pressed/expanded…) do not name these — a gap the interaction map (step 2) should surface. | Nothing overwritten, stated explicitly in the sheet's `foot` line — safety made visible, not just true. |
| 11 | Policy passport | Watches page-by-page progress, then taps between four tabs. | Reads a 48-page document and shows **real** progress: "Reading page 4 of 48" … "page 48 of 48," each held 430ms (`hold:430` overrides the 1050ms default in `think()`). | The card with three numbers reveals once (`reveal([c],id)`, default gap); tab switches use `tabset()`'s own 70+90k ms stagger, not `reveal` — confirming two independent stagger mechanisms exist in the same file. | Tabs (`tabset`) recur at 13 (Now/All/Changes) and nowhere else — a two-use pattern, not yet a habit. | Long documents made honest: the page count *is* the loading state, not a spinner standing in for it. |
| 12 | Add a medicine | Shows a box photo or types/speaks a sentence; picks which statin from chips if the box only says "STATIN". | Reads what it can, marks each field Sure/Need-you, and **asks rather than guesses** when the box only names a drug family. | Rows reveal at 220ms/200ms depending on branch; the clarifying chip row (`choose()`, line 190) races an 6s auto-pick against the user's own tap — the only place in the blueprint where a choice has a timeout fallback (for the "Play the journey" auto-demo, not for a real user). | The Sure/Need-you row pattern (`row()`, inline in this scene) is a one-off, close cousin of `ReviewField` in the kit. | Refusing to guess: "which statin?" instead of silently keeping "STATIN". |
| 13 | Medicine registry | Switches between Now/All/Changes tabs; taps "Show my pharmacist". | Merges every source (papers, receipts, spoken additions) into one list per medicine, and flags the same medicine under two names as a question. | `tabset()` stagger again; the "Show my pharmacist" sheet reuses `openSheet()` with a `Done` two-state (no middle "ing" state this time — the content is already assembled, so there's nothing to wait for). | The med-card shape (plain name, real name, dose, prescriber, source chips) is this scene's; `registry`'s cards do not reuse `report`'s `lab()` rows — different object, different template, correctly. | Being prepared for someone else to judge: "Nura lists. Your pharmacist judges." |
| 14 | Everything connected | Reads one number's full context, taps any related row to navigate to it. | Shows every door out of one fact: source, related medicine, kept-for visit, policy line, analyst mention, and a contextual clip — all from one screen. | `reveal([c,...r.children],id,170)` for the five related-rows, then the media card reveals separately after. Every row is `data-go`-wired via `wire()` (line 187) — same navigation mechanism as the tab bar and back button. | This is the **shared-element philosophy stated in data**, not motion: the blueprint does not actually morph the card from `connected`'s trigger into this screen (no shared-element transition exists in its own code — see cross-cutting notes). | "One record, many doors" — the antidote to a dashboard: nothing is orphaned. |
| 15 | Home | Reads the headline, taps into the insight card, a reminder line, or a feed line. | Composes one sentence as the day's headline from the top feed item (blueprint comment, `s.does`). | `stream($('#hb'),'Four numbers to raise with your *doctor.*',id,85)`; three elements (`insight card`, `reminder line`, `feed line`) reveal together at `reveal([c,m,f],id,220)` — three things, not more, matching spec §4's "one card each" rule. | The composite header (`.hd` avatar + greeting + "Not well?") and the docked `dock({ask:true,tabs:'home'})` recur on every tabbed screen from here on. | The day distilled to one sentence before anything else loads. |
| 16 | Ask Nura | Types/asks two questions in sequence, the second one a follow-up. | Answers with sources first (`looked()`), then structure, remembers the first question when answering the second. | Two full `nura()` turns in one scene, each preceded by its own `looked()` chip row; the second turn's cards reveal at `reveal(...,320)` — the slowest stagger measured, because there are only two cards and they are dense (a cost estimate, a pre-procedure card). | The `me()`/`nura()`/`looked()` triad, now doing real multi-turn work — same primitives as scene 03, now carrying an actual conversation. | Being remembered: the second answer explicitly builds on the first, stated by the UI chip "Remembers this chat". |
| 17 | Health | Reads a summary card, a trend chart, three paper rows. | Nothing active in this scene — it is a static composed view (no `nura()` call), unusual among the 26. | `reveal([a,b,...c.children],id,200)` — the trend card's `<svg class="spark">` polyline is drawn once, fully formed (no animated path-length reveal in the blueprint's own code, despite spec §18's "charts draw themselves"). | The trend-card shape recurs at 10 and 14 (same inline SVG sparkline, not componentised in the blueprint). | Insight before raw data — the analyst card is first, the chart second, the paper list third. |
| 18 | Health Analyst | Reads through four sections in order; taps "Turn these into visit questions". | Narrates its own process (`t:[4 stages]`), then a `looked()` chip row, then reveals **one section card at a time**, in a loop: `for(const s of S){const c=add(...);await reveal([c],id,260);}` — each section pauses 260ms before it arrives, individually, not as a batch. | This per-card sequential loop (as opposed to `reveal`'s usual all-at-once staggered array) recurs only at 22 (For you) — both are "read down a list Nura assembled" scenes. | A report that omits empty sections rather than showing them blank (`s.see`: "a section with nothing to say is left out"). |
| 19 | Medicines | Taps "I took it" per dose; taps to photograph an unidentified tablet. | Turns the tap itself into the record (button becomes the receipt: `.btn.light`→`.btn.done` with a check icon, no separate confirmation step). | Rows reveal at 200ms; the "taken" state change is instantaneous on tap (no `nura()` call, no thinking) — correctly, since recording a tap needs no AI reasoning. | The `.dose` row shape is this scene's own, distinct from `.row`/`.card`. | Immediate, low-ceremony compliance: one tap, done, no modal. |
| 20 | Visits and costs | Reads the next-visit card, taps "What might it cost?" or "Draft the message". | Estimates a cost from the person's own past receipts (cites them), drafts a message it will never send itself. | Two sheets, both via `openSheet()`, both three-state buttons; `reveal([a,b,...c.children],id,220)` for the base screen. | The "Nura never sends anything" line appears here and again at 16 and 20's sibling scenes — a repeated safety statement, not a one-off. | Proposes, never books, never sends — stated in the sheet's own `foot` text. |
| 21 | Insurance | Reads the policy card and a claims ledger; taps to add a receipt. | Nothing active — static composed view, like 17. | `reveal([a,...r.children],id,220)`. | The ledger row shape (`item()`) is the same generic row used in nine other scenes — the one true "list row" primitive in the blueprint's own code. | Money as a short list with chips, not a spreadsheet. |
| 22 | For you | Taps Play on a clip; captions stream under it. | Chooses two clips and a "Did you know" card *because of* something specific to this person, states why before what. | Cards reveal one at a time in a loop (`for(const f of F){...await reveal([c],id,260);}`, mirroring scene 18); on Play, `stream(c.querySelector('.cap'),...,210)` writes the spoken caption word-by-word under the poster, at 210ms/word — the slowest word-pace measured, matching spoken cadence rather than reading cadence. | The poster/play-button/progress-bar shape (`.poster`, `.pl`, `.pg`) is scene 22's own; nothing else in the blueprint plays media. | Why before what, literally in reading order: the reason line sits under the headline, before the source line. |
| 23 | Not feeling well | Taps a symptom chip (e.g. "Chest pain"). | Breaks the calm deliberately: no thinking animation, no streaming, no delay. | `phone.classList.add('alarm')` swaps the entire background gradient (`.phone.alarm .atmos`, line 55: red-toned `linear-gradient`) in the same frame as the card appears (`reveal([a],me2,60)` — 60ms, the fastest reveal gap in the file, i.e. almost immediate). | Nothing from the calm vocabulary is reused here on purpose — no `nura()`, no `think()`, no `looked()`. | The one place the product is allowed to feel urgent — measured by what is *withheld* (no shimmer, no stagger) as much as by the red. |
| 24 | Connect | Reads three people's access rows, taps "Let someone in" or "See it as Mei". | Nothing active in this scene — static, like 17/21. | `reveal([...r.children],id,220)`, then a message card and two actions reveal together. | The role-badge row shape is this scene's own. | People, not settings — stated as the scene's own `s.see`. |
| 25 | Mei's Home | Reads the same Home, spoken about Pa. | Recomposes every sentence with a caregiver voice — same structure as scene 15, different pronouns throughout. | `stream($('#mb'),'His pressure has been up for five *mornings.*',id,85)` — identical call shape to scene 15's headline, proving the caregiver view is a **data substitution**, not a different template. | Every element from Home (header, insight card, two rows) reappears unchanged in structure. | Care made visible without making Pa the subject of a sentence spoken to a stranger. |
| 26 | Profile | Reads six rows, most already answered in one line ("On", "English · Bahasa Melayu · 中文"). | Nothing active — the most static scene in the blueprint. | `reveal([...r.children],id,150)`, then one reassurance note. | The plain list-row shape, no cards. | Settings reduced to sentences: "most of what used to be settings is now a sentence you say to Nura" (`s.does`). |

---

## The cross-cutting reading

**Motion language — what enters, from where, how fast.** Everything that is not the orb enters the same way:
opacity 0 → 1, a slight upward translate (`translateY(10px)`→0 for structure via `.rv`, `translateY(2px)`→0 for
individual words via `.w`), with a blur that resolves alongside the fade (`blur(6px)`/`blur(5px)`→0) — never a
slide from the side, never a scale-in, never a bounce. The two exceptions are the sheet (`translateY(105%)`→0,
a vertical arrival from off-screen, because it is a distinct surface, not a card) and the alarm scene's colour
swap (no positional motion at all). Durations cluster in two bands: **fast** (220ms word entrance, 350ms
status-line entrance, 550ms structure entrance) for anything that is *arriving*, and **slower, stage-paced**
holds (900–1150ms per thinking stage, 1050ms default) for anything the AI is *doing*. Nothing in the blueprint
measures faster than the sheet's 550ms open or slower than the 48-page policy read's per-page 430ms hold — nothing
is instantaneous except the "not well" alarm (60ms), which is the one scene deliberately built to skip the
whole vocabulary above.

**Hierarchy rules, measured.** One `.big` headline per screen (33px per the CSS variable scale referenced in
`design-build-2.md` §2's own measurement of the app, though the blueprint's own `.big` rule at line 66 sets
`font-size:33px;font-weight:300`), at most one italic emphasised word per headline (`.ser`, always inside the
`*asterisks*` markup `stream()` parses at line 171), body text is always `.body`/`p` at plain weight. Every
scene puts the AI's own words above the data it is presenting — `head` always streams before the rows that
support it — matching spec §3's order (what matters → why → what to do).

**The composer's behaviour.** The docked bar (`dock({ask:...})`, line 185) never changes shape in the
blueprint: tapping it calls `go('ask')`, which is a full scene change (`show()`, line 258), not an in-place
expansion. This is a direct contradiction of spec §9 ("the compact pill expands in place… do not open a
separate full-screen chatbot") — **the blueprint itself, not just the built app, treats Ask as a navigation**.
This matters for step 2: the spec's in-place-composer requirement has no reference implementation to copy: it
must be designed fresh, not reverse-engineered.

**How disclosure unfolds.** Three shapes recur, and they are distinct:
1. **The `nura()` triad** (think → headline → body/rows) — used for anything the AI is actively reasoning
   about (06, 08, 09, 10, 16, 18, 23-adjacent scenes that call it). This *is* progressive disclosure per spec
   §11, playing out over the single conversation thread.
2. **The static composed view** (17, 21, 24, 26) — no `nura()` call, content simply reveals via `reveal()`.
   These are "the record, looked at," not "the AI, explaining" — a real second mode the spec does not name
   separately but the blueprint consistently distinguishes by *whether `nura()` is invoked at all*.
3. **The sequential list-reveal loop** (18, 22) — `reveal([single-item],id,gap)` called repeatedly inside a
   `for` loop, rather than `reveal([...items],id,gap)` called once on the whole array. The visible difference is
   that in 18/22 each section/card gets its *own* full 260ms pre-wait rather than a shared stagger — items feel
   authored one at a time, not spawned from a list.

**Where the same object expands vs where a new surface appears.** Measured against the blueprint's own `go()`
navigation (line 259) and `openSheet()` (line 182): **every** detail in the blueprint is either a full scene
change (`go`, wired via `data-go` and `wire()`) or a bottom sheet (`openSheet`). There is **no shared-element
transition anywhere in the blueprint's own code** — no CSS `view-transition`, no FLIP animation, no card that
morphs into its own detail. Spec §12's "a Home card transforms into the detail: position, shape, typography and
identity kept" is asserted in scene 14's *content* (a card whose every row leads somewhere) but never demonstrated
in its *motion*. This is the single most consequential gap between what the specification asks for and what the
26-scene reference actually shows: **the shared-element transition is a spec requirement invented from the
product's intent, not something to copy from the blueprint's own animation code**, because the blueprint has
none. Sheets, by contrast, are real and consistent: every "propose an action, confirm, done" moment (08's keep,
10's dose conflict, 12's added medicine, 13's pharmacist summary, 20's draft/cost) uses `openSheet()`.

**How the orb is used.** Three distinct roles, not one: (a) the large, breathing hero on Welcome only (`.orb.lg`,
the one scene where the orb *is* the screen); (b) the small inline marker beside every `nura()` turn's text
(`orb()` at default size, spinning at 7s, or 2.2s while `.think` is active) — an avatar, not a status indicator
most of the time; (c) implicitly absent during static composed views (17/21/24/26) and during the alarm scene
(23), where no orb call is made at all. The orb never appears in a "listening" or "responding" CSS state in the
blueprint — those are spec §8 concepts with no reference frame to point to.

---

## Ten conclusions for the owner to confirm or correct

1. **The composer must be designed, not copied.** The blueprint's own "Ask" bar navigates to a new scene
   (`go('ask')`) every time; the in-place expansion spec §9 demands has zero reference frames. Confirm this is
   understood as new design work, not extraction.
2. **Shared-element transitions do not exist in the blueprint's code.** Spec §12 is an intent statement, not a
   captured pattern — the reference never morphs a card into its detail. Building it is invention constrained by
   the spec's words, not reverse-engineering.
3. **The orb has two real states in the reference (idle spin, `.think` faster spin) plus one size variant (`.lg`,
   breathing).** Spec §8's five states (idle/listening/thinking/responding/error) are three states beyond what
   the blueprint ever shows. Confirm the three missing states should be designed from the spec's prose alone.
4. **There is no press/tap feedback anywhere in the blueprint's CSS.** Spec §7's tactile press is unattested in
   the reference; it must come from the spec and from `motion.md`'s existing `--press` token, not from the
   blueprint.
5. **Two disclosure modes are conflated in the spec but distinct in the blueprint:** a "static composed view"
   (Health, Insurance, Connect, Profile — no AI turn at all) versus an "AI turn" (`nura()` — thinking, then
   headline, then structure). The interaction map (step 2) should carry this distinction explicitly, because it
   changes which AI state applies — a static view has no AI state at all, and forcing one onto it would
   misrepresent the reference.
6. **Two independent stagger mechanisms exist in the blueprint** — `reveal()`'s array stagger and `tabset()`'s
   own `70+90k` ms `setTimeout` loop. A single `MotionProvider`/stagger token (spec §24) needs to absorb both,
   or the tab-switch case will keep its own hand-rolled timing.
7. **List density predicts stagger speed, empirically:** a 5-row lab table staggers at 110ms/row, a 7-row inbox
   at 80ms/row, a 2-card answer at 300–320ms/card. If the built system is to have *one* card-enter token (spec
   §24), it should still vary by list length the way the reference does, or dense screens will feel slower than
   the reference, not just different.
8. **The word-stream pace is not one number.** Headlines stream at 62–90ms/word depending on scene; body text at
   36–58ms/word; a spoken video caption at 210ms/word. Confirm whether the built system should carry these as
   one `motion.fast/standard/slow` token or keep per-content-type pacing — the reference clearly varies it by
   what kind of text is arriving.
9. **The "not well" scene is defined by what is withheld, not what is added.** No thinking, no streaming, no
   stagger beyond a 60ms reveal — it is the *fastest*, not the loudest, scene in the file. Any error/alarm
   pattern the built system adds should be checked against "does this skip the vocabulary" as much as "is this
   red."
10. **The caregiver view (scene 25) is proven to be a data substitution, not a second template** — its one
    `stream()` call is structurally identical to Home's. This should set the bar for every other caregiver twin:
    same function calls, same timings, different words — not a parallel component tree.
