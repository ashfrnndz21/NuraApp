# SaMD boundary review: HSA (Singapore) and MDA (Malaysia)

**Story** E16-03 · **Acceptance** written review signed off before any flag ships · **Status** draft for the regulatory adviser; nothing in this table ships a flag

Nura works things out from the record: how the day should be held, what to ask the doctor, what the doctor said, whether two medicines are a question to raise. Software that works things out about a person's health can be a medical device. This review states the regulatory question in each country, the product's position, and — surface by surface — what is computed, where any clinical rule comes from, whether it is real-time, the plain-words boundary line it shows, and the test in this repository that proves the boundary holds. It ends with the residual risks, the things that would move the product across the line (so the team knows what not to build), and the questions for the adviser.

**Scope.** The T1 inference surfaces. E09-03 (cross-signal correlation and pattern flags) is a T2 story and is out of scope here; this review is revisited before it ships. Feeling inference (E17-02) and question generation (E05-02) are in scope as T1 surfaces, on the operator's decision of 14 September 2026.

---

## 1. The regulatory question

**Singapore.** The Health Products Act and HSA's *Regulatory Guidelines for Software Medical Devices — A Life Cycle Approach* decide whether software is a medical device by its intended purpose: software intended for diagnosis, prevention, monitoring, treatment or alleviation of disease is a device; software that only stores, communicates or displays information, or supports general wellness, is not. HSA's treatment of clinical decision support turns on whether the software *informs* a clinical decision a person can independently review, or *drives* one. (Citations and current edition to be verified by the adviser.)

**Malaysia.** The Medical Device Act 2012 (Act 737) and MDA's guidance on medical device software classify by intended use and risk (Class A to D), with the *Guidance Document on Medical Device Software* setting out which software is a device at all. `docs/build-plan.md` §5 names the line the product must stay under: Class B is where software that influences treatment decisions begins. (To be verified by the adviser.)

The question for both is the same: **is any output of Nura intended to diagnose, treat, or drive a clinical decision about the person?**

## 2. The product's position

Nura organises, prepares and surfaces patterns to discuss. It does not diagnose or treat, and it does not tell anyone to start, stop or change a medicine. Everything it infers is:

- **guideline- or record-referenced**: every clinical rule comes from licensed drug data, a published guideline, or the person's own record — the word a clinician already wrote, the dose already on the label. The model writes the sentence, never the pharmacology (`CLAUDE.md`);
- **non-real-time**: it works from what has been written down, on the day's rhythm, never from a live stream of readings; there is no monitoring loop and no alarm;
- **informational**: it prepares a person for a conversation with a clinician and hands the decision to that conversation. Every inferring surface carries the boundary line: *This is not a doctor's advice. Ask Dr Tan.*

Three structural facts hold this in place, and each has a test: nothing infers without provenance (`ck_fact_has_provenance`; `tests/test_memory.py`), nothing renders without State (`RenderedFromState`; `tests/test_state.py`), and nothing changes a medicine or books anything without a person's explicit confirm bound to what was shown (`app/keys/confirm.py`; `tests/test_medicines.py:184`).

## 3. The boundary line

`backend/app/safety/boundary.py` holds the register of inferring surfaces (`INFERRING_SURFACES`) and the words each carries, in English, Malay and Chinese, tagged `@patient` and checked by `make plain-words`. Every surface's line ends on the same two sentences, so he hears the same words wherever he is:

| | |
|---|---|
| English | This is not a doctor's advice. / Ask Dr Tan. |
| Malay | Ini bukan nasihat doktor. / Tanya Dr Tan. |
| Chinese | 这不是医生的意见。/ 问 Dr Tan。 |

The first line says what Nura did on that surface, and no more (`WHAT_NURA_DID`). The line is structure, not convention: a rendered row for an inferring surface names its `Surface` and cannot be written without the register's line for it — `render_from_state` refuses the row (`NoBoundaryLine`), the way it refuses a row with no State; the mixin carries the line in a `boundary` column. `tests/test_boundary.py` holds the register to the table below, refuses the row without its line, and shows the one surface on main today carrying it on `GET /state`.

The not-feeling-well card is the one surface that says more: it opens with a reassurance ("Ash knows now." or "You did right to say so.", rule 9), then what Nura did, then — where a Fact holds the discharge letter's own instruction — those words in the letter's name ("Dr Tan wrote this in your hospital letter."), and the boundary last. No other surface may carry a letter.

## 4. The T1 inference surfaces

Real-time means computed from a live signal as it arrives. Every surface below is computed from the record after a person has confirmed what went in.

| Surface | What it computes | Source of any clinical rule | Real-time | Boundary line (first line, English) | Test that proves the boundary |
|---|---|---|---|---|---|
| `state_posture` | The posture of the day — stable, watch, act — and the six dimensions, from facts already confirmed. Posture is the wash on the screen and the order of the feed, never a finding. | The person's own record only: a posture rises from a clinician's control word already in the record, a discharge, an admission, a visit window. No threshold on any reading lives in State (`app/state/dimensions.py:1`). | No | Nura put your day in order. | State never rises from a number: `tests/test_state.py:130`; it follows the clinician's word: `tests/test_state.py:149`; an unreadable word is kept and not settled: `tests/test_state.py:194`; a disputed fact does not move State: `tests/test_state_acceptance.py:142`; the line is on `GET /state`: `tests/test_boundary.py` |
| `interaction_flag` | Whether two active medicines are a pair the licensed data flags, and the severity the data gives it. Rendered as a question for the doctor, never as advice. | Licensed drug data only (`app/drugs`); the model does not write pharmacology. Dose changes are the same: a different amount on a new label is a question, never the new amount as an instruction. | No | Nura is only asking a question about your medicines. | Screened before saved, flag names both, rendered as a question: `tests/test_medicines.py:292`; an interaction is a question in his words: `tests/test_medicine_story.py:185`; a dose change is a question and never the new amount: `tests/test_medicine_story.py:165`; supersedes only with his yes: `tests/test_medicines.py:184`; a register that does not know a label does not guess: `tests/test_medicines.py:101` |
| `brief` | The pre-visit brief: what changed since the last visit, from the record. (E05, not on main yet.) | The person's own record; no clinical rule. | No | Nura prepared this from your papers. | The line exists in every language and a brief row cannot be written without it: `tests/test_boundary.py`; the surface's own test is owed by the E05 PR (follow-up note in the E16 PR) |
| `questions` | Questions for the doctor generated from the record: gaps, changes, things the person said. (E05-02.) | The person's own record; any medical framing is a question, not a statement. | No | Nura wrote these questions for you to ask Dr Tan. | `tests/test_boundary.py` (no line starts, stops or changes a medicine, in any language); the surface's own test owed by E05 |
| `summary` | What the doctor said, from the recording, in the patient's language, and the memo in his words. (E05.) | The doctor's own words; Nura restates, it does not add. | No | Nura wrote down what Dr Tan said. | `tests/test_boundary.py`; runtime text passes `plain_words.verify` before it reaches him (`tests/test_plain_words.py`); the surface's own test owed by E05 |
| `learning_card` | Which short explanation to show, chosen from State, and the few lines it becomes: an allowlisted page compressed into his language, citing the passage it came from. A safety notice, the same compression of a regulator's page, is the same surface. (E21.) | Allowlisted publishers only, approved in the pharmacist's review (`app/delivery/feed/sources.py`); an uncited compression is rejected, and a line that would change treatment is not a card but a question for the doctor, held for the memo (`app/delivery/feed/search.py`). No clinical rule. | No | Nura explains one thing in simple words. | Every learning card and notice ends on the line and carries it on its row; a card without it, or a card that infers nothing with one, is not made: `tests/test_feed.py`; the line is on the card over HTTP: `tests/test_feed_api.py`; a source off the allowlist is refused: `tests/test_feed.py`; a treatment change becomes a question for the memo: `tests/test_feed_api.py`; words in every language: `tests/test_boundary.py` |
| `feeling_inference` | A pattern in how he said he feels, offered as a thing to talk about. (E17-02.) | The person's own check-ins, read against a new medicine's licensed monograph rule ids, the direction of his own blood pressure, and a visit or discharge this week; no diagnostic rule, no threshold. | No | Nura noticed this in how you said you feel. | `tests/test_boundary.py` (words in every language; no line starts, stops or changes a medicine in any of them; the reassurance first; the letter's words only in the letter's name); the surface's own: `backend/tests/test_feelings_inference.py` (every note ends on this line and is rendered from State; at most two things to tell the doctor, each naming its reason by id; a medicine only where its licensed monograph lists the feeling; no template starts, stops or changes a medicine or names a condition, in any language; a red word or a yes that makes one red takes the red-flag path and makes no note) |
| `not_feeling_well` | Who to tell and whether today or not a worry, from the roster and the person's own discharge instructions. | The person's own hospital letter and conditions (the red-flag list in `.claude/rules/safety.md` is the letter's own words, carried on the card only where a Fact holds them, in the letter's name: "Dr Tan wrote this in your hospital letter"). | No | You did right to say so. / Nura wrote down how you feel. On a red flag the card is urgent: the reassurance, the calls, then "Nura does not decide what is wrong." — never "Ask your doctor." after an emergency number. | `tests/test_boundary.py` (words in every language; no line starts, stops or changes a medicine in any of them; the reassurance first; the letter's words only in the letter's name); the surface's own test owed by its PR |
| `recall` | Which things on his own record a question is about — a reading, a visit, a medicine line, a paper — said back in template lines filled only with the values of what each line cites, every cited line naming the ids it rests on. (E03-05.) | The person's own record only. Which things a question is about is decided behind a port (`app/search/retrieve.py`): keywords by default, a fixture in the tests; no model is called and none writes a line. A question that would change treatment gets a question for the doctor, never an answer. | No | Nura looked in your papers. | Every answer ends on the line, the honest line when nothing answers ("Nura does not have that written down."), a treatment question rerouted to the doctor, every cited line citing ids that exist, and every line passing plain words: `tests/test_recall.py`; over HTTP: `tests/test_timeline_api.py`; words in every language: `tests/test_boundary.py` |

Two rules the table rests on, and their tests:

- **A dispute keeps the person's number.** When an extraction disagrees with what a person confirmed, the person's number stays current and State does not move until a person settles it: `tests/test_memory_review.py:560`; `tests/test_state_acceptance.py:142`.
- **Anything below the confidence threshold is asked, not assumed.** A review-card field the extractor was unsure of is shown dotted and must be confirmed or corrected; nothing is stored silently: `tests/test_ingestion.py:349`.

### The high-risk drug rule (E16-04)

The rule that most directly touches treatment is the one that refuses: a dose of warfarin, insulin, digoxin, methotrexate or an opioid is saved from a label photo and never from words alone. It is a hook under the memory store (`app/safety/high_risk.py`), so it holds for every writer path — the review card, the medicines module, a WhatsApp message, a voice note — and the refusal is on the audit trail. `tests/test_high_risk.py` is the rule's own suite; `tests/test_high_risk_conformance.py` is the story's acceptance line walked end to end: every generic from a voice note and from a photo, the review card's fact shape from every non-photo artefact, the WhatsApp shape, the medicines route over HTTP, the review-card route, and the readings route, which cannot express a medicine at all. The suite walks every generic name in every class, not one per class: the review found methadone missing from the opioid list, and a representative cannot catch an absence. The oral anticoagulants that share warfarin's risk are in the anticoagulant class too. The rule is a product safeguard on data entry, not a clinical judgement: it decides what is good enough evidence of what the doctor prescribed, never what the dose should be.

## 5. Residual risks

1. **The posture word can be read as a verdict.** "Watch" is a clinician's word carried over, but on a screen it can look like Nura's opinion. Mitigation: the wash is colour and order, never a sentence; the boundary line is under it; the caregiver view shows the source of every driver.
2. **Questions can carry an implication.** "Ask Dr Tan whether the water pill is right for your kidneys" implies a concern. Mitigation: questions name the fact they come from and never a conclusion; the plain-words verifier refuses red words; the reviewer checks rule 8 (the question he would actually ask).
3. **A summary can restate a doctor's instruction as Nura's.** Mitigation: the summary names the visit and the recording; the memo is in his words; the line "Nura wrote down what Dr Tan said" is on it.
4. **The red-flag list looks like triage.** Mitigation: it is the discharge letter's own instructions, surfaced in the letter's name; it bypasses ranking because the letter said "today", not because Nura decided; this is question 4 for the adviser.
5. **Translation drift.** A Malay or Chinese line could carry a stronger word than the English. Mitigation: a native speaker's pass before the first family; the verifier's shared rules run in every language.
6. **The learning supply.** An explainer about a condition, shown to a person with that condition, is not advice, but it is close — and E21 compresses the page into a few lines for him, so the words on the card are written per person from a publisher's page. Mitigation: only allowlisted publishers the pharmacist approved; every card cites the passage it came from and an uncited compression is rejected; a line that would change treatment is rerouted as a question for the doctor, never a card; every card names its State and ends on the boundary line; the compressed lines pass the plain-words verifier before the card is made.

## 6. What would move the product across the line

The team does not build these without a new review:

- A threshold on any reading — "138 is high" — anywhere State, delivery or reasoning can see it. Trends are shown; they are not judged.
- Anything computed from a live device stream, or any alarm that fires without a person having written something down.
- A dose calculation, a dose suggestion, or an instruction to start, stop, change, skip or double a medicine. A different amount is a question.
- An individualised risk score, a probability, or a "most likely cause".
- A recommendation of a level of care ("go to A&E") that is Nura's rather than the hospital letter's own words.
- Booking, rescheduling or messaging a clinic without a person's confirm.
- Pharmacology, interactions or dosing from a model rather than the licensed data.
- Closing the loop with a clinic in a way that lets Nura's output stand in for a clinician's decision.

Any of these changes the intended purpose and therefore the classification; the review is redone first, and the boundary lines are re-read for whether they still tell the truth.

## 7. Questions for the regulatory adviser

1. Does HSA regard software whose every clinical rule is the person's own record or licensed reference data, with no threshold and no real-time input, as outside the definition of a medical device, or as a device that qualifies for the lowest class? Which edition of the software guidelines applies at our submission date?
2. Under MDA's software guidance, does "prepares questions for the doctor from the record" influence a treatment decision in the Class B sense, or is it information management? What evidence would MDA want to see for the position that it does not?
3. Is the interaction question — two medicines the licensed data flags, rendered as "Ask Dr Tan about taking these together" — clinical decision support in either country's sense, given that the pair and the severity come from licensed data and the person can review the source?
4. The red-flag list repeats the discharge letter's own "come back today if" instructions and escalates them ahead of everything else. Is repeating a clinician's instruction, in the clinician's name, a triage function?
5. Does the boundary line's wording — "This is not a doctor's advice. Ask Dr Tan." — satisfy what each regulator expects an informational product to say, and where in the app and the listing must it appear (App Review 1.4.1 asks for the same)?
6. Does the T2 pattern-flag story (E09-03: correlation across signals, phrased as things to raise) cross the line as described, and what would keep it on the right side?
7. Are there labelling, quality-system or post-market obligations that attach even to software the regulator does not classify as a device, that we should meet from T1?
8. Does a translation of a boundary line count as a change to labelling that needs recording?

## 8. Sign-off

| Country | Adviser | Date | Outcome |
|---|---|---|---|
| Singapore (HSA) | | | |
| Malaysia (MDA) | | | |

No flag ships before both rows are filled, and the review is revisited before E09-03.
