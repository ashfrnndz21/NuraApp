# Claude Code sessions, in order

Each session is one backlog story or one tightly related group. Start every session in plan mode, name the story ID, and paste the prompt. Approve the plan before Claude writes. Before each PR that touches keys, consent, medicines, reasoning or safety, ask the clinical-safety-reviewer subagent to review and paste its findings.

## Session 0 — orientation, no code
"Read CLAUDE.md, docs/00-MASTER-BUILD-SPEC.md sections 0 and 6, and docs/product-reset.md. Then read docs/feature-backlog.xlsx and list every T1 story in epics E00 and E01 with its acceptance line. Propose the order you would build E00 in and why. Do not write code."

## Session 1 — E00-01, E00-02, E00-07: identity, consent, audit
"Implement Person, Profile, Key, Consent and AuditEntry as SQLAlchemy models with Alembic migrations, plus the key context resolver and the scope check that every repository requires. Registration by phone code and email link as FastAPI endpoints behind a provider interface (no real SMS yet). Tests: a caregiver key with scope [medicines, visits] cannot read notes; the refusal writes an audit entry the owner can list."

## Session 2 — E00-03, E00-04: memory stores and State
"Implement Artifact, Event, Fact (with provenance and confidence, immutable with supersession), the appointments spine, providers, and the State model service that recomputes on any new Fact. Tests: a Fact without provenance is rejected; adding a reading recomputes State and records the trigger."

## Session 3 — E01-01, E01-02 and the doors: proxy setup and claim
"Implement the doors endpoint (for me, for someone, invited), profile creation against a phone number with deduplication, stewardship, and the claim flow that transfers ownership on the patient's OK. Tests: two people cannot create two profiles for one number; claim converts steward to chief key and records consent."

## Session 4 — E02-01, E02-07: photo extraction and the review card
"Implement the ingestion pipeline for a photo: store the Artifact in the profile's region, run extraction behind an interface (fixture extractor for tests), produce a review card with per-field confidence, and on confirm write Facts with provenance. Use docs/medications-module.md section 2 for label parsing. Add the first family's redacted papers as fixtures in backend/tests/fixtures/paper/."

## Session 5 — E04-01 to E04-06: medicines
"Implement drug identification through the licensed client interface (fixture registry), reconciliation (refill, dose change, new line), the interaction check on add, running count and reorder date, and the medication story renderer. Enforce the high-risk drug label rule. Tests per docs/medications-module.md section 9."

## Session 6 — E22-01: plain-words verifier
"Implement app/safety/plain_words.py from docs/plain-words.md: sentence completeness, readability, glossary substitutions, banned words, day-and-date detection, who-does-next check. Wire `make plain-words`. Tests: the glossary examples pass; the fragment examples fail."

## Session 7 — E05-01, E05-02, E05-05, E05-06: the visit loop
"Implement the pre-visit brief, question generation from gaps, memos and flags, the post-visit summary from a transcript, and memo consolidation. Transcript in, memo out, in the profile's language, through the plain-words verifier."

## Session 8 — E21 backend: the feed
"Implement FeedItem, SearchJob, Source with the allowlist, ranking with caps and quiet hours, the supply order (now, today, gate, story, learning) with cursor pagination, and the engagement events endpoint. Compression behind an interface with a fixture. Tests per docs/health-feed-spec.md section 9."

## Session 9 — E19-01 to E19-03: WhatsApp
"Implement the provider interface, the inbound webhook, media fetch, sender-to-Person resolution, the classifier (document, health event, coordination, other), template sending outside the 24-hour window, and the patient Level 0 flow. Tests: a forwarded photo files itself and replies; a health event becomes a proposal needing the poster's confirm."

## Session 10 — iOS foundation
"Generate the Xcode project from project.yml. Implement DesignSystem tokens from docs/design-system.md, the two densities, Sign in with Apple and phone code against the backend, the profile switcher, and the Today shell with the Now card and Taken. Add the medium widget. Follow .claude/rules/ios-patient-mode.md."

## Session 11 — iOS feed
"Implement FeedPagerView, FeedStore with cursor pagination and prefetch, FeedCardView variants, voice playback on tap, the gate card, and the four side actions. Acceptance: no autoplay; the list pages endlessly past the gate; offline launch shows the cached page."

## Session 12 — iOS onboarding
"Implement onboarding from docs/onboarding.html: about you, the dynamic word cloud from a condition graph JSON, read-back with yes and no, assistant-led records, questions from records, gaps and unlocks. Every string through the plain-words check."

Then continue down the T1 backlog in dependency order: capture connectors, emergency card and not-feeling-well, family and roster, push composer, helper list, smart nudges and the feeling cloud, safety review.
