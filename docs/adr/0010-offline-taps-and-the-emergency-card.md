# ADR 0010 — Taps held offline carry their moment; the emergency card outlives midnight

**Date** 2026-09-15 · **Status** proposed (W4, #8) · **Decided by** the builder; for the operator to confirm

## Context

E00-08 asks for today's medicines and the emergency card to open with no network, on a five-year-old phone, and for taps made offline to count. The web client already keeps the Today page and the feed's first page under one rule (W1, W2): bound to the key and scope set that read them, deleted on a refusal, a switch of papers and sign-out, and deleted at the region's midnight so that no dose is ever shown from yesterday's data. Two things did not fit that rule as it stood:

1. **A tap made offline.** *Taken* on a Now card the backend marked due (a live read), tapped when the network has gone. Sent later, `POST …/taken` wrote the moment of the replay, not the moment he took the tablet, and a replay whose answer was lost could write the dose twice.
2. **The emergency card.** It is what a stranger needs when he cannot speak for himself (E13-01: "works offline… the reason he keeps the app installed"). Deleted at midnight like the Today page, it would be missing exactly when a fall at night makes it needed.

## Decision

**Held taps.** The phone holds the tap (`web/src/offline/queue.ts`, `queue.<profile>` in IndexedDB) with the moment he made it, under the Today page's rules — bound to the key and scope set, deleted with the rest of the phone's copy, and dropped at the region's midnight (yesterday's tap is not today's tablet). When the network is back the taps are sent once each, oldest first, one at a time; a tap leaves the phone's list as soon as the backend has answered it, yes or no, and a refusal is said in the catalogue's sentence for the backend's refusal. `TakenIn` gains an optional `taken_at` (`AwareDatetime`): the backend writes the DOSE_TAKEN event as having happened then (recorded now), only if that moment is today on the region's clock and not later than now beyond two minutes of phone-clock drift (`TapNotToday`, 400), and writes the same tap — same person, line, anchor and moment — once however often it arrives. No migration: the moment is the tap's identity. A red word on the feeling strip is never held; it is the moment to call.

**The emergency card.** The phone keeps the card (`web/src/offline/emergencyCache.ts`, `emergency.<profile>`): the JSON's verified lines and the backend's printable page, so it reads and prints with no network. It is bound to the key and scope set and deleted on a refusal, a switch of papers and sign-out like everything else — but **not at midnight**. It is read again once a day (the first time Today is open with a network after the region's midnight) and every time the card is opened with one, and it always says when it was read ("Nura read this card on Monday 14 September at 10:00 am."). A read that meets no network, a server that could not answer, or a State behind the record keeps the copy; a no to the key deletes it.

## Consequences

- Past midnight with no network, Today shows "Nura cannot reach your papers right now." and the kept emergency card, dated — no dose, no list. The e2e helper that looks for medicine names on the phone past midnight leaves the card out and checks it on its own; sign-out is checked to leave none of it.
- The phone holds his medicine names past midnight in one place: the card. It is his own card on his own phone under his own key, and the printed copy in his wallet has the same lines. If the operator prefers the card to follow the midnight rule too, `loadCard` takes the same expiry as `loadToday` and nothing else changes.
- A feeling tap has no moment on the wire yet (`FeelingIn`); the web has no feeling strip (E17's web half), so none is held today. When the strip comes, `FeelingIn` needs the same `at` before its taps are held.
