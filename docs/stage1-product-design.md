# Nura — Stage 1 product design

Working title only. Scope: the direct-to-consumer product for an elderly patient in Malaysia/Singapore and the adult child who runs his care. Everything here is designed now; the tier column says when it ships inside Stage 1.

Tiers: **T1** = first build (weeks 0–12, the daily loop). **T2** = weeks 12–24 (the clinical loop). **T3** = weeks 24–36 (navigation and media). All three are Stage 1.

---

## 1. Who we serve

Five people touch the product. Two are primary. Everything is personalised against the person it is rendered for, not the account that pays.

| Person | Role in the product | What they need | Surface |
|---|---|---|---|
| **Dad — the patient** | Owns the health graph. The person every artefact is rendered for. | To not be scared, not be nagged, remember what the doctor said, know what to do today, and be able to answer the doctor's questions. | Voice-first. WhatsApp first, app second. Large type. His language. |
| **Ash — the chief** | Runs the care. Has the broadest grant. | To probe Dad's state without calling him, plan his week, push him simple instructions, catch things early, and stop carrying it all in his head. | Full app on phone and web. Notifications digested, not streamed. |
| **Co-caregivers** — siblings, spouse | Scoped grants. Share the load. | To know what changed, take assigned tasks (drive, refill, sit in the visit), and not duplicate Ash. | App, WhatsApp group thread. |
| **The domestic helper / live-in carer** | Administers medicines and meals in many MY/SG households. Missed in every competitor. | A tiny surface: today's medicine list with photos, "given" taps, a way to flag "he is not well." No access to history. | WhatsApp only, in her language (Bahasa Indonesia / Tagalog / Burmese). |
| **The clinic** — doctor, nurse, pharmacist | Never logs in. Receives. | A one-page brief before the visit, a medication list they trust, a clean packet for a second opinion. | Share link, PDF, printed page. |

Secondary segments (busy professionals managing their own chronic condition, the sandwich generation managing both parents and children) are served by the same architecture with a different default surface. They are not designed for separately in Stage 1.

---

## 2. Personalisation: the State model

Everything the product shows is rendered from the person's **State**, which the reasoning layer recomputes continuously and stores in working memory. State is the single input to ranking, format, language, cadence and escalation.

**Clinical state** — active conditions and their control status (stable / watch / act), current medications, last labs and direction, open episodes, recent discharge, allergies.

**Functional state** — mobility, falls history, vision, hearing, dexterity (can he tap? can he read a 14pt card? does he need voice?).

**Cognitive and literacy state** — reading language, spoken dialect, health literacy level, memory support needs. Set by Ash at onboarding; adjusted by observed behaviour (does he open text or only voice notes?).

**Situational state** — pre-visit (T-7 to T-0), in-visit, post-visit (T+0 to T+3), post-discharge (T+0 to T+30), unwell today, travelling, fasting.

**Preference state** — his own goals in his words, what he has agreed to, what he has said no to, how many nudges he tolerates, who he wants told what.

**Family state** — who has which grant, who is on duty this week, who to escalate to and how.

Rule: a card is not shown, a clip is not generated and a nudge is not sent unless the State justifies it. "Why am I seeing this" is always available on the artefact.

---

## 3. Dad's hooks — what gets him to engage

Principles first, because the failure mode is well documented: consumer health apps for the elderly die from setup burden, nagging, and dashboards.

1. **Zero setup.** Dad never configures anything. Ash sets up; Dad receives.
2. **Reach him where he already is.** WhatsApp is the primary surface. The app is for when he wants more. Voice is always an option.
3. **Presence, not surveillance.** He should feel his children are *with* him, not watching him. "Ash saw your reading" reads as care; "Ash has been notified of a missed dose" reads as a report card.
4. **Immediate personal payoff.** Every interaction gives him something back about *him* within seconds.
5. **Dignity.** Never scold. Celebrate quietly. He owns the data and can say "don't share this."
6. **One thing at a time.** One card, one number, one action. If it needs a chart, it is two cards.

The hooks, ordered by how often they fire:

| Hook | Cadence | What it is | Why it works |
|---|---|---|---|
| **The morning card** | Daily, fixed time tied to breakfast | One card in his language: today's medicines, one thing to do, anything coming up. Voice note version auto-sent on WhatsApp. | Ritual anchored to an existing habit. Zero decisions. |
| **"Taken" tap** | Per dose | Medicine name, photo of the pill, one button. Helper can tap it for him. | Smallest possible action; feeds the adherence loop the family relies on. |
| **Food snap with a personal verdict** | Any meal | Photo → "Salt is high for your pressure, lighter dinner tonight." Tags the systems it touches. Never a calorie lecture. | Instant, personal, slightly playful. Works at the kopitiam. |
| **"Ask me"** | Whenever | He speaks Hokkien or Malay; gets an answer grounded in his own record: "When did I last see Dr Tan?" "What did he say about the water pill?" Plays the clip if there is one. | Recall is the thing the elderly most want and no app gives them. |
| **The visit companion** | Every appointment | T-3: what this visit is for, what to bring, GL status. T-0: the questions on one card. T+0: what was said, in plain words, in his language. | The moment the app is obviously useful. Removes fear. |
| **Family loop** | Continuous | Messages and photos from children appear inside the same thread as his health cards. Confirmations he taps are seen by them. | The social reason to open it. Adherence improves when family is involved. |
| **Your numbers** | After each lab or reading | One big number, one arrow, one sentence: "Sugar is better than March." | Pride. He can tell the doctor. |
| **Weekly recap clip** | Weekly | 30 seconds, narrated in his language: what went well, what to watch, what is coming. | Passive, watchable, forwardable to the family group. |
| **Emergency card on the lock screen** | Always | Conditions, medicines, allergies, contacts, in two languages. Works offline. | Daily-carry trust. The reason he keeps the app installed. |
| **"Not feeling well"** | When needed | One button. Voice-captures what is wrong, checks his recent readings and medicines, tells him what to do now (rest / call clinic / go to A&E) and tells Ash. | Turns fear into a plan. The most valuable single button in the product. |

Hooks deliberately excluded: streaks that shame, leaderboards, points, daily quizzes, any notification that is not tied to his State.

---

## 4. Ash's side — probe, plan, push

The caregiver surface has three verbs. Everything in it is answered from Dad's memory with provenance.

### Probe — "what is his state?"

- **State card** — "Most likely state: stable, watch blood pressure." Three drivers with sources (readings, last consult clip, medication change). Confidence shown. Not a diagnosis; a synthesis with citations.
- **What changed since I last looked** — a diff view: new readings, new documents, new symptoms, confirmations missed, family notes. The busy adult child's home screen.
- **Ask anything** — natural-language questions over history, records, clips, notes: "What did the cardiologist say about the diuretic in March?" returns the clip at the timestamp plus a summary. "Has his potassium ever been high?" returns the values and the lab report.
- **Timeline** — episodes and appointments as the spine; artefacts hang off events; filter by body system.
- **Gaps** — what the record is missing: "No lipid panel in 14 months." "Dosage of amlodipine not confirmed since the discharge." Becomes a question for the next visit automatically.
- **Appointment radar** — last check-up, last visit, next visit, prep status, GL status, who is attending.
- **Questions to ask Dad this week** — the agent suggests what Ash should check in on, in Dad's language if Ash wants to forward it.
- **Medication story** — for every medicine: why, who prescribed, since when, what changed, what it interacts with.

### Plan — "what should his week look like?"

- **Routine builder** — medicines, readings (BP morning, glucose fasting), walks, meals, sleep, hydration. Rendered to Dad as cards; to the helper as a WhatsApp list.
- **Care plan with roles** — who drives Thursday, who collects the refill, who sits in the visit. Assignable to siblings and the helper.
- **Condition-aware, culture-aware diet plans** — hawker and home food, festive periods (Chinese New Year, Hari Raya, Deepavali), fasting months with medication timing shifts.
- **Mobility and falls plan** — simple exercise cards, home-hazard checklist, walking targets set by Dad not by the app.
- **Visit prep workspace** — the brief, the questions, the packet, the logistics, the GL — all in one place, editable, then pushed to Dad as one card.

### Push — "send him something he will actually read"

- **Compose → render** — Ash writes in English; the system renders a large-type card, a voice note, or a 30-second clip in Dad's language. Ash previews exactly what Dad will see before it sends.
- **Schedule and confirm** — sends at the right time for Dad's State; his tap comes back as a confirmation.
- **Memo cards** — every conversation Ash or Dad has with the agent ends in a memo in Dad's own words: "Bring the BP log Thursday. Lighter dinners. Ask Dr Tan about the dosage." Filed against the next appointment. Nudges reference the memo, never the system's targets.

### Co-caregivers and the helper

- Role-based grants: chief (Ash), caregiver (siblings), viewer (an aunt), helper (medication list and "given" taps only, no history), emergency-only.
- Scoped by category and time: cardiology yes, mental-health notes no; access for the two weeks after discharge.
- One family thread where health cards and human messages coexist; digest notifications, not a stream.
- Audit: Dad's surface shows who looked at what. He can mark something "only me."
- Escalation: if Dad ignores two nudges, the third goes to whoever is on duty, not to Dad.

---

## 5. The feature system

Fourteen modules. Each feature has a tier and the job it does. The eight features you listed are marked **★**.

### A. Capture and ingestion

| Feature | Tier | Job |
|---|---|---|
| Photo of any document → OCR → structured extraction (labs, reports, prescriptions, receipts) | T1 | The ASEAN ingestion reality |
| Handwriting recognition for clinic slips and handwritten prescriptions | T1 | Malaysian GP reality |
| PDF import (hospital portals, email, WhatsApp forwards) | T1 | |
| **WhatsApp ingestion** — forward a photo or PDF to the app's number and it files itself | T1 | Removes the "open the app" step entirely |
| Consult recording with consent prompt, transcription, speaker separation, timestamped summary | T1 | Recall; provenance |
| Scribble and voice notes attached to any event | T1 | |
| Medicine box / pill photo → identification → added to the list | T2 | Reconciliation |
| Pharmacy receipt → medicine + cost captured | T2 | Feeds ledger and refills |
| Wearable and home-device sync (BP cuff, glucometer, scale, Apple Health, Google Health Connect) | T2 | |
| **Health biography onboarding** — a guided session that turns a shoebox of ten years of paper into a record in one sitting (Ash-led, agent-assisted) | T1 | The activation moment; nobody does this |

### B. Memory and timeline

| Feature | Tier | Job |
|---|---|---|
| Episodic, semantic and working memory stores with provenance on every fact | T1 | |
| Appointments as the timeline spine: last check-up, last visit, next visit | T1 | |
| Providers directory: every doctor, clinic, hospital, pharmacy he has used, with history and Ash's notes ("good, but long waits") | T1 | Navigation input |
| "What changed" diff view | T1 | Ash's home screen |
| Natural-language recall for Dad (voice) and Ash (text) | T1 | |
| Body-systems map: every insight tagged to heart, kidneys, sugar, joints, eyes… doubles as a filter | T2 | The visual that answers "which part of me" |

### C. Medications

| Feature | Tier | Job |
|---|---|---|
| Reconciled medication list with source for each line (which visit, which doctor) | T1 | The list the clinic will trust |
| Schedule, "Taken" taps, helper-administered taps, family visibility | T1 | Adherence loop |
| Interaction check on every addition, including supplements and TCM | T1 | |
| **★ Polypharmacy and deprescribing review** — five-plus medicines screened against Beers, STOPP and START criteria, surfaced as talking points for the doctor, never as instructions to stop | T2 | Highest-value inference for this cohort |
| Refill tracking, days-remaining, reminder to whoever collects | T2 | Retention driver |
| Generic substitution and price comparison across pharmacies | T3 | |
| Side-effect diary linked to medication changes | T2 | Correlation input |
| Fasting and festive timing adjustments (Ramadan, pre-procedure fasting) | T2 | Local necessity |
| Medication story per drug (why, who, since when, what changed) | T1 | Dad's most common question |

### D. The visit loop

| Feature | Tier | Job |
|---|---|---|
| Pre-visit brief: what this visit is for, what changed since last time, open questions, what to bring | T1 | |
| Questions to ask, generated from gaps, memos and State; editable by Ash; one card for Dad | T1 | The thing his dad forgets |
| **★ Guarantee-letter and coverage check before the visit** — panel status, likely out-of-pocket, GL requested / approved / pending | T2 | The paperwork that blocks admission |
| Logistics card: time, place, parking, who is driving, what to bring | T1 | |
| In-visit recording and live capture | T1 | |
| Post-visit summary in Dad's language, action items, medication changes reconciled, follow-ups scheduled | T1 | |
| **★ Doctor-facing share link** — a one-page brief the clinic opens in a browser: conditions, medicines, recent readings, questions. Expires. No login. | T2 | Makes the product welcome in the room |
| **★ Second-opinion packet** — one clean bundle (summary, medicines, key labs, imaging list, prior opinions) a new doctor reads in three minutes | T2 | |
| Memo card at conversation end | T1 | Commitment loop |

### E. Discharge and transitions

| Feature | Tier | Job |
|---|---|---|
| **★ Discharge summary ingestion → plan** — new medicines reconciled against the old list, follow-up appointments extracted and scheduled, red flags listed in plain language | T2 | Where elderly care breaks |
| Readmission-risk watch for 30 days: daily check-in card, weight and symptom triggers, escalation to the caregiver on duty | T2 | Caregiver-mediated follow-up outperforms phone calls to the elderly |
| Hospital bag checklist and admission-day card (GL, ID, medicines, contacts) | T2 | |
| Transition memo for the GP after discharge | T3 | |

### F. Insurance, cost and administration

| Feature | Tier | Job |
|---|---|---|
| Policy on file: insurer, plan, panel hospitals, limits, exclusions, renewal date, in plain language | T2 | |
| **★ Guarantee-letter tracking** — requested / approved / rejected / expired, with the agent chasing via a drafted message | T2 | |
| **★ Claims tracking** — submitted / pending / paid / shortfall, receipts attached | T2 | |
| **★ Running cost ledger** — out-of-pocket, claimed, reimbursed, per episode and per year; MediSave/MediShield (SG), EPF/SOCSO/employer panel (MY) | T2 | |
| Cost expectation before care: likely bill range for this visit, test or procedure at this hospital | T3 | |
| Panel-doctor list matched to his conditions | T2 | Navigation input |

### G. Care navigation

| Feature | Tier | Job |
|---|---|---|
| Provider recommendation with reasons: sub-specialty match, prior history, panel status, distance, waiting time, when he is alert, who can drive | T3 | |
| Second-opinion logic: different institution, matched sub-specialty, not the same practice group | T3 | |
| Best time and easiest route: clinic peak hours, traffic, parking, transport | T3 | |
| Drafted WhatsApp message or call script to the clinic; booking only on confirmation | T3 | The friction remover in MY/SG |
| Transport coordination with the family plan | T3 | |

### H. Health intelligence and correlation

| Feature | Tier | Job |
|---|---|---|
| Lab trends with age- and lab-adjusted reference ranges | T1 | |
| Cross-signal correlation: readings vs medicines vs meals vs sleep vs symptoms | T2 | |
| Pattern flags with provenance and confidence, phrased as things to raise with a clinician | T2 | The safety boundary, built in |
| Food snap → what matters for him (salt, sugar, potassium, vitamin K), tagged to body systems | T2 | |
| **★ Age-appropriate screening and vaccination schedule** localised to MOH Malaysia and HealthHub Singapore guidance | T2 | |
| Plain-language explanation of his own condition and risk profile, in his language, as a clip | T2 | Onboarding content that keeps working |
| Seasonal and environmental alerts relevant to his conditions (haze, dengue, heat) | T3 | Local |

### I. Daily living and routines

| Feature | Tier | Job |
|---|---|---|
| Routine builder (medicines, readings, walks, meals, sleep) rendered per person | T1 | |
| Reading capture by photo of the device screen (BP cuff, glucometer) | T1 | Removes typing |
| Condition- and culture-aware meal guidance; hawker food library | T2 | |
| Mobility exercises as short clips; falls-risk check and home-hazard list | T3 | |
| Sleep and hydration nudges only when a condition makes them matter | T3 | |

### J. Delivery and engagement

| Feature | Tier | Job |
|---|---|---|
| **★ WhatsApp as a surface** — cards, voice notes, "Taken" replies, forwards in, helper list, family thread | T1 | Where the family already coordinates |
| Ranked feed: "today" top three, then explore; every card carries "why am I seeing this" | T1 | |
| Card grammar: one number, one direction, one colour, one action; 24–32pt type | T1 | |
| Voice notes generated from any card in Malay, Mandarin, Hokkien, Tamil, English | T1 | |
| 30-second clips: weekly recap, condition explainer, post-visit summary | T3 | |
| Trigger taxonomy — rule-based (dose, appointment, refill), pattern-based (BP up nine days, 2 kg in three days), event-based (lab arrived, family note) — with channel and cap per type | T1 | Alert-fatigue defence |
| Escalation ladder: Dad → helper → caregiver on duty → chief | T1 | |
| Memo cards and subtle nudges tied to his own commitments | T1 | |
| Engagement feedback: if he never opens text, switch to voice; if he ignores clips, switch to cards | T2 | The format adapts, not the person |

### K. Family and sharing

| Feature | Tier | Job |
|---|---|---|
| Patient-owned graph; scoped grants by role, category and time window | T1 | |
| Caregiver-led onboarding with explicit, revocable consent captured; LPA and equivalent documents stored | T1 | PDPA-aligned |
| Helper mode on WhatsApp in her language | T2 | Missed by everyone |
| Family thread, digests, duty roster | T1 | |
| Audit trail visible to Dad; "only me" marking | T1 | |
| Incapacity and death handling: who inherits the graph, what is deleted | T3 | |

### L. Safety and emergency

| Feature | Tier | Job |
|---|---|---|
| **★ Offline emergency card** — conditions, medicines, allergies, blood type, contacts, insurer, in two languages; lock-screen widget; printable wallet card | T1 | |
| "Not feeling well" button: voice capture → check State → what to do now → notify family | T1 | The most valuable button |
| A&E vs clinic vs wait guidance with the nearest appropriate option and its cost | T3 | |
| Advance care planning documents stored and shareable | T3 | |

### M. Symptoms and observations

| Feature | Tier | Job |
|---|---|---|
| Symptom log by voice, with severity and duration, in his words | T1 | Doctor input |
| Photo timelines for wounds, rashes, swelling, with side-by-side comparison | T2 | |
| Mood and energy as one tap, only if a condition or medicine makes it relevant | T3 | Kept out of clinical framing |

### N. Data, trust and boundaries

| Feature | Tier | Job |
|---|---|---|
| Provenance on every fact and every card | T1 | |
| Export and portability (PDF, FHIR bundle) | T2 | |
| Deletion, retention controls, in-region hosting | T1 | |
| The stated boundary on every screen that infers: organises, prepares, surfaces patterns to discuss; does not diagnose or treat | T1 | HSA / MDA line |

---

## 6. What was missing until now

Added across the modules above; called out here so they are not lost.

- **The domestic helper as a first-class user** with her own WhatsApp surface. In many households she administers the medicines.
- **The health biography onboarding session.** Activation is the shoebox. If the first week doesn't turn paper into a record, nothing else fires.
- **The "Not feeling well" button** as the anchor safety feature, not a symptom checker.
- **Supplements and TCM** in the medication list and interaction checks. Common in MY/SG, routinely omitted, real interactions (warfarin, antihypertensives).
- **Fasting and festive adjustments** to medicine timing and diet.
- **Reading capture by photo of the device screen**, so no typing of numbers.
- **The engagement feedback loop**: the format adapts to what he opens.
- **Escalation to the person on duty**, not to Dad, after two ignored nudges.
- **Old-Android reality**: the app must run on a five-year-old device, low storage, patchy data; WhatsApp-first is also the technical answer.
- **Hearing and vision accommodations**: voice-first, high-contrast, large type as defaults not settings.
- **Caregiver load for Ash**: a weekly "your load" view (hours, tasks, who did what) so the siblings can see the distribution. Kept practical, not clinical.
- **Advance care planning and LPA** storage with the family grants.

---

## 7. Stage 1 sequencing — a spine, not one feature

Every module above is designed now. The build order follows the loops the family runs, so each tier is usable on its own.

**T1 — weeks 0–12: the daily loop.** Health biography onboarding; capture (photo, PDF, handwriting, WhatsApp forward, consult recording); reconciled medication list with interactions; routine and "Taken" loop; the visit loop end to end (brief, questions, logistics, record, summary, memo); family grants and thread; emergency card; "Not feeling well"; WhatsApp surface; feed and card grammar; trigger taxonomy and escalation. Success: Dad receives and confirms daily; Ash probes weekly; one full visit completed through the product.

**T2 — weeks 12–24: the clinical loop.** Polypharmacy review; discharge-to-follow-up with readmission watch; GL and claims tracking; cost ledger; doctor share link; second-opinion packet; wearable and device sync; food snap; screening schedule; body-systems map; helper mode; photo timelines; engagement feedback. Success: one polypharmacy review actioned by a doctor; one GL tracked to approval; one discharge managed end to end.

**T3 — weeks 24–36: navigation and media.** Care navigation with drafted messages; cost expectation; clips (weekly recap, explainers, post-visit); mobility and falls; seasonal alerts; advance care planning; incapacity handling. Success: a second-opinion visit navigated end to end; weekly clip forwarded in the family group without prompting.

---

## 8. Measures that matter

| Person | Leading indicator | Lagging indicator |
|---|---|---|
| Dad | Daily "Taken" confirmation rate; WhatsApp replies; "Ask me" uses per week | Month-6 retention of the paying family; visits completed with a brief |
| Ash | Probes per week; "what changed" opens; pushes sent and confirmed | Self-reported load down; fewer calls to Dad about medicines |
| Family | Active grants; roster tasks completed by non-chief members | |
| Clinical | Medication list accepted by a clinic unchanged; polypharmacy talking points raised; GL resolved before admission | Readmission within 30 days of a managed discharge |

The gate from the research holds: a paying cohort retained past month six before Stage 2 spend. If Dad's daily confirmations fall below half, the issue is the hooks, not the funnel.

---

## 9. Open decisions

- Who pays: Ash (most likely), the insurer, or the hospital group. Pricing model follows the channel decision.
- Launch language set: Malay, Mandarin, English first; Hokkien and Tamil voice at T2 or T1.
- Consult recording consent pattern: prompt the doctor aloud, or a printed notice Dad carries. Needs legal review in both countries.
- Whether the helper surface ships at T1 for households that have one. Recommendation: yes, it is small and it is where adherence actually happens.
- How much of care navigation can be pre-loaded from your own account network (panel lists, hospital cost bands) before T3.
