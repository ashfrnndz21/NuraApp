# Nura — the app: product, users, user stories, experience, features, safety, design, architecture, status

*Compiled from the repository on `redesign` (worktree branch `product-spec-doc`, based on `origin/redesign` at `914591c0`), 2026‑09‑22. Every claim below cites the file it rests on. Where two documents disagree, this document says so rather than picking one.*

---

## 1. What Nura is

Nura is, in its own README, **"a health chief of staff for one person and the family around them. Quiet most days; flawless on the four days a year that matter."** (`README.md`). `CLAUDE.md` (repo root) expands the audience: **"A family health app for Malaysia and Singapore: an elderly patient, the adult child who runs his care, a domestic helper on WhatsApp, and a clinic that only receives."**

**For whom.** The demo seed — the one living record the repo ships — names the two people concretely: **Pa**, who owns the profile, and **Mei**, who "holds a chief key: every scope, the same window as any chief's" (`docs/deploy-demo.md` §3a). Pa is the patient: elderly, reading in Malay, Chinese or English, sometimes reached only on WhatsApp. Mei is the caregiver who runs his care day to day. A third role recurs throughout the design corpus without a fixed demo account: the doctor visit itself — the pre-visit brief, the questions card, the post-visit summary and memo (`backend/app/reasoning/visits/__init__.py`) — which the product treats as a recurring event to prepare for and to record, never a role Nura interacts with directly ("Nura never sends anything itself," `backend/app/reasoning/navigation/__init__.py`).

> **Naming note.** The root `CLAUDE.md`'s own "Domain vocabulary" section says: *"'Pa' and 'Ash' are example people in the docs, never identifiers in code"* — but every current design document (`docs/deploy-demo.md`, `docs/design/design-build-2.md`, `docs/design/audit-2026-09-22.md`, `docs/design/build-plan.md`) and the demo seed itself use **Mei**, not Ash, as the caregiver's name. `docs/design-system.md` (the older design system) also still says "Chief (Ash)." The caregiver's name changed from Ash to Mei at some point after `CLAUDE.md` and `design-system.md` were last touched; both are stale on this one point. This document uses Pa and Mei throughout, per the current demo seed and design corpus.

**The promise, in one paragraph.** Nura takes everything it can honestly know about one person — his medicines, his papers, his insurance, his daily readings, his appointments, what he eats, what he has asked — and turns it into what to do next: a reminder at the right moment, what to prepare for the doctor, a plain-words explanation of a result, a short video that applies to him. `docs/recommendation-engine.md` §0 quotes the owner's own brief for this: *"the core of what i wanted to build was … based on this and anything else i forgot, becomes a correlative recommendation to the user of the app, on reminders, what to prep for when meeting the doc, what to prep, personalized reads, personalized video feeds etc."* The experience specification the owner registered as binding states the same intent as an interaction model: **"AI understands → AI prioritizes → AI surfaces → user explores → AI explains → user acts"** (`docs/design/design-build-2.md` §1.1). Nura organises, prepares and surfaces; it never diagnoses or treats (`CLAUDE.md`, "Non-negotiables").

**The principles**, each traceable to a binding rule, not a slogan:

- **Plain words.** *"Every string on the patient's surface, on WhatsApp and in every voice note"* follows a thirteen-rule standard and a glossary that replaces every clinical term with what a person already calls it — "the water pill," "your blood pressure book," "the sugar tablet" (`docs/plain-words.md` §1–2). `CLAUDE.md`: *"Every string the patient sees or hears passes `docs/plain-words.md`."*
- **Nothing reaches a patient unchecked.** Every card records the State it was rendered from and is refused if it fails the plain-words verifier (`backend/app/state/__init__.py`; `backend/app/delivery/feed/__init__.py`: *"the lines come from `app.delivery.strings`, pass `app.safety.plain_words.verify` … an item that fails either is not created"*).
- **The person's own yes.** *"Nothing changes a medicine, books anything, or sends anything without an explicit confirm from a person"* (`CLAUDE.md`). Ingestion is described the same way: *"A photo comes in and its bytes go to the object store … Extraction runs … answers with fields, each carrying a confidence; nothing it says is a fact yet"* until *"the person's explicit yes"* (`backend/app/ingestion/__init__.py`).
- **Consent and scopes.** *"The consent record is a mandatory parameter on every cross-entity call"* is not this repo's own wording, but its own equivalent is exact: every read and write of profile data goes through `app/keys/` scope enforcement (`CLAUDE.md`, "Non-negotiables"; `backend/app/keys/__init__.py`), and a `Consent` row records *"what the patient, or someone acting for him, agreed to, in which words, and when"* (`backend/app/consent/__init__.py`).
- **Region residency.** *"Profiles are pinned to a region (SG or MY). Health data never leaves its region"* (`CLAUDE.md`). The one narrow exception — a Claude-backed model call, and only in a declared demo or the owner's own dev laptop — is its own ADR, not a loophole in this rule (`docs/adr/0017-claude-runtime-features-demo-only.md`).
- **The audit trail.** *"Every read, every write and every share of one person's health graph"* is written down; *"The owner and his chief are the only readers"* (`backend/app/audit/__init__.py`).

---

## 2. User stories

Grouped by journey, in the form "As Pa / As Mei, I want…, so that…". Status is marked **Built**, **Partly**, or **Not built**, drawn from `docs/design/build-plan.md`'s progress table (the 24 work packages against the redesign) and `docs/design/audit-2026-09-22.md`'s screen-by-screen verdicts against `docs/design/experience-blueprint.html`'s 26 scenes. Where a story exists only on the pre-redesign `main` branch, that is noted from `docs/parity.md`.

### Arrive & set up
- *As Pa, I want to sign in with my phone number and a code, so that I never need a password.* **Built** — scene 02 "Matches… nothing to fault" (`audit-2026-09-22.md` §2, row 02).
- *As Pa, I want to say who the profile is for (me, my parent, someone else), conversationally, so that setup feels like being asked, not filling a form.* **Partly** — the app "is two large static cards, no orb, no bubbles, no reply… intent preserved, form not" (`audit-2026-09-22.md` §2, row 03); package 9 (onboarding) is marked Done in `build-plan.md` but the audit, taken after, found this regression, tracked under PR #318.
- *As Pa, I want to say what conditions I have by tapping a cloud of words or just saying it in a sentence, so that setup is low-friction either way.* **Partly** — "13 one-question screens" now stand between consent and the cloud, and the cloud itself "renders as a two-column grid of same-size, same-tint pills, not the blueprint's irregular cloud" (`audit-2026-09-22.md` §2, row 04; D‑10, D‑11).
- *As Pa, I want to skip adding papers today with no penalty, so that I am never blocked.* **Partly** — "right options, plainer treatment, no icons, no sublines" (`audit-2026-09-22.md` §2, row 05).

### Load a paper
- *As Pa, I want to hand Nura a photo of one paper and watch it read the paper in real stages, so that I trust what it found.* **Built** — scene 06 is *"the best screen in the app"* per the audit, because *"the stages are the backend's own, not invented"* (`audit-2026-09-22.md` §2, row 06; `design-build-2-reading.md` scene 06).
- *As Pa, I want the extracted values shown as one table with ranges, not twenty-five separate cards, so that I only have to say yes once.* **Partly** — built (checkpoint 2, `build-plan.md` package 4, "Done (#296)"), but the audit found *"the headline count does not match the rows,"* a raw analyte code shown ("Apo‑B"), an unreadable unit, and a date format the app's own plain-words rule 5 forbids (`audit-2026-09-22.md` §2 row 07, D‑12).
- *As Pa, I want to see one paper flagged for me to check rather than every field, so that I am not asked twenty-five small questions.* **Built** in the report table's design (`design-build-2-reading.md` scene 07: *"one thing needs a yes, not twenty-five"*).
- *As Pa, I want Nura to connect what the paper just confirmed to my medicines and my next visit, unprompted, so that I don't have to ask.* **Partly / unreachable** — "Reached from the onboarding papers step and from Your papers only. From Home's 'Add a paper' it is never reached" (`audit-2026-09-22.md` §2, row 08; D‑5, three independent safety reviews, `build-plan.md` "checkpoint 3" log).
- *As Pa, I want to send a whole folder of papers at once and get one summary at the end, so that a backlog of papers isn't twenty-five separate chores.* **Not built** — "the batch grid and one-yes-for-all exist. No inbox, no verdicts" (`audit-2026-09-22.md` §2, row 09; `build-plan.md` package 18 "Not started: needs owner decisions").
- *As Pa, I want Nura to check whose paper it is before filing anything, so that a family member's result never lands on my record by mistake.* **Not built** — "Nothing checks whose paper it is… a wrong person's `birth_year`/`sex` overwrite the profile's own and then drive reference ranges, the emergency card and the screening schedule" (`audit-2026-09-22.md` §3.2, D‑2, Critical). Requirements are specified in `build-spec.md`'s "Owner requirement added 2026‑09‑22: whose paper is it" and `build-plan.md` package 19.
- *As Pa, I want the same paper photographed twice not to become two papers, so that my record stays trustworthy.* **Not built** — "No duplicate detection of any kind… I uploaded the same policy twice and got two policies; the same panel three times and got three papers, silently" (`audit-2026-09-22.md` §1.6, §3.2, D‑4).

### Read it (table, ranges, what it means)
- *As Pa, I want my blood test shown with the doctor's own range and whether I'm inside or above it, in one line, so that I understand it without asking.* **Built** in substance — `docs/health-feed-spec.md` §2's "own-data insight" card type and `build-plan.md` package 3's Done status; deltas noted above (D‑12).
- *As Mei, I want a fuller reading with the raw values and every flagged field, so that I can judge what needs a doctor's attention.* Reflected in `docs/design-system.md` §3's "Chief" density and `docs/design/design-build-2.md` §15 ("Insight before raw data"). **Partly** built per the redesign's Health screen deltas (§2 below, D‑18: "no trend chart… blood pressure is a plain text row").

### Ask Nura (multi-turn, memory, clarifying questions, elapsed time, waiting papers)
- *As Pa, I want to ask Nura a question in my own words and get an answer that names its source, so that I can trust it.* **Partly, with a critical content defect** — Ask's empty state and streaming both work (`audit-2026-09-22.md` §2 row 16: "matches well"), but *"Ask cannot state a value from a confirmed paper"*: reproduced live, *"How is my cholesterol?" → "Your cholesterol test from Friday 18 September is in your papers."* (no number) (`audit-2026-09-22.md` §3.1, D‑1, Critical).
- *As Pa, I want a follow-up question to remember what I just asked, so that I don't repeat myself.* **Built** — "conversation memory works: `Conversation`/`Turn` rows… six turns verbatim" (`audit-2026-09-22.md` §3.3), and scene 16 shows this explicitly: *"Remembers this chat"* (`design-build-2-reading.md` scene 16).
- *As Pa, I want Nura to ask me a clarifying question when my question is ambiguous, rather than guess, so that I'm not given a wrong answer.* **Not built as a real interruption** — "the clarifying question is not an interrupt: `ClarifyOut` rides inside the **final** `answer` event… the chip tap starts a **whole new run**" (`audit-2026-09-22.md` §7.1). Live-tested twice by the operator on 2026‑09‑22: "no clarifying question was proposed" (`build-plan.md`, log entry 2026‑09‑22).
- *As Pa, I want to know how long it has been since my last blood test, computed for me, so that I don't have to do the arithmetic myself.* **Built**, and specifically fixed under the "ask‑quality" defect (`build-plan.md` package 8 log, #302): "elapsed time computed by the backend," verified live: *"A blood test dated Saturday 12 September is waiting for you to check"* (`build-plan.md`, log entry 2026‑09‑22, Stage 1 merge).
- *As Pa, I want to be told a paper is waiting for me to check, without Nura stating any of its unconfirmed values as fact, so that nothing unchecked reaches me.* **Built**, as a safety fix: *"a waiting paper now exposes only its kind (closed list), its printed date (validated, never in the future) and when it was added — no extracted text at all"* (`build-plan.md` package 8 log, #302). The underlying rule is named explicitly in the user's own memory of this project and confirmed in the repo's log: *"an extractor-written string is hostile until the person confirms it"* (`build-plan.md`, 2026‑09‑21 log entry).

### Home briefing
- *As Pa, I want one sentence that tells me what matters today, composed from what actually happened, so that I don't have to hunt for it.* **Partly** — Home's headline exists and is data-driven, but the priority order the code uses (`doseDue → allTaken → today's reading → a visit within a week → a reorder → paper → (quiet)`) puts a newly filed paper **last**: "Pa confirmed a blood test and Home still said 'Every tablet for today is taken.'" (`audit-2026-09-22.md` §3.5, §2 row 15, D‑22).
- *As Pa, I want a single insight card, a reminder and one feed line — never more — so that Home never overwhelms me.* **Partly** — the app's Home carries "a 5-element header," more elements than the blueprint's two-line header and quiet composite (`audit-2026-09-22.md` §2 row 15).

### Health & Analyst
- *As Pa, I want my blood pressure shown as a trend with a plain "above your usual" line, so that I see the direction, not just today's number.* **Not built** — "there is **no chart anywhere in the app**… blood pressure is a plain text row" (`audit-2026-09-22.md` §2 row 17, D‑18).
- *As Mei, I want a weekly analyst report that reads what changed and turns it into visit questions, so that I walk into the appointment prepared.* **Partly** — "Generates and streams real stages," but repeats its own finding, says "Ask Dr Tan this" (a wording the operator had already rejected once), and shows a stray glyph and two competing date lines (`audit-2026-09-22.md` §2 row 18, D‑23).

### Medicines (registry, add by photo/file/typing, which statin, safety screening, reorder)
- *As Pa, I want to add a medicine by photographing the box, so that I never have to type a drug name.* **Built** — `docs/design/build-plan.md` package 11 "Done (#313)". Registry strength: *"233 products, 25 interaction pairs, 50 monographs"* (`docs/design/build-spec.md` §6), and brand→generic resolution is measured above 95% (`docs/parity.md`, E00‑06).
- *As Pa, I want Nura to ask "which statin?" rather than record "STATIN" when the box only names the drug family, so that nothing vague is kept as fact.* **Not built as designed** — "the app: photo/type-it entries exist; voice not built. On a class-only box the read-back prints 'The medicine: STATIN' with 'Looks right' as the primary — no 'which statin?' question" (`audit-2026-09-22.md` §2 row 12, D‑6). The backend itself already refuses to store a class name as a medicine (`build-plan.md`, package 13 log, #313: *"a class name ('STATIN') can never be stored as a medicine"*) — the defect is in the screen offering "Looks right" over that refusal, not in the write path.
- *As Pa, I want a dose taken to be one tap, with no confirmation modal, so that the daily ritual stays effortless.* **Built** — scene 19: "the button itself becomes the record… no separate confirmation step" (`design-build-2-reading.md` scene 19).
- *As Pa or Mei, I want two medicines of the same class flagged for the pharmacist, never as a verdict Nura makes itself, so that I know Nura is not deciding pharmacology.* **Built** — "an `InsightKind.MEDICINE` insight, `ask_who=PHARMACIST` — already the blueprint's 'Ask your pharmacist' pattern, already routed to the pharmacist, never a verdict" (`docs/design/build-spec.md` §6).
- *As Pa, I want a reminder before I run out, so that I never miss a refill.* **Built** — E04‑04/E04‑05, "the count drops per tap, and the reorder date moves with the lead time" (`docs/parity.md`, E04‑04, done); the Ask‑to‑order tap itself still does nothing (`docs/parity.md`, E04‑05, missing).
- *As Pa, I want a high-risk medicine's dose only ever recorded from a label photo, never from a voice note or a typed message, so that a dangerous dose is never guessed at.* **Built** — enforced at the write layer for every writer: *"a dose of one is saved from a label photo, never from a message or a voice note alone"* (`backend/app/safety/__init__.py`; `docs/parity.md`, E16‑04, done).
- *As Pa, I want to add a medicine by voice, so that I don't need to use the camera or type.* **Not built** — named explicitly as a gap at every mention (`build-plan.md` package 11 and 13 logs: "Not built: adding a medicine by voice").

### Insurance
- *As Mei, I want my policy's essentials — what it covers, what it excludes, how to claim — read from the PDF with a page citation on every line, so that I can trust what I'm told.* **Not built as a "passport"; a much flatter, person-typed summary exists.** *"Today's `Policy` is a person-typed summary… the blueprint's `policy` scene is a document-read"* (`docs/design/build-spec.md` §5). The Insurance "essentials" half of package 12 is merged (`build-plan.md` package 12: "Insurance half done (#309)"), but the audit still found a dead end: after "Looks right," a sheet renders over a stale empty state and "the tab bar stops responding" (`audit-2026-09-22.md` §2 row 11, D‑16).
- *As Pa, I want one line on the emergency card naming my insurer, so that a stranger at a hospital desk knows who to call.* **Built** — `insurer` stays on `Scope.EMERGENCY`, "the one line the emergency card says" (`backend/app/insurance/__init__.py`).
- *As Mei, I want to see how much has been claimed this year, without a made-up percentage of "covered," so that I know only what the insurer actually said.* **Built** on the ledger side — `insurance_ledger()` sums claims by policy (`docs/design/build-spec.md` §5); the display rule is enforced in code: *"never a made-up midpoint, never a 'covered' percentage invented"* (`cost_expectation.py`, cited in `build-spec.md` §5).

### Visits (planner, questions to ask, logistics)
- *As Pa, I want the questions Nura suggests for my next visit to be first-person and drawn from what actually happened, not a raw code, so that they read the way I would say them.* **Built**, after rework — the first pass showed "a raw code ('Ldl on this paper is outside the range printed on it.'), native checkboxes that did nothing"; sent back, rebuilt as *"one card 'For Dr Lim on 25 September,' first-person questions from a checked bank, 'Keep these for my visit'"* (`build-plan.md` package 7 log, #303).
- *As Mei, I want a driver suggested for the visit from the family roster, confirmed with a yes, so that logistics don't fall entirely on me.* **Built** — `docs/parity.md`, E05‑03, done.
- *As Pa, I want Nura to record what the doctor said and turn it into my own memos, never a silent medicine change, so that nothing changes without my say-so.* **Built** — *"actions become memos, a medicine change becomes a flag and a question (never a change)"* (`backend/app/reasoning/visits/__init__.py`); `docs/parity.md`, E05‑05, done (web confirm step still API‑only).
- *As Mei, I want an estimate of what a procedure might cost, cited to past receipts, even before a visit is booked.* **Not built** — "today's engine has no unbooked-procedure estimator" (`design-build-2-map.md`, row 44; `docs/design/build-plan.md` package 17, "Not started").

### The feed (clips, articles, story, quiet hours, live search)
- *As Pa, I want a short video that applies specifically to me, with why I'm seeing it stated before what it is, so that it never feels generic.* **Not reachable today** — the live web search that would produce clips and articles has never run on the redesigned backend; the API returns text-only cards with `source_id: null` (`audit-2026-09-22.md` §2 row 22; `build-plan.md` package 13: "Done except the live web-search run… needs the owner's OK, a server restart and credits").
- *As Pa, I want the feed to stop offering new cards once I've seen today's, with an honest "that's all for now," and then move into my own story and evergreen learning.* **Built**, after a fix — the initial order put every story card ahead of every learning card, hiding eight learning cards behind twenty-six story ones; fixed to "the newest card per story; past the gate a learning card first, then turns, one card per kind" (`build-plan.md` package 13 log, #315). `docs/health-feed-spec.md` §0 defines the order: *"Now … → Today … → a gate … → His story … → Learning."*
- *As Pa, I want Nura to stay quiet at night, so that I'm never pinged outside reasonable hours.* **Built** — verified live: "the feed is quiet 21:00–07:00 by design" (`build-plan.md` package 13 log, 2026‑09‑22).
- *As Pa, I want to say "not for me" on a card and have that preference remembered, so that the feed learns without me having to explain why.* **Built** — `docs/health-feed-spec.md` §3 step 9: *"engagement events… feed novelty and format fit; two ignored text cards flip the profile's preferred format to voice."*
- *As Mei, I want to see what was sent to Pa this week, with its source and whether he opened it, so that I can watch without having to ask him.* Specified in `docs/health-feed-spec.md` §1 ("Caregiver · For Pa" placement); not confirmed built in the redesign pass reviewed here.

### Not well / emergency card
- *As Pa, I want tapping "not well" to skip every animation and thinking delay, so that the moment feels urgent, not performative.* **Built, by design** — scene 23: "no thinking animation, no streaming, no delay" (`design-build-2-reading.md` scene 23; `audit-2026-09-22.md` §2 row 23: "No thinking animation, no delay — correct").
- *As a stranger who finds Pa unable to speak, I want an emergency card with his conditions, medicines, allergies and a number to call, available offline, so that I know what to do.* **Built** on the backend, with a real client-side gap — `docs/parity.md`, E13‑01, "missing": the web shows only a placeholder ("Nura will keep your emergency card here.") offline; the printable page exists.
- *As Pa, I want a red flag I raise myself to reach my family immediately, never held for the quiet hours, and to climb to the next person if nobody answers.* **Built** — the escalation ladder: *"Red flags skip his rung. A red flag goes straight to the roster… never held for the quiet hours"* (`docs/adr/0005-the-ladder-is-the-one-escalation-record.md`, decision 2).
- *As Pa, on medicine or on foot, I want a fall while I'm on a blood thinner to always be treated as an ambulance case, whatever the hour, so that a dangerous bleed is never treated as "wait until morning."* **Built, but gated off pending clinical sign-off** — the two-tier logic exists (`docs/adr/0010-red-flag-tiers.md`), but *"None of this reaches a family until a clinician signs the table… Unset — every deployment until the sign-off — every red flag's step is the ambulance"* (same ADR, "Behind a switch until it is signed").

### Connect & family
- *As Pa, I want to name a role for someone (chief, viewer, helper) and know exactly what they can and can't see, so that sharing is precise, not all-or-nothing.* **Built on the backend, thin on the web** — `docs/parity.md`, E12‑01, done on the backend; "Web cuts only a 'caregiver' key by parts: no role choice, no time window, no narrowing." The redesigned Connect screen is **Not built** — `build-plan.md` package 14, "Not started"; the audit shows an avatar grid with three empty states where the blueprint shows populated role rows (`audit-2026-09-22.md` §2 row 24).
- *As Pa, I want my "only me" setting to take a part of my record out of a live key instantly, and to be on the trail, so that I keep control even after I've shared.* **Built on the backend** — `docs/parity.md`, E12‑04, done (no web trail or control yet).
- *As Mei, I want a duty roster so that tasks are assigned to a named person, not left to whoever notices.* **Backend-only** — `docs/parity.md`, E12‑03.

### Caregiver view
- *As Mei, I want the same Home screen Pa sees, recomposed in a caregiver's voice about him, not a different app.* **Built, proven to be a data substitution, not a parallel template** — "its one `stream()` call is structurally identical to Home's" (`design-build-2-reading.md`, "Ten conclusions," #10; scene 25).
- *As Mei, I want every medicine line spoken in one consistent voice, not switching between "Pa takes…" and "the sugar tablet," so that reading his medicines doesn't feel inconsistent.* **Not built / defect** — "Mei's Medicines mixes voices inside one list: row 1 'Pa takes 1 tablet of Pa's blood pressure tablet…', rows 2–5 'Take 1 tablet of the sugar tablet…'" (`audit-2026-09-22.md` §4.3, D‑20).

### ASEAN by configuration
- *As the owner, I want the app's emergency number, drug register, currency, publishers, ID format and residency region to all change from one country setting, so that adding Thailand (or another ASEAN market) is adding a pack, never rewriting a caller.* **Decided, partly built.** The two facts a country pack must get right (emergency number, drug register) already work for both existing regions (`docs/design/build-spec.md` §0(a): "Region-derived facts already exist for both"). The generalisation into a first-class "country pack" concept is the owner's decision of 2026‑09‑22, recorded as `build-plan.md` package 24, **Not started**: *"one country setting (MY, SG first; TH and others by adding a pack) that tailors the emergency number, the licensed drug register, currency, the trusted publishers, ID format, privacy wording and the region the data lives in."*

---

## 3. The experience

### The 26 scenes

`docs/design/experience-blueprint.html`'s own `SC` array defines exactly **26** scenes in six groups (`experience-blueprint.html:192` onward; confirmed by direct extraction of each scene's `k`/`g`/`n` fields). Note: `docs/design/build-spec.md`'s own header describes the blueprint as having "25 scenes" — this is the one place in the corpus that disagrees with the file itself and with every other document (`design-build-2.md`, `design-build-2-reading.md` and `audit-2026-09-22.md` all say 26). The list below is authoritative against the HTML source.

| # | Group | Title | What it shows |
|---|---|---|---|
| 1 | Arrive | Welcome | The orb alone, breathing, before any account or data exists; one streamed sentence, then one **Start** button (`design-build-2-reading.md` scene 01). |
| 2 | Arrive | Sign in | Phone number, then a code field, revealed one at a time — "no password anywhere in Nura" (scene 02). |
| 3 | Arrive | Who is this for | A conversation: Nura's bubble, three chips (Me / My parent / Someone else), the person's reply, Nura's second turn (scene 03). |
| 4 | Arrive | What is part of your health | The "bubble cloud": tappable condition bubbles that bob continuously, or a sheet to say it in one sentence instead (scene 04). |
| 5 | Your papers | Add a paper | Three entry rows (photo / file / many at once) or "I have no papers today," with no penalty for skipping (scene 05). |
| 6 | Your papers | Nura reads it | Four real backend stages narrated in place, then a headline, then five summary rows — "the best screen in the app" per the audit (scene 06; `audit-2026-09-22.md` §2 row 06). |
| 7 | Your papers | The report table | One table, range bars, "Looks right" / "Fix a number," one flagged uncertain row (scene 07). |
| 8 | Your papers | What it means for you | Questions for the doctor, connected unprompted to medicines and the next visit; "Keep these for my visit" (scene 08). |
| 9 | One record | Many papers at once | Seven papers as a visible queue, one shared status, each row's own flag cycling live (scene 09). |
| 10 | One record | What changed in your record | Six plain verdicts — New/Same/Newer/Conflict/Replaces/Yours? — never silent, never a raw diff (scene 10). |
| 11 | One record | Policy passport | Real page-by-page progress ("Reading page 4 of 48…"), then four tabs (scene 11). |
| 12 | One record | Add a medicine | A box photo or typed/spoken entry; asks "which statin?" rather than guessing when the box only names a family (scene 12). |
| 13 | One record | Medicine registry | Every source merged into one card per medicine; a "Show my pharmacist" summary sheet (scene 13). |
| 14 | One record | Everything connected | One fact's full context — source, medicine, visit, policy line, analyst mention, a clip — five doors from one screen (scene 14). |
| 15 | Every day | Home | One composed headline, one insight card, a reminder, a feed line — three things, not more (scene 15). |
| 16 | Every day | Ask Nura | Two questions in sequence, sources shown before the answer, the second remembering the first (scene 16). |
| 17 | Every day | Health | A summary card, a trend chart, three paper rows — a static composed view, no AI turn (scene 17). |
| 18 | Every day | Health Analyst | Four narrated stages, then sections revealed one at a time; a section with nothing to say is left out, never shown empty (scene 18). |
| 19 | Every day | Medicines | Tap "I took it" — the button itself becomes the record, no modal (scene 19). |
| 20 | Care and money | Visits and costs | The next-visit card; "What might it cost?" and "Draft the message," both via a sheet; Nura never sends anything itself (scene 20). |
| 21 | Care and money | Insurance | Policy card and a claims ledger as a short list, not a spreadsheet (scene 21). |
| 22 | Every day | For you | Two clips and a "Did you know" card, chosen because of something specific to this person; why before what (scene 22). |
| 23 | Safety | Not feeling well | The one deliberately urgent scene: background swaps colour in the same frame as the card, no thinking, no stagger (scene 23). |
| 24 | Family | Connect | Three people's access rows with role badges, "Let someone in," "See it as Mei" (scene 24). |
| 25 | Family | Mei's Home | The same Home template, recomposed with a caregiver's voice — proven a data substitution, not a second template (scene 25). |
| 26 | Family | Profile | Six rows, most already answered in a sentence; the most static scene in the file (scene 26). |

### The interaction model

The owner's own words, registered as binding from 2026‑09‑22: **"AI understands → AI prioritizes → AI surfaces → user explores → AI explains → user acts. Minimise navigation, maximise contextual interaction."** (`docs/design/design-build-2.md` §1.1). The design-reading pass found this realised in the blueprint through two distinct disclosure modes, not one: an **"AI turn"** (the `nura()` function: think → headline → body/rows, used wherever Nura is actively reasoning — scenes 06, 08, 09, 10, 16, 18) and a **"static composed view"** (scenes 17, 21, 24, 26: content simply reveals, with no AI turn at all) — *"a real second mode the spec does not name separately but the blueprint consistently distinguishes"* (`design-build-2-reading.md`, "Ten conclusions," #5).

Two of the specification's own core claims have **no reference implementation** in the blueprint itself, which the reading pass calls out explicitly so they are understood as design work, not extraction:
1. **The composer never expands in place** in the blueprint — tapping the docked "Ask" bar is always a full scene change (`go('ask')`), directly contradicting spec §9's *"the compact pill expands in place… do not open a separate full-screen chatbot"* (`design-build-2-reading.md`, cross-cutting notes; conclusion #1).
2. **No shared-element transition exists anywhere in the blueprint's own code** — every detail is either a full scene change or a bottom sheet; spec §12's "a Home card transforms into the detail" is *"asserted in scene 14's content… but never demonstrated in its motion"* (`design-build-2-reading.md`, cross-cutting notes; conclusion #2).

### The state machines (`design-build-2.md` §28, `mobile-architecture.md` §3)

**AI state:** `idle → listening → thinking → responding → idle`, `* → error → idle`, driven only by events from a stream, never a timer (`mobile-architecture.md` §3). The current backend, however, has no event that maps cleanly onto this: *"idle → listening: … None — no capture-start event exists in any of the six vocabularies"*; *"responding → idle: … None — no explicit 'run finished' signal"* (`design-build-2-map.md` §2.1). The blueprint's own reference implementation shows only two of the five CSS states in motion (idle spin, `.think`'s faster spin, plus a `.lg` breathing size variant on Welcome) — *"three states beyond what the blueprint ever shows"* (`design-build-2-reading.md`, conclusion #3).

**Card state:** `collapsed → pressed → expanded → interactive → dismissed`, with `loading` and `error` reachable from `expanding` (`mobile-architecture.md` §3). A tap is meant to become "the expanded object, never Screen A → Screen B" — a promise the current build does not keep: `ExpandableCard` "confirmed absent" (`design-build-2.md` §2).

**Media state:** `idle → loading → playing ⇄ paused → complete` (`mobile-architecture.md` §3). `playing → paused` is *"not modelled anywhere — the blueprint's `.pl` button has no pause affordance… a gap in the reference, not just the app"* (`design-build-2-map.md` §2.3).

---

## 4. Features in detail

For each domain: what it does, the modules that implement it, the safety rules that bind it, what the person actually reads (quoted), and open defects by D-number (`docs/design/audit-2026-09-22.md` §5) where they exist.

### Ingestion — reading a paper

**What it does.** A photo or PDF's bytes go to the object store of the profile's own region; extraction runs behind a port and answers with per-field confidence, never a fact yet; a person confirms, corrects or rejects field by field; only on a yes are Facts written, with the photo as provenance (`backend/app/ingestion/__init__.py`).

**Modules.** `backend/app/ingestion/extract.py` (the `Extractor` port), `claude_extract.py` (`ClaudeExtractor`, demo/dev-only), `review.py` (the review card), `objects.py` (region-pinned storage), `connectors/` (read-only calendar).

**Safety.** Importing the package "wires the label-photo rule for a high-risk drug… onto the memory store, so that a medicine dose cannot land from anything but a photo whichever surface writes it" (same file). Region residency is enforced twice — at the door and again inside the adapter (`docs/adr/0017-claude-runtime-features-demo-only.md`, decision 1 and 4).

**What the person sees.** *"Looks right"* (`web/src/strings/en.ts:1760`), *"Nura wrote it down"* (`en.ts:1761`), *"This paper is waiting for you to check"* (`en.ts:938`).

**Open defects.** D‑2 (whose paper is it — Critical), D‑4 (no duplicate detection — High), D‑5 (Home's "Add a paper" never reaches the insight screen — High).

### Matching — one record

**What it does (specified, not built).** No matching engine exists in code today — `docs/design/build-spec.md` §4 marks the whole section **GAP**. The design specifies six verdicts per fact: New, Same, Newer, Conflict, Replaces, and "Not yours?" — the last two and Conflict *always* need a person's yes (§4, "Which verdicts need the person's yes"). A synonym table mapping a lab's printed name to a canonical analyte code is the first missing piece; ten canonical analytes already have clinically-sourced bands in `backend/tests/fixtures/labs/ranges.json`, and thirty more are proposed but explicitly flagged: *"every row NEEDS CLINICAL REVIEW"* (`build-spec.md` §4).

**Safety.** *"Rules decide, never a model"* — the matching engine follows the analyst's existing pattern: a model may rephrase, never decide (`build-spec.md` §4 header, citing `RuleAnalyst`).

### Medicines

**What it does.** A label is identified through the licensed registry, reconciled against active lines (refill, dose change, new line, duplicate), and its high-risk class enforced at the write layer (`backend/app/medicines/__init__.py`; `backend/app/drugs/__init__.py`).

**Modules.** `app/medicines/service.py` (`_one_product`, `reconcile`, `record_dose_taken`), `app/drugs/fixture.py` (233 products, 25 interaction pairs, 50 monographs, NPRA/HSA-shaped registration numbers — `build-spec.md` §6), `app/safety/high_risk.py` (5 hand-named classes: anticoagulant, insulin, cardiac glycoside, antimetabolite, opioid).

**Safety.** *"Nothing here writes a sentence: a monograph is rule ids, and the words for them live in `app.medicines.strings`"* (`backend/app/medicines/__init__.py`). *"Explicitly NO interaction judgement… Nura lists, a pharmacist judges"* (`build-spec.md` §6).

**What the person sees.** *"The medicine you kept"*, and the class-only refusal path: *"a class name… can never be stored as a medicine"* (`build-plan.md` package 13 log). Glossary: *"The water pill,"* *"Your blood pressure tablet,"* *"The cholesterol tablet,"* *"The sugar tablet"* (`docs/plain-words.md` §2).

**Open defects.** D‑6 (offers "Looks right" over "The medicine: STATIN" — High), D‑19 (docked pill clips the card behind it; a one-at-a-time pager instead of a list — Medium).

### The feed

**What it does.** A vertical pager, ranked `now → today (1–2 new cards) → a gate → his story → learning`, capped at two new cards a day, never on an alert day, respecting quiet hours (`docs/health-feed-spec.md` §0, §1). A safety notice about one of his own medicines is **never** a card in his feed — held for the chief, or rerouted as a doctor's question — resolved explicitly after an earlier draft of the same spec read ambiguously: *"§0 wins"* (`docs/health-feed-spec.md` §2, "A safety notice is never his card").

**Modules.** `backend/app/delivery/feed/__init__.py` (`items`, `compose`, `rank`, `engagement`, `search`), `backend/app/delivery/recommend/__init__.py` (the broker described in ADR 0016).

**Safety.** *"An item that fails [the plain-words verifier] is not created"* (`backend/app/delivery/feed/__init__.py`). `create_item` "refuses a `TreatmentChangingCard` outright, the same choke point that refuses a `NOTICE` built for the patient" (`docs/health-feed-spec.md` §2).

**What the person sees.** *"Nura keeps quiet at night"* (`en.ts:904`), *"Not for me"* (`en.ts:884`), *"Your story"* (`en.ts:874`).

**Open defects.** The live web search has never run on the redesigned backend (`build-plan.md` package 13); D‑15 (every card's prepared voice fails to build, falling back to the phone's own voice ten times in one walk — Medium).

### Recommendation / correlation

**What it does.** `docs/recommendation-engine.md`'s own audit (§1.2) is blunt: *"Today the inputs and the outputs exist, and nothing connects them. Each output reads its own narrow inputs."* Correlation is designed to sit **beside** State, not inside it, for four reasons written into `docs/adr/0016-correlation-sits-beside-state.md`: State promises never to judge a number; posture (the day's colour) is the worst of six dimensions and must not move from a correlation; State recomputes inside every single fact write, while a pattern reads weeks of series; and a pattern can span two scopes, which State's per-subject narrowing cannot hide correctly.

**Modules (designed, largely not yet built).** `app/reasoning/patterns/` (a `PatternDetector` port, arithmetic-only default adapter — "two groups of his own answered days, a minimum of days in each, a noise gate… It computes no probability and no coefficient," ADR 0016 decision 1); `app/delivery/recommend/` (the broker — `models.py` for `Evidence`/`Candidate`, `broker.slate()`; "the broker writes no words and no rows," `backend/app/delivery/recommend/__init__.py`).

**Safety.** *"A model never chooses which of his numbers to compare, never writes a pattern's sentence, and never sets a candidate's audience or safety class"* (ADR 0016, decision 6). Patterns render only behind `NURA_PATTERNS=1`, and until a pharmacist approves a rule, every rendering carries *"A pharmacist has not checked this yet"* (ADR 0016, decision 7).

### Visits

**What it does.** The pre-visit brief, question generation, post-visit summary and memo consolidation, all rendered from State and passed through the plain-words verifier (`backend/app/reasoning/visits/__init__.py`).

**Safety.** *"On his yes, actions become memos, a medicine change becomes a flag and a question (never a change)"* (same file).

**What the person sees.** *"For Dr Lim on 25 September"*, *"Keep these for my visit"* (`build-plan.md` package 7 log).

### Insurance

**What it does.** A person-typed summary today (insurer, reference, dates, free-text `covers`), not a document-parsed passport; a fuller, cited "policy passport" (limits, exclusions, how-to-claim, all with `{quote, page}` citations) is specified but not built (`docs/design/build-spec.md` §5). `app/insurance/__init__.py`: *"The one place an insurance identifier is kept… identity-card numbers never outside this module."*

**Safety.** Policy and claim data sit under `Scope.MONEY`, held to a chief only by default; `insurer` alone (the emergency-card line) sits on `Scope.EMERGENCY`, which every role holds — *"a different question, on purpose, from what a policy pays for"* (`backend/app/insurance/__init__.py`).

**What the person sees.** *"Your insurance letter is ready"* (`docs/plain-words.md` §2), *"Nura has no insurance written down for you yet"* (`audit-2026-09-22.md` §2 row 11).

**Open defects.** D‑9 (unclear whether a confirmed policy actually saved — the screen is trapped by D‑16), D‑16 (the propose sheet renders over a stale empty state and the tab bar stops responding — High), D‑13 (the structured, cited policy lists exist on the backend and are invisible to Ask — Medium).

### Safety systems (not well / emergency)

**What it does.** A fixed emergency-card projection readable under a scope every role holds; a not-feeling-well button and symptom log that write a red flag before anything else happens; an escalation ladder that climbs Pa → helper → caregiver on duty → chief (`backend/app/safety/__init__.py`; `docs/adr/0005-the-ladder-is-the-one-escalation-record.md`).

**Safety.** *"A word tapped on the feeling cloud, free text on WhatsApp, the words said or typed to the not-feeling-well button and the symptom log all raise the same `Flag`… before any ranking or cap, telling every live key with the emergency scope"* (`backend/app/safety/__init__.py`). *"A flag that depends on a fact not on the record is written with why it was suppressed, so the caregiver sees it was considered."*

**What the person sees.** *"Nura does not decide what is wrong."* (closing line on every red-flag reply, `docs/adr/0010-red-flag-tiers.md`); *"Mei knows now."* / *"You did right to say so."* (`docs/adr/0002-emergency-scope-and-the-safety-layers-posture.md`, decision 12).

**Open defect.** D‑0 (Critical) — *"opening Profile freezes the app within 500 ms"* on WebKit, the only engine on an iPhone; the emergency card, Insurance and the way back out of Profile are all downstream of it (`audit-2026-09-22.md` §1, §5).

### Family / Connect

**What it does.** Roles and scoped grants (six preset roles, each with a window, in plain words), a family thread with digests, a duty roster, an audit trail in Pa's own words with an "only me" control (`backend/app/family/__init__.py`).

**Safety.** *"The 'only me' floor itself lives with the keys… because it is enforced in the resolver; this package writes the rows and renders the words"* (same file).

**Open defect.** Package 14 (Connect, Mei's Home rebuild, Not well, Profile) is **Not started** on the redesign (`build-plan.md`); the pre-redesign Connect screen shows three empty sections where the blueprint shows three populated role rows (`audit-2026-09-22.md` §2 row 24).

---

## 5. Safety & trust

### Plain words

Thirteen rules and a three-language glossary bind everything the patient reads or hears (`docs/plain-words.md` §1–2). The standard is enforced twice: at build time (`make plain-words`, `CLAUDE.md`) and at run time by `app/safety/plain_words.py`, *"the verifier behind `make plain-words`… every string tagged `@patient` passes the standard or does not ship, and `plain_words.verify` is the same check for the memos and cards the backend writes at run time"* (`backend/app/safety/__init__.py`). A relaxed profile exists for Ask's own conversational answers (`kind="ask"`): one idea per line is relaxed and the word ceiling rises from fifteen to twenty, but *"every other rule — 14 (the boundary) above all — runs exactly as it does… a profile relaxes shape, never safety"* (`docs/plain-words.md` §1a).

### The vetoes

No code path may output advice to start, stop or change a medicine (`CLAUDE.md`); reasoning explicitly disclaims this power: *"Nothing here diagnoses or treats, and nothing here calls a model to decide pharmacology"* (`backend/app/reasoning/__init__.py`). A value not yet confirmed by a person is never stated as fact — the rule the "ask-quality" fix (`build-plan.md`, #302) exists specifically to enforce, discovered when *"the reviewer proved, with a working test, that an unchecked number could reach the patient as fact"* (`build-plan.md`, package 8 log). **Whose paper it is** is the newest veto, added at the owner's explicit instruction on 2026‑09‑22 and specified as deterministic rules only, never a model decision (`docs/design/build-spec.md`, "Owner requirement added 2026‑09‑22"). All four vetoes are currently held together as *audit findings against the live build*, not yet all closed in code: D‑1, D‑2 and D‑3 (`audit-2026-09-22.md` §5) name exactly the places the ask-quality and whose-paper rules are not yet fully wired into Ask.

### Consent scopes and keys

Every read of profile data goes through one resolver (`app/keys/__init__.py`: *"`resolve_key_context` is the only way to get a `KeyContext`, and `scoped_select`/`scoped_new` are the only way to touch a row of profile data with one"*). A `Consent` row records what was agreed, in which words, when (`backend/app/consent/__init__.py`). A sharing consent's role and window are **required, never optional** — `docs/adr/0015-…` records that an earlier attempt made them optional and the real web client never sent them, silently unbinding every family grant; the fix made both fields non-defaultable at the API boundary. Scopes named in the corpus: `RECORDS`, `MEDICINES`, `READINGS`, `VISITS`, `FAMILY`, `MONEY`, `EMERGENCY`, `ASK` (`docs/adr/0004-…`, `backend/app/insurance/__init__.py`).

### Row scope

A row is read only under the scope it was written under — fixed in `docs/adr/0004-rows-are-read-under-the-scope-they-were-written-under.md` after per-table scope checks were found to leak rows written under a *different* scope through the same table (a RECORDS key could read a family's WhatsApp messages stored in the same artefact table). *"A reference the key may not follow is withheld by name… never the id, never a silent gap."*

### The audit trail

*"Every read, every write and every share of one person's health graph"* — one writer, one query, gated by the same doors every service reaching profile data goes through; *"The owner and his chief are the only readers"* (`backend/app/audit/__init__.py`). Escalations to the family are recorded once, through one door (`escalate_flag`), replacing three separate, non-sending records that predated it (`docs/adr/0005-…`).

### Region residency

*"Profiles are pinned to a region (SG or MY). Health data never leaves its region"* (`CLAUDE.md`). `app/regions.py` pins every Person/Profile at creation; ambulance number, currency, timezone and drug register all already vary correctly by region (`docs/design/build-spec.md` §0(a)). The one designed exception — a Claude-backed model call — is scoped narrowly and audited as a distinct event: *"Every Claude-backed adapter's bytes reaching Anthropic is audited as a reach outside the region, distinct from an ordinary read or write"* (`docs/adr/0017-…`, decision 3), and is permitted **only** in a declared demo (`NURA_DEMO_MODE=1`) or the owner's own declared dev laptop run (`NURA_DEV_CODE_SENDER=1`) — never on a public deployment (`docs/adr/0017-…`, "Decision" and its 2026‑09‑17 addendum).

### The model-per-task table (ADR 0018)

Before this ADR, every Claude-backed adapter hard-coded the most expensive model regardless of task; one live feed run made *"about 48 Opus calls… and produced one card"* (`docs/adr/0018-model-per-task-cheapest-that-keeps-the-safety-behaviour.md`, "Context"). The fix is one resolved table:

| Model | Tasks | Why |
|---|---|---|
| **Opus 5** | `extract` (reading a paper), `ask` | *"A misread field or a wrong answer reaches a family directly; quality and safety matter most here"* |
| **Sonnet 5** | `analyst`, `search` (needs server tools Haiku 4.5 lacks), `estimate`, `draft` | *"the cheapest model that still supports them"* / checked against guards before being trusted |
| **Haiku 4.5** | `compress`, `clip`, `narrate` | *"short rewrites over text Nura already has, not open-ended reasoning"* |

A run itself is capped independently of the model: `NURA_MAX_JOBS_PER_RUN` (default 6) and a per-call server-tool cap (`SEARCH_TOOL_MAX_USES = 3`) — *"the model decides what one call costs, the cap decides how many calls one run can make"* (ADR 0018, decision 4).

### What runs live vs fixture

Nine model call sites exist in the backend, one per task (`app/llm/models.py`), all through the raw `anthropic` SDK — *"There is no Claude Agent SDK anywhere"* (`audit-2026-09-22.md` §7.1). Every one defaults to a fixture adapter; a real deployment cannot construct any Claude-backed adapter at all outside a declared demo or dev run (`docs/adr/0017-…`). On the demo deployment specifically, `NURA_EXTRACTOR`, `NURA_SEARCHER` and `NURA_COMPRESSOR` all default to `fixture`, reading only from `backend/tests/fixtures/` (`docs/deploy-demo.md` §5): *"That is the safer default for a first deploy: it needs no key, it cannot send anything anyone types to a third party."*

---

## 6. Design

### Visual language — two competing statements

`docs/design/design-build-2.md` §2 (binding from 2026‑09‑22) specifies: *"Deep indigo/violet environment; subtle purple-to-warm gradients; soft radial lighting; translucent surfaces; glass-like cards; large rounded corners… Premium, calm, intelligent, human, cinematic, modern, slightly futuristic."* This directly supersedes the older `docs/design-system.md` §1, which specifies **light** washes ("Mist," "Blush," "Lavender," "Sage") on the premise that *"Glassmorphism fails the elderly… text on a blurred, translucent surface over a gradient drops contrast."* Both documents are still in the repository; `design-build-2.md` is the one marked "binding, from 22 September 2026," so it is authoritative going forward, but the older document's specific accessibility warning about glass-on-gradient contrast has not been re-answered under the new dark visual language — `docs/design/build-spec.md` §10 raises exactly this: *"text-on-glass-on-gradient is a three-layer contrast problem, and the brief's own ≥4.5:1 rule must be checked against the worst-case composite, which a static Figma comp would not catch."*

### Type scale and tokens

`design-build-2.md` §2 calls for Figtree with an Instrument Serif italic accent word per headline; `design-system.md` §2 (older) specifies Outfit throughout. `build-plan.md`'s Checkpoint 1 scope confirms the newer choice is what shipped: *"Figtree and the serif accent bundled into the app."* Measured against the brief's own scale, the shipped app diverges in several places: Welcome's tagline renders at *"31.2px weight 500, line-height 36.8px"* against a brief of *"33px / 1.08 / 300"*; section titles render at weight 700 against an allowed 300–600; captions render as low as 11px against a 12.5px floor (`audit-2026-09-22.md` §4.4, D‑21).

### The card system and tiers

Specified: one `Card` component with named variants (insight, reminder, video/content, metric, recommendation, document, AI summary, action, alert) across three tiers — primary, secondary, tertiary (`design-build-2.md` §5). Built: *"cards are several components"* — `Glass`, `GlassTile`, `TintCard`, `FeedCard`, `MemoCard`, with *"one card component with named variants and three tiers does not exist"* (`design-build-2.md` §2 gap table; `design-build-2-map.md` §3).

### Motion tokens and rules

The one governing principle: *"motion shows real state, never fakes time. Nothing in `web/src/ui/kit` runs an animation on a timer with no state behind it"* (`docs/design/motion.md` §title). Two tokens carry every duration today: `--settle` (220ms) for an entrance, `--press` (90ms) for a tap, both collapsing to 0ms under reduced motion (`motion.md`). The specification calls for a much larger family — `motion.fast/standard/slow`, `spring.gentle/standard/bouncy`, `card.enter`, `sheet.enter`, `orb.idle/listening/thinking/responding` — none of which exists yet: *"No spring family, no per-role tokens, values hard-coded in places"* (`design-build-2.md` §2). The blueprint's own reference file additionally reveals that stagger speed varies empirically with list density (a 5-row lab table staggers at 110ms/row; a 7-row inbox at 80ms/row; a 2-card answer at 300–320ms/card) and that word-reveal pace is not one number (62–90ms/word for headlines, 36–58ms/word for body text, 210ms/word for a spoken video caption) — open questions for whoever builds the single `MotionProvider` (`design-build-2-reading.md`, conclusions #7–#8).

### Orb states

Specified: five states — idle, listening, thinking, responding, error (`design-build-2.md` §8). Built: two — idle and a faster-spinning `.think`, plus a `.lg` breathing size variant used only on Welcome (`design-build-2-map.md` §3; confirmed against the blueprint's own CSS, `design-build-2-reading.md` conclusion #3). The orb's own real-world driver is unresolved: no backend event exists yet to trigger `listening` or `responding` honestly (`design-build-2-map.md` §2.1).

### Loading / empty / error rules

Specified in prose, not "Loading…": *"'Looking through your recent results…', 'Connecting the dots…'"* for loading; *"why, what, next"* for empty and error, *"never an HTTP code"* (`design-build-2.md` §21–23). None of the three has a shared primitive today — *"four places do pieces of one job"* (`design-build-2-map.md` §3, `LoadingState`/`EmptyState`/`ErrorState` rows, all marked **add**). One real measured instance of a correct empty state exists in the live app: *"Nura has no insurance written down for you yet"* (`audit-2026-09-22.md` §2 row 11), alongside six different hand-written rejection strings for the single condition "the terminal stream event never came" (`audit-2026-09-22.md` §7.1).

### Navigation

Five tabs — Home, Health, Connect, Services, Profile — already match the blueprint exactly at the tab-bar level: *"a 1:1 match with the blueprint's `TABS` const… no navigation redesign needed at the tab-bar level"* (`docs/design/build-spec.md` §9). `docs/design/design-build-2.md` §17: *"Minimal bottom navigation… visually quiet, subtle but obvious active state. Content is the hero; navigation is infrastructure."*

### Responsiveness

On the web, the entire app sits inside a simulated 390px phone frame above 600px viewport width, with a real phone rendering full-bleed (`docs/design/build-plan.md`, Checkpoint 1 scope). `design-build-2.md` §26: *"Mobile first. Tablet/desktop widen intelligently, keep card proportions… same hierarchy and interaction philosophy."*

### Accessibility

Contrast 4.5:1 minimum (`build-plan.md`, "Rules that do not bend"); the older `design-system.md` §5 (patient/"Dad" density specifically) is stricter still — 7:1 and above, 20px body minimum, 56px targets. `CLAUDE.md`'s patient-mode rule is exact: *"one thing per screen, no horizontal gestures, no pull-to-refresh, no badges, no autoplay of the next card, 20pt body, 56pt targets, 7:1 contrast, every card has a spoken twin."* Measured against this rule live, several captions fall under the 12.5px caption floor the newer brief sets (11–11.5px — `audit-2026-09-22.md` §4.4, D‑21), and no target under 44px was measured anywhere (`audit-2026-09-22.md` §4.4).

### Languages

Three ship today — English, Malay, Chinese — with every catalogue held to the same table by `make language` (`docs/plain-words.md` §6; `backend/app/language/__init__.py`). Hokkien and Tamil are voice-only, deferred to "T2" (`docs/parity.md`, E11‑04, E15‑05). Thai is named as the next language a fourth country pack would need (`docs/design/build-spec.md`, "Owner decision 2026‑09‑22: ASEAN-ready by configuration").

---

## 7. Architecture

### Backend

FastAPI, one app builder shared by `main` and the tests, serving every route twice — once bare (for `/docs` and the checkpoints) and once under `/api` (for the web client) — from one router (`backend/app/channels/api/__init__.py`). SQLAlchemy models with Alembic migrations; every datetime column goes through one `UTCDateTime` type decorator, because SQLite silently drops timezone offsets that Postgres keeps (`docs/adr/0009-times-are-stored-as-utc.md`). The layout follows the port/adapter shape `CLAUDE.md` prescribes: `identity`, `keys`, `consent`, `audit` (accounts and access); `ingestion` (capture, review); `memory` (episodic/semantic/working, the spine); `state` (six dimensions); `reasoning` (trends, medicines, questions, brief, summary, memo, feeling inference, gaps); `search` (ask); `delivery` (feed, triggers, nudges, escalation); `channels` (app API, WhatsApp); `safety` (boundary, high-risk, red flags, plain words). Model calls are confined to `app/llm/` — one client factory, prompts as files, never a string inlined in an adapter (`backend/app/llm/__init__.py`; `CLAUDE.md`, "backend/CLAUDE.md" reference in the audit).

**Streams.** The current reality is fragmented: *"six bespoke SSE vocabularies"* across `/ask/stream`, `/find/stream`, `/insights/stream`, `/papers/{id}/insight/stream`, `/photos|imports/stream` and `/not-feeling-well/stream`, each with its own event names, its own `_sse()` serialiser copy-pasted five times, and *"four mutually incompatible terminal events for one concept"* (`answer`, `results`, `report`, `card`) (`docs/design/audit-2026-09-22.md` §7.1). This is the single largest engine-side gap the audit names, and it is what the design build's "event vocabulary decision" answers (below).

### Web

Preact ("the kit"), served from `web/src`, with tokens (`ui/tokens.css`), two densities (patient/caregiver), a strings layer (`en`/`ms`/`zh`, tagged `@patient`), and a component kit under `ui/kit` (`CLAUDE.md`, "Layout"). `ADR 0001` made the web client the *first* client and requires it to carry every user story the native plan had, substituting for four platform-only hooks (HealthKit, widgets/Live Activity, the share extension, Siri) with web equivalents (`docs/adr/0001-web-first-client.md`).

### The planned native app

`docs/design/mobile-architecture.md` is also marked **"binding, from 22 September 2026,"** and specifies a full native rewrite: Expo, React Native, Expo Router, Reanimated 4, Gesture Handler, React Native Skia for the orb/ambient/chart layer, Zustand — with Nura's own FastAPI backend and model layer kept (the owner's original stack list named Supabase and OpenAI/a "preferred model layer"; both are explicitly overridden: *"Two of the owner's rows change, for reasons already decided in this repo"* — `mobile-architecture.md` §2). The decision to actually go native is **not yet made**: it hangs on a "Home spike" — Phase 1 and Phase 2 for Home only, judged on the owner's own iPhone against the blueprint's Home, composer, expand and sheet scenes — *"If it clears the bar, design-build-2 steps 8–12 proceed native and this file governs. If it does not, the reasons are written here and the web stack continues"* (`mobile-architecture.md` §5).

> **Contradiction to flag.** The root `README.md` and `CLAUDE.md` both still describe the native client as a **SwiftUI iOS app** (`README.md`: *"`ios/` — SwiftUI app (iOS 17+)"*; `CLAUDE.md`, "Commands": *"iOS: `cd ios && xcodegen generate`… `make ios-test` runs `xcodebuild test`"*), and `docs/health-feed-spec.md` is written entirely against a SwiftUI/`FeedPagerView`/`WidgetKit` implementation. `docs/design/mobile-architecture.md`, dated the same day and marked equally binding, specifies React Native/Expo instead, on the owner's own later instruction. None of README.md, CLAUDE.md or the health-feed spec has been updated to reflect this; as of this document, the repository states two different native-stack decisions simultaneously, and the Home-spike gate that would resolve which one governs has not yet run.

### Data model

Facts carry a validity window and a confidence state — *"immutable, replaced only by supersession"* (`backend/app/memory/__init__.py`); the four core memory primitives are Artifacts (bytes in the region's object store), Events (a moment something happened), Facts (statements with provenance and confidence) and the spine (Providers, Appointments) (same file). Review cards are the one place a proposed, unconfirmed value lives before a person's yes (`backend/app/ingestion/__init__.py`). Policies are typed rows, not yet cited document reads (`docs/design/build-spec.md` §5). Medicine lines carry `generic, brand, strength, form, registration_no, drug_class, high_risk, source_kind, status, change_kind, confidence` (`docs/design/build-spec.md` §6). Feed items are immutable, each stamped with the State snapshot it was rendered from (`backend/app/delivery/feed/__init__.py`).

### The event vocabulary decision (AG-UI shape)

The audit's own recommendation, adopted into the design plan: **"Adopt the event vocabulary over the existing SSE. Do not adopt the library."** (`docs/design/audit-2026-09-22.md` §7.4). AG-UI's roughly sixteen event types — lifecycle (`RUN_STARTED`/`RUN_FINISHED`/`RUN_ERROR`), text (`TEXT_MESSAGE_START/CONTENT/END`), tool calls (`TOOL_CALL_START/ARGS/END/RESULT`), and state (`STATE_SNAPSHOT`/`STATE_DELTA`) — would collapse six incompatible unions into one, give the UI a real place to show a tool call instead of an opaque localised sentence, and let an unknown event become a typed no-op instead of a silent drop (`audit-2026-09-22.md` §7.1, §7.4). Adopting the AG-UI *library* is explicitly rejected — it would bring in integrations the repo does not use and would violate the "never assume the orchestrator" instinct the audit itself applies by analogy (`audit-2026-09-22.md` §7.4). `docs/design/design-build-2.md` §4, design step 6, schedules this work (~20h) as a precondition for the orb's five states to be driven by anything real.

---

## 8. Status and plan

### The 24 work packages

Per `docs/design/build-plan.md`'s own progress table (Done / done-with-caveats / Not started; percent complete counted as done packages ÷ 24, "a count, not a forecast"):

| # | Package | State |
|---|---|---|
| 1 | The look, phone frame, shared components | **Done** |
| 2 | Build spec (doc) | **Done** |
| 3 | Report data: labels, ranges, no blank lines | **Done** |
| 4 | Reading screen and report table | **Done**, polish deferred to `papers-library` |
| 5 | Insight engine after a paper | **Done** |
| 6 | New Home with the living orb | **Done** |
| 7 | "What it means for you" wired after "Looks right" | **Done** (after being rejected and rebuilt once) |
| 8 | Ask Nura interface | **Done**; answer-quality follow-up in `ask-quality` |
| 9 | Onboarding: Welcome, sign in, who is this for, bubble cloud | **Done** (after a rejected first pass) |
| 10 | Health and Health Analyst screens | **Done** (after a rejected first pass) |
| 11 | Medicines screens | **Done**; voice add not built |
| 12 | Visits and costs, Insurance | **Insurance half done**; visits and costs **not started** |
| 13 | For you feed screens | **Done except the live web-search run** |
| 14 | Not feeling well, Connect, Mei's Home, Profile | **Not started** |
| 15 | Feed database-lock fix, failed searches retried | **Done** |
| 16 | Streamed reading (rows as they're read) | **Not started** |
| 17 | Cost of a procedure with no visit booked | **Not started** |
| 18 | The inbox for many papers | **Not started** — needs owner decisions |
| 19 | The matching engine and its verdicts | **Not started** — needs owner decisions and real papers |
| 20 | Policy passport | **Not started** — needs real policies |
| 21 | Medicine registry and Add a medicine | **Not started** — needs the country decision |
| 22 | Connections and content in context | **Not started** |
| 23 | Merge to main, full checks, full pass as Pa and Mei | **Not started** |
| 24 | ASEAN-ready country packs | **Not started** |

At the point `docs/design/build-plan.md`'s log ends, the count stood at **13 of 24**.

### The audit's ranked defects

`docs/design/audit-2026-09-22.md` §5 ranks 26 defects (D‑0 through D‑25). The four rated **Critical**: **D‑0** (Profile freezes the app on WebKit/Safari within 500ms — the only engine on an iPhone), **D‑1** (Ask cannot state a value from a confirmed paper — no catalogue template exists for any non‑blood‑pressure measurement), **D‑2** (nothing checks whose paper it is, and a wrong person's data can overwrite the profile's own birth year and sex), **D‑3** (a conclusion-language drop discards an answer with no record of why, so the repair round never fires). The audit's own recommended build order (§6) is: D‑0 first ("everything else is cosmetic next to an app that stops on his phone"), then D‑3/D‑7/D‑1 ("make Ask able to say a fact it already holds… it is the owner's complaint"), then D‑2 ("nothing else should be filed until this exists"), then D‑4 (duplicates), then the two unreachable promised behaviours (D‑5, D‑6), then memory correctness (D‑8, D‑13), then a wording-and-type pass, then the three structurally wrong screens (Health's chart, Medicines' list, the onboarding cloud), then packages 14 and 12 ("the four screens that read as 'a different app' to him"), then Part D's minimum agentic-layer change.

### Design build 2's twelve steps

`docs/design/design-build-2.md` §4 lays out twelve steps from "Analyse the reference" through "Test every interaction," interleaved explicitly with the audit's own engine-fix order: *"Steps 0–5 of the audit's order… run first and in parallel with design steps 1–5, because they change what the screens can truthfully say. Design step 6 carries the event vocabulary. Design step 9 carries the judge and the unified context."* As of this document, step 1 ("Analyse the reference," `design-build-2-reading.md`) and step 2 ("Interaction map," `design-build-2-map.md`) are both drafted and awaiting the owner's confirmation — both files' own headers say **"Status: draft for owner confirmation."** Steps 3 onward (architecture, tokens, motion system, core shell, Home, expandable/detail, AI interaction, secondary experiences, polish, testing) have not started.

### The Home spike decision

Not yet run. `docs/design/mobile-architecture.md` §5: the spike is Phase 1 + Phase 2 for Home only, against the real backend, judged on the owner's own iPhone against the blueprint's Home, composer, expand and sheet scenes — the gate that decides whether the native rewrite proceeds in React Native/Expo or the web stack continues through design steps 3–9.

### What the owner can test today

Per `docs/design/build-spec.md`'s own testing note: always the same place, `http://localhost:8000/app/`, running the last build that reached a checkpoint — *"never work in progress"* — signed in as *"Try it as Pa"*, *"Try it as Mei,"* or a real number; individual components can be tried in isolation at `http://localhost:8000/app/#/blueprint-kit` (`docs/design/build-plan.md`, header). `docs/design/build-plan.md`'s own log entry for 2026‑09‑22 records the owner's own definition of "Test Day 1" — register, set up profile and health details, load documents including medicine boxes and insurance papers, get a first personalised video and web feeds, insights on the record, and a multi-turn conversation with natural clarifying questions — with doctor appointments explicitly coming after. That request re-sequenced the remaining build order toward packages 7, 9, 10, 11, the insurance half of 12, and 13, plus Ask's answer quality and clarifying questions (`build-plan.md`, log entry, "Owner defines the first real test run").

---

## 9. Glossary of Nura's own words

| Word | Meaning | Source |
|---|---|---|
| **Paper** | Any document — a lab result, a prescription, a letter, a policy, a receipt — never "document" or "record" to the patient. | `docs/plain-words.md` §2: "Feed, timeline, record" → "Your Today page. Your papers." |
| **Card** | One self-contained unit on the feed or Today page: a headline, body, why-line, source, one action. | `backend/app/delivery/feed/__init__.py`; `docs/health-feed-spec.md` §2 |
| **"Looks right"** | The one confirming tap over a review card — never "Confirm," "Submit" or "Approve." | `web/src/strings/en.ts:1760` |
| **Waiting papers** | A paper extracted but not yet confirmed; nothing from it is stated as fact until the person's yes. | `web/src/strings/en.ts:938`, `:645`; `build-plan.md` package 8 log ("waiting papers named without any of their values") |
| **Story** | The vertical feed's recall section: cards drawn from a person's own record — what the doctor said, how a number changed, a family photo. | `docs/health-feed-spec.md` §0; `web/src/strings/en.ts:874` |
| **Clip** | A short (20–30 second), captioned, sourced video excerpt specific to the person's own medicines or conditions. | `docs/health-feed-spec.md` §2 |
| **Chief** | The key role with the fullest scope short of the owner — Mei's role in the demo seed. | `docs/deploy-demo.md` §3a; `docs/design-system.md` §3 |
| **Caregiver** | A narrower key role (RECORDS-holding, typically no FAMILY), distinct from a chief. | `docs/adr/0002-…`, decision 6 |
| **Scope** | One of a fixed set of named permissions (RECORDS, MEDICINES, READINGS, VISITS, FAMILY, MONEY, EMERGENCY, ASK) that gates every read and write of a profile's data. | `backend/app/keys/__init__.py`; `docs/adr/0004-…` |
| **Boundary** | The rule, and the copy, that keeps Nura from diagnosing, treating or advising — every inferring surface must carry its own boundary line. | `backend/app/safety/__init__.py`; `docs/adr/0002-…`, decision 12 |
| **Red flag** | A symptom or word the app never waits to act on — escalated before any ranking, cap or delay. | `backend/app/safety/__init__.py` |
| **State** | The six-dimension model recomputed on every new fact; every card names the State it was rendered from. | `backend/app/state/__init__.py` |
| **Ladder** | The one escalation record — who was told, in what order, whether they answered. | `docs/adr/0005-the-ladder-is-the-one-escalation-record.md` |
| **Pattern** | A reviewed, arithmetic-only comparison across a person's own record, kept deliberately separate from State — never a Fact, never folded into posture. | `docs/adr/0016-correlation-sits-beside-state.md` |
| **Consent** | A recorded, versioned, revocable agreement — never inferred, never defaulted. | `backend/app/consent/__init__.py` |
| **Demo mode** | A declared, banner-carrying, nightly-wiped deployment that may run on fixtures and test-only phone numbers — never mistakable for a real deployment. | `docs/adr/0008-demo-mode.md` |

---

## Where the sources disagree

1. **Scene count: 25 vs 26.** `docs/design/build-spec.md`'s own header describes `experience-blueprint.html` as having "25 scenes"; every other document that counts them (`design-build-2.md`, `design-build-2-reading.md`, `audit-2026-09-22.md`) says 26, and a direct extraction of the HTML's own `SC` array confirms 26. `build-spec.md` is the outlier.

2. **The caregiver's name: Ash vs Mei.** The root `CLAUDE.md` ("Domain vocabulary") and the older `docs/design-system.md` name the caregiver **Ash**. Every 2026‑09‑2x design document and the live demo seed (`docs/deploy-demo.md` §3a) name her **Mei**. Neither older document has been updated to match.

3. **The native client's stack: SwiftUI vs React Native.** `README.md` and `CLAUDE.md` describe a SwiftUI iOS 17+ app under `ios/`, with `xcodegen`/`xcodebuild` build commands; `docs/health-feed-spec.md` is written entirely against that SwiftUI implementation. `docs/design/mobile-architecture.md`, dated the same day and marked equally "binding," specifies Expo/React Native/Reanimated/Skia instead, on the owner's later instruction — and explicitly gates the actual decision on an unrun "Home spike." As of this document neither older file has been reconciled with the newer one, and the gate that would resolve the contradiction has not run.

4. **The visual language: light glass vs dark dusk-glass.** `docs/design-system.md` (older) specifies light washes (Mist, Blush, Lavender, Sage) on Outfit type, with an explicit accessibility argument against heavy glassmorphism for an elderly reader. `docs/design/design-build-2.md` (newer, "binding from 22 September 2026") specifies a deep indigo/violet dark environment on Figtree + Instrument Serif. `build-plan.md`'s Checkpoint 1 log confirms the newer, dark language is what actually shipped, but the older document's specific contrast warning about text on blurred glass over a moving gradient has not been re-answered under the new palette — `build-spec.md` §10 raises the identical concern independently, against the new visual language, unresolved.

5. **What `docs/health-feed-spec.md` describes vs what exists.** The whole document is written against a SwiftUI/iOS implementation (`FeedPagerView`, `WidgetKit`, `AVQueuePlayer`) that predates `docs/adr/0001-web-first-client.md`'s decision to build web first. Its acceptance criteria and architecture section describe screens and components that do not exist under those names anywhere in `web/src` or the current `ios/` scaffold; its card-type table and safety rules (§0–§2, §7) remain the accurate, current specification, cited throughout §4 of this document, but §6 ("iOS implementation") is stale against the actual client.
