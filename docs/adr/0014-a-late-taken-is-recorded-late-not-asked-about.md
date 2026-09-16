# ADR 0014 — A late "Taken" is recorded as late, not asked about, its own pattern signal, and the ladder tells whoever it reached that it stood down

**Date** 2026-09-16 · **Status** accepted (owner's decision on #198) · **Decided by** the owner · **Stories** E11-06, E04-02, E11-10 (the weekly pattern signal)

## Context

`doses_for_reply` (`backend/app/delivery/triggers/ladder.py`) resolves which dose a "Taken" or
"given" reply lands on: first the doses the open ladder has asked this person about today,
then the doses whose window is open now and untapped, and — with neither — the latest-anchor
dose that has passed today with nothing tapped. That fallback is the concern #198 raised: a
reply that arrives after the window has closed, and after the ladder has already climbed —
asked him, asked the helper, told the chief — still lands on that dose and marks it taken.
Today that tap and a same-moment one are the same row: nothing says the reply came late, and
the ladder's own work (it asked, it climbed, it told someone) leaves no mark once a tap closes
it.

Three readings of a late reply are genuinely available from a two-word message: he took it on
time and is only now replying; he is taking it now, because the ladder's asking worked; or
someone else answered for him with no tablet actually taken. Nothing in "sudah makan" tells
these apart, and asking him a clarifying question on a day that has already gone wrong (the
window closed, Pa was asked, Siti was asked, Mei was told) costs him more than it buys — a
frail, possibly unwell person, mid-escalation, held up by a question Nura can't even use the
answer of with any confidence.

There was a second, quieter question underneath: when a "Taken" reply closes a ladder that had
already reached someone, does anything tell that person it's over? Reading `climb`,
`acknowledge_dose` and `acknowledge_flag`, the answer is no. A flag's ladder is closed by
`acknowledge_flag` (a person telling Nura "I have it"), which changes the row and nothing
else. A dose's ladder is closed by `acknowledge_dose` (a Taken tap, from anyone) or by the
engine noticing on its next run, and neither told anyone. Mei, once called about a tablet, was
never told the second the tablet was tapped that she could stop worrying.

## Decision

1. **Record it, and record when the reply came.** The tap is still written — nobody is asked a
   clarifying question, and nothing is refused. `DoseTaken` gains a stored `late: bool`
   (migration `0036_dose_taken_late`), worked out once, when the tap is written
   (`app.medicines.windows.is_late`), from the anchor and the tap's own moment — never
   inferred by a reader comparing `taken_at` to the anchor's window each time it is read. A tap
   with no anchor is never late; there is no window to be late against.

   This is a stored, derived fact, not a second timestamp: `taken_at` already carries the
   moment that matters (see point 2), and `anchor` already says which window it is against.
   `late` exists so every consumer — the Today card, a family digest, a future trend — reads
   one bit instead of re-deriving the same comparison, possibly differently, in five places.

2. **The moment stored is the reply's own time, not the backend's processing clock.** The
   WhatsApp path (`_write_taken` in `app.channels.whatsapp.inbound`) now passes
   `taken_at=work.message.at` — the provider's timestamp on the message — into
   `record_dose_taken`, where before it left `taken_at` unset and got the moment the backend
   happened to process the reply. A queued or retried webhook, or a slow classifier run,
   previously pushed the recorded time later than he actually sent it; that is now bounded to
   the actual delay, not compounded by it. This is also what makes `late` correct rather than
   an artifact of processing lag.

3. **What this deliberately does not do.** It does not ask "did you take it at breakfast or
   just now?" — that is the second option the issue raised, and the owner's decision is
   explicit that it is not worth the cost of asking on a day already gone wrong for an answer
   Nura could not fully trust anyway. It does not stand the ladder down "without rewriting the
   dose" (the third option) — the dose is still marked taken, because a late "Taken" is still a
   "Taken". And it does not try to distinguish "took it on time, replying late" from "taking it
   now because the ladder worked": both are `late=True`, on purpose. The timestamp is what
   lets a person — Mei, or a doctor reading the trend — draw that distinction themselves; Nura
   does not draw it for them from two words.

4. **The pattern signal reads lateness too, alongside the untapped count.** `_pattern`
   (`app.delivery.triggers.engine`) already tells the one on duty when three or more tablets
   have no Taken in seven days — arithmetic on the taps, a count and never a diagnosis. A late
   tap is still a tap, so it was never in that count, and a week of doses consistently taken
   two hours after their window looked exactly like a perfect week. `_late_pattern`, the same
   shape beside it, counts taps whose stored `late` bit is true in the same seven-day window
   and, at three or more, sends the one on duty the same kind of count
   (`TriggerType.DOSES_LATE`, template `doses_late_count`, rule
   `three_late_doses_in_seven_days`) through the same `deliver` and the same cap and quiet
   hours as `DOSES_UNTAPPED`. It reads the stored bit rather than re-deriving it, and it does
   not touch `_pattern`, `tapped_by`, or how an untapped dose is found — a late tap still
   correctly never appears in that count, because it was taken.

5. **Whoever the ladder reached is told it stood down — once, through the ladder's own
   delivery rules.** `acknowledge_dose` (the WhatsApp path's immediate close) and `climb`'s
   own answered-check (the engine's periodic close, for an app tap or any tap it notices on
   its own next run) both call a new `_notify_dose_resolved`. It reads the ladder's own
   `Delivery` rows for who was actually reached (`outcome is SENT`, `to_person_id`) — never
   everyone with a key, never the person whose tap just closed it (already knows), never the
   patient told about himself — and sends each of them one `dose_resolved` message
   (`TriggerType.DOSE_RESOLVED`, a new pending WhatsApp template) through the same `deliver`
   every other rung goes through: quiet hours held, capped once a day, the channel list tried
   in order, the ladder's `dedupe_key` (suffixed `:resolved`) so it is asked for once. It is
   `Category.CONTEXT`, not `Category.ALERT` — it carries no urgency of its own, so nothing
   about it bypasses the machinery an alert bypasses. This is not a second path around the
   ladder: it is two call sites (the instant WhatsApp close, and the engine's own close) both
   reading the same `Delivery` rows the climb already wrote, and sending through the same
   `deliver` function.

6. **The escalation stays in the record.** `close()` was already append-only — `closed_at` and
   `closed_because` are set on the existing `Ladder` row, which is never deleted — so the
   ladder that climbed to Siti and told Mei is still there, closed, after a late tap. #198's
   "the escalation vanishes from the record" was true only in the sense that nothing *read* it
   as distinct from an on-time tap and nothing told Mei it was over; the row itself was never
   erased. This ADR does not change `close()`; it adds a read of what it already wrote
   (`_who_it_reached`) and a notice, once, from it.

## Consequences

- A dose tapped late is not "missed", is not asked about a second time, and is not silently
  rewritten as on-time. The Today card's `Slot` gains `taken_late: bool` (true only when
  `taken` is also true) so a client can show it without re-deriving the comparison; the API's
  `SlotOut` and `TakenOut` carry it through. The weekly pattern signal reads it too: `DOSES_LATE`
  (`_late_pattern`) tells the one on duty when three or more taps in seven days were late,
  the same shape, cap and quiet hours as `DOSES_UNTAPPED` beside it — no new caregiver trend
  screen, just the existing pattern machinery reading one more stored bit.
- The WhatsApp reply that wrote a late tap says so, once, in his own words, after the normal
  confirmation: "This was written down later than usual." (`written_down_late` in
  `app.channels.whatsapp.strings`) — never "late" about him, never "missed", never twice.
- `dose_resolved` and `doses_late_count` are two more pending WhatsApp templates
  (`approved=False`, like every other one E11 added, twenty-four now in all); a deployment's
  number carries either only once Meta approves it, same as the rest.
- `acknowledge_dose` now takes `via: Via` as a required keyword argument — not defaulted,
  because a caller that closes a dose ladder without a way to notify would silently drop the
  notice for good (the ladder is already closed by the time anything downstream could notice).
  Its only caller today, the WhatsApp inbound path, already has everything `Via` needs.
- This does not touch `_answered`, `close`, the rung timing, the DOSE_RUNGS gaps, or the order
  any existing check runs in. Nothing here makes the ladder less likely to escalate in any
  scenario: the fallback in `doses_for_reply` still lands a late reply on the same dose it did
  before, and every existing refusal (`NotOnTheLadder`, scope checks, consent, quiet hours for
  a reminder, an alert's own never-quiet-never-capped rule) is unchanged. `_late_pattern` is
  additive beside `_pattern`, in the same non-safety part of the engine (the weekly family
  count, not the ladder); it does not change `tapped_by` or how `_pattern` finds an untapped
  dose, so a late tap still correctly never counts as one.
