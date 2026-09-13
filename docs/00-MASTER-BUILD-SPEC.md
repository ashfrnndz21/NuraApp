# Nura — master build specification, v1

**Name.** Nura: a blend of "nurture" and "aura", with "nur" (light) underneath. Two soft syllables, non-clinical, the same in every language the family speaks. Nura is the app, the WhatsApp number and the assistant's voice: "Nura says the water pill is at 8."

This is the one document to start from. It consolidates everything designed in this work into the scope, architecture and plan for the first build. Where a topic has its own detailed document or prototype, this file says what it is and points to it; it does not repeat it.

---

## 0. The pack: what to read, in what order

**Read first**
1. `product-reset.md` — identity model, registration, the three doors, one app with a profile switcher, the end-to-end journey.
2. `elderly-experience.md` — the five moments, four levels of surface, the test for anything new.
3. `design-for-the-absent-user.md` — why nobody opens it daily and how it works anyway; metrics; business model.
4. `plain-words.md` — the writing standard for everything the patient reads or hears.
5. `system-map.html` — every feature (131), its layer, what feeds it and what it enables; thirteen traced scenarios. This is the architecture, interactive.

**Feature specifications**
- `stage1-product-design.md` — personas, State model, hooks, probe/plan/push, the fourteen modules.
- `medications-module.md` — photo-first medicines: inference chain, counts, reorders, safety rules.
- `experience-and-feed-engine.md` — upload flow, search, self-search jobs, compression, ranking.
- `health-feed-spec.md` — the vertical feed: card types, pipeline, data model, API, iOS build, acceptance.
- `smart-nudges.md` — eight nudge kinds, the feeling cloud, stickiness, what is refused.
- `gaps-and-unlocks.md` — missing-context cards, catalogue, cadence and stop rules.
- `whatsapp-agent.md` — what the agent can see, the group and private threads, platform rules, classifier, guardrails.
- `read-only-connectors.md` — email, photos, calendar, SMS, WhatsApp export: what can be read, the allowlist design, compliance.
- `design-system.md` — tokens, glass and paper, state washes, type, components, accessibility.

**Prototypes (open in a browser)**
- `onboarding.html` — sign-in, about you, dynamic word cloud, read-back, records with the assistant, questions from records, gaps and unlocks, ready.
- `setup-bind-probe.html` — set up the patient, bind family with scoped keys and consent, a bound caregiver probing.
- `prototype.html` — the full click-through for patient, caregiver and helper.
- `reduced-app.html` — the three-tab patient app.
- `feed-vertical.html` — the full-screen vertical feed with the gate and evergreen supply.
- `health-feed.html` — where the feed lives for patient and caregiver.
- `feeling-cloud.html` — the state-conditioned check-in and the week's nudges.
- `doctor-memo.html` — before, during and after a visit; the patient's three cards.
- `appointment-planner.html` — bring forward, add, sequence, with reasons; re-planning from a feeling.
- `whatsapp-agent.html` — the family group and the chief's private thread.
- `ui-mockup-v2.html` — feed-first Today, the add-and-organise flow, ask-or-find.

**Brand**
- `nura-brand/BRAND.md` — the mark (open heart of two halves), files, colour, sizes, motion, voice name. SVGs and PNG exports at every iOS icon size in `nura-brand/`.

**Planning**
- `feature-backlog.xlsx` — every story with epic, persona, tier, priority, size, dependencies, acceptance.
- `build-plan.md` — team, stack, licences, Apple requirements, regulatory, phases, money, risks.
- `research report` (from the extended research) — competitive teardown, PMF evidence, moats, positioning.

---

## 1. What we are building

A health chief of staff for one person and the family around them. It holds the messy record (photos, PDFs, handwriting, recordings, readings), works out the person's state, prepares every visit, keeps the family in the loop with scoped keys, and speaks to the patient in plain words in his language. It is quiet most days and flawless on the four days a year that matter: the visit, the discharge, the new medicine, the bad day.

**Principles that outrank features**
- The patient never sees features; he sees five moments (morning, a feeling, a visit, something for him, not feeling well).
- Most days nobody opens it, and it still works.
- Plain is not clipped: whole sentences a daughter would say out loud.
- One thing at a time; the same shape every day; voice both ways; nothing he has to resolve; presence, not surveillance; dignity.
- Nothing infers without provenance; nothing renders without State; nothing changes a medicine or books anything without a confirm.
- The boundary: organises, prepares, surfaces patterns to discuss; does not diagnose or treat.

---

## 2. Identity

Three objects. **Person** registers (phone code, email link, Apple, Google; no passwords) and owns at most one **Profile** (the health graph, exactly one owner, stewarded until claimed) and holds any number of **Keys** (role, scope, window, basis, audit). After registration: for me / for someone I care for / I was invited. Proxy setup creates a profile against the patient's number; his WhatsApp "OK" claims it. Deduplicated by phone number. Scope enforcement is one module beneath every read. Four surface levels per profile: WhatsApp only, one screen, three tabs, full.

---

## 3. Scope by tier

**T1 — weeks 0–12, the daily loop (the first build)**
Registration and doors; proxy setup and claim; onboarding (about you, word cloud, read-back, assistant-led records, questions from records, gaps and unlocks); capture from photo, handwriting, PDF, screenshot, device screen, Share Extension, WhatsApp forward; consult recording with consent; capture review card; memory stores with provenance; appointments spine; providers directory; what-changed diff; ask over the record with recall and clips; medicines from the bag with reconciliation, interaction check, counts, reorder, medication story, missed-dose guidance; the visit loop (brief, questions, logistics, recording, summary, memo) and the Doctor Memo before/during/after; State model; lab trends; feeling cloud and feeling inference; symptom log; smart nudges (eight kinds, caps, escalation ladder); triggers and reminders; the vertical feed with text and voice cards, the gate, story and learning supply; card grammar; voice notes in English, Malay, Mandarin; keys, consent, audit, family thread, roster, push composer; emergency card offline and on the Lock Screen; not-feeling-well flow; WhatsApp mirror for the patient and helper list; photos scan and calendar connectors; design system with patient and caregiver density; localisation framework; boundary copy, high-risk drug rule, recording consent pattern, SaMD boundary review, PDPA data map; in-region hosting; licensed drug database; audit and observability.

**T2 — weeks 12–24, the clinical loop**
Polypharmacy review (Beers, STOPP/START) as talking points; discharge reconciliation and thirty-day watch; coverage, insurance letters, claims, ledger; doctor share link and second-opinion packet; appointment planner; email connector with sender allowlists; WhatsApp family health group (if supported in market); pill and receipt identification; recount photo; helper given-taps; dose-change proposals from recordings; refill queue; fasting and festive shifts; cross-signal correlation and pattern flags; food verdict; screening and vaccination schedule; body-systems map; photo timelines; format feedback; export and deletion; connector rules.

**T3 — weeks 24–36, navigation and media**
Care navigation with drafted messages; cost expectation; thirty-second clips and compressed video; weekly recap; mobility and falls; seasonal alerts; caregiver load view; incapacity and handover; advance care planning; SMS on Android; generic price comparison; chat export import.

---

## 4. Architecture

Twelve layers, as in the system map: identity and access → onboarding and context → capture → memory → State → reasoning → search and jobs → delivery → channels → family → safety → platform. Two structural facts: State is the choke point (nothing renders without it), and scope enforcement sits beneath every service. The safety layer is an input to reasoning, not a disclaimer on top.

**Deployment.** One backend per country (Singapore, Malaysia), profiles pinned to a region, per-profile encryption keys. Native iOS client. WhatsApp via the Business Platform through a provider. Managed agent runtime and memory for the reasoning loops.

**Data flow for the common case.** Artefact in (photo, PDF, message, reading) → extraction with confidence → review card → facts with provenance → State recompute → reasoning (trends, reconciliation, questions, flags) → search jobs where warranted → cards ranked and capped → delivered to the surfaces the profile uses → engagement back into State.

---

## 5. Data model

Person, Profile, Key, Consent, AuditEntry; Artifact, Event, Fact (with provenance and confidence), Episode, Appointment, Provider, Medication (reconciled line with source), Policy; State (six dimensions); Card / FeedItem, SearchJob, Source, Engagement; Memo; Gap; Nudge; Plan (appointment planner recommendations); WhatsAppThread and GroupBinding.

Every Fact links to at least one Artifact or Event. Every Card links to the State it was rendered from. Every read writes an AuditEntry.

---

## 6. Services

| Service | Owns | Key rules |
|---|---|---|
| Identity and keys | Registration, OTP, claim, stewardship, key issuance, scope enforcement | Scope check on every read; keys expire; consent versioned |
| Ingestion | Photo, handwriting, PDF, screenshot, voice, device, connectors; extraction; review cards; dedupe | Confidence per field; nothing stored silently; batch match for packs |
| Memory | Episodic, semantic, working; spine; providers; index; provenance | Facts immutable with supersession; recall returns the artefact |
| State | Six dimensions recomputed on change | Single input to delivery; wash and density derive from it |
| Reasoning | Trends, correlation, flags, medication logic, questions, brief, summary, memo, discharge, planner, feeling inference, gap detection, triage | Licensed drug data; clinician framing; suppress flags on missing facts; red flags bypass planning |
| Search and jobs | Ask, find, act; self-search jobs; allowlist; compression; verify | Uncited output rejected; treatment-changing content rerouted as doctor questions |
| Delivery | Feed ranking, card grammar, voice, clips, triggers, caps, escalation, nudges, push composer | Two smart nudges a day; quiet hours; escalation to the roster |
| Channels | App surfaces, WhatsApp threads and group, share links, widgets, printables | Level per profile; templates outside the 24-hour window |
| Family | Roster, thread, digests, load, handover | Presence lines, not reports |
| Consent and audit | Consent records, audit log, owner visibility | Refusals visible; "only me" honoured |
| Content | Plain-words verify, glossary, translation, voice synthesis | Every patient string passes the standard |

---

## 7. iOS app

**Targets.** iOS 17 minimum; iOS 18 for MeshGradient washes; iOS 26 features (glass effect, on-device models) when available.

**Modules.** Identity (Sign in with Apple, Google, email link, phone OTP; Keychain; profile switcher). Onboarding (word cloud, read-back, records, gaps). Capture (VisionKit document camera, Vision text recognition, PhotosPicker, Share Extension, Speech, AVFoundation recording with consent prompt, HealthKit read). Feed (vertical pager, FeedStore, SwiftData cache, BGAppRefreshTask, silent push, AVQueuePlayer with captions, voice playback). Medicines (list, story, Taken, reorder). Visits (Doctor Memo before/during/after, questions card, planner). Ask (App Intents, Siri, voice-first sheet). Family (keys, roster, thread, push composer with preview). Safety (emergency card widget and printable, not-feeling-well flow). Settings per profile (level, language, voice speed, quiet hours, what he's shown).

**Surfaces.** Patient levels 1–3: one screen, three tabs (Today, Ask, Me), full. Caregiver: Today for the profile, Ask, the profile's name tab with sheets. Widgets: medium (Now with Taken), Lock Screen (emergency card). Live Activity on visit day (T2).

**Constraints.** Patient mode: vertical paging only, no horizontal gestures, no pull-to-refresh, no long-press, no badges, 20pt body, 56pt targets, 7:1 contrast, every card has a spoken twin, works inside Assistive Access. No autoplay of the next card. Offline: today's list, the emergency card, the last feed page.

---

## 8. WhatsApp service

Business number per country via a provider; private thread per key holder (phone number is identity); a dedicated family health group with the agent as a member where the platform supports it, else forwarding with in-thread replies. Templates for everything proactive; free-form replies within the 24-hour window. Classifier keeps documents and health events only; events become proposals confirmed by the poster; "ignore" honoured; red flags escalate immediately. Helper list in her language with given-replies. The patient's Level 0 lives here entirely.

---

## 9. Content standards

**Brand.** The mark is the open heart of two halves (`nura-brand/`): plum left stroke and dot, aura right stroke, an opening at the bottom. App icon on the wash; plum for dark mode and the Lock Screen; the speaking heart as the WhatsApp avatar. Wordmark "nura" in Outfit Medium. Rules in `BRAND.md`.

Plain words (`plain-words.md`): whole sentences, one idea per line, his names for things, day and date, who does the next thing, the small reassurance, no red words, nothing to decode, the same words every time. Card grammar: one number, one direction, one colour, one action, a why line, a source. Design system: glass for chrome, paper for decisions, the wash is the status, Outfit with weight as the persona dial, one plum button per screen, coral only for not-feeling-well.

---

## 10. Safety, regulatory, privacy

The boundary line on every inferring surface. Licensed drug and interaction data; the model writes the sentence, never the pharmacology. High-risk drugs need a label photo. Red flags from the patient's own discharge plan and conditions; they bypass planning and go to the same-day path. SaMD review (HSA, MDA) before any flag ships: guideline-referenced, non-real-time, informational. PDPA in both countries: explicit consent at claim and per key, data map, DPO, breach runbook, portability, deletion, in-region hosting. Recording consent pattern reviewed by counsel. Connectors: purpose-bound, allowlisted, shown before stored, third parties dropped, nothing trains anything. App Review: health data handling, privacy manifest, medical-accuracy guideline, the listing describes the boundary.

---

## 11. Integrations and licences

Drug identification: NPRA and HSA registers plus a licensed Asia-coverage database. Interactions: a licensed database. Criteria: Beers, STOPP/START. Monographs: licensed or pharmacist-written for the top sixty drugs. Speech: English, Malay, Mandarin via cloud; Hokkien and Tamil as a research item with recorded voice fallback. WhatsApp Business Platform via a provider. Google OAuth verification and security assessment for Gmail; Outlook and IMAP first. Insurer panel lists scraped and verified for v1.

---

## 12. Quality

**Test set.** Real Malaysian paper from the first family: the medicine bag, a discharge letter, three lab reports, a clinic slip, a pharmacy receipt, an insurance card. Extraction accuracy measured weekly from week one.

**Acceptance for T1 (selected).** A bag photo becomes a reconciled list with sources and an interaction check before the first dose. A lab photo becomes a trend and, within ten minutes, an explainer card with a voice note. A consult recording becomes a summary in the patient's language the same day and a memo in his words. A six-month-old profile shows "what changed" correctly after eleven days of no opens. A key holder outside scope gets a visible, polite refusal and the owner sees the audit entry. The patient's feed never autoplays, never exceeds two new cards a day, and never shows a source off the allowlist. Every patient string passes the plain-words check. The emergency card opens with no network.

**Metrics.** Readiness (medicines reconciled in ninety days, next visit on the spine, emergency card complete, a key holder active); peaks served; background yield; return cost; check-in taps; nudge acceptance by kind; retention at month six for the paying family.

---

## 13. Team and timeline

**Team.** iOS lead; backend and agent engineer; product designer; pharmacist part-time; you as product owner and first family. Second mobile engineer from week 8 if the patient cohort is on Android. Six people to the App Store.

**Milestones.**
- Week 0–2: foundations — repo, CI, tokens in Swift, Figma from the prototypes, identity and keys service, schema, regions, licences applied for, WhatsApp verification started, pharmacist engaged, test set built.
- Week 8: first family on TestFlight with the T1 daily loop.
- Week 14: five families; consult recording and the Doctor Memo hardened; simple mode inside Assistive Access.
- Week 20: App Store submission with the boundary review complete; T2 clinical loop in.
- Week 24: channel pilot signed (insurer or hospital group) or the decision to pivot to embedded.
- Week 36: T3 navigation and media.

---

## 14. Risks that decide the outcome

Ingestion quality on real handwritten paper (measure from week one). The patient's actual phone (decides iOS versus WhatsApp-first for him). Drug data licence lead times. Consent and stewardship edge cases (counsel early). Alert fatigue in the caregiver (caps and escalation are T1 features). WhatsApp group support availability (design the forwarding fallback regardless).

---

## 15. Decisions to close before week 2

1. Launch market: Malaysia first, Singapore second, or both? (Affects regions, registries, insurer lists.)
2. The first patient's phone and therefore his level (0 or 1).
3. Which drug database and interaction vendor.
4. Stewardship basis when the patient cannot consent and there is no LPA.
5. Whether email launches with Outlook/IMAP only while Google verification runs.
6. Who pays in the pilot: the family, or a channel partner from day one.

---

## 16. What we do now

This week:
- Photograph the first family's papers and medicine bag; that is the test set and the first health biography.
- Open the Apple Developer organisation account and the AWS accounts in both regions.
- Request quotes and terms from a drug database vendor and an interaction database vendor.
- Start WhatsApp Business verification with a provider; draft the six templates.
- Engage a pharmacist for four hours a week; give them `plain-words.md` and the first fifty patient strings.
- Turn `design-system.md`, `reduced-app.html`, `feed-vertical.html`, `onboarding.html` and `doctor-memo.html` into a Figma file.
- Hire or assign the iOS lead and the backend engineer; their first ticket is the identity-and-keys service and the schema, because everything else depends on it.

Then run the T1 backlog in order: identity → capture and review card → memory and State → medicines → the visit loop → feed and nudges → WhatsApp → family → safety. Ship to the first family at week eight and let them break it.
