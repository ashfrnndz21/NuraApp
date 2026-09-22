# Motion system — every token, what it means, where it fires

**Status: reference, from 23 September 2026.** The second of the three documents
`docs/design/mobile-architecture.md` requires before production UI. Its own governing line, verbatim
from `design-build-2.md` §24: *"Centralised tokens, nothing hard-coded."* No screen may write a
literal duration, delay or easing curve; every value below is read from
`apps/mobile/components/motion/motionTokens.ts` (native) or `web/src/ui/tokens.css` (web), and the
lint in §7 fails a build that doesn't.

**Sources, read in full.** `experience-blueprint-v2.html`'s `:root` block (the one place every
duration and curve is declared, per its own comment: "Every duration and every easing in this file is
declared here and nowhere else"). `apps/mobile/components/motion/motionTokens.ts`,
`components/motion/springs.ts`, `components/motion/transitions.ts`, `components/motion/
useReducedMotion.ts` (all on `origin/home-spike`) — `motionTokens.ts`'s own docstring: "copied verbatim
from the `:root` block… same names, same values as the reference — only the units change." ADR 0019
(`docs/adr/0019-...md`) §4 (the event vocabulary) and point 4 ("motion represents real state and never
fakes time"). `apps/mobile/scripts/lint-motion.js`. `docs/design/design-build-2.md` §6, §7, §18, §19,
§24, §25. `docs/design/design-build-2-map.md` §2 (the three state machines, with what drives each
transition today and under the AG-UI vocabulary).

---

## 1. Every token: value, meaning, where it applies

All durations in ms unless noted. Source column: **v2** = `experience-blueprint-v2.html` `:root`;
**spike** = `motionTokens.ts` (verbatim copy, confirmed identical for every row below).

### 1.1 Base durations and curves

| Token | Value | Meaning | Applies to |
|---|---|---|---|
| `motion.fast` | 140ms | The shortest deliberate transition | Fade-exit's duration component; sheet/composer close |
| `motion.standard` | 320ms | The default transition length | Fade-enter's duration component; ambient brightness cross-fade (`AmbientBackgroundCanvas.tsx`'s `timing.standard()`) |
| `motion.slow` | 560ms | The longest simple transition | `word.enter` (a streamed word's own fade+blur-in) |
| `spring.gentle` | cubic-bezier(.22,.61,.36,1) | The default "settles softly" curve | Card enter, fade enter/exit, control button colour/opacity transitions |
| `spring.standard` | cubic-bezier(.2,.8,.2,1) | A slightly snappier settle | Sheet enter |
| `spring.bouncy` | cubic-bezier(.34,1.42,.5,1) | Overshoots slightly before settling | Press release (scale back to 1) |

### 1.2 Composite transitions (a duration paired with a curve, named for its use)

| Token | Duration | Curve | Meaning | Applies to |
|---|---|---|---|---|
| `fade.enter` | 320ms (`motion.standard`) | spring-gentle | Something appearing that wasn't there | Sheet backdrop, composer pill fade-out |
| `fade.exit` | 140ms (`motion.fast`) | spring-gentle | Something leaving | Composer's docked pill hiding behind the expanded composer (`.composer .line{transition:opacity var(--fade-exit)...}`) |
| `card.enter` | 520ms | spring-gentle | A card's own arrival — fade 0→1 + 12px upward rise | Every `NuraCard` and its variants (`InsightCard`, `ExpandableCard`'s content reveal, `ReminderCard`, `MediaCard`) |
| `sheet.enter` | 550ms | spring-standard | The sheet rising into place | `BottomSheet.tsx`'s open transition (`springs.standard`) |
| `scale.press` | to 0.985 | — | The pressed-down scale factor, not a duration | Every tappable card/pill/button |
| `press.in` | 100ms | linear | Finger-down response — deliberately linear, not eased, so it reads instant | Press-down scale + brighten on `NuraCard`, `ExpandableCard`, `ReminderCard` |
| `press.out` | 260ms | spring-bouncy | Release, with a slight overshoot | Every press-release across the app |

### 1.3 Orb (per state — spin duration of the conic sweep)

| Token | Value | Meaning |
|---|---|---|
| `orb.idle` | 7000ms | Slowest, calmest sweep — "present without demanding attention" (§8) |
| `orb.listening` | 3400ms | Faster, brighter, expanding halo |
| `orb.thinking` | 2200ms | Fastest — the most dynamic state |
| `orb.responding` | 4200ms | Slower than thinking, settling toward idle |
| (error) | reuses `orb.idle` (7000ms) — v2 has no distinct error spin duration; only the gradient desaturates and the glow dims (see `DESIGN_SYSTEM.md` §10.2) | |

### 1.4 Word/status reveal (streaming text)

| Token | Value | Meaning | Applies to |
|---|---|---|---|
| `word.enter` | 560ms (`motion.slow`) | A single streamed word's own fade+blur-in | Every `stream()`-rendered word (headline, response body, sheet content) |
| `status.in` | 350ms | Status line fading in | `StatusLine.tsx` |
| `status.out` | 220ms | Status line fading out before the next one replaces it | `StatusLine.tsx`; `ExpandableCard.tsx`'s content-dismiss step |
| `sweep` | 1500ms | The shimmer/text-shine loop period | Loading shimmer bars, the "thinking" status text's light-sweep |

### 1.5 Ambient/idle looping motion

| Token | Value | Meaning | Applies to |
|---|---|---|---|
| `breathe` | 4500ms | The orb's idle scale pulse (1 → 1.04 → 1) | `IntelligenceOrbCanvas.tsx`'s idle-only `breath` animation |
| `drift` | 16000ms | Atmosphere blob A's slow position drift | `.atmos i.a` (CSS); not yet Skia-driven in the spike's `AmbientBackgroundCanvas.tsx`, which drives layer A only by scroll parallax, not v2's own idle drift loop — see `DESIGN_SYSTEM.md` §1.2 |
| `drift-slow` | 20000ms | Atmosphere blob B's slower drift | `.atmos i.b` — same native gap as above |
| `bob` | 6000ms | The "cloud of conditions" bubble idle bob | Onboarding only (not built in the Home spike) |

### 1.6 Stagger (list entrance — density-dependent, per `design-build-2.md` §6)

| Token | Value | When it's used |
|---|---|---|
| `stagger.dense` | 80ms | 6+ items in a list |
| `stagger.rows` | 110ms | 3–5 items |
| `stagger.tight` | 150ms | — (named, not directly wired to a density band in the map's own `density()` function — see §1.7) |
| `stagger.mid` | 200ms | — |
| `stagger.step` | 230ms | — |
| `stagger.wide` | 260ms | — |
| `stagger.cards` | 300ms | Fewer than 3 items — Home's own card list (`home.tsx` passes `staggerCards` to every top-level card) |

### 1.7 The measured density rule

`experience-blueprint-v2.html`'s own `density()` function (line 317): `n=>n>=6?MO.dense:n>=3?MO.rows:
MO.cards` — only **three** of the seven named stagger tokens (`dense`, `rows`, `cards`) are wired to
this rule; `tight`, `mid`, `step` and `wide` are declared in `:root` but not consumed by the reveal
logic anywhere in v2's own script. The spike's Home screen (`app/(tabs)/home.tsx`) uses `staggerCards`
(300ms) uniformly for its five top-level cards — a five-item list, which by v2's own `density()`
function would actually fall in the **dense** band's neighbour (`n>=3` → `rows`, 110ms) once it grows
past four, not `cards` (300ms, reserved for lists under three). This is worth flagging: Home's card
count (five, not counting the composer) sits right at the edge of the rule its own reference defines,
and the spike has not yet re-derived the correct band as the card count grew — a concrete place for a
future PR to re-check the density math against `density()`, not a design decision to make.

### 1.8 Chart, count-up, media, alarm

| Token | Value | Meaning | Applies to |
|---|---|---|---|
| `chart-draw` | 900ms | A trend line drawing itself, stroke-dashoffset animation | `BPChartCanvas` (Health's expandable card, step 1) |
| `count-up` | 1100ms | A number counting from 0 to its value, eased (`1-(1-k)^3`) | v2's `countUp()`; not yet built in the spike's `ExpandableCard.tsx`, which renders "148" as static text — a gap against `design-build-2.md` §18 ("Numbers count smoothly") and A-159's own pass criterion |
| `alarm-reveal` | 60ms | The fastest transition in the entire system — the not-well flow's background+card swap | Not built in the Home-only spike (`mobile-architecture.md` §5); referenced in `ExpandableCard.tsx` only as the delay before the chart's own draw begins, a reuse of the token's *value*, not its original *meaning* |
| `media-run` | 9000ms | A video clip's total simulated/real duration | `MediaCard.tsx`'s progress-bar animation |
| `atmos-fade` | 800ms | The atmosphere's own colour cross-fade when its gradient stops change | Not directly wired in the spike; `AmbientBackgroundCanvas.tsx` uses `motion.standard` (320ms) for its brightness cross-fade instead, a different token than v2's own `--atmos-fade` for what looks like the same kind of change — another small, real divergence |

### 1.9 Stream pace, per content type

| Token | Value (ms/word) | Content type |
|---|---|---|
| `stream.head` | 85 | Headline words (Home's own editorial headline) |
| `stream.sub` | 50 | Sub-status text |
| `stream.body` | 36 | The AI's own response body — the **fastest** pace, since body text is read, not savoured |
| `stream.sheet` | 58 | Text streamed inside a sheet |
| `stream.spoken` | 210 | The **slowest** pace — a video caption meant to track spoken narration, not reading speed |
| `word-hold` | 220ms | The pause after a full line finishes streaming, before the next action (e.g. chips appearing) |

### 1.10 Thinking/pacing holds

| Token | Value | Meaning |
|---|---|---|
| `think-hold` | 1050ms | How long each "thinking" status line is shown before the next stage replaces it |
| `think-page` | 430ms | Per-page hold on a multi-page read (e.g. the policy passport's "Reading page 4 of 48…") |
| `busy-hold` | 950ms | A three-state button's busy label hold ("Keeping…" before "Kept") |
| `beat` | 700ms | A generic pause between two related reveals |
| `auto-pick` | 1200ms | Autoplay's own pacing when the journey plays itself |
| `user-pick` | 6000ms | How long a user-driven choice is given before autoplay would move on |

---

## 2. The state → motion mapping

### 2.1 AI state (idle / listening / thinking / responding / error)

Source: `apps/mobile/components/ai/AIState.ts` (the Zustand store) and `docs/design/
mobile-architecture.md` §3's own table, reproduced here with the motion values filled in from §1.

| State | Orb | Background | Composer | Cards | Response |
|---|---|---|---|---|---|
| idle | `orb.idle` spin (7000ms), `breathe` pulse (4500ms), glow .35 | brightness +0 (`BRIGHTNESS_BY_STATE.idle`) | collapsed pill | normal `card.enter` | — |
| listening | `orb.listening` spin (3400ms), halo animation, glow .55 | +0.14 brightness, `motion.standard` cross-fade | expanded (`AIComposer`'s `openComposer`) | normal | — |
| thinking | `orb.thinking` spin (2200ms), pulse halo, glow .55 | +0.22 brightness | expanded, status line cycling every `think-hold` (1050ms) | quieter (no explicit dim value sourced — `design-build-2.md` §28's table names the state, no numeric opacity) | status line changes in place (`status.in`/`status.out`) |
| responding | `orb.responding` spin (4200ms), wave halo, glow .55 | +0.28 brightness (the brightest of any state) | expanded | the relevant card materialises via `card.enter` | words arrive at `stream.body` (36ms/word), CTA/chips after |
| error | `orb.idle` spin reused, desaturated gradient, glow .18 (dimmest) | **−0.08 brightness** — the only state that *dims* the background rather than lifting it | expanded, calm error line + "Try again" | normal | one calm sentence, no streaming shown in the spike's fixture |

### 2.2 Card state (collapsed / pressed / expanding / expanded / interactive / dismissed)

Source: `apps/mobile/components/cards/ExpandableCard.tsx` (`ExpandableCardState`) and
`mobile-architecture.md` §3.

| Transition | What drives it | Motion |
|---|---|---|
| collapsed → pressed | finger down on the card | `press.in` (100ms linear) scale to 0.985, haptic (native) |
| pressed → expanding (step 1) | release, first tap | `chart-draw` (900ms) content-opacity fade-in, chart progress `withDelay(alarm-reveal, withTiming(chart-draw))` — the 60ms `alarm-reveal` token reused here as a small pre-roll delay, not its original not-well-flow meaning (§1.8) |
| expanding → expanded (steps 2–4) | further taps | `motion.standard` (320ms) content fade per step |
| expanded → interactive (step 5) | fifth tap | same `motion.standard` fade, reveals the "what you can do" action |
| interactive → dismissed (step 6, the sixth tap) | sixth tap | `status.out` (220ms) fade, then `setTimeout` back to collapsed after the same duration |

Six taps cycle the object through all six states and back to collapsed — never a navigation, per
`design-build-2.md` §11 and A-159/A-164 (`end-to-end-acceptance.md`).

### 2.3 Media state (idle / loading / playing / paused / complete)

Source: `apps/mobile/components/cards/MediaCard.tsx` (`MediaState`).

| Transition | What drives it | Motion |
|---|---|---|
| idle → loading | tap the poster's play button | `press.out` (260ms) is the delay before playback is simulated to begin (`setTimeout(..., pressOut)`) |
| loading → playing | the simulated/real asset becomes ready | progress bar starts a linear `withTiming` over the remaining `media-run` fraction |
| playing → paused | tap again while playing | `cancelAnimation(progress)` — instant, no eased transition (matches `design-build-2-map.md`'s own finding: "not modelled anywhere" in v2's reference — the spike had to invent this transition, since pause has no source) |
| paused → playing | tap again while paused | resumes the linear progress animation from its current value |
| playing → complete | progress reaches 1 | `runOnJS(setAndNotify)('complete')` fires when the timing animation finishes |
| complete → idle | tap the replay affordance | progress resets to 0, instant |

---

## 3. "Motion represents real state, never fakes time"

**The rule, verbatim.** ADR 0019 point 4: *"The orb, the cards, the composer and Home's recomposition
are all driven from [the event stream] — motion represents real state and never fakes time."* This is
the same principle `AIState.ts`'s own docstring states for the spike: *"Every subscriber… reads this
one store… Never a timer changes this on its own."*

**The event vocabulary that drives every transition** (ADR 0019 §4, AG-UI-shaped; the exact union is
declared in `apps/mobile/lib/ai/events.ts`'s `NuraEvent` type):

| Event | Drives |
|---|---|
| `RUN_STARTED` | Clears any stale error message; the first event of a turn |
| `TEXT_MESSAGE_START` (`role: 'user'`) | AI state → `listening`; a new message bubble opens |
| `TEXT_MESSAGE_START` (`role: 'assistant'`) | AI state → `responding`; the response's own message bubble opens |
| `TEXT_MESSAGE_CONTENT` | Appends a streamed delta to the open message — the visible word-by-word arrival |
| `TEXT_MESSAGE_END` | Closes the current message (no state change by itself) |
| `TOOL_CALL_START` | AI state → `thinking`; `statusLine` set to the event's own `label` — this is what actually drives the "Looking at your paper…" style status text, not a hard-coded string in the component |
| `TOOL_CALL_ARGS` / `TOOL_CALL_END` / `TOOL_CALL_RESULT` | No direct state change in the spike's reducer (`AIState.ts`'s `consumeEvent` `return`s on these without a `set()`) |
| `STATE_DELTA` (with a `chips` array in its patch) | Populates the composer's action chips |
| `STATE_SNAPSHOT` | No-op in the current reducer (reserved for a future full-state sync) |
| `RUN_FINISHED` | AI state → `idle`; clears the status line |
| `RUN_ERROR` | AI state → `error`; sets `errorMessage` from the event |

**What this rules out.** No component may set the orb's `data-state`/`stateOverride` from a
`setTimeout` alone (`IntelligenceOrbCanvas.tsx`'s own comment: "state comes only from `AIState`… never
from a timer inside this component"). `lint-motion.js` cannot catch a *state-source* violation the way
it catches a hard-coded duration (§7) — this is a code-review discipline, not a static-analysis one,
and is worth naming as a gap: nothing today would fail CI if a future screen wired the orb to a plain
timer instead of the event store.

---

## 4. Reduced-motion mapping

Source: `apps/mobile/components/motion/useReducedMotion.ts` (reads `AccessibilityInfo.
isReduceMotionEnabled`) and `experience-blueprint-v2.html`'s own `@media (prefers-reduced-motion:
reduce)` rule plus its `RM()`/`FORCE_RM` JS flag.

**The rule, both places, identically:** movement is removed; state changes remain visible as instant
opacity/colour changes. `design-build-2.md` §25: *"prefers-reduced-motion: remove movement, keep state
transitions as opacity/colour."*

| Token/behaviour | Normal | Reduced |
|---|---|---|
| `card.enter` | 520ms fade + 12px rise | opacity set to 1, translateY set to 0, instantly (`NuraCard.tsx`: `if (reducedMotion) { opacity.value = 1; translateY.value = 0; return; }`) |
| Orb spin | rotates continuously at the state's own duration | `cancelAnimation(rotation); rotation.value = 0` — frozen, not slowed |
| Orb breathe | scales 1↔1.04 on a loop | frozen at 1 |
| Orb halo (listening/thinking/responding) | animated opacity+scale loop | frozen at a static value (0 normally, 0.4 for error — the halo's *state-carrying* opacity is kept even with motion off, since "error" is a state, not a movement) |
| `ExpandableCard`'s chart-draw / content fade | 900ms / 320ms fades, staggered by `alarm-reveal` delay | all opacities/progress set to their end value instantly |
| `countUp()` (v2 only — not yet built in the spike) | eased count from 0 | v2's own `countUp()`: `if(RM()){el.textContent=pre+to.toFixed(dp)+post;return;}` — final value shown immediately |
| `drawChart()` (v2 only) | stroke-dashoffset animates over `chart-draw` | v2's own `if(RM()){...opacity=1...return;}` — fill/highlight shown at final opacity, no draw |
| Sheet enter/exit | spring transform | `translateY.value = reducedMotion ? 0 : withTiming(...)` — snaps to open/closed position |
| Media progress bar | linear animation over `media-run` | not specially handled in `MediaCard.tsx` today — a gap: the progress bar still animates under reduced motion, since its `withTiming` call has no `reducedMotion` branch, unlike every other animated value in the spike |

**A gap worth naming plainly.** `MediaCard.tsx`'s playback progress bar is the one animated value in
the spike's component set that does not check `useReducedMotion()` before calling `withTiming` — every
other card, the orb, and the sheet do. This is a concrete, small fix for whichever screen next touches
media playback, not a design decision.

---

## 5. Performance rules

Source: `design-build-2.md` §25 ("60 fps. No giant blurred layers, no expensive animation of large
surfaces, no animation while not visible") and `mobile-architecture.md` §4 ("a measured frame-time
trace on every animated path; 60 fps on an iPhone 12 class device is the bar — measured, not
asserted"), plus `end-to-end-acceptance.md` **A-175**/**A-177**.

- **Transform/opacity only.** Every animated value in `motionTokens.ts`/`springs.ts`/`transitions.ts`
  drives a Reanimated `useAnimatedStyle` producing `opacity`/`transform` (scale, translateY) — never a
  layout-triggering property (width/height/padding animated directly; `ExpandableCard`'s own layout
  changes are driven by conditional rendering + `onLayout`, not an animated layout property).
- **No blur animated on a large layer.** The orb's blur is a fixed per-size value (§`DESIGN_SYSTEM.md`
  §5), never itself animated; the sheet/composer/card `BlurView`s are static-intensity — only their
  *opacity* (backdrop) or *position* (sheet) animates, never the blur radius itself.
- **Nothing runs off-screen.** A-177's own pass criterion: no animation attributed to an element
  outside the visible viewport. The spike does not yet have an automated check for this (no
  intersection-observer-equivalent gating in `NuraCard.tsx`'s entrance effect, which fires on mount
  regardless of scroll position) — a gap against A-177, not something the current code guarantees.
- **60 fps / no frame over 32ms**, measured, not asserted (A-005, A-175). The spike has no frame-time
  harness wired yet — `mobile-architecture.md` §4 calls for "a measured frame-time trace on every
  animated path" as a delivery rule for every screen, and `design-build-2.md` §4 step 5 names the
  harness as its own deliverable ("the Playwright frame-time harness"). Neither exists in the
  worktree read for this document; this is a known, named gap, not a silent omission.

---

## 6. The lint: `apps/mobile/scripts/lint-motion.js`

**What it does.** Scans `components/`, `app/` and `features/` for four literal-duration patterns:
`duration: <number>`, `withTiming(_, <number>`, `withDelay(<number>`, and `setTimeout(_, <number>)`
outside `lib/ai` (the one place a literal delay is legitimate — the fixture emitter's own pacing,
which itself reads its numbers from `motionTokens.ts`, e.g. `streamBody`/`thinkHold` imported into
`lib/ai/events.ts`). `components/motion/motionTokens.ts`, `springs.ts` and `transitions.ts` are the
only exempt files — the tokens themselves are allowed to contain numbers; everything that *consumes*
them may not.

**What it does not catch** (named, not silently assumed complete):

- A literal number passed as a *prop* rather than inside `withTiming`/`withDelay`/`duration:` —
  e.g. a raw `7000` handed to a custom hook that itself calls `withTiming` internally would not match
  any of the four regexes.
- CSS-side literals in `web/src/ui` — the lint's `SCAN_DIRS` is `['components', 'app', 'features']`
  resolved from `apps/mobile`, so it does not check the web kit's own CSS/`tokens.css` consumers at
  all; a second, CSS-shaped version of this lint (checking for a bare `ms`/`s` duration outside
  `tokens.css` itself) does not exist yet in either worktree read for this document.
- The state-source violation named in §3 (an orb driven by a bare timer rather than the event store)
  — a duration read correctly from a token but attached to the wrong *trigger* passes this lint
  cleanly, since the lint only checks where numbers come from, never what causes a transition to fire.

**Exit behaviour.** Non-zero exit and a per-line report (`file:line  literal <pattern> — <line text>`)
on any violation; `lint-motion: clean (N files scanned)` and exit 0 otherwise. It is registered as
`"lint:motion": "node scripts/lint-motion.js"` in `apps/mobile/package.json`, so it is runnable on
its own — but the repo's CI (`.github/workflows/ci.yml`, both `home-spike` and `redesign`) runs `make
lint`, and the root `Makefile`'s `lint` target is `cd backend && python3 -m ruff check . && python3 -m
mypy app` — the backend only. `lint:motion` is not called from `make lint`, from `ci.yml`, or from any
other workflow in either branch read for this document. `design-build-2.md` §4 step 5 calls for "a
lint fails a hard-coded value" as an acceptance criterion; the script exists and passes today, but
nothing yet fails a PR that reintroduces a hard-coded duration.
