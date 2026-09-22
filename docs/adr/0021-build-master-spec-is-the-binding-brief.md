# ADR 0021 — The Build Master Specification is the binding brief; the signed build is the closing action

**Status:** accepted, 23 September 2026, 00:35 (the owner's document, registered verbatim as
`docs/design/NURA-BUILD-MASTER-SPEC.md`; his instruction: *"ensure that the Apple Developer /
Expo Go step is the last step, and all the AI and interactive app design is consistent to this as
you build"*). Consolidates and takes precedence over `design-build-2.md` §1, `mobile-architecture.md`
§1 and ADR 0019 wherever they differ. ADR 0019's decisions stand where the master spec is silent.

## Decision

1. **`NURA-BUILD-MASTER-SPEC.md` is the brief every builder reads first.** Its 47 sections are the
   contract for the AI runtime (§4–§6, §41–§42), the safety gates (§8, §39, §44), the visual and
   interaction language (§10–§20, §28–§33), the primitives (§34), the structure (§35) and the order
   of build (§38, §43). A brief that does not name the master-spec sections it delivers against is
   not sent. A capture, a stream or a state machine that differs from the section it names is
   rejected, whatever its tests say.

2. **The signed build is the closing action, not a step.** Master spec §3 ("Apple Developer / EAS
   credentials are not a prerequisite… Do not allow signing/distribution setup to block experience
   development"), §38 Phase 5 and §43 step 14 ("only then proceed toward physical-device /
   TestFlight distribution"), read with the owner's rule of 22 September 23:30–23:40 (ADR 0019,
   Consequences): Apple Developer → EAS → a build on the owner's phone → TestFlight happens only
   after the **entire** app works end to end — every Tier 1, 2 and 3 moment, the four gates, the
   evaluation set at the pass rate the owner accepts, `end-to-end-acceptance.md` signed off. No
   builder starts signing, provisioning, EAS or App Store work before the owner says the app is
   complete. **Expo Go is not that step**: it is the development vehicle the master spec's §3
   ("the local Expo … experience") and §38 Phase 1 name for testing the app on the owner's own
   iPhone *before* any signed build, and it stays the phone-testing route until Xcode is installed
   for the Simulator.

3. **Consistency is checked, not assumed.** Every builder — engine or client — is checked against
   the master-spec sections in its row of the table below, in addition to the blueprint-v2 frame,
   the motion lint and the acceptance items already required by ADR 0019.

## Reconciliation — the master spec against what exists (measured 23 Sep 00:30)

| Master spec | What exists on `redesign` | Status |
|---|---|---|
| §3 stack: RN, Expo, TypeScript, Expo Router, Reanimated 4, Gesture Handler, Skia, Zustand; FastAPI kept | `apps/mobile/` Home spike (#325) on exactly that stack; backend unchanged | consistent |
| §4 AI / card / media state machines | `components/ai/AIState.ts`, `ExpandableCard` machine, `MOTION_SYSTEM.md` §3 (#328) | consistent; media machine not yet built (Tier 3, scene 22) |
| §5 event vocabulary, `runNura(intent, subject, context)` | ADR 0019 points 4–5; `backend/app/runtime/events.py` + `run.py` + `POST /profiles/{id}/runs` (Runtime builder, in progress) | consistent; ADR 0019 adds `CUSTOM`, which the spec does not forbid |
| §6 deterministic owns consent, permissions, matching, ownership, confirmation, thresholds, safety gates, escalation, audit, residency; AI owns extraction, summary, explanation, language, candidates | ADR 0019 point 6, verbatim the same boundary; the vetoes in `app/safety`, `app/consent`, `app/keys` | consistent |
| §7 facts: validity window, confidence, source, confirmation state; supersession only | `app/memory` facts (validity + confidence, ADR 0004/0008); review cards hold unconfirmed values | consistent |
| §8 whose paper before facts; Answer → Fact → Artifact → source shown; audit incl. rejections | D2 (Engine B, in progress), D1 (Engine A, PR #327 under review), D3 (Runtime builder) | in progress — the three builders were briefed on exactly these gates |
| §9 scopes RECORDS MEDICINES READINGS VISITS FAMILY MONEY EMERGENCY ASK | `app/keys/scopes.py` has those eight plus NOTES, SEND, PROFILE | consistent (superset); row-scope Walk tests cover every route |
| §9 roles owner / chief / caregiver / grants / only-me / thread / roster; country packs SG, MY | `app/family`, `app/consent`, `config/countries` (SG, MY) | consistent |
| §10–§11 visual language, Figtree + Instrument Serif | `DESIGN_SYSTEM.md` (#328): tokens, measured contrast | consistent; **four pairs miss 7:1** (ink/glass 6.81, soft/glass 5.55, ink/paper 6.07, soft/paper 5.00) — all pass AA; owner decision whether to lift |
| §12 orb: idle / listening / thinking / responding / error, Skia | `IntelligenceOrb` + Canvas, five states, driven only by `AIState` | consistent in behaviour; **name**: spec §34 says `AIOrb`, ADR 0020 kept `IntelligenceOrb` — resolved below |
| §13 Home = greeting → story → insight → reminder → feed → composer, recomposed from state | spike Home is that composition on fixture events; recomposition from the Health Graph is the golden-path builder's work | in progress |
| §14–§15 one Card system; enter 400–600 ms primary, 300–450 secondary, stagger 40–100 ms; press 1 → .985 in 80–120 ms; no large bounce | `NuraCard` variants × tiers; `cardEnter` 520 ms, `pressIn` 100 ms, `scalePress` .985 — consistent; **`staggerCards` is 300 ms** in blueprint v2 and the spike (v2 `--stagger-cards`), against the spec's 40–100 ms; `pressOut` uses `spring.bouncy` | **one owner decision**: keep the 300 ms Home-card stagger he accepted in the v2 demo, or bring it to ≤100 ms per §15. Until he answers, v2's token stands (ADR 0019 point 9) |
| §16 progressive disclosure: card expands → detail emerges; shared element | `ExpandableCard`; `paper/[id]` shared-element route not yet built | golden path |
| §17 composer pill → in place; §18 context-first answers with [Explain] [Show my readings] [Ask something else] | `AIComposer`; Ask engine's context-first shape (`design-build-2.md` §10) | consistent |
| §19 feed: why-am-I-seeing-this, order Now → Today → gate → His story → Learning, quiet 21:00–07:00, two new cards/day, "Not for me" remembered, no treatment change | `feed/rank.py`: `DAILY_CAP` two new cards, `QUIET_FROM/UNTIL` 21:00/07:00, `not_for_me`, the order | consistent — **this closes the "daily cap" question** that was open for the owner |
| §21 medicines: photo / typed / voice later / registry / "Which statin?" / high-risk from the label | Medicines (#313), statin clarify (Engine B); voice not built | consistent; voice = later, as the spec says |
| §22 paper journey incl. real stages, whose paper, batch with per-paper status and duplicates | intake stream; Engine B (whose paper, duplicates); batch queue = Tier 3 scene 9 | in progress |
| §23–§26 visits, insurance passport, not-well, connect / Mei on the same Home template | `app/visits`, insurance essentials (#309), not-well ladder, `app/family`; Mei's Home reuses `home.tsx` | Tier 2 |
| §27 five quiet tabs | `_layout.tsx` five tabs; ADR 0020: extract `BottomNavigation`, read tokens | consistent, one extraction owed |
| §28 sheets: handle, spring, drag, velocity dismissal | `BottomSheet` (spike); thresholds unsourced in `MOTION_SYSTEM.md` | consistent, thresholds to be named as tokens |
| §29 loading / empty / error copy, never technical | `LoadingState / EmptyState / ErrorState` **not built** (ADR 0020 gap) | golden-path builder builds them first |
| §30 motion tokens `motion.* spring.* fade.* scale.press card.enter sheet.enter orb.*` | `motionTokens.ts` exports the same names; `lint-motion.js` rejects literals (not in CI yet) | consistent; lint into `make lint` |
| §31–§32 60 fps, reduced motion, accessibility | `MOTION_SYSTEM.md` reduced-motion mapping; frame-time trace required per builder (`mobile-architecture.md` §4) | measured per delivery |
| §34 primitives | ADR 0020 maps every name; two renames differ from the spec (`AIOrb` → `IntelligenceOrb`, `NuraCard` as the base) | resolved below |
| §35 structure adds `/domain` and `/design/{tokens,motion,typography,colors}.ts` | spike has `components/motion/motionTokens.ts`; no `/domain`, no `/design` | golden-path builder creates `design/` (tokens split by file) and `domain/` (typed models the API client returns) |
| §36 realistic fixtures, Pa and Mei, never lorem | fixtures are the demo patient's real-shaped data | consistent |
| §37 26 scenes; §38 phases 0–5; §43 steps 1–14 | ADR 0019 tiers and the owner's order 0–5 | mapped below |
| §39 D0–D3 as release gates | ADR 0019 point 7 | consistent |
| §41 Opus 5 extraction + Ask; Sonnet 5 analyst, search, estimate, draft; Haiku 4.5 compression, clip, narration; caps enforced; calls audited | `app/llm/models.py` `DEFAULT_MODELS` is exactly that table (ADR 0018); `MAX_JOBS_PER_RUN`, `JOB_DEADLINE_SECONDS`; every call audited | consistent |
| §42 fixture and live adapters emit the same events | ADR 0019 point 12; Runtime builder's contract | in progress |

### Names (spec §34 wins)

The spec's names are the public names. `AIOrb` is exported as the canonical name of the orb
(`IntelligenceOrb` remains an alias until the golden-path builder removes the last import);
`NuraCard` stays the internal base that the spec's card variants compose over, and is not a public
primitive. Everything else in ADR 0020 already matches §34.

### The order of build, mapped

| Owner's order (ADR 0019) | Master spec | Where it stands |
|---|---|---|
| 0 Expo/RN locally | §38 Phase 0, §43 steps 1–5 | done (#325 branch) |
| 1 Home spike | §38 Phase 1, §43 steps 6–8 | on the owner's phone (Expo Go) and web; his verdict pending |
| 2 animation and interaction system | §30, §43 step 5 | `MOTION_SYSTEM.md` + `motionTokens.ts` (#328) |
| 3 connect the FastAPI backend | §43 steps 9 and 11 | Runtime builder (backend); `lib/api` + `lib/ai` = the golden-path builder |
| 4 golden path, then the full app | §38 Phase 2 (§43 step 10), then Phases 3–4 (step 12) | next, after the verdict |
| 5 test everything | §38 Phase 5, §43 step 13, `end-to-end-acceptance.md` | last build stage |
| — closing action — | §3, §43 step 14: Apple Developer → EAS → phone → TestFlight | **only after 5 is signed off** |

## The design is baked into every builder — extended for the master spec

| Builder / step | Master-spec sections the brief must name | Checked against |
|---|---|---|
| Runtime (backend) | §4, §5, §6, §7, §8 (audit), §39 D3, §41, §42 | event tests; fixture and live streams byte-compatible; Opus review for §6 |
| Engine A (D0/D1) | §8 (source grounding), §18, §29 (errors), §39 | Opus review; A-074…A-090 |
| Engine B (D2) | §8 (paper identity), §21 (class disambiguation), §22, §39 | captures vs v2 frames 05–07; Opus review; A-040…A-062 |
| Golden path (client) | §1, §2, §4, §10–§18, §20, §22, §27–§36, §38 Phase 2, §44, §45 | v2 frame per scene; both engines; frame-time trace; reduced motion; A-010…A-106; the §45 quality gate answered in the report |
| Tier 2 / Tier 3 builders | the scene's own section (§19, §21, §23–§26) + §29, §44, §45 | same |
| Acceptance / release | §38 Phase 5, §39, §43 step 13; then and only then step 14 | the sign-off sheet |

## Consequences

- Every brief opens with: "Read `docs/design/NURA-BUILD-MASTER-SPEC.md` first; you deliver
  §…; do not replace a contextual interaction with a conventional screen because it is easier
  (§43, §44)."
- The §45 quality gate is answered, question by question, in every builder's report; "not
  applicable" is an answer, silence is not.
- Two owner decisions are opened by this reconciliation: the Home-card stagger (300 ms accepted in
  v2 vs §15's 40–100 ms) and the four contrast pairs under 7:1. One is closed: the two-new-cards-a-day
  cap is already the engine's rule (§19).
- `mobile-architecture.md` §5 and ADR 0019 point 15 are read with §38 Phase 1: the Simulator
  requires Xcode, which this Mac does not have; until it is installed, Expo Go on the owner's iPhone
  and the web target are the spike's judges.
