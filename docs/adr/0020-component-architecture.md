# ADR 0020 — Component architecture: the §27 list, mapped to what actually exists

**Status:** accepted, 23 September 2026. Companions: `docs/design/design-build-2.md` §27 (the
component list this ADR maps), `docs/design/design-build-2-map.md` §3 (the same mapping exercise
already done once against the **web** kit, reused here rather than redone), `docs/design/
mobile-architecture.md` (the native file tree), ADR 0019 (the `Nura*`-prefixed primitive list in
point 8, which this ADR either confirms or supersedes per component, decided below), `docs/design/
DESIGN_SYSTEM.md` and `MOTION_SYSTEM.md` (the third document `mobile-architecture.md` requires before
production UI, together with this one, are read as a set). Acceptance items are cited from `git show
origin/e2e-acceptance:docs/design/end-to-end-acceptance.md` by their **A-number**.

**Sources, read in full.** `design-build-2.md` §27 ("`AppShell`, `AmbientBackground`,
`BottomNavigation`, `AIOrb`, `AIComposer`, `EditorialHeadline`, `InsightCard`, `ReminderCard`,
`MediaCard`, `MetricCard`, `TrendCard`, `DocumentCard`, `ExpandableCard`, `BottomSheet`,
`ContextualAction`, `LoadingState`, `EmptyState`, `ErrorState`, `MotionProvider`"). The `home-spike`
branch: every file under `apps/mobile/components/`, `apps/mobile/app/(tabs)/`,
`apps/mobile/features/home/mock.ts`. `web/src/ui/kit/*` and `design-build-2-map.md` §3 (already maps
every §27 name onto the web kit — not repeated here except where the native mapping disagrees with
it). `mobile-architecture.md` §2's ASCII file tree (the planned, not-yet-built, directory structure).

**A scope note.** Of the six screens the task names (Home, Health, Ask, Medicines, Visits, Insurance),
only **Home** is built (`apps/mobile/app/(tabs)/home.tsx`). Health, Connect, Services and Profile are
`PlaceholderScreen` stubs (`mobile-architecture.md` §5: "Home only" for the spike). There is no
`medicines.tsx`, `visits.tsx`, `insurance.tsx` or `ask.tsx` route anywhere in `home-spike` — Ask exists
only as `AIComposer`'s in-place expansion on Home; Medicines, Visits and Insurance exist only as
*planned* feature folders in `mobile-architecture.md`'s own ASCII tree, never as files. §3 below
composes each of the six from primitives as the sources specify, and says plainly, screen by screen,
which composition is built today and which is still a plan.

---

## Decision

### 1. The §27 list, mapped

Columns: **Spec name** (§27, verbatim) → **Built as** (spike file, or "—" if unbuilt) → **Variants /
props** → **States** → **Tokens consumed** (see `DESIGN_SYSTEM.md`/`MOTION_SYSTEM.md` for values) →
**Driving event(s)** → **Caregiver-twin rule** → **Acceptance (A-#)** → **Decision**.

#### `AppShell`

| | |
|---|---|
| Built as | `apps/mobile/app/(tabs)/_layout.tsx` (the `Tabs` root + its own inline `BottomNavigation`) |
| Variants/props | none — one shell, five fixed tabs (`TAB_ITEMS`) |
| States | active tab only (`pathname` match) |
| Tokens | none named — colours/sizes hard-coded in `_layout.tsx`'s `StyleSheet` (`#1c1728` bar fill, `rgba(255,246,240,0.55)`/`#fbf6f0` label states) — **not sourced from `motionTokens.ts` or any colour token file**, a gap against "nothing hard-coded" |
| Driving event | route change (`usePathname`) |
| Caregiver twin | none — chrome only, no patient-facing prose |
| Acceptance | A-073 (thin navigation) |
| **Decision** | **rename to `AppShell`** — today it is an anonymous default export inside `_layout.tsx` with an inline, unnamed `BottomNavigation` function; extracting both into named components (`AppShell`, `BottomNavigation`, next) is a structural move, not new design work |

#### `AmbientBackground`

| | |
|---|---|
| Built as | `apps/mobile/components/ambient/AmbientBackground.tsx` (+ `AmbientBackgroundCanvas.tsx`, the Skia implementation split out per the file's own platform-loading comment, `DESIGN_SYSTEM.md` §1.2) |
| Variants/props | `width`, `height`, `scrollY?` (a Reanimated `SharedValue`) |
| States | none of its own — brightness derives from `AIStateName` (idle/listening/thinking/responding/error) |
| Tokens | `phoneTokens` (atmosphere gradient + two of three blob layers, `motionTokens.ts`), `motion.standard` (brightness cross-fade) |
| Driving event | `useAIStateName()` (the same store every other AI-driven primitive reads) + the host screen's own scroll handler |
| Caregiver twin | none — decorative, no prose |
| Acceptance | none named directly; underlies A-162's "background" column indirectly (not itself acceptance-tested) |
| **Decision** | **keep** — name matches §27 exactly; layer-c gap (`DESIGN_SYSTEM.md` §1.2) is a bug to fix in the existing component, not a naming or architecture question |

#### `BottomNavigation`

| | |
|---|---|
| Built as | inline function inside `_layout.tsx` (see `AppShell`, above) — not its own file |
| Variants/props | none — `TAB_ITEMS` is a fixed 5-tuple |
| States | per-tab `active`/inactive (opacity + weight, `DESIGN_SYSTEM.md` §11) |
| Tokens | none — hard-coded, see `AppShell` |
| Driving event | route change |
| Caregiver twin | tab labels (Home/Health/Connect/Services/Profile) are structural, not persona-voiced — no twin needed |
| Acceptance | A-073 |
| **Decision** | **extract into its own file**, `components/nav/BottomNavigation.tsx`, and read its colours from the token set — both a naming and a token-sourcing fix, same underlying gap as `AppShell` |

#### `AIOrb`

| | |
|---|---|
| Built as | `apps/mobile/components/ambient/IntelligenceOrb.tsx` (+ `IntelligenceOrbCanvas.tsx`) |
| Variants/props | `size?: 'sm'\|'md'\|'lg'` (`OrbSize`), `stateOverride?: AIStateName` (for showcase/test use, normally omitted) |
| States | idle / listening / thinking / responding / error (`AIStateName`) — five, matching spec §8 exactly |
| Tokens | `orb.idle/listening/thinking/responding` (spin duration), `breathe`, the six-stop conic gradient, per-state glow opacity — full table in `DESIGN_SYSTEM.md` §10 |
| Driving event | `useAIState((s) => s.state)` only — never a local timer (`IntelligenceOrbCanvas.tsx`'s own comment; `MOTION_SYSTEM.md` §3) |
| Caregiver twin | none — no text, an `accessibilityLabel` of `"Nura, {state}"` is the only string, and it names the product, not the person, so it does not change between Pa's and Mei's views |
| Acceptance | A-010 (orb-first Welcome), A-162 (driven by events, never a timer) |
| **Decision** | **rename `AIOrb` → `IntelligenceOrb`** (keep the spike's name) — ADR 0019 point 8 separately proposed `NuraOrb`; neither the spec's `AIOrb` nor the ADR's `NuraOrb` is what exists. `IntelligenceOrb` is accepted as canonical because it is the name already built, tested (five states) and imported by `AIComposer` — renaming working, imported code to match a name that was never built costs more than documenting the name that was |

#### `AIComposer`

| | |
|---|---|
| Built as | `apps/mobile/components/ai/AIComposer.tsx` |
| Variants/props | `answer: AskFixtureAnswer`, `onOpenReadings`, `onOpenAsk`, `testID?` |
| States | collapsed (pill) ⇄ expanded (composer); internally tracks its own `messages`, `chips`, `chipsDisabled`, `explainOpen`, `draft` |
| Tokens | `cardEnter`, `fadeExit` (expand/collapse), `IntelligenceOrb size="sm"` inside the expanded header |
| Driving event | the full `NuraEvent` stream via `runAskFixture`/`runExplainFixture` (`lib/ai/events.ts`) — `consumeEvent` feeds the shared `AIState` store, `onEvent` additionally builds the composer's own message list |
| Caregiver twin | **yes** — every streamed answer/question here is patient-facing prose; a caregiver session (Mei's) needs the same component with "Pa's," never "your" (A-137) — the component itself is persona-agnostic (it renders whatever `answer` it is given), so the twin is a **content** responsibility of the caller, not a second component |
| Acceptance | A-074 (expands in place), A-075 (context-first), A-163 (full state walk) |
| **Decision** | **rename `AIComposer` → keep `AIComposer`** — spec name and built name already match; ADR 0019's `NuraComposer` is superseded, same reasoning as `IntelligenceOrb` |

#### `EditorialHeadline`

| | |
|---|---|
| Built as | `apps/mobile/components/text/EditorialHeadline.tsx` |
| Variants/props | `text: string` (one `*accent*` word marked with asterisks), `size?: number` (default 33) |
| States | none — pure presentation |
| Tokens | `word.enter` for the streamed variant (the component itself does not stream — `AIComposer`/`home.tsx` would drive streaming via `stream()`-equivalent logic, not built yet on native, see below) |
| Driving event | none directly — the *value* of `text` is composed by the caller from the day's top-ranked feed item (A-069) |
| Caregiver twin | **yes** — Mei's Home renders the identical component with caregiver-voiced text (map row 55: "structurally identical to #26; listed separately only because the words differ") |
| Acceptance | A-069 (headline with accent), A-055 (Mei's Home, same call) |
| **Decision** | **keep** — matches spec name exactly. **Gap, not a naming question:** the component renders `text` statically; v2's own `home` scene streams the headline word-by-word at `stream.head` (85ms/word). Nothing in `EditorialHeadline.tsx` performs that stream — `home.tsx` passes the full string directly. This is missing behaviour, not a missing name. |

#### `InsightCard`

| | |
|---|---|
| Built as | `apps/mobile/components/cards/InsightCard.tsx` (wraps `NuraCard` variant `insight`, tier `primary`) |
| Variants/props | `title`, `segments?: [string, string]`, `date: {day, month}`, `body`, `ctaLabel`, `onPressCta`, `enterIndex?`, `staggerMs?` |
| States | one internal `segment` index (which of the two segments — e.g. "Today"/"This week" — is active) |
| Tokens | inherits `NuraCard`'s `card.enter`/press tokens; own layout constants (18px title, 14.5px body, etc. — `DESIGN_SYSTEM.md` §2) |
| Driving event | none — a segment tap is local UI state, not a stream event |
| Caregiver twin | **yes** — the insight's `body` text is patient-facing prose (A-070) |
| Acceptance | A-070 (primary insight card), A-072 (its CTA opens the detail via shared-element, not built yet — see `ExpandableCard`) |
| **Decision** | **keep** — matches §27 exactly. `design-build-2-map.md` §3 (web) merges three web components (`FeedCard`, `MemoCard`, `TintCard`) into this one spec name; the **native** side never had three to merge — `InsightCard` was built once, correctly, from the start |

#### `ReminderCard`

| | |
|---|---|
| Built as | `apps/mobile/components/cards/ReminderCard.tsx` |
| Variants/props | `label`, `done?`, `onToggle?`, `enterIndex?`, `staggerMs?` |
| States | `done`/not-done — the tap **is** the record (`design-build-2-map.md` row 41: "no AI turn at all… correctly, recording a tap needs no reasoning") |
| Tokens | `cardEnter`, `pressIn`/`scalePress`, `springs.bouncy` |
| Driving event | local tap only — no stream event, by design |
| Caregiver twin | **yes** — `label` is patient-facing ("Evening blood pressure tablet due" style text); a caregiver view would read "Pa's evening tablet," same component |
| Acceptance | A-092 (Today rows / Taken) |
| **Decision** | **keep** — matches §27. Note for §3 below: it is *not* built on `NuraCard` the way `InsightCard`/`MediaCard` are — it renders its own `.line`-shaped Pressable directly, sharing only the entrance/press motion values, not the `NuraCard` component itself. Worth confirming with the owner whether that is deliberate (the `.line` shape in v2 is visually distinct from `.card`, so it may be correct) or an oversight before more screens copy the pattern either way |

#### `MediaCard`

| | |
|---|---|
| Built as | `apps/mobile/components/cards/MediaCard.tsx` (wraps `NuraCard` variant `media`, tier `secondary`) |
| Variants/props | `title`, `why`, `publisher`, `duration`, `enterIndex?`, `staggerMs?`, `onStateChange?` |
| States | `MediaState`: idle → loading → playing ⇄ paused → complete (`MOTION_SYSTEM.md` §2.3) |
| Tokens | `mediaRun`, `pressOut` (loading delay) |
| Driving event | tap only — no real asset wired (fixture-level; a real `voice` route response would drive `loading → playing` in production, per `design-build-2-map.md` §2.3) |
| Caregiver twin | **yes** — `why`/`title` are patient-facing ("Because you take amlodipine") |
| Acceptance | A-118–130 (feed, not yet exercised against real media) |
| **Decision** | **keep name**, but **confirm against ADR 0019 point 8**, which composes Home as "Headline + InsightCard + ReminderCard + **FeedCard** + Composer" — the spike built `MediaCard`, not `FeedCard`. Since §27 itself names `MediaCard` (not `FeedCard`), and the spike matches §27, this ADR resolves the conflict in §27's favour: **`FeedCard` in ADR 0019 point 8 is retired as a name; `MediaCard` is canonical** |

#### `MetricCard`

| | |
|---|---|
| Built as | not a distinct component — `NuraCard` variant `metric`, tier `primary`, is used directly by `ExpandableCard` as its own surface (`ExpandableCard.tsx` line 111: `<NuraCard variant="metric" tier="primary" ...>`) |
| Variants/props | (none of its own — see `NuraCard`) |
| States | (none of its own) |
| Tokens | `NuraCard`'s own |
| Driving event | n/a |
| Caregiver twin | n/a (no standalone prose) |
| Acceptance | folded into A-159 (the expandable trend card) |
| **Decision** | **merge `MetricCard` into `NuraCard variant="metric"`** — no evidence anywhere in the spike of a static (non-expanding) metric card existing separately from the expandable one; if a future screen needs a metric card that does **not** expand, it should still be `<NuraCard variant="metric">` directly, not a new component |

#### `TrendCard`

| | |
|---|---|
| Built as | not a standalone component — the trend-drawing behaviour lives **inside** `ExpandableCard.tsx` (`BPChart`/`BPChartCanvas`) as step 1 of its five-step reveal, not as an independently reusable card |
| Variants/props | (`BPChart`'s own: `points`, `width`, `height`, `progress` — a chart primitive, not a card) |
| States | tied to `ExpandableCard`'s own step state |
| Tokens | `chartDraw` |
| Driving event | `ExpandableCard`'s `advance()` |
| Caregiver twin | the chart itself carries no prose; the surrounding note ("Your own usual band…") does, and is patient-facing |
| Acceptance | A-159 |
| **Decision** | **add `TrendCard` as its own component**, wrapping `BPChart` the way `MediaCard` wraps its poster — today `BPChart` can only be reached through `ExpandableCard`'s step 1, so **Health's own trend card (spec §15–16) cannot be built without first extracting one**, since Health needs a chart that may not always be inside a six-tap expansion sequence. This is the one genuine "add" in this table that blocks a named Tier-2 screen, not just a naming tidy-up |

#### `DocumentCard`

| | |
|---|---|
| Built as | not a distinct component — `home.tsx` renders the blood-test document row as a bare `<NuraCard variant="document" tier="secondary">` with inline `Text` children, not through a named `DocumentCard` |
| Variants/props | (none of its own) |
| States | (none of its own) |
| Tokens | `NuraCard`'s own |
| Driving event | tap → opens the lab-results sheet |
| Caregiver twin | **yes** — the paper's own title/subtitle are patient-facing |
| Acceptance | A-060/A-061 (reopen a confirmed paper, see the original) |
| **Decision** | **add `DocumentCard`** wrapping `NuraCard variant="document"` with named props (`title`, `subtitle`, `ctaLabel`, `onPress`) the way `InsightCard`/`MediaCard` already do — `home.tsx`'s inline version is the one card on Home built as raw JSX rather than a named component, and it is the most likely place a second, slightly-different copy gets pasted into Health or Insurance next, which is exactly the duplication §27's own line ("Composable primitives, no duplicates") exists to prevent |

#### `ExpandableCard`

| | |
|---|---|
| Built as | `apps/mobile/components/cards/ExpandableCard.tsx` |
| Variants/props | `bpExplain`, `possessive: 'your' \| "Pa's" \| string`, `onKeepForVisit?`, `onStateChange?` |
| States | `ExpandableCardState`: collapsed → pressed → expanding → expanded → interactive → dismissed (exactly `mobile-architecture.md` §3's six) |
| Tokens | `alarmReveal` (reused as a pre-roll delay, `MOTION_SYSTEM.md` §1.8), `chartDraw`, `motionStandard`, `pressIn`, `scalePress`, `statusOut` |
| Driving event | tap only (`advance()`); no stream event — the content at each step is static/mock, not yet backed by a real per-tap fetch |
| Caregiver twin | **built in** — the `possessive` prop (`'your' \| "Pa's"`) is the one component in this whole table that takes its persona twin as a **typed prop** rather than leaving it to the caller's copy alone; every other card leaves the twin entirely to what string the caller passes |
| Acceptance | A-159, A-164, A-072 (its Home instance is the model case for shared-element, not yet using the View Transitions path) |
| **Decision** | **keep** — matches §27. The current build is Home-specific (blood pressure only, hard-coded `BP_DAYS`/`BP_POINTS`); generalising it to any metric (the way `NuraCard` generalises across variants) is future work for whichever PR builds Health, not a rename |

#### `BottomSheet`

| | |
|---|---|
| Built as | `apps/mobile/components/sheets/BottomSheet.tsx` |
| Variants/props | `visible`, `onDismiss`, `title?`, `children` |
| States | visible/hidden, plus drag-in-progress (implicit in the `Gesture.Pan()` handler, not exposed as a prop) |
| Tokens | `motionFast` (backdrop fade, snap-back), `springs.standard` (open/settle) |
| Driving event | `onDismiss` (tap backdrop, drag past threshold/velocity) — content inside is whatever the caller streams in, e.g. lab rows on Home today |
| Caregiver twin | n/a itself (chrome); its `title`/`children` carry whatever twin the caller supplies |
| Acceptance | A-166 |
| **Decision** | **rename `BottomSheet` → keep `BottomSheet`** — spec name and built name match (`ADR 0019`'s `NuraSheet` is superseded, same reasoning as `IntelligenceOrb`/`AIComposer`) |

#### `ContextualAction`

| | |
|---|---|
| Built as | not a component — every "action" in the spike today is either a bare `Pressable` (the CTA inside `InsightCard`, the action button inside `ExpandableCard`'s step 5, the composer's chips) or a `ReminderCard` toggle |
| Variants/props | n/a |
| States | n/a |
| Tokens | `pressIn`/`scalePress`/`springs.bouncy` (repeated inline in at least four places: `NuraCard`, `ExpandableCard`, `ReminderCard`, and the composer's chip `Pressable`) |
| Driving event | tap |
| Caregiver twin | whatever label text the caller passes |
| Acceptance | A-168 (press feedback everywhere) |
| **Decision** | **add `ContextualAction`** — the press-scale-haptic pattern is hand-written four separate times today with the same three token imports each time; `design-build-2-map.md` §3 already flagged this exact gap on the **web** side (`PillButton`/`ThreeStateButton`/`Rows` "merge" into `ContextualAction`) — the native side has the identical duplication, unflagged until now. This is the clearest "no duplicate components" violation in the current spike |

#### `LoadingState` / `EmptyState` / `ErrorState`

| | |
|---|---|
| Built as | **none of the three exist in the spike** — no file under `components/states/` implements any of them; `PlaceholderScreen.tsx` is a *build-stub* ("this spike is Home only"), not the spec's `EmptyState` |
| Variants/props | (specified in `DESIGN_SYSTEM.md` §14, from v2's own `loadingState()`/`emptyState()`/`errorState()`) |
| States | n/a |
| Tokens | `sweep` (shimmer), `statusIn`/`statusOut` (loading line swap) |
| Driving event | `LoadingState` — a real fetch/stream in flight; `ErrorState` — `RUN_ERROR` or a rejected request; `EmptyState` — a real "nothing here yet" response |
| Caregiver twin | **yes**, all three — why/what/next copy is patient-facing prose in every case |
| Acceptance | A-167 (one primitive each) |
| **Decision** | **add all three** — this is the single largest gap against §27 on the native side: `AIComposer.tsx`'s `errorMessage` handling is the *only* place any of the three concepts appears today, and it is inline `Text` styling, not a shared component. `design-build-2-map.md` §3 found the identical gap on web ("four places do pieces of one job"); the native gap is total, not partial |

#### `MotionProvider`

| | |
|---|---|
| Built as | no provider component exists — `motionTokens.ts`/`springs.ts`/`transitions.ts` are plain module exports, imported directly by each component |
| Variants/props | n/a |
| States | n/a |
| Tokens | is the token set itself |
| Driving event | n/a |
| Caregiver twin | n/a |
| Acceptance | A-161 (nothing hard-coded, enforced by `lint-motion.js` — see `MOTION_SYSTEM.md` §6) |
| **Decision** | **do not add** — a provider component would exist to inject *context* (e.g. a themed/overridable token set); nothing in the spec, the spike, or the acceptance doc calls for tokens to vary by anything other than `useReducedMotion()`'s own boolean, which is already a plain hook, not a context value. Module-level constants plus the lint are a complete, working substitute for what `MotionProvider` was specified to do — recommend the spec's own §27 line be read as satisfied by the lint, not built as an unnecessary React context |

---

### 2. Composition of each named screen

**Home — built.** `apps/mobile/app/(tabs)/home.tsx`: `AmbientBackground` → header (avatar circle +
greeting + "Not well?", inline JSX, not a named component — a gap the same shape as `DocumentCard`'s,
not separately tabled above since it carries no patient-facing prose of its own) → kicker text →
`EditorialHeadline` → `InsightCard` (primary) → `ExpandableCard` (the blood-pressure metric) → a bare
`NuraCard variant="document"` (should be `DocumentCard`, decision above) → `ReminderCard` →
`MediaCard` → docked `AIComposer` → a `BottomSheet` (lab results) reachable from three different taps
(the insight CTA, the document card, and `ExpandableCard`'s "keep for visit" action). Cross-checked
against ADR 0019 point 8's own composition ("Home = Headline + InsightCard + ReminderCard + FeedCard +
Composer"): the built screen has **two more primitives** than that sentence names
(`ExpandableCard`, `NuraCard`/`DocumentCard`) and **one renamed** (`FeedCard` → `MediaCard`, resolved
above) — ADR 0019's composition line was written before the spike, and this ADR's own table is the
more current source for what Home actually is.

**Health — specified, not built** (`health.tsx` is `PlaceholderScreen`). Per `design-build-2.md`
§15 and ADR 0019 point 8 ("Health = SummaryCard + TrendCard + PaperCards"): an AI summary card
(no built component — would be `NuraCard variant="ai-summary"` directly, or a small wrapper the way
`InsightCard` wraps `insight`), the blood-pressure `TrendCard` (not yet extracted from
`ExpandableCard`, decision above — **this is the actual blocker** for building Health at all), and a
`PaperCards` list (would be a list of `DocumentCard`, once that exists). Nothing here needs a new
motion or colour token — every token Health would consume already exists in `DESIGN_SYSTEM.md`/
`MOTION_SYSTEM.md`; the blocker is component extraction, not design.

**Ask — the composer's own expansion, built; a dedicated screen, not built.**
`mobile-architecture.md`'s file tree names `app/ask.tsx` ("the full conversation, only when it
outgrows the composer") — that file does not exist in `home-spike`. Today, "Ask" **is**
`AIComposer` expanded in place on Home (A-074), which is a complete, working composition on its own
(`IntelligenceOrb size="sm"` + streamed message list + chips). A separate `ask.tsx` would compose the
same primitives (`AIComposer`'s own conversation body, generalised) plus `BottomNavigation`/`AppShell`
as its shell — there is no new primitive Ask would need that Home's composer doesn't already have.

**Medicines — specified only; no route, no feature folder file exists yet.**
`mobile-architecture.md` §2 lists `features/medicines/` in its planned tree; nothing under that path
exists on `home-spike` (`features/home/mock.ts` is the only file under `features/`). Per
`design-build-2-map.md` rows 21–23 (add a medicine, registry, tabs), its composition would be:
`DocumentCard`-or-`MediaCard`-shaped entry rows (photo/type/speak), a `TabBar`-driven Now/All/Changes
switch (not `BottomNavigation` — a **second-level** tab switch, a different primitive than the app's
five root tabs, and not named anywhere in §27 — worth the owner's confirmation whether this is a
`BottomNavigation` reuse or a new `SegmentedControl`-shaped primitive; `InsightCard`'s own `segments`
prop is the closest existing precedent, a two-item segment, not the three-item Now/All/Changes case),
and `ContextualAction` (once built) for "Add to my medicines."

**Visits — specified only; the tab is named `services.tsx`, not `visits.tsx`.**
`_layout.tsx`'s `TAB_ITEMS` names the fourth tab "Services," not "Visits" — the spec's own scene name
(`design-build-2-map.md` row "Visits (tab)") and the built route name disagree. This ADR does **not**
resolve that naming question (whether "Services" absorbs Visits, or Visits becomes its own tab, or
"Services" is renamed to "Visits") — it is a product-scope decision (what else, if anything, lives
under "Services"?) outside a component-architecture ADR's remit, and is flagged for the owner rather
than decided here. Composition, once the naming is settled: one `NuraCard`-based card (propose-never-
book, per A-113), draggable `BottomSheet`s for cost/message drafting (A-111, A-115).

**Insurance — specified only; planned to live inside Profile, not as its own tab.**
`mobile-architecture.md` §2: `"profile.tsx Profile (insurance, emergency card, settings)"` — Insurance
is a **section within** the Profile tab in the planned tree, not a sixth tab. `design-build-2-map.md`
row 46 confirms this is reached "from Visits' 'Insurance · See' row," i.e. a `navigate`, matching
Profile-as-destination. Composition, once built: a policy `NuraCard` (or `DocumentCard`, once
extracted) plus `EmptyState` (once built) for the no-policy-on-file case — `design-build-2-map.md` row
46 names this the "one measured `EmptyState` instance in the whole codebase" already live in the real
app today, ahead of the spike having a shared component to render it with.

---

### 3. "No duplicate components," made checkable

A grep-able rule, following the same shape as `lint-motion.js` (`MOTION_SYSTEM.md` §6) but not yet
built as a script — named here as the check a future `scripts/lint-components.js` should perform:

1. **No second card surface.** Every card-shaped UI element imports `NuraCard` (directly or through a
   named wrapper — `InsightCard`, `MediaCard`, `ExpandableCard`, and once built, `DocumentCard`,
   `TrendCard`). A `View` with its own `borderRadius`/`backgroundColor` styled to look like a card,
   outside `components/cards/`, is a duplicate. (Today's one violation: `home.tsx`'s bare
   `NuraCard variant="document"` is *not* a duplicate — it correctly imports `NuraCard` — but it is
   the pattern most likely to be copy-pasted into the next screen as a second, slightly different
   "document card," which is why `DocumentCard`'s extraction is recommended above.)
2. **No second press/entrance animation.** Every tappable/enterable element reads `cardEnter`,
   `pressIn`, `scalePress`, `springs.bouncy` from `components/motion/` (enforced today by
   `lint-motion.js` for the *values*; not enforced for *reuse* — four components each re-implement the
   same three-line press handler inline, the `ContextualAction` gap above).
3. **No second loading/empty/error shape.** Once `LoadingState`/`EmptyState`/`ErrorState` exist, a
   screen writing its own "Loading…"-style text or its own shimmer bars is a duplicate — today there
   is nothing to duplicate *against*, which is itself the gap (§1, above).
4. **One state store per concern.** `AIState.ts`'s `useAIState` is the only place `AIStateName`
   changes; a component holding its own local `useState<'idle'|'thinking'|...>` mirroring it would be
   a duplicate store, not just a duplicate component. None found in the spike today — `MediaState`
   (`MediaCard`) and `ExpandableCardState` (`ExpandableCard`) are legitimately separate machines
   (`mobile-architecture.md` §3 names all three as distinct), not copies of `AIState`.

---

## Consequences

- Three components are missing entirely (`LoadingState`, `EmptyState`, `ErrorState`) and block every
  screen's honest failure/empty handling, not just Health/Medicines/Visits/Insurance — this is the
  single highest-leverage gap this ADR found.
- `TrendCard` and `DocumentCard` need extracting from where their behaviour currently lives
  (`ExpandableCard`'s step 1; `home.tsx`'s inline JSX) before Health or a second document-bearing
  screen can be built without copying code.
- `ContextualAction` needs building to stop the four-way duplication of the press/haptic handler.
- `AppShell`/`BottomNavigation` need extracting from `_layout.tsx`'s inline functions and their colours
  moved onto tokens, matching the rest of the app's "nothing hard-coded" rule.
- `MetricCard` is retired as a name (folded into `NuraCard variant="metric"`); `MotionProvider` is
  retired as a component (the module-level token files plus `lint-motion.js` satisfy its spec intent).
- `FeedCard` (ADR 0019 point 8) and `NuraOrb`/`NuraComposer`/`NuraSheet`/`NuraHeadline` (ADR 0019
  point 8's `Nura*` prefix convention) are superseded by this ADR's names (`MediaCard`,
  `IntelligenceOrb`, `AIComposer`, `BottomSheet`, `EditorialHeadline`) — the spike's built, tested,
  imported names win over the earlier sketch's names, per component, as tabled in §1. `NuraCard`
  itself is the one `Nura*`-prefixed name that survives, because it is also the one actually built
  that way.
- The Visits/Services naming disagreement (§2) is raised, not resolved — it needs the owner's word,
  not a component-architecture decision.
