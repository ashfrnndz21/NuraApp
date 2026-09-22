# ADR 0019 — One stateful system: Nura Run, the event protocol, the Health Graph, and the order of build

**Status:** accepted, 22 September 2026 (the owner's decision; his words are quoted where they set the
rule). Supersedes the package-by-package order of `docs/design/build-plan.md` for everything not yet
built. Companions: `docs/design/design-build-2.md` (experience contract), `docs/design/
mobile-architecture.md` (native stack), `docs/design/experience-blueprint-v2.html` (the reference),
`docs/design/audit-2026-09-22.md` (the measurements this answers).

## Decision

> "Don't build Nura as 26 screens. Build one stateful intelligence system that happens to have 26
> experiential moments."

1. **The loop is the product.** Person → Nura understands context → paper / medicine / event → Nura
   extracts → verifies → updates STATE → prioritises → Home recomposes → user explores → Nura explains →
   user acts. The first target is one vertical slice of that loop: Welcome → Pa → paper → Nura reads →
   interpretation → medicine connection → Home → Ask Nura. Not all 26 scenes.
2. **The screen is a projection of state.** One runtime — Nura State, AI Runtime, Health Graph,
   Interaction Runtime, Safety Runtime — and an Experience Renderer that projects it as Home, Health,
   Medicines, Visits, Connect. Never six pieces of code independently deciding what happened.
3. **The Health Graph is the canonical state.** Person → medicines, facts, visits, policies → events →
   Nura State → Home, Ask, feed → actions, explanation, learning. In this repo that is `app.state`
   (`current_state`) made the real choke point: Ask, the Analyst and intake read it; the thirteen
   divergent readers the audit counted (§7.2) collapse into it.
4. **The event protocol is first-class.** One vocabulary, AG-UI-shaped: `RUN_STARTED`,
   `TEXT_MESSAGE_START/CONTENT/END`, `TOOL_CALL_START/ARGS/END/RESULT`, `STATE_SNAPSHOT`, `STATE_DELTA`,
   `RUN_FINISHED`, `RUN_ERROR`. The UI consumes the stream and never knows whether the intelligence came
   from Opus, Sonnet, Haiku, deterministic code, a fixture, the database or search. The orb, the cards,
   the composer and Home's recomposition are all driven from it — **motion represents real state and
   never fakes time.** Adopt the vocabulary, not the library (audit §7.4).
5. **Nura Run is the unit.** `runNura({intent, subject, context})` with intents `understand_paper`,
   `answer_question`, `generate_analysis`, `prepare_visit`, `generate_recommendations`,
   `triage_red_flag`, over the existing streamed routes — one runtime, not six AI systems.
6. **Deterministic decides; AI interprets.** The system alone decides permissions, consent, matching,
   safety gates, escalation, confidence, source validity, scopes, whether a paper belongs to Pa, whether
   a value is confirmed, whether a red flag may be delayed, whether a medicine change is allowed, what is
   clinically safe. The model interprets, summarises, explains, phrases, personalises, and proposes
   recommendation candidates. This is the existing safety architecture, now named as the boundary of the
   runtime.
7. **Four hard gates before the UI scales.** D0 — Profile must not freeze WebKit. D1 — every value Nura
   states traces Answer → Fact → Artifact → confirmed; never "the model remembers 3.8". D2 — whose paper:
   identity extraction → match → confidence → "Is this Pa's report?" → confirm → fact; impossible to
   bypass. D3 — a rejected or corrected AI conclusion is recorded (conclusion, user response, reason,
   timestamp, actor, new state), never thrown away.
8. **Primitives, not bespoke screens.** `NuraOrb, NuraCard, NuraHeadline, NuraComposer, NuraSheet,
   NuraChip, NuraMetric, NuraPaper, NuraMedicine, NuraTimeline, NuraVideo, NuraSource, NuraAction,
   NuraAlert, NuraAvatar, NuraTabBar`; Home = Headline + InsightCard + ReminderCard + FeedCard +
   Composer; Health = SummaryCard + TrendCard + PaperCards; and so on.
9. **The motion system before the screens.** Motion, spring, transition tokens; orb, card, sheet,
   loading, media and reduced-motion states — `experience-blueprint-v2.html`'s `:root` tokens are the
   source of truth.
10. **Three tiers.** Tier 1 (core): scenes 1–8, 15–16, 19–20. Tier 2 (trust and utility): 10, 11, 13,
    17, 18, 21, 24, 25. Tier 3 (advanced): 9, 14, 22, 23, 26. Tier 1 feels right before Tier 2 starts.
11. **Keep the FastAPI backend.** A runtime layer (State, Events, Safety) goes above the existing modules;
    nothing moves to another backend or model provider.
12. **Fixtures emit real events.** `FixturePaperExtractor`, `FixtureMedicineMatcher`, `FixtureSearch`,
    `FixtureCompressor` emit the same stream as the live adapters, so Fixture → Claude is configuration.
13. **Live AI one capability at a time**, each behind its own safety boundary: paper extraction → Ask
    (source-grounded) → medicine extraction + deterministic registry → state recomputation
    (deterministic) → Analyst → feed → voice → multimodal.
14. **Navigation stays thin; interaction happens in context.** Five tabs; a tap expands the object
    ("Your latest blood test is in." → "LDL is 3.8 mmol/L." → what it means → [Prepare for my visit]
    [Ask Nura] [Show the report]) — never Home → Health → Reports → year → month → report → result.
15. **Native after the Home spike.** The RN/Expo vs SwiftUI question is answered on the owner's iPhone
    with the Home spike (`mobile-architecture.md` §5), not philosophically.
16. **The evaluation set exists before the loop is called magical** (operator's addition, accepted): the
    owner's own papers and questions with expected answers, and a pass rate reported on every change.

## Consequences

- The web app's remaining screens are not built on the old seams; web work is limited to engine fixes
  and what the slice needs until the spike decides the client.
- Every builder brief cites this ADR, the event vocabulary, and the gate it must not weaken.
- `build-plan.md`'s package table stays as the record of what exists; the order of new work is this
  ADR's, compressed by the owner into days: **Day 1** — event protocol + Nura Run + fixture events;
  Health Graph step one; D0–D3; the Expo Home spike against the real backend. **Day 2** — the client
  decision on the phone; the golden path (scenes 1–8) on the chosen client. **Day 3+** — Home + Ask +
  medicine connection (the loop), then Tier 2.
- Anything that would need the model to decide a §6 matter is a defect, whatever it passes.
- **The signed build is the extreme last step (owner, 22 Sep 23:30).** Apple Developer + EAS → a
  build on the owner's phone happens only after the entire app works end to end — every Tier 1, 2
  and 3 moment; the register path; papers, Ask, medicines, insurance, feed, Health, not-well, Connect,
  Mei, Profile; the four hard gates; whose-paper and duplicates; reduced motion, accessibility,
  offline; the evaluation set at a pass rate the owner accepts — verified in the iOS Simulator (once
  Xcode is installed) and in Expo Go. No builder may start EAS or signing work before the owner says
  the app is complete. The order of build: 0 Expo/RN locally → 1 Home spike → 2 animation and
  interaction system → 3 connect the FastAPI backend → 4 the golden path (paper → state → Home →
  Ask) → 5 test thoroughly in the Simulator → 6 Apple Developer + EAS, last.
