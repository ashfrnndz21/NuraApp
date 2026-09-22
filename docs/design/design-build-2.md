# Design build 2 — the experience contract, and the plan that reaches it

**Status: binding, from 22 September 2026.** The owner registered the experience specification below
as part of the design build. Every screen, component and motion delivered from this date is held to
it, in addition to the 26 scenes of `experience-blueprint.html` (the frames at
`docs/design/screens/blueprint-ref/` when checked in). `docs/design/audit-2026-09-22.md` measured the
app against the blueprint and the engine against the agentic patterns; this document is the plan
that closes both gaps, in the owner's own twelve-step order.

Two rules that override everything else in this file:

1. **Build fewer experiences deeply.** No new screen is started while a delivered one fails the
   checklist in §3. Twenty shallow screens are the failure mode this plan exists to end.
2. **Every delivery is proved, not described.** Captures against the blueprint frame, the
   checklist below ticked line by line by the operator, chromium *and* webkit, reduced-motion
   on and off, and a measured frame-time trace for anything that animates.

---

## 1. The specification (verbatim, the owner's words)

> I am giving you a reference of the product experience I want to reproduce. Do not treat the
> reference as a collection of static screens. Reverse-engineer the EXPERIENCE, interaction
> model, motion language, visual hierarchy, transitions, component behavior and emotional quality
> of the interface. The goal is to build a real, production-quality consumer application with the
> same design philosophy and interaction language — not a static mockup.

### 1. Core experience
The product should feel like *"an intelligent companion that understands what matters and brings it
to the user."* Not a SaaS dashboard, an enterprise application, a CRUD app, a chatbot wrapped in a UI,
a collection of cards, or an analytics dashboard. The experience is: **AI understands → AI
prioritizes → AI surfaces → user explores → AI explains → user acts.** Minimise navigation, maximise
contextual interaction. The user should rarely ask "where do I go to find this?"

### 2. Visual design language
Deep indigo / violet environment; subtle purple-to-warm gradients; soft radial lighting; translucent
surfaces; glass-like cards; large rounded corners; very soft borders; low-contrast separation;
generous whitespace; large editorial typography; restrained iconography; subtle glow; soft depth
rather than hard shadows. Premium, calm, intelligent, human, cinematic, modern, slightly futuristic,
trustworthy. Avoid Material Design, dense dashboards, excessive borders, rectangular tables, bright
saturated buttons, excessive icons, aggressive gradients, excessive glassmorphism, excessive
animation, "AI gimmick" effects. **Hierarchy over decoration.**

### 3. Design principle
Every screen answers: *What matters to me right now? Why does it matter? What can I do about it?*
Progressive disclosure: "Four things changed this week." → the four things → "Here's why." → "Here's
what you can do."

### 4. Home
A personalised briefing. Top: a small contextual greeting ("Good evening, Tan" / "How are you
today?") with a subtle action. Primary story: a large editorial headline with one word emphasised
("Four numbers to raise with your *doctor.*"). Primary insight card: contextual label, date, concise
insight, explanation, one integrated CTA ("See them in a table"). Secondary actions below: reminder,
personalised content, educational content, AI interaction — small cards, one thing each.

### 5. Card system
One reusable Card with variants — insight, reminder, video/content, metric, recommendation, document,
AI summary, action, alert — and three tiers: **primary** (large, dominant), **secondary** (smaller,
quieter), **tertiary** (minimal surface, stronger type). Large radius, translucent background,
subtle border, soft blur where supported, internal spacing, clear type hierarchy. Not all identical.

### 6. Card motion
Cards feel physical: enter with fade 0→1 and a slight upward translate, spring/eased, subtly
staggered. Primary 400–600 ms, secondary 300–450 ms, stagger 40–100 ms. Never every card
independently with excessive motion. They settle into place.

### 7. Press / touch
Immediate response: scale 1→0.985 over 80–120 ms, surface slightly brighter, shape kept, haptic on
mobile; release on a spring, no large bounce. Expensive and controlled.

### 8. AI presence
A small luminous orb. States: **idle** (subtle breathing, low glow), **listening** (brighter,
expanding halo, gentle pulse), **thinking** (more dynamic, gradient shifts, halo expands and
contracts), **responding** (brighter, wave, settle to idle), **error** (subdued, never aggressive
red). Present without demanding attention.

### 9. AI input
A contextual composer near the bottom ("Ask Nura anything" + microphone / Speak) that feels part of
the interface. On activation the compact pill **expands in place** into a conversational composer;
do not open a separate full-screen chatbot unless the interaction needs it.

### 10. Conversational UI
Not a generic chatbot. Context first ("Your blood pressure has been slightly higher than usual this
week." → "Would you like me to explain what changed?" [Explain] [Show my readings] [Ask something
else]). The AI summarises, explains, asks clarifying questions, recommends, surfaces, connects. Short.

### 11. Progressive disclosure
"Blood pressure — 148 over 92 today — Above your usual" tap → weekly chart → daily values → trend
explanation → contextual interpretation → related information → suggested action. **The same object
expanding, not a navigation.**

### 12. Shared-element transitions
A Home card ("Blood test · 4 outside · Look") transforms into the detail: position, shape,
typography and identity kept. Never fade-out → new page.

### 13. Content / video cards
Editorial media cards: large gradient visual, circular minimal play button, then "Your blood pressure
tablet, in 30 seconds" / "Because you take amlodipine" / "National Heart Centre · 0:32". The user
sees **why** before **what**.

### 14. Personalisation
Continuous, shown by the interface itself, never a settings page: greeting, primary insight, content,
reminders, education, suggested questions, card order. "Because you take amlodipine", not
"Recommended videos".

### 15. Health / data view
Same language, deeper. "Your health" → "Your week, looked at closely" with an AI summary ("Ready
since Monday. Two things changed." [Read it]) → Blood pressure [Week] [Month] minimal trend, "148
over 92 today", "Above your usual" badge → Blood test · 12 September · 5 results · 4 outside [Look];
Clinic letter · 2 September · Dr Lim [Read]; Prescription · 2 September · 3 tablets [Read]. **Insight
before raw data.**

### 16. Data visualisation
Editorial and minimal: thin lines, one highlighted point, subtle fill, contextual annotation, a large
primary number, a plain-language interpretation. No gridlines, legends, multiple colours or technical
axes unless necessary.

### 17. Navigation
Minimal bottom navigation (Home · Health · Connect · Services · Profile), visually quiet, subtle but
obvious active state. Content is the hero; navigation is infrastructure.

### 18. Micro-interactions
Numbers count smoothly; cards respond to touch; buttons compress; toggles spring; charts draw
themselves; highlighted metrics pulse gently; the orb breathes; content staggers in; sheets rise;
expandable cards morph; loading shimmers; success is restrained. Every animation has a purpose:
state, feedback, hierarchy, orientation. Never decoration.

### 19. Scroll
Smooth and continuous; no page boundaries; subtle parallax where it helps; hero can compress;
navigation stable; background lighting may respond subtly. Do not overuse.

### 20. Modals / sheets
Bottom sheets over dialogs: drag handle, spring entrance, rounded top, backdrop blur/dim, interactive
drag, velocity-aware dismissal. Physically connected to the interface beneath.

### 21. Loading states
Never "Loading…". "Looking through your recent results…", "Connecting the dots…", "Preparing your
weekly summary…" — the orb plus a subtle shimmer. Intelligent, not technical.

### 22. Empty states
"We don't have any blood pressure readings yet." → "Add your first reading". Why, what, next.

### 23. Error states
Calm and recoverable. "We couldn't reach your clinic records right now." [Try again]. Never an HTTP
code.

### 24. Motion system
Centralised tokens, nothing hard-coded: `motion.fast/standard/slow`, `spring.gentle/standard/bouncy`,
`fade.enter/exit`, `scale.press`, `card.enter`, `sheet.enter`, `orb.idle/listening/thinking/responding`.

### 25. Performance
60 fps. No giant blurred layers, no expensive animation of large surfaces, no animation while not
visible. `prefers-reduced-motion`: remove movement, keep state transitions as opacity/colour.

### 26. Responsive
Mobile first. Tablet/desktop widen intelligently, keep card proportions, larger editorial
compositions, sensible columns, same hierarchy and interaction philosophy.

### 27. Component architecture
`AppShell`, `AmbientBackground`, `BottomNavigation`, `AIOrb`, `AIComposer`, `EditorialHeadline`,
`InsightCard`, `ReminderCard`, `MediaCard`, `MetricCard`, `TrendCard`, `DocumentCard`,
`ExpandableCard`, `BottomSheet`, `ContextualAction`, `LoadingState`, `EmptyState`, `ErrorState`,
`MotionProvider`. Composable primitives, no duplicates.

### 28. State model
Explicit state machines. AI: idle / listening / thinking / responding / error. Card: collapsed /
pressed / expanded / loading / complete / error. Media: idle / loading / playing / paused / complete.

### 29. Data architecture
Realistic mock data, never lorem ipsum / John Doe / 123456. UI, domain models, mock data and API
layer separated so real APIs replace mocks.

### 30. Implementation approach
1 analyse the reference · 2 interaction map · 3 screen/component architecture · 4 design tokens · 5
motion system · 6 core shell · 7 Home · 8 expandable/detail interactions · 9 AI interaction · 10
secondary experiences · 11 polish · 12 test every interaction. **Fewer experiences, deeper.**

### 31. Quality bar
Not "an AI-generated app": a premium consumer product by an experienced team. Priority: interaction
quality, visual hierarchy, motion, typography, spacing, responsiveness, accessibility, architecture —
over feature count.

### 32. Final principle
Calm → intelligent → personal → contextual → responsive → alive. The product works for the user, not
the user for the product. Before any feature: *can this be more contextual, more effortless, more
human?* If yes, build that.

---

## 2. Where the build stands against it (measured 22 September)

What the kit already has (`web/src/ui/kit`, `web/src/ui/tokens.css`, `docs/design/motion.md`):

| Spec item | Exists | Gap |
|---|---|---|
| Glass surfaces, rounded, soft borders (§2, §5) | `Glass`, `GlassTile`, `TintCard` | One card component with named variants and three tiers does not exist; cards are several components |
| Orb (§8) | `Orb` with **two** states (idle, thinking) | listening, responding, error states missing |
| One status line, soft text, reveal (§6, §21) | `StatusLine`, `SoftText`, `Reveal`/`RevealGroup`, `Skeleton` | Enter motion exists (`--settle`); no stagger token, no spring family |
| Press feedback (§7) | `--press` token | Applied inconsistently; no brightness change |
| Composer (§9) | `AskBar` docked pill | Opens a separate Ask screen; **no in-place expansion** |
| Conversational patterns (§10) | `Exchange`, `MessageBubble`, `LookedAt`, clarify chips | Context-first framing and action chips after an answer are not the default shape |
| Progressive disclosure / expandable cards (§11) | none | **No `ExpandableCard`; every detail is a navigation** |
| Shared-element transitions (§12) | none | **None anywhere** |
| Media cards (§13) | `FeedCard`, `Poster`, `PlayerStrip`, why-line | "Because you take amlodipine" is the why-line; publisher · duration metadata partial |
| Health view (§15, §16) | `Sparkline`, `MetricRow`, Analyst card | **No Week/Month trend chart; charts do not draw themselves; no count-up numbers** |
| Bottom navigation (§17) | `TabBar` | Matches |
| Sheets (§20) | `Sheet`, `ActionSheet` | No drag handle, no interactive drag, no velocity dismissal |
| Loading / empty / error (§21–23) | `StatusLine` lines, per-screen empty copy, `Refused` handling | No shared `LoadingState`/`EmptyState`/`ErrorState` primitives; some empties still terse |
| Motion tokens (§24) | `--settle`, `--press`, `--wash-fade` (3 tokens) | **No spring family, no per-role tokens, values hard-coded in places** |
| Reduced motion (§25) | honoured in `tokens.css` | Kept |
| State machines (§28) | implicit in signals | Not explicit; AI states not modelled as one machine |
| Mock data (§29) | demo seed Pa/Mei, fixture papers | Matches |
| Streams to the UI | six bespoke SSE vocabularies (audit §7.1) | One AG-UI-shaped vocabulary needed for §8/§21 states to be driven by real events |

And the engine gaps the audit ranked (D-0…D-25) are what make the experience *true*: the orb can
only "think" honestly if the stream says so; the Home headline can only be right if the paper was
filed for the right person; "Would you like me to explain what changed?" can only be offered if Ask
can state the value.

---

## 3. The delivery checklist (every screen, every PR — the operator ticks it)

- [ ] Answers the three questions (§3) in the first screenful, in that order.
- [ ] Type on the blueprint scale; one accent word per headline; no caption under 12.5px.
- [ ] One status line that changes in place; never a stack of chips; never "Loading…".
- [ ] Every card enters with `card.enter` and staggers; press uses `scale.press`; nothing hard-coded.
- [ ] Orb state is driven by a real event (never a timer).
- [ ] Detail opens as the same object expanding, or as a sheet — never fade-out → new page.
- [ ] Empty and error states say why, what, next; no HTTP code reaches the screen.
- [ ] Captures at 390×844 and 1280×900 in chromium **and** webkit, beside the blueprint frame.
- [ ] `prefers-reduced-motion` walk: no movement, states still visible.
- [ ] A Playwright trace with measured frame times on the animated path; no frame over 32 ms on the
      reference Mac (the number is measured, not asserted from belief).
- [ ] Caregiver twin for every new line; ms/zh present; `plain-words` and `language` at 0.
- [ ] Independent review (Opus) for anything that changes what a patient reads or a gate.

---

## 4. The plan, in the owner's twelve steps

Hours are the audit's estimates where an item overlaps it; **an item marked "after step 2" is
estimated once the interaction map exists** — no number is written here that was not measured or
derived from one.

| Step | Deliverable | Acceptance | Depends on |
|---|---|---|---|
| **1 Analyse the reference** | A one-page reading of the blueprint's 26 scenes as *interactions*: what the user does, what the AI does, what moves, what stays. Written into this file. | Owner confirms it matches the reference. | — |
| **2 Interaction map** | Every user moment → AI state → screen state → transition type (expand / sheet / stream / navigate), as a table; the state machines of §28 drawn out. | Every blueprint scene appears in the map; no transition type "navigate" without a reason. | 1 |
| **3 Architecture** | The component list of §27 mapped onto the kit: what is renamed, merged, added. One `Card` with variants and tiers; `ExpandableCard`; `AIComposer`; `BottomSheet`; the three state primitives. | ADR in `docs/adr`; no duplicate components remain in the plan. | 2 |
| **4 Design tokens** | `tokens.css` carries colour, type scale, radius, spacing, glow, blur — every screen reads them; a lint fails a hard-coded value. | Lint green; captures unchanged where the screen already matched. | 3 |
| **5 Motion system** | `motion.*`, `spring.*`, `fade.*`, `scale.press`, `card.enter`, `sheet.enter`, `orb.*` as tokens plus a `MotionProvider`; reduced-motion mapping; the Playwright frame-time harness. | Every existing animation moved onto tokens; the harness runs in CI (chromium) and locally (webkit). | 3 |
| **6 Core shell** | `AppShell`, `AmbientBackground` (lighting that responds subtly to scroll), `BottomNavigation`, the orb with all five states driven by one event stream, the composer that expands in place. **Includes the engine's one event vocabulary (audit §7.5 item 3, ~20 h)** — without it the orb states are fiction. | Orb states change from real events in a recorded trace; composer expands without leaving Home. | 4, 5, audit step 8 |
| **7 Home** | The briefing exactly as §4: greeting, editorial headline, primary insight card, secondary cards; personalised order; "Because you take amlodipine". **Includes audit D-5 (insight reachable) and the headline rule already merged.** | Frame 15 match; three questions answered; all cards on `card.enter`. | 6 |
| **8 Expandable / detail** | `ExpandableCard` and shared-element transitions: Home insight → blood test table; blood pressure → week chart → values → explanation → action, as one object. `TrendCard` with a chart that draws itself and a count-up number. | Frames 07, 15, 17; no fade-to-page anywhere on these paths; trace under budget. | 6 |
| **9 AI interaction** | The composer's conversational shape (§10): context first, one question back, action chips; clarifying questions; the orb listening/thinking/responding. **Depends on the engine: audit D-1/D-3/D-7 (Ask states facts, ~16 h), model judge + vetoes (~16 h), unified context (~16 h).** | Frame 16; the owner's cholesterol question answered with the number and date; "is it high?" answered from the paper's range. | 6, audit steps 1, 6, 9 |
| **10 Secondary experiences** | Health view as §15–16; media cards as §13; sheets as §20; loading/empty/error primitives everywhere; Not well, Connect, Mei's Home, Profile rebuilt on the same primitives (package 14). | Frames 17–26; checklist per screen. | 7, 8, 9 |
| **11 Polish** | One pass over type, spacing, colour, motion timing against §2, §6, §7, §24 with the frames side by side; the wording pass the audit lists (D-12, D-14, D-17, D-20, D-21). | Owner's frame-by-frame review. | 10 |
| **12 Test every interaction** | The interaction map becomes the test list: one Playwright walk per interaction in both engines, reduced-motion on and off, frame-time trace on every animated path; a graded evaluation set for Ask and intake (audit step 5, ~16 h) so the AI's part is measured too. | All walks green in CI; the eval pass rate reported on every PR. | all |

**Interleaving with the engine (audit §6).** Steps 0–5 of the audit's order (WebKit Profile freeze;
Ask states facts; whose paper; duplicates; insight reachable + which statin; evaluation harness) run
**first and in parallel with design steps 1–5**, because they change what the screens can truthfully
say. Design step 6 carries the event vocabulary. Design step 9 carries the judge and the unified
context. Packages 18–22 (One record) and 24 (ASEAN) wait until step 10.

**What is not in this plan.** Voice add for medicines; a native app; anything the blueprint does not
show. Each would be a new scene first.
