# The experience — journey, upload, search and the feed engine

Simple in front, intelligent behind. This document describes what the person experiences end to end, and what the backend is doing at each step.

---

## 1. The whole journey

**Day 0 — Ash sets up (20 minutes).** Who Pa is, who the family is, roles, language. Then the health biography: Ash photographs the shoebox — discharge letters, lab reports, appointment cards, the bag of medicines — in one sitting. The system groups pages by date and provider, extracts, reconciles, builds the timeline, the medicine list and the providers directory, and shows Ash a single review: "Found 4 conditions, 6 medicines, 3 doctors, 11 results across 2 years. Two things to confirm." Behind the scenes the State model initialises and the first self-search jobs are queued for each condition and medicine.

**Day 1 — Pa receives.** A WhatsApp voice note in his language introduces the app in one sentence. The morning card arrives with breakfast: today's medicines. He taps Taken. Nothing to set up, nothing to read that isn't about him.

**Week 1 — the feed fills.** Explainers for his conditions and medicines appear as 20–30 second cards in his language, one or two a day, each saying why it's there. He snaps a meal and gets a verdict. He asks "when did I last see Dr Tan?" and hears the answer. Ash sees what he opened.

**Before a visit.** Three days out: the brief, the questions, the logistics, GL status. The feed shifts to visit mode. Ash adds a question from her own search ("has his potassium ever been high?"). Pa gets one card with the questions.

**The visit.** Ash records with consent. The transcript lands in the record.

**After.** A summary in Pa's language within minutes. Medicine changes become proposals for Ash to confirm. The memo card captures what was agreed. The feed responds: an explainer for the new medicine, the next recheck on the radar, a compressed clip of the one thing the doctor stressed.

**Ongoing.** Every new fact — a result, a reading, a dose change, a note from Mei — recomputes State, which reranks the feed and may trigger a search. The weekly recap clip goes out on Sunday. If something drifts, the wash changes colour and the caregiver on duty hears about it before Pa is nagged.

---

## 2. Uploading records

There is one Add button and it is everywhere: the camera icon in the search bar, the Records tab, and the app's WhatsApp number.

**What can be added.** Photos of paper. Screenshots of hospital or insurer apps. PDFs from portals and email. Photos of medicine boxes, labels and receipts. Consult recordings. Voice notes. Forwards on WhatsApp. Bulk selections of thirty photos at once.

**What happens next, visibly.** A short progress card shows the work: read the pages; identified the document (lab panel, imaging report, prescription, discharge summary, receipt, insurance letter, appointment card); dated it; linked it to the provider, the episode and the nearest appointment; checked it against medicines and past results; prepared an explainer. Then a review card with the extracted fields, solid underline for confident values and dotted for ones to check, and one button. The card ends with what changed as a result: "Filed under Kidneys. A 20-second explainer is on the feed. One question added for Thursday."

**What happens next, invisibly.** Deduplication against existing artefacts. Trend recomputation for any analyte. Interaction check for any medicine. State update. Feed rerank. Search jobs fired for anything new (a new drug, a new diagnosis, a new procedure). Provenance links written so every downstream card can cite the page.

**How it's organised.** No folders. The person sees the record four ways: by time (the timeline), by body system (the map), by provider, and by type. Everything is also reachable by asking.

---

## 3. Search

One bar. The system decides silently whether the question is about him or about the world, and answers with cards.

- **Ask about him** — runs over memory: records, transcripts, readings, notes. Answers cite the artefact and play the clip at the timestamp where a doctor said it. "Has his potassium ever been high?" returns the values, the dates, the consult remark, and offers to add it to the visit questions.
- **Find in the world** — runs web, video and provider searches scoped by his State. "Best cardiologist for a second opinion in Penang" is answered with reasons drawn from his record and the panel list, not a generic list.
- **Act** — "order the metformin", "add this to Thursday's questions", "send Pa the kidney explainer". Confirmed before anything leaves.

Pa's version is voice-first with the same three behaviours. Ash's version has filter chips (Records, Web, Providers, Videos) and shows sources.

---

## 4. The feed engine

### What goes in

Two kinds of raw material.

**Personal signals** — every fact in the record and every change to State: results, readings, medicines, appointments, confirmations, family notes, memos.

**External knowledge, found by self-search.** The system runs its own searches on the person's behalf. Jobs are created from State and re-run on a schedule or on change:

| Job | Trigger | Sources | Cadence |
|---|---|---|---|
| Explainer for a condition or medicine | New diagnosis or drug | Health authorities, hospital groups, professional societies, their video channels | On change |
| Safety and recall notices | Any medicine on the list | HSA, NPRA, manufacturer notices | Daily |
| Local environmental risk | Address and conditions | State and city health offices | Daily |
| Food and lifestyle relevant to his conditions | Conditions, culture, season | Dietitian associations, hospital nutrition pages | Weekly |
| Provider signals | Upcoming visit or navigation request | Hospital sites, panel lists, waiting-time pages | Before visits |
| Procedure preparation | Scheduled procedure | The hospital's own patient pages | On scheduling |

Sources are allowlisted. No supplement marketing, no forums, no content that contradicts his doctor's plan without being framed as a question for the doctor.

### Compression

Everything found is compressed to the part that applies to this person.

- **Text** → three sentences and one action, in his language, with the source named.
- **Video** → transcribed, the relevant 20–30 seconds identified against his State, narrated in his language over a still or a short excerpt, captioned, with a link to the full video. The compression is per person: the same cardiology video yields a different 30 seconds for someone on a diuretic than for someone with a stent.
- **His own data** → one number, one direction, one sentence ("slightly higher than June, not urgent"), and a question for the next visit if warranted.

### Ranking

Every candidate card gets a score from State: urgency (is there a dose or a visit?), relevance (does it touch an active condition or medicine?), novelty (has he seen this?), format fit (does he open text, or only voice?), and freshness. The top three form "Now" and "For you today". The rest is "explore" below, in order. Caps per day per persona. Decay so nothing lingers. Every card carries "why you're seeing this" and can be dismissed, which feeds back into ranking.

### Feedback

Opened, played, replayed, dismissed, asked-more. Ash sees this for anything sent to Pa. If he never opens text, the system switches to voice notes; if he ignores clips, it tries cards. The format adapts, not the person.

### Recommendations

Providers, meals, next steps, content and questions all come through the same engine with the same rules: derived from State, reasons shown, sources cited, confirm before acting. The boundary line sits in caption size on anything that infers.

---

## 5. What Ash sees of the engine

The caregiver's Home shows the machinery in plain words: the questions she's asked and their answers, a "Watching for Pa" list of the active search jobs and their cadence, and "Sent to Pa this week" with what he opened. She can add a watch ("look out for anything about this new tablet"), pause one, or push any found item to Pa in his format.

---

## 6. What Pa sees of the engine

Nothing. A feed that is short, in his language, about him, with a reason on every card and a big play button on the ones that speak.
