# Waiting for the pharmacist's or the clinician's sign-off

Wording and rules that are built but must be signed off by the pharmacist or a clinician before they reach a real family (checkpoint 19, real profiles). Each one is listed with where it lives and what the person signing it is asked. When one is signed, write who signed it, on what date, and what changed.

| # | What | Where | Who signs | Status |
|---|---|---|---|---|
| 1 | Potassium called "your body salt" in all three languages (#126) | `backend/app/delivery/trend_strings.py`, `timeline_strings.py`; the glossary row in `docs/plain-words.md`; ADR 0007 | Pharmacist | Open |
| 2 | The red-flag tiers (#147, ADR 0010) | `backend/app/safety/red_flags.py`: `AMBULANCE_FLAGS`, `step_for`; SaMD review, question 10 | Clinician, and the regulatory adviser | Open |
| 3 | A fall on a blood thinner is the ambulance at any hour (#147) | `backend/app/safety/red_flags.py`: `ANTICOAGULANT_CLASSES`, `AMBULANCE_ON_A_THINNER`, `on_a_blood_thinner` | Clinician, with the pharmacist for the class | Open |

## 1. Potassium as "your body salt" (#126)

Salt substitutes are potassium chloride. So someone told to watch his potassium may reach for "low-salt" salt, and a low result could read as "eat more salt". The choice: keep it; pair it with the name ("your potassium, a body salt"); or reword it, and update the glossary row in all three languages.

## 3. A fall on a blood thinner

**The rule.** When a fall is raised while a medicine on his list is one the drug register classes as an anticoagulant, the step is the ambulance tier at any hour, whether or not a hospital is marked. He is told "Call the ambulance now on 995." (999 in Malaysia, from the region table), and the family gets the ambulance notice ("Call Pa now. If Pa has not called the ambulance, call the ambulance now on 995."). Without a thinner, a fall keeps its same-day rows. The rule only ever raises a fall; it never lowers anything.

**Why.** Someone on warfarin or one of the newer thinners (apixaban, rivaroxaban, dabigatran, edoxaban) who falls can bleed inside the head hours later. That needs same-night assessment. At night with no hospital marked, the same-day row said "Sit down and rest now. / If it gets worse, call the ambulance now on 995. / Call Dr Tan in the morning."

**Where it applies.** Every path that tells anyone about a flag: the WhatsApp reply, and the family's notice from the ladder, whether the fall came from WhatsApp (typed, or a voice note), the not-feeling-well button, the symptom log or the feeling cloud. The button's own card already says the ambulance for every red flag.

**Tests.** `backend/tests/test_red_flag_escalation.py`: a fall on warfarin and on apixaban, at 14:00 and at 22:30, with and without a panel hospital, in English, Malay and Chinese; a fall with no thinner keeps today's rows; a stopped thinner does not raise it; a helper's word gets the same step; the button, the log and the cloud; 999 in Malaysia.

**Questions for sign-off.**

1. The class. It is the register's `anticoagulant` class, the same one the label-photo rule guards (warfarin, apixaban, rivaroxaban, dabigatran, edoxaban). It does not include heparin injections (enoxaparin) or the antiplatelets (aspirin, clopidogrel, ticagrelor, two of them together). Should any of those raise a fall too?
2. Held and stopped. A line marked held still counts, because a thinner paused for a few days still thins the blood. A stopped line does not. Is that right? Should a thinner stopped in the last few days still count?
3. Only a fall is raised. Should a knock to the head without a fall, or another same-day flag on a thinner (one-sided swelling, blood in the stool), be raised as well?
4. It reads his list in Nura only. A thinner nobody recorded cannot raise it, and a licensed register that files the newer thinners under another class code (for example by mechanism) would not either. The deployment's register must be checked against the class before real profiles.
5. The step. Is "the ambulance now", rather than "go to the emergency department now", the right step at 14:00 in his doctor's hours, when he may be able to get there himself?
