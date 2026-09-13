# What it takes to build this as an iOS app

A concrete plan from the current design to a family on TestFlight and then the App Store. Assumes Malaysia and Singapore first, English, Malay and Mandarin at launch, and the reduced v1 scope from the product reset.

---

## 1. The team

| Role | Why | When |
|---|---|---|
| iOS lead (SwiftUI, HealthKit, widgets, Live Activities) | The client is native and the elderly-mode work is fiddly | Week 0 |
| Backend and agent engineer (Python or TypeScript, AWS) | Ingestion, memory, State, feed, WhatsApp | Week 0 |
| Product designer (mobile, accessibility) | Turns the HTML references into a real design system and Figma | Week 0 |
| Clinical advisor, part time (a pharmacist first, then a GP) | Medication rules, plain-language content, the safety boundary | Week 2 |
| Second mobile engineer (Android or shared) | Only if the patient cohort is on Android, which in Penang it will be | Week 8 |
| You | Product owner, the account network for the channel pilot, first family | Throughout |

Four people to the first family on TestFlight. Six to the App Store.

---

## 2. The stack

### iOS client
- Swift 6, SwiftUI, iOS 17 minimum (iOS 18 for MeshGradient and the newer widget APIs; iOS 26 for the glass effect and on-device Foundation Models, used when available).
- Frameworks: HealthKit (readings from Bluetooth cuffs, glucometers, scales via Health), VisionKit and Vision (document capture, text recognition), Speech and AVFoundation (voice in, voice out), App Intents (Siri and Shortcuts for Ask), WidgetKit and ActivityKit (Home Screen widget, Lock Screen emergency card, visit-day Live Activity), UserNotifications with time-sensitive interruption level for doses, Share Extension for "Add to record" from Photos, Files and WhatsApp.
- Accessibility: Dynamic Type through accessibility sizes, VoiceOver, Reduce Motion, and Assistive Access compatibility for simple mode.
- Local: SwiftData or GRDB for the offline cache (today's list, emergency card, last cards), CryptoKit for the local store, Keychain for tokens.
- Auth: Sign in with Apple, Google, email magic link, phone OTP; passkeys when the backend supports them.

### Backend, on AWS
- Region: ap-southeast-1 (Singapore) and ap-southeast-5 (Malaysia) for residency; one deployment per country, profiles pinned to a region.
- Identity: Cognito or Auth0 for accounts; keys and scope enforcement are your own service, one module, called by every read.
- Agent runtime and memory: Bedrock AgentCore (Runtime for the agent loops, Memory mapped to episodic and semantic stores, Gateway for tools, Identity for per-profile credentials). Models via Bedrock (Claude for reasoning and plain-language rendering; a vision-capable model for documents).
- Ingestion: Textract for printed and handwritten extraction, a vision model for labels and pill photos, Transcribe for consult recordings (English, Malay, Mandarin), your own extraction prompts producing facts with confidence and provenance.
- Data: Aurora PostgreSQL for the graph (Person, Profile, Key, Event, Fact, Consent, Audit), S3 with per-profile KMS keys for artefacts, OpenSearch for recall and search, EventBridge and Step Functions for State recomputation and self-search jobs.
- Delivery: a feed service that ranks cards from State; Polly for voice notes (English, Malay, Mandarin); a clip renderer later.
- WhatsApp: Meta's Cloud API through a business solution provider; approved message templates for reminders; inbound webhook for forwards and replies.
- Observability: every card and flag logged with the State it came from; every read logged to the audit table.

---

## 3. Licences and integrations you cannot build around

| Need | Option | Note |
|---|---|---|
| Drug identification and local brands | Malaysia NPRA product register and Singapore HSA register (public); MIMS or an equivalent Asia-coverage database (licence) | Registration numbers on packs are the key |
| Interactions and dosing | A licensed interaction database (DrugBank, FDB, Lexicomp) | Never the model's memory; budget for this early |
| Deprescribing criteria | Beers (AGS) and STOPP/START | Open, versioned |
| Patient-information monographs | Licensed, for missed-dose and food guidance | Or written by your pharmacist for the top 60 drugs first |
| Speech in Hokkien and Tamil | No mainstream cloud service covers Hokkien well; Tamil is partially covered | Launch English, Malay, Mandarin; Hokkien via recorded family voice and a specialist vendor as a research item |
| WhatsApp Business | A BSP such as Twilio or 360dialog; Meta business verification; template approval | Two to four weeks of lead time |
| Insurer panel lists | Public PDFs per insurer, or a partnership | Scrape and verify for v1; partner for scale |
| Records in SG/MY | No consumer API from NEHR or MySejahtera | All ingestion is photo, PDF and screenshot for now |

---

## 4. Apple requirements

- Apple Developer Program, an organisation account, and an App Store Connect team.
- HealthKit entitlement and a published privacy policy; HealthKit data never leaves the device without explicit consent and never goes to third parties.
- Privacy manifest and nutrition labels declaring health data, contacts, photos, microphone, camera.
- App Review guidelines that bite here: medical accuracy (1.4.1), data collection and consent (5.1.1), health data handling (5.1.3), and the line that apps behaving as regulated medical devices need regulator approval. The stated boundary — organises, prepares, surfaces patterns to discuss, does not diagnose or treat — is what keeps you on the right side, and it must appear in the app and the listing.
- TestFlight for the family pilot; up to a hundred internal testers without review, ten thousand external with a light review.
- Background modes for audio (consult recording) and remote notifications; Family Sharing not needed.

---

## 5. Regulatory and data

- **Singapore (HSA):** keep inference guideline-referenced, non-real-time and informational; document the boundary review before any flag ships. **Malaysia (MDA):** the same, with attention to the Class B line for software that influences treatment decisions.
- **PDPA in both countries:** explicit consent for health data at claim and at every key; data map; breach runbook; a named data protection officer; portability and deletion.
- **Consult recording:** doctor notified aloud or by printed notice; consent stored with the recording; reviewed by counsel in both countries.
- **Stewardship basis:** define what is acceptable when the patient cannot consent (LPA, medical letter, recorded verbal consent) before the first proxy setup ships.

---

## 6. Phases

**Weeks 0–2 — foundations.** Repo, CI, design tokens in Swift, Figma from the HTML references, account and key service, schema, region setup, licences applied for, WhatsApp verification started, pharmacist engaged.

**Weeks 2–8 — the daily loop (T1).** Registration and three doors, proxy setup and claim, onboarding with the word cloud and gaps, photo and PDF ingestion with review cards, medicine list from the bag with Taken and reorder, Today with one thing and two cards, Ask over the record, emergency card and widget, not-feeling-well, keys and audit, WhatsApp mirror and helper list. Your family on TestFlight at week 8.

**Weeks 8–14 — harden and learn.** Fix what the family breaks. Consult recording and the visit loop. Format feedback. Offline. Simple mode inside Assistive Access. Second family, then five.

**Weeks 14–24 — the clinical loop (T2).** Polypharmacy talking points, discharge watch, insurance letter tracking, cost ledger, doctor share link, second-opinion packet, device sync. App Store submission around week 20 with the boundary review done. Channel pilot conversation with an insurer or hospital group runs in parallel from week 10.

**Weeks 24–36 — navigation and media (T3).** Care navigation, clips, cost expectation, Android if the cohort demands it.

---

## 7. Money, roughly

- People: four to six for nine months is the real cost.
- Apple: the developer programme is nominal.
- AWS: low thousands a month for a pilot; model calls dominate; per-profile KMS keys are cheap.
- Licences: the drug and interaction databases are the largest line after people; get quotes in week 1.
- WhatsApp: per-conversation pricing; trivial at pilot scale.

---

## 8. Risks that decide the outcome

1. **Ingestion quality on real Malaysian paper.** Handwritten prescriptions and clinic slips are the moat and the risk. Build the labelled test set from your own family's papers in week 1 and measure every week.
2. **The patient's phone.** If he's on an old Android, iOS-only means WhatsApp is his app. Decide by looking at his phone, not by preference.
3. **Drug data licensing lead time.** Start the conversations before the code.
4. **Consent and stewardship edge cases.** One bad case here ends the product; get counsel's view early.
5. **Alert fatigue in the caregiver.** The escalation ladder and caps are product features, not settings; ship them in T1.

---

## 9. This week

- Look at your dad's phone and his medicine bag. Photograph the bag, the last discharge letter, three lab reports and a clinic slip: that's the first test set.
- Open the developer account and the AWS accounts in both regions.
- Ask MIMS and one interaction-database vendor for pricing and terms.
- Start WhatsApp business verification.
- Brief a pharmacist for four hours a week.
- Turn the reduced-app and onboarding HTML into a Figma file with the tokens from design-system.md.
