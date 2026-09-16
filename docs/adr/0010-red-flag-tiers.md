# ADR 0010: Red flags in two tiers, by the doctor's hours

**Status** proposed — built on the operator's instruction of 15 September 2026; awaiting a clinician's sign-off on the table and the regulatory adviser's answer to question 10 of `docs/trust/samd-boundary-review.md`.

## Context

Every red flag used to be answered the same way on WhatsApp: "Call {doctor} today." At 22:30 his clinic is closed, so the line gave him nothing he could do. Chest pain on WhatsApp was answered with it too, while the not-feeling-well card in the app said "Call the ambulance now on 995." for every red flag.

## Decision

The red flags (`app.safety.red_flags.RED_FLAGS`) are in two tiers. `AMBULANCE_FLAGS` is a subset of that one list: chest pain, breathless at rest, the signs of a stroke (the worst headache ever, sudden blurring, confusion), and shaky and sweaty on a medicine that drops his sugar. Everything else — a fall, one-sided swelling, the weight after a heart discharge — is the same-day tier.

A fall while he is on a blood thinner is the ambulance tier at any hour (`AMBULANCE_ON_A_THINNER`, the operator's instruction of 15 September 2026). "On a blood thinner" means a line in force on his list, active or held, whose register class is in `ANTICOAGULANT_CLASSES` (the register's `anticoagulant`: warfarin, apixaban, rivaroxaban, dabigatran, edoxaban). A bleed inside the head can come hours after a fall, and needs seeing that night, not "Call Dr Tan in the morning". The list is read as the system (`on_a_blood_thinner`), so a helper's word gets the same step.
- A thinner is known by its register class in any case, or by its generic name as the label-photo rule's matcher reads it (whole words, so "warfarin sodium" too).
- If the list cannot be read, the step is the ambulance.
- Among the same-day flags a message matches, a fall wins, so "I fell and my leg is swollen on one side" never misses the thinner.
- A fall said with a flag that would be held back for want of a fact on the record ("I fell, I am shaky and sweaty", with no sugar condition or sugar medicine) is raised as the fall (`flag_to_raise`), so it is never lost. "Fall asleep" is not a fall.

Awaiting the same sign-off, listed in `docs/trust/clinical-sign-off.md`.

A message that matches several flags is tiered by the most urgent (`detect`).

`step_for` chooses the step, top row first:

| Tier | His doctor's hours | Hospital on his insurance marked | What the thread says to do now |
|---|---|---|---|
| ambulance (and a fall on a blood thinner) | any | any | Call the ambulance now on 995. |
| same day | in | no | Call Dr Tan today. If it gets worse, call the ambulance now on 995. |
| same day | in | yes | Call Dr Tan today. If it gets worse, go to {hospital} now. {hospital} is on your insurance. |
| same day | out | yes | Go to the emergency department at {hospital} now. {hospital} is on your insurance. If you cannot get there safely, call the ambulance now on 995. |
| same day | out | no | Sit down and rest now. If it gets worse, call the ambulance now on 995. Call Dr Tan on {day and date} in the morning. |

**Behind a switch until it is signed.** None of this reaches a family until a clinician signs the table. The table is chosen in one door, `escalation_for` (through `escalation_now`), and only when `Settings.red_flag_tiers` is set (`NURA_RED_FLAG_TIERS=1`). Unset — every deployment until the sign-off — every red flag's step is the ambulance: the thread says "Call the ambulance now on 995.", and the family gets the ambulance notice. That is the stricter step the not-feeling-well card already gives for every red flag, and no level-of-care step of Nura's own. A dev run sets it (`make dev`), so the checkpoints and the tests see the table. `tests/test_red_flag_escalation.py` holds that a build without the switch never says the doctor today, the hospital now, or rest and the morning.

**His list is read as the system.** For a fall, `escalation_now` reads his medicine list with the system's reach (`on_a_blood_thinner`, a `_system_read` of `medication_line` under the medicines scope, written down in the raiser's name), whatever the raiser's key opens. It does not call `context.require(Scope.MEDICINES)`, on purpose: only a yes or no leaves the rule, never a medicine, and a helper who saw him fall must get the ambulance when he is on a thinner.

"Out of hours" is outside the named doctor's hours from the directory, with the last hour before closing counted as out. When the directory does not give hours, out of hours is 20:00 to 08:00 on his wall clock.

Every reply ends "Nura does not decide what is wrong." The family's notice follows the same step: pending templates `red_flag_notice_ambulance`, `_hospital` and `_night`. Until Meta approves them they go as free text inside the family member's 24-hour window; outside it the approved notice goes, so a flag never waits on Meta.

The not-feeling-well card in the app keeps its red-flag row as it was: the ambulance, for every red flag. That card is the stricter surface on purpose; the operator asked for its row to be unchanged.

## Consequences

- The hour and a hospital marked never lower a tier; they choose between two ways of acting tonight.
- A blood thinner only ever raises a fall to the ambulance; it never lowers anything. It is read from his list in Nura: a thinner nobody recorded cannot raise it, and a register that classes the newer thinners under another code would not either, which the clinician and the pharmacist check against the deployment's register.
- The same-day step out of hours depends on whether a hospital is marked. The clinical-safety review asked that it not, and that out of hours the same-day tier always say "go to the nearest emergency department now". **This is a blocking question for the clinician:** the switch is not set until it is answered.
- Weekends and public holidays are not in the directory yet, so a Sunday reads like a weekday.
- The family's tiered notices are pending Meta. **Settled:** the approved notice stays the last resort, because a flag never waits on Meta. The switch must not be set in a deployment until `red_flag_notice_ambulance`, `_hospital` and `_night` are approved; that is a condition of the sign-off (`docs/trust/clinical-sign-off.md`). Until then, with the switch unset, every flag's notice is the ambulance one inside the window. Outside the family member's 24-hour window the approved notice goes, and it says "Call Dr Tan today." That holds for the ambulance tier too, a fall on a thinner included, until the notices are approved.
- A red flag heard in a visit transcript carries a code and no feeling, so the family's notice for it is the approved one ("Call Dr Tan today."): he was with the doctor. Whether a fall heard at a visit, on a thinner, should still be the ambulance is a question for the clinician.
- When a fall gets the ambulance because of a thinner, a helper whose key does not open his medicines can guess that he is on one. This is accepted for his safety, pending sign-off.
- A level-of-care line that is Nura's rather than the hospital letter's is on the list in §6 of the SaMD review. This ADR is the record of that decision, and question 10 there is the adviser's.
