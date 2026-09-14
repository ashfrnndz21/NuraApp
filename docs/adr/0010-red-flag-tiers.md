# ADR 0010: Red flags in two tiers, by the doctor's hours

**Status** proposed — built on the operator's instruction of 15 September 2026; awaiting a clinician's sign-off on the table and the regulatory adviser's answer to question 10 of `docs/trust/samd-boundary-review.md`.

## Context

Every red flag used to be answered the same way on WhatsApp: "Call {doctor} today." At 22:30 his clinic is closed, so the line gave him nothing he could do. Chest pain on WhatsApp was answered with it too, while the not-feeling-well card in the app said "Call the ambulance now on 995." for every red flag.

## Decision

The red flags (`app.safety.red_flags.RED_FLAGS`) are in two tiers. `AMBULANCE_FLAGS` is a subset of that one list: chest pain, breathless at rest, the signs of a stroke (the worst headache ever, sudden blurring, confusion), and shaky and sweaty on a medicine that drops his sugar. Everything else — a fall, one-sided swelling, the weight after a heart discharge — is the same-day tier.

A message that matches several flags is tiered by the most urgent (`detect`).

`step_for` chooses the step, top row first:

| Tier | His doctor's hours | Hospital on his insurance marked | What the thread says to do now |
|---|---|---|---|
| ambulance | any | any | Call the ambulance now on 995. |
| same day | in | no | Call Dr Tan today. If it gets worse, call the ambulance now on 995. |
| same day | in | yes | Call Dr Tan today. If it gets worse, go to {hospital} now. |
| same day | out | yes | Go to the emergency department at {hospital} now. {hospital} is on your insurance. If you cannot get there safely, call the ambulance now on 995. |
| same day | out | no | Sit down and rest now. If it gets worse, call the ambulance now on 995. Call Dr Tan in the morning. |

"Out of hours" is outside the named doctor's hours from the directory, with the last hour before closing counted as out. When the directory does not give hours, out of hours is 20:00 to 08:00 on his wall clock.

Every reply ends "Nura does not decide what is wrong." The family's notice follows the same step: pending templates `red_flag_notice_ambulance`, `_hospital` and `_night`. Until Meta approves them they go as free text inside the family member's 24-hour window; outside it the approved notice goes, so a flag never waits on Meta.

The not-feeling-well card in the app keeps its red-flag row as it was: the ambulance, for every red flag. That card is the stricter surface on purpose; the operator asked for its row to be unchanged.

## Consequences

- The hour and a hospital marked never lower a tier; they choose between two ways of acting tonight.
- The same-day step out of hours depends on whether a hospital is marked. The clinical-safety review asked that it not, and that out of hours the same-day tier always say "go to the nearest emergency department now". That is a question for the clinician signing this off.
- Weekends and public holidays are not in the directory yet, so a Sunday reads like a weekday.
- A level-of-care line that is Nura's rather than the hospital letter's is on the list in §6 of the SaMD review. This ADR is the record of that decision, and question 10 there is the adviser's.
