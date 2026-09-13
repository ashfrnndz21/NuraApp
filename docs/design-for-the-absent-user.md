# Design for the absent user

Nobody opens a health app every day. There is no reason to. A well person has nothing to do; a sick person has other things to do; a caregiver has a job. Any design that needs daily opens will fail, and any metric that measures them will lie.

So the product is built on the opposite assumption: **most days, nobody opens it, and it still works.** Here is how.

---

## 1. Value accrues while it's closed

The system does its work in the background and the person collects it when they show up.

- Records forwarded on WhatsApp file themselves. A receipt photo updates the count. A result from the hospital portal, shared from the Photos app in two taps, becomes a trend.
- State recomputes on every new fact; search jobs run on their own; the feed is ready whenever it's next looked at.
- Readings arrive from the cuff through Health with nobody touching the app.
- Reorder dates, insurance renewals, screening due dates and letter expiries are tracked without being watched.

When she opens it after eleven days, "What changed since you last looked" is the first screen and it is exactly right.

---

## 2. Everything important comes to them

The person never has to remember to check. The app's real surfaces are the ones that don't require opening it:

- WhatsApp for the patient: the morning card, the visit card, the family note, the feeling words. Reply "OK" or tap the button in the message.
- The Lock Screen for the emergency card and the Home Screen widget for the one thing with Taken on it.
- The Dynamic Island on visit day.
- Siri for "when did I last see Dr Tan".
- One notification a day at most, and only when there is one.

The native app is where you go for more. Most days there is no more.

---

## 3. Others feed the record

The patient is not the data entry clerk, and neither is the chief.

- Every key holder adds signal: Mei forwards the clinic slip, Siti taps "given", Aunt Lily notes he looked tired.
- The pharmacy receipt and the discharge letter are photographed once by whoever is holding them.
- The clinic gets a share link and, in the next phase, returns the visit summary through it.
- The medicine bag is photographed when it's refilled, not on a schedule.

The record grows from the household's normal movements, not from anyone's discipline.

---

## 4. The peaks are the product

Usage is episodic, so the episodes have to be extraordinary. Four moments a year decide whether the family keeps paying:

| Peak | What the app must do, without fail |
|---|---|
| **The visit** | The brief three days before; the questions on one card; the recording; the summary in his words the same day; the letter approved before he walks in. |
| **The discharge** | The letter photographed once; the medicines reconciled by the evening; the thirty-day watch running; the follow-up on the calendar; the helper's list updated. |
| **The new medicine** | One photo of the bag; the interaction check; the story in his language; the count and the buy-by date; the feeling words for the first fortnight. |
| **The bad day** | The coral button; what to do now; the family told; the emergency card in a stranger's hand. |

Between peaks, the product's job is to be quiet and ready.

---

## 5. Re-entry costs nothing

- No login on return. The device is the credential; a PIN only on a shared phone.
- The first screen is always the same shape, whether it's been a day or a month.
- For the caregiver, "what changed" is a thirty-second read, then close.
- For the patient, the one thing is the same card in the same place.
- Nothing has expired, nagged, or piled up. Missed nudges are dropped, not queued. There is never a badge with forty-one unread items.

---

## 6. Low-frequency rituals that earn a return

Not daily. Weekly, monthly, yearly, and only where they carry information.

- **Sunday**: the thirty-second week, forwardable to the family group.
- **Monthly**: one message to the chief: readiness — medicines current, next visit prepared, letter status, anything the system couldn't read.
- **Before each visit**: the one time the app should feel indispensable.
- **Yearly**: the cost ledger, the screening schedule, the insurance renewal, and a review of who holds which key.

Each is a reason to come back that exists in the person's life already; none is manufactured.

---

## 7. Metrics that fit

Daily active users would punish the product for succeeding. Measure instead:

- **Readiness**: share of profiles with medicines reconciled in the last ninety days, next visit on the spine, emergency card complete, at least one key holder active.
- **Peaks served**: visits with a brief; discharges reconciled within a day; new medicines checked before the first dose; bad days where a person was reached within five minutes.
- **Background yield**: facts added by someone other than the owner; records that filed themselves from WhatsApp.
- **Return cost**: seconds from open to "what changed" read.
- **Retention at month six for the paying family**, which remains the gate.

If those hold, low daily use is not a problem. It is the design working.

---

## 8. The business model has to agree

A product used four times a year cannot be priced or sold like a habit app.

- Framed and priced as readiness, the way insurance or a smoke detector is: a family plan, paid by the chief, justified by the four peaks and the bad day.
- Or paid by the channel: an insurer or hospital group, which values the same peaks (fewer readmissions, letters resolved, reconciled medicines) and does not care about daily opens at all.

Both fit the absent user. A per-seat consumer subscription justified by engagement does not, and should not be attempted.

---

## 9. In one line

Build it like a service that runs while nobody is watching, surfaces itself where people already are, is fed by the household rather than the patient, and is flawless on the four days a year that matter.
