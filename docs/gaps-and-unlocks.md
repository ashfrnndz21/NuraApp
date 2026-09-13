# Gaps and unlocks

Every piece of context the person skips or hasn't given yet becomes a gap. A gap is never a wall and never a red badge. It is a short card that says what is missing, what having it would let the system do, and the one action that fills it.

---

## 1. The card

Three lines and two buttons, always in this order.

```
Missing
Your usual blood pressure numbers
With it I can say whether a reading is normal for you rather than for
everyone, and notice a drift a week before your visit.
[ Snap your monitor's screen ]   Later
```

Rules for the copy: "Missing" names the fact in the person's words, not the field name. "With it I can…" is written from the system's side and promises only what the reasoning layer can actually do with that fact. The action is one physical thing, usually a photo or a tap, never a form.

---

## 2. The catalogue (v1)

| Gap | Triggered by | Unlocks | Action | Tier |
|---|---|---|---|---|
| Which tablets, and the doses | Any medicine word, or five-plus medicines | Interaction checks, meal-tied reminders, reorder dates, a list the doctor will trust | Snap the medicine bag | 1 |
| Your usual blood pressure numbers | High blood pressure without home readings | Normal-for-you judgement; drift detection before a visit | Snap the monitor's screen | 1 |
| Your weight most mornings | Heart failure without weighing | Fluid build-up caught days before breathlessness | Snap the scale weekly | 1 |
| Which medicine you're allergic to | Allergy tapped, none named | Emergency card entry; blocked in every check | Tap which one | 1 |
| Which blood thinner | Thinner tapped, kind unknown | Blood-test reminders if needed; food and painkiller warnings | Tap which kind | 1 |
| What was changed in hospital | Hospital stay, no discharge letter | Before/after reconciliation; thirty-day watch | Add the discharge letter | 1 |
| Last cholesterol result | Cholesterol, no labs | Direction over time; next-check timing | Add any lab result | 2 |
| Last three-month sugar | Diabetes, no labs | What meals do to it; next-check timing | Add any lab result | 2 |
| Last kidney result | Kidneys, no labs | Every new medicine checked against the kidneys | Add any lab result | 2 |
| Your doctor and next visit | Any condition, no clinic card | Questions three days before; coverage check; driver reminder | Add a clinic card | 2 |
| Your insurance policy | Nothing on file | Panel hospitals; likely cost; when a letter is needed | Snap the insurance card | 2 |
| Breakfast and dinner times | Routine not set | Reminders tied to meals, not the clock | Two taps | 2 |
| Someone who can see your record | No keys cut | They can ask about you and be told of a drift | Invite one person | 3 |

The catalogue grows with the reasoning layer: a gap exists only when there is a capability that needs the fact. No capability, no gap.

---

## 3. Where gaps appear

- **At the Check step of onboarding**, as the list of what the system doesn't know yet, four at most, the rest summarised as a count.
- **When records are skipped**, the next screen names what stays locked, three cards, so skipping is an informed choice rather than a dead end.
- **On the Ready screen**, one card: the first thing the system will ask for tomorrow, and how many follow.
- **On Today**, in the explore section below the two cards, one gap card per day at most, ranked by tier and by what has changed since (a new medicine makes the labs gap more urgent).
- **On WhatsApp**, folded into the weekly recap as one sentence: "One thing would help: a photo of the medicine bag."
- **In the caregiver's view**, the full list with tiers, so the person who actually has the papers can close several at once.

---

## 4. Cadence and stop rules

- One gap per day per person, never more, and never on a day that already carries an alert.
- **Later** defers the gap. The system asks once more after a few days. A second Later retires the gap from nudges; it stays visible in the caregiver's list and in the Me tab, and comes back only if something changes that makes it matter again (a new medicine revives the labs gap).
- A gap closes itself the moment the fact arrives by any route, including from a record the person added for another reason.
- No streaks, no completion percentage on the patient's side. The bar in the records step is the assistant's knowledge, shown once during onboarding, not a score the person carries.
- Tier 1 gaps can interrupt the order when a record reveals them (a bag photo showing a blood thinner creates the "which kind" gap and it goes first).

---

## 5. How gaps feed reasoning

A gap is stored as a fact about the profile: `missing(blood_pressure_baseline)`, with the capability it blocks. The reasoning layer reads it two ways. Flags that depend on a missing fact are suppressed rather than guessed, and the suppression is visible to the caregiver ("Can't judge this reading yet: no usual numbers on file"). And the visit brief lists open tier-1 and tier-2 gaps as questions for the doctor when the doctor is the fastest way to close them ("Ask Dr Tan for the last kidney result").

---

## 6. What the prototype shows

In `onboarding.html`: gap cards on the Check step with "Later"; a "what stays locked" screen if records are skipped; the tomorrow-morning nudge on Ready; the cadence explained once; and the context panel listing each gap with the first thing it unlocks and a count of how many were deferred.
