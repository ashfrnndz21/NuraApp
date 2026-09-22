# Mobile architecture — the native app, structured around experiences

**Status: binding, from 22 September 2026** (the owner's stack and structure, recorded verbatim in §1
and mapped onto Nura in §2). Companion to `design-build-2.md` (the experience specification and the
twelve steps) and `experience-blueprint-v2.html` (the clickable reference). The decision to go native
is taken on the evidence of the Home spike (§5); until then this file is the plan, not a commitment
to rewrite.

## 1. The owner's stack and structure (verbatim)

| Layer | Technology | Why |
|---|---|---|
| App | React Native | True mobile UI |
| Project/build | Expo | Fastest setup/deployment |
| Navigation | Expo Router | Clean screen architecture |
| Animation | Reanimated 4 | High-performance UI-thread animation |
| Gestures | Gesture Handler | Swipe, drag, sheets, interactive gestures |
| Visual effects | React Native Skia | Orb, gradients, blur, charts, ambient effects |
| State | Zustand | Lightweight app state |
| Backend | *(owner listed Supabase initially)* | see §2 — Nura keeps its own backend |
| AI | *(owner listed OpenAI / preferred model layer)* | see §2 — Nura keeps its model layer |
| Analytics | PostHog | Product analytics |
| Deployment | EAS Build + EAS Submit | TestFlight / App Store / Play Store |

"Don't build it screen-by-screen. Structure the project around experiences":

```
/app
   /(tabs)
      home.tsx
      insights.tsx
      profile.tsx
/components
   /ambient      AmbientBackground.tsx  IntelligenceOrb.tsx  GlowField.tsx
   /cards        InsightCard.tsx  MetricCard.tsx  MediaCard.tsx  ReminderCard.tsx  ExpandableCard.tsx
   /ai           AIComposer.tsx  AIConversation.tsx  AIResponse.tsx  AIState.ts
   /motion       motionTokens.ts  springs.ts  transitions.ts
   /sheets       InsightSheet.tsx  AIActionSheet.tsx
/features
   /home  /insights  /conversation  /personalization
/lib
   /ai  /api  /analytics  /storage
```

"Make the app state-driven. The AI orb has states — IDLE → LISTENING → THINKING → RESPONDING → IDLE —
and the entire interface responds to those states." Card interaction is also state-driven: COLLAPSED →
PRESSED → EXPANDING → EXPANDED → INTERACTIVE → DISMISSED, so a tap physically becomes the expanded
object, never Screen A → Screen B. Skia is used selectively — orb, ambient field, glow, charts, blur,
cinematic transitions — and ordinary React Native for text, cards, buttons, navigation, forms, lists,
accessibility and AI messages.

Three sources of truth for the coding agent: the reference (the experience blueprint v2 stands in
for the video, which the agent cannot watch), the experience specification (`design-build-2.md` §1),
and the HTML prototype (`experience-blueprint-v2.html`). Before production UI: `EXPERIENCE_SPEC.md`
(= `design-build-2.md`), `MOTION_SYSTEM.md`, `DESIGN_SYSTEM.md`.

Phases: **1 Foundation** (Expo, RN, TypeScript, Expo Router, Reanimated, Gesture Handler, Skia,
Zustand; the design-token system; nothing else). **2 The magic** (Home only, exceptionally polished:
ambient background, orb, hero, insight card, card expansion, bottom sheet, gesture dismissal, AI
composer, AI state transitions — do not move on until those feel right). **3 AI** (AIComposer → AI
service → streaming response → AIState → OrbState → UIState, so the AI is not bolted on). Loop:
Claude Code → Git → EAS → TestFlight → iPhone → feedback.

## 2. Mapped onto Nura

Two of the owner's rows change, for reasons already decided in this repo:

- **Backend stays Nura's own** (FastAPI, Postgres/SQLite, the audit trail, the safety gates, the
  consent model, ms/zh, 3,000+ tests). `lib/api` is a typed client over the existing routes; nothing
  moves to Supabase. Auth is the existing phone-code sign-in.
- **AI stays Nura's model layer** (`app/llm`, per-task models, the vetoes). `lib/ai` is the client
  for the streamed routes and the one AG-UI-shaped event vocabulary the audit asks for (§7.5 item
  3) — the same events drive `AIState` in the app and the orb.

The structure, with Nura's real domains filled in:

```
apps/mobile/
  app/
    (tabs)/
      home.tsx          Home — the briefing (spec §4)
      health.tsx        Health — insight before data (spec §15)
      connect.tsx       Connect
      services.tsx      Services
      profile.tsx       Profile (insurance, emergency card, settings)
    paper/[id].tsx      a paper's table, reached by shared element, never a cold navigation
    ask.tsx             the full conversation, only when it outgrows the composer
  components/
    ambient/            AmbientBackground (Skia field that answers scroll and AIState), IntelligenceOrb
                        (five states, driven only by AIState), GlowField
    cards/              Card (variants × tiers), InsightCard, MetricCard, TrendCard, MediaCard,
                        ReminderCard, DocumentCard, ExpandableCard (the collapsed→…→dismissed machine)
    ai/                 AIComposer (pill → composer in place), AIConversation, AIResponse (context
                        first, one question back, chips), AIState.ts (the machine + the event mapping)
    motion/             motionTokens.ts, springs.ts, transitions.ts (shared-element + expand)
    sheets/             BottomSheet (handle, drag, velocity), InsightSheet, AIActionSheet, ClarifySheet
    states/             LoadingState, EmptyState, ErrorState (spec §21–23)
    text/               EditorialHeadline, SoftText (word-by-word), StatusLine (one line, in place)
  features/
    home/  health/  conversation/  papers/  medicines/  insurance/  feed/  personalization/  caregiver/
  lib/
    ai/                 event stream client, AIState reducer
    api/                typed client over the Nura routes; consent scopes; row-scope errors → ErrorState
    analytics/          PostHog (events named after the interaction map, never PII)
    storage/            offline copies (the kept Today page, emergency card), never facts
    i18n/               en / ms / zh catalogues shared with the web app's `@patient` rules
  motion/
    MOTION_SYSTEM.md    the tokens and their meaning (spec §24), written before UI
  design/
    DESIGN_SYSTEM.md    colour, type scale, radius, blur, glow (spec §2, §4–5), written before UI
```

The web app (`web/`) remains for the caregiver on a desktop and as the fallback; it shares the
backend, the catalogues and the plain-words gates. No web screen is built while the spike runs.

## 3. The state machines (spec §28), as the app's spine

**AIState** — `idle → listening → thinking → responding → idle`, `* → error → idle`. Driven only by
events from the stream (`RUN_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `RUN_FINISHED`, `RUN_ERROR`;
`listening` by the composer's own focus/voice). Never by a timer. Every subscriber reads one store:

| State | Orb | Background | Composer | Cards | Response |
|---|---|---|---|---|---|
| idle | slow breathing, low glow | almost static | collapsed | normal | — |
| listening | larger, brighter, expanding halo | ambient light up slightly | expanded | normal | — |
| thinking | gradient moves, halo pulses, slight rotation | — | expanded | quieter | status line changes in place |
| responding | pulse → settle | — | expanded | the relevant card materialises | words arrive; CTA after the insight |
| error | subdued | — | expanded | normal | calm line + Try again |

**Card** — `collapsed → pressed → expanding → expanded → interactive → dismissed`, with `loading` and
`error` reachable from `expanding`. Expansion is a shared-element transform of the same object.

**Media** — `idle → loading → playing ⇄ paused → complete`.

## 4. Delivery rules (from `design-build-2.md` §3, unchanged)

Captures beside the blueprint v2 frame; a measured frame-time trace on every animated path (60 fps
on an iPhone 12 class device is the bar — measured, not asserted); reduced motion on and off;
accessibility (VoiceOver labels, focus order); caregiver twins, ms/zh; an independent review for
anything a patient reads; an EAS internal build on the owner's phone for every delivered experience.

## 5. The decision point — the Home spike

Phase 1 + Phase 2 for **Home only**, against the real backend, judged on the owner's iPhone against
blueprint v2's Home, composer, expand and sheet scenes. If it clears the bar, design-build-2 steps
8–12 proceed native and this file governs. If it does not, the reasons are written here and the web
stack continues with steps 3–9. Either way the engine work (audit steps 0–9) is unaffected.
