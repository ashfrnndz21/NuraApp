# Waiting for the pharmacist's or the clinician's sign-off

Wording and rules that are built but must be signed off by the pharmacist or a clinician before they reach a real family (checkpoint 19, real profiles). Each one is listed with where it lives and what the person signing it is asked. When one is signed, write who signed it, on what date, and what changed.

| # | What | Where | Who signs | Status |
|---|---|---|---|---|
| 1 | Potassium called "your body salt" in all three languages (#126) | `backend/app/delivery/trend_strings.py`, `timeline_strings.py`; the glossary row in `docs/plain-words.md`; ADR 0007 | Pharmacist | Open |
| 2 | The red-flag tiers (#147, ADR 0010), behind `NURA_RED_FLAG_TIERS` | `backend/app/safety/red_flags.py`: `AMBULANCE_FLAGS`, `step_for`, `escalation_for`; SaMD review, question 10 | Clinician, and the regulatory adviser | Open — blocking: the out-of-hours same-day step (see 2 below) |
| 3 | A fall on a blood thinner is the ambulance at any hour (#147) | `backend/app/safety/red_flags.py`: `ANTICOAGULANT_CLASSES`, `AMBULANCE_ON_A_THINNER`, `on_a_blood_thinner` | Clinician, with the pharmacist for the class | Open |

## 1. Potassium as "your body salt" (#126)

Salt substitutes are potassium chloride. So someone told to watch his potassium may reach for "low-salt" salt, and a low result could read as "eat more salt". The choice: keep it; pair it with the name ("your potassium, a body salt"); or reword it, and update the glossary row in all three languages.

## 2. The red-flag tiers

**Behind a switch.** The table reaches a family only with `NURA_RED_FLAG_TIERS=1`. Unset, every red flag's step is the ambulance; that is the not-feeling-well card's own step. A dev run sets it. Before it is set in a deployment:

- **Blocking question.** Out of the doctor's hours, with no hospital marked, a same-day flag is told "Sit down and rest now. / If it gets worse, call the ambulance now on 995. / Call Dr Tan on Tuesday 15 September in the morning." The clinical-safety review asks that out of hours every same-day flag say "go to the nearest emergency department now" instead, whether or not a hospital is marked. Which is it?
- The three tiered family notices must be approved by Meta. Until they are, outside the family member's 24-hour window the approved notice goes, and it says "Call Dr Tan today."
- Question 10 of the SaMD review must be answered by the regulatory adviser.

## 3. A fall on a blood thinner

**The rule.** With the tiers switched on (`NURA_RED_FLAG_TIERS=1`; switched off, every red flag is the ambulance anyway), a fall is raised while a line in force on his list is a blood thinner. That means its register class is in `ANTICOAGULANT_CLASSES` (the register's `anticoagulant`, any case), or its generic name is one the label-photo rule's own matcher reads as that class (`high_risk_class`, whole words, so "warfarin sodium" and "dabigatran etexilate" count too). The names are read from `HIGH_RISK_CLASSES`, not copied. Then the step is the ambulance tier at any hour, whether or not a hospital is marked.
- He is told "Call the ambulance now on 995." (999 in Malaysia, from the region table).
- The family's notice is the ambulance one: "Call Pa now. If Pa has not called the ambulance, call the ambulance now on 995."
- Without a thinner, a fall keeps its same-day rows.
- The rule only ever raises a fall; it never lowers anything.
- A message that says a fall and another same-day flag ("I fell and my leg is swollen on one side") is heard as the fall, so the thinner is never missed.
- A message that says a fall and a flag that is held back without a fact on the record ("I fell, I am shaky and sweaty", with no sugar condition or sugar medicine) is raised as the fall (`flag_to_raise`). It is never written down as a held-back flag that tells nobody.
- "Fall asleep" is not a fall.
- If his list cannot be read, the step is the ambulance.

**Why.** Someone on warfarin or one of the newer thinners (apixaban, rivaroxaban, dabigatran, edoxaban) who falls can bleed inside the head hours later. That needs assessment the same night. At night with no hospital marked, the same-day row said "Sit down and rest now. / If it gets worse, call the ambulance now on 995. / Call Dr Tan in the morning."

**Where it applies.** The WhatsApp reply, and the family's notice from the ladder, including its later rungs. That covers a fall from WhatsApp (typed, or a voice note), the not-feeling-well button, the symptom log and the feeling cloud. The button's own card, and the log's, already say the ambulance for every red flag.

**Where it does not, yet.**
- *Outside the family member's 24-hour WhatsApp window, until Meta approves `red_flag_notice_ambulance`,* the only approved notice goes, and it says "Call Dr Tan today." This is the same for chest pain; it is the PR's open question. The tiered notices must be approved, or a notice that never says "today" must be, before real profiles.
- *A fall heard in a visit transcript* raises a flag with no feeling on it. That family notice is the approved one ("Call Dr Tan today."), because he was with the doctor. ADR 0010 asks whether that is right.

**Tests.** `backend/tests/test_red_flag_escalation.py`:
- a fall on warfarin and on apixaban, at 14:00 and at 22:30, with and without a panel hospital, in English, Malay and Chinese
- a fall with no thinner keeps today's rows
- a line no longer in force (superseded) does not raise it
- a class under another code or in capitals, and a name with its salt ("warfarin sodium")
- a fall said with swelling, and a fall said with shaky and sweaty in three languages, on WhatsApp, the button and the log
- "fall asleep"
- a helper's word, and the system's read of his list on the audit trail
- a list that cannot be read, including a real database error
- the button, the log and the cloud
- his voice note
- the family's notice in Malay and Chinese, and as free text inside the window
- 999 in Malaysia

**Questions for sign-off.**

1. The class. It is warfarin, apixaban, rivaroxaban, dabigatran and edoxaban (acenocoumarol is rare here). It does not include the heparin injections (enoxaparin), fondaparinux, a single antiplatelet (aspirin, clopidogrel, ticagrelor), or two antiplatelets together. Should any of them raise a fall too? Two antiplatelets together especially.
2. Held and stopped. A line the list marks as held would count, because a thinner paused for a few days still thins the blood. Nothing in Nura writes "held" or "stopped" yet: a medicine leaves his list only when its line is superseded, and it stops counting then. Should a thinner that left his list in the last few days still count?
3. Only a fall is raised. Should a knock to the head without a fall, or another same-day flag on a thinner (one-sided swelling, blood in the stool), be raised as well?
4. It reads his list in Nura only. A thinner nobody recorded cannot raise it. The deployment's licensed register must be checked against the class and the names before real profiles.
5. The step. At 14:00 in his doctor's hours, when he may be able to get there himself, is "the ambulance now" right, rather than "go to the emergency department now"?
6. The helper can tell. When a fall gets the ambulance, a helper whose key does not open his medicines can guess that he is on a blood thinner. Is that acceptable for his safety?
7. False alarms. The words for a fall still match "my hair is falling out", "afraid of falling", "nearly fell but held the rail" and "he did not fall". Only "fall asleep" is left out. On a thinner each of these would now be the ambulance and the family's ambulance notice. Should near-falls and "did not fall" be read as a fall or not? It errs towards the ambulance until the clinician says otherwise.
