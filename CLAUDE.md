# Nura — instructions for Claude Code

## What this is
A family health app for Malaysia and Singapore: an elderly patient, the adult child who runs his care, a domestic helper on WhatsApp, and a clinic that only receives. The full specification is in `docs/00-MASTER-BUILD-SPEC.md`; read its section 0 before any non-trivial task. The interactive architecture is `docs/system-map.html` (131 features, 12 layers, dependencies).

## Non-negotiables (apply to every change)
- Scope enforcement lives in one module (`backend/app/keys/`) and every read of profile data goes through it. Never query profile data without a key context.
- Nothing infers without provenance: every Fact links to an Artifact or Event; every Card records the State it was rendered from.
- Nothing changes a medicine, books anything, or sends anything without an explicit confirm from a person.
- The boundary: Nura organises, prepares and surfaces patterns to discuss; it does not diagnose or treat. No code path may output advice to start, stop or change a medicine; reroute as a question for the doctor.
- Licensed drug data only for identification, interactions and dosing. The model writes the sentence, never the pharmacology.
- Every string the patient sees or hears passes `docs/plain-words.md`. See `.claude/rules/patient-strings.md`.
- Patient mode: one thing per screen, no horizontal gestures, no pull-to-refresh, no badges, no autoplay of the next card, 20pt body, 56pt targets, 7:1 contrast, every card has a spoken twin.
- Profiles are pinned to a region (SG or MY). Health data never leaves its region. No analytics vendor receives health data.
- Nothing trains on user data.

## Working style
- Start every task in plan mode. Read the relevant spec section and the backlog row (ID in `docs/feature-backlog.xlsx`) before proposing changes.
- One backlog story per branch. Branch name `E04-03-short-slug`. Commit messages start with the story ID.
- Write the test first when the story has an acceptance line; the acceptance line is the test.
- Ask before adding a dependency. Prefer the standard library and what is already here.
- When a patient-facing string is added or changed, run `make plain-words` and include the output in the PR description.
- When a change touches keys, consent, audit, medicines or anything under `backend/app/safety/`, ask the `clinical-safety-reviewer` subagent to review before finishing.
- Never delete data migrations. Never store identity-card numbers outside the insurance module, and only when a guarantee letter needs one.

## Commands
- Backend: `make dev` (run), `make test`, `make lint`, `make plain-words`; `make checkpoint N=<n>` walks a checkpoint from `docs/checkpoints.md` against the running server, `make reset-db` starts the local database over.
- iOS: `cd ios && xcodegen generate`, then open `Nura.xcodeproj`; `make ios-test` runs `xcodebuild test` on the simulator. Builds require Xcode on macOS.
- Infra: `cd infra && cdk synth`.

## Layout
- `backend/app/identity`, `keys`, `consent`, `audit` — Person, Profile, Key, Consent, AuditEntry.
- `backend/app/ingestion` — photo, PDF, handwriting, voice, device, connectors; review cards.
- `backend/app/memory` — episodic, semantic, working; spine; providers; index.
- `backend/app/state` — the six-dimension State model.
- `backend/app/reasoning` — trends, medicines, questions, brief, summary, memo, planner, feeling inference, gaps.
- `backend/app/search` — ask, find, act; jobs; allowlist; compression.
- `backend/app/delivery` — feed ranking, cards, voice, triggers, nudges, escalation.
- `backend/app/channels` — app API, WhatsApp, share links.
- `backend/app/safety` — boundary copy, high-risk drug rule, red-flag rules, plain-words verifier.
- `ios/Nura/` — Identity, Onboarding, Capture, Feed, Medicines, Visits, Ask, Family, Safety, Settings, DesignSystem.

## Domain vocabulary
Person, Profile, Key, Consent, Artifact, Event, Fact, Episode, Appointment (spine), Provider, Medication line, Policy, State, Card/FeedItem, SearchJob, Source, Memo, Gap, Nudge, Plan. Use these names in code. "Pa" and "Ash" are example people in the docs, never identifiers in code.
