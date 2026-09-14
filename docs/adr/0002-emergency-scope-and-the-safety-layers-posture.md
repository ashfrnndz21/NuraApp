# ADR 0002 — What the EMERGENCY scope opens, and how the safety layer sets the day's posture

**Date** 2026-09-14 · **Status** accepted · **Decided by** the E13 builder, for the operator to confirm

## Context

E13-01 gives every role preset the `EMERGENCY` scope so that a neighbour or a helper holding
an emergency-only key can hand a stranger the card. But the card is made of things other
scopes guard — conditions (RECORDS), medicines (MEDICINES), the chief's number (FAMILY) — and
State (`app/state/service.py`) only renders for a key that can recompute it, which an
emergency-only key cannot. E13-02 must move the day's posture to ACT on a red flag, but
`app/state/dimensions.py` reads a posture from one thing only: a `control` word on a fact.

## Decisions

1. **EMERGENCY opens one fixed projection and nothing else.** `app/safety/emergency_card.py`
   reads, under `Scope.EMERGENCY` and on the trail as such: control-word facts in the clinical
   dimension, allergy facts, a blood-type fact, a birth-year fact (shown as a decade band),
   the active medication lines, the active chief keys (and the Person rows they name, for a
   display name and a number), the profile's providers, and the date of the last READING
   event. No reading values, no notes, no visits, no history. The projection is the
   definition of the scope; adding to it is a change to this ADR.

2. **A key that cannot recompute State renders from the last snapshot, checked the narrow
   way.** `render_from_last_snapshot` (added to `app/state/service.py`) reads the latest
   snapshot under the caller's own scope and refuses the card unless every fact the card was
   composed from is in the snapshot's `computed_from` and its `stale_after` has not passed.
   The same promise as `render_from_state` — a stale card is refused, not shown — kept without
   reading anything the key does not hold. Keys that can recompute keep using
   `render_from_state`. Nothing else uses the new path.

3. **The safety layer sets the posture through a fact, never a snapshot.** A press of the
   not-feeling-well button writes a `feeling.control` fact — `act` for a red flag, `watch`
   otherwise — with a 24-hour window and the SYMPTOM event as provenance. `feeling` folds into
   the situational dimension, so it raises the day's posture without appearing among his
   conditions. State stays the choke point; safety is an input to it, as the spec says.

4. **Two things are data, not sentences.** The chief's phone number and a medicine's strength
   are what the standard forbids in a patient sentence and what a paramedic needs, so the card
   carries them as fields beside the verified lines (and in the printable page's table), never
   through a template. In Malay and Chinese the medicine sentence carries his name for it
   alone; the register's name is in the table.

5. **The words stay in the artefact.** A voice note is a VOICE artefact and typed words a
   MESSAGE artefact in the object store; the fact about how he feels holds codes from fixed
   tables (`app/safety/symptoms.py`, `app/safety/red_flags.py`). A notice to the family quotes
   the table's words for the code in the reader's language, never the transcript.

## Consequences

- Every role can hand over the card; a viewer or helper still cannot read a reading, a
  note or a visit. The emergency-only path is audited under EMERGENCY, so the owner sees
  exactly who rendered the card and when (`emergency_card` rows).
- A stale card for an emergency-only key is a 409 until the owner or the chief opens the
  app; the web client's cached last render covers the offline day. The operator may prefer
  a background recompute later; nothing here precludes it.
- `shaky_sweaty` is suppressed and named when no medicine is on record, per the rule that a
  flag depending on a missing fact is suppressed visibly.
