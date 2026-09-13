# Medications module — photo-first design

Extends module C of the Stage 1 design. Principle: **a photo is the only input; a tap is the only confirmation.** Nobody fills a table.

---

## 1. What a photo can teach the system

Five kinds of photo, each carrying different facts. The agent asks for the next photo only when the first one leaves a gap.

| Photo | What it reliably gives | Where it's found in MY/SG |
|---|---|---|
| **Pack front** (box, bottle, strip) | Brand, generic, strength, form, tablets per pack, registration number (Malaysia MAL number, Singapore SIN number), expiry | Every retail purchase |
| **Dispensing label** (sticker on the bag or box) | Patient name, drug, dose, frequency, quantity dispensed, date, clinic or pharmacy, sometimes "with food" | Government hospital and polyclinic pharmacies, private clinics, chain pharmacies |
| **Receipt** | Price, quantity, pharmacy, date | Retail purchase |
| **Prescription** (often handwritten) | Intended drug, dose, duration, prescriber | Private GP, specialist |
| **What's left** (strip or bottle) | A recount to recalibrate the running count | Any time |

A pharmacy bag laid on the table usually has three of these in one frame. One photo, three sources, cross-checked.

---

## 2. The inference chain

Every step produces a value, a confidence and a source. Ash (or Dad) sees the result as one card and taps to confirm. Low-confidence fields are asked as a single tap-or-voice question, never as a form.

1. **Identify the drug.** Vision + OCR on the pack and label. Brand → generic via the local product registries (Malaysia NPRA product register, Singapore HSA register) and a licensed drug database. The registration number on the pack is the strongest key; brand name and strength are the fallback. Local generics (Malaysian and Indian brands) are resolved here, not guessed.
2. **Strength and form.** From the pack. Half-tablet and split-dose regimens are inferred from the label ("½ biji") and confirmed.
3. **Dose and frequency.** From the dispensing label, parsed in Malay and English ("1 biji, 2 kali sehari", "1 tab BD", "1 tablet twice daily"). If the label is missing, the agent asks one question by voice: "How many times a day did the doctor say?" It never silently defaults to standard dosing for drugs with variable regimens.
4. **Quantity.** In priority order: label ("Qty 60"), pack count ("28 tablets"), receipt quantity, blister count from the image (cells × strips). Loose pills in a bottle are not counted; the agent asks for the label.
5. **Match to the record.** Same drug and strength as an existing line → refill. Same drug, different strength or frequency → dose change, flagged to Ash with the source. New drug → new line, interaction check runs before it's saved.
6. **Compute supply.** Days supply = quantity ÷ daily dose. Running count = quantity − doses confirmed since dispensing. Reorder date = today + (running count ÷ daily dose) − lead time. Lead time is per source: 2–3 days for a retail pharmacy, longer for a hospital pharmacy refill appointment or medicine-by-post.
7. **Safety screens.** Interactions against the full list including supplements and TCM; duplicate therapy; Beers, STOPP and START criteria once the list reaches five or more. Output is talking points for the next visit, never an instruction to stop.
8. **Generate the medication story.** What it treats, tied to his own condition in the record ("for your blood pressure", not "hypertension"); how it works in one sentence; when and how to take it; what to look out for that matters for him; what to avoid; what to do if a dose is missed. Rendered in his language as a card and a voice note.
9. **Confirm.** One card. Tap. Done.

---

## 3. "How many left" without counting

The running count has three inputs and the system says which one it's using.

- **Dispensed quantity** from the label or pack: the starting point.
- **Confirmed doses** from "Taken" taps by Dad or the helper: the ground truth as it accumulates.
- **Scheduled doses** where taps are missing: the system assumes the dose was taken for supply purposes (conservative for reordering) and treats it as unconfirmed for adherence.

When the estimate drops below seven days, or when confirmations have been sparse, the card asks for a recount photo: "Snap what's left." Blister strips are counted from the image; the count replaces the estimate. This happens a few times a month at most.

PRN (as-needed) medicines count down by taps only. Syrups and insulin count in doses or units, not tablets, and use the label's total volume or pen count.

---

## 4. Reminders

- Times are anchored to his routine, not the clock: "with breakfast", "with dinner", "before bed". The routine is set once by Ash.
- Each dose is one card with the pill photo, the name, the purpose and one button. The helper gets the same list on WhatsApp in her language and can tap "given".
- Missed-dose guidance is per drug from the licensed database, rendered in plain words: "If you forgot this morning, take it now. Do not take two tonight."
- Fasting days and festive periods shift the schedule when the drug allows it and flag it to Ash when it doesn't.
- Escalation follows the ladder: Dad → helper → caregiver on duty. Two ignored reminders and the third goes to the roster, not to Dad.

---

## 5. "When to buy next"

The reorder card appears at the lead-time threshold and knows where it came from last time.

- Retail: last pharmacy, last price from the receipt, generic alternative and its price, drafted WhatsApp order to the pharmacy if they take orders that way.
- Hospital pharmacy: the refill appointment or collection date, and whether medicine-by-post or a nearer collection point is available.
- Clinic: whether a repeat needs a visit, and if so it joins the visit loop.

"Ask Ash to order" is the default action on Dad's card. "I have more" triggers the recount photo. Ash's reorder queue lists everything due in the next fourteen days with one tap to draft the message.

---

## 6. Insights and what to look out for

Content comes from a licensed drug database and open criteria lists, then is filtered by his State so he only sees what applies to him.

- **Purpose**, linked to his condition and the doctor who prescribed it.
- **Watch-outs that matter for him**: ankle swelling on amlodipine if he's already on a diuretic; bleeding signs on warfarin; dizziness on standing if his readings run low.
- **Avoid**: grapefruit, NSAIDs, alcohol, specific supplements and TCM, per drug.
- **Interactions** across the list, ranked by severity, with the two drugs named and one sentence on why.
- **Polypharmacy talking points** for the next visit: "Ask whether both blood pressure medicines are still needed" — with the criterion cited for Ash, plain words for Dad.
- **What changed**: every dose change and every new drug, with the source (label, consult recording, discharge summary), in the timeline.

---

## 7. Two views

**Dad.** Today's doses as cards at the anchor times. The medicine list with pill photos, purpose in his words, count and reorder date. "What is this pill?" by photo. Voice note of any medication story. Nothing to edit.

**Ash.** The reconciled list with source per line and confidence. Medication story per drug. Change log. Reorder queue. Adherence by week (confirmed / unconfirmed / missed) without shaming language. Interaction and polypharmacy panel with talking points ready for the next visit. Export as the list the clinic will trust.

---

## 8. Edge cases the design has to handle

- Two strengths of the same drug in the cupboard: both lines kept, the label decides which is current, the other is marked "old stock".
- A verbal dose change in the consult: the recording proposes the change; Ash confirms; the label at the next refill closes the loop.
- Medicines from three sources (government hospital, private specialist, retail): one list, source shown per line, duplicates flagged.
- TCM and supplements with no label: photographed anyway, named by Ash by voice, screened for known interactions.
- Expired packs: flagged from the pack photo.
- Shared households: the label's patient name prevents a spouse's medicine landing on Dad's list.

---

## 9. Safety rules

- The system never changes a dose. It proposes; a person confirms.
- High-risk drugs (warfarin, insulin, digoxin, methotrexate, opioids) require the label photo before the dose is saved; a verbal report is not enough.
- Every inferred value shows its source and confidence; anything below the threshold is asked, not assumed.
- Interaction and criteria checks run on a licensed database with citations. The model writes the plain-language sentence; it does not supply the pharmacology.
- The boundary is on the card: "This helps you take what your doctor prescribed. Ask your doctor or pharmacist before changing anything."

---

## 10. Data sources to license or integrate

- Drug identification and local brands: Malaysia NPRA product register, Singapore HSA register, a licensed Asia-coverage drug database (MIMS or equivalent).
- Interactions and dosing: a licensed interaction database; not the model's memory.
- Criteria: Beers (AGS), STOPP/START — open, versioned.
- Missed-dose and food guidance: licensed patient-information monographs.
- Local refill services: MOH Malaysia medicine-by-post and integrated dispensing options; Singapore polyclinic and hospital pharmacy refill channels.

---

## 11. Build order inside Stage 1

- **T1**: pack and label photo → identify, dose, quantity, match, story; reminders and "Taken"; running count; reorder card; interaction check on add.
- **T2**: receipt capture and price; recount from blister photo; polypharmacy review; helper "given" taps; consult-recording dose changes; refill queue with drafted messages.
- **T3**: generic price comparison across pharmacies; pharmacy ordering integrations where they exist.
