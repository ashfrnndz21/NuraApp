# ADR 0002 — What the EMERGENCY scope opens, and how the safety layer sets the day's posture

**Date** 2026-09-14 · **Status** accepted · **Decided by** the E13 builder; decisions 6–12 added
after the safety review of #111 and the merges of E16 and E19, on the operator's calls

## Context

E13-01 gives every role preset the `EMERGENCY` scope so that a neighbour or a helper holding
an emergency-only key can hand a stranger the card. But the card is made of things other
scopes guard — conditions (RECORDS), medicines (MEDICINES), the chief's number (FAMILY) — and
State (`app/state/service.py`) only renders for a key that can recompute it, which an
emergency-only key cannot. E13-02 must move the day's posture to ACT on a red flag, but
`app/state/dimensions.py` reads a posture from one thing only: a `control` word on a fact.

The safety review of #111 found three more things this ADR has to settle: whose Person rows
the safety layer reads and how that is written down; whether a red flag raised by someone
other than the patient — a caregiver, the WhatsApp helper — escalates; and what makes a flag
durable when something later in the same request is refused.

## Decisions

1. **EMERGENCY opens one fixed projection and nothing else.** `app/safety/emergency_card.py`
   reads, under `Scope.EMERGENCY` and on the trail as such: control-word facts in the clinical
   dimension, allergy facts, a blood-type fact, a birth-year fact (shown as a decade band),
   the active medication lines, the active chief keys, the profile's providers, and the date
   of the last blood-pressure READING event inside a year. No reading values, no notes, no
   visits, no history. The projection is the definition of the scope; adding to it is a
   change to this ADR.

   **The chief's name and number are part of the projection, by design.** A Person row is an
   account, not profile data, and `app.audit.access.person_display_name` gates a key holder's
   name on `Scope.FAMILY`. The card is the one exception: an EMERGENCY key exists for the
   moment he cannot speak, and a card with nobody to call is no card. So the account each
   active chief key names is read for its display name and phone number and nothing else,
   through `app.safety.people.key_holder`, under EMERGENCY, with its own READ line on the
   trail (target `person`, the account's id, the reader's key). Nothing reads a Person row raw
   in the safety layer. Precedent: `app/identity/doors.py` reads an account the same narrow
   way for a door that must name someone.

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
   tables (`app/safety/symptoms.py`, `app/safety/red_flags.py`). A notice to the family says
   the table's words for the code in the reader's language, never the transcript, and says
   so: "Nura heard this: chest pain."

6. **The red-flag path runs under EMERGENCY, whoever pressed.** "Red flags escalate
   immediately" (spec §8, `.claude/rules/safety.md`) does not depend on who heard the words.
   The button's door is `Scope.EMERGENCY`, which every role holds. The flag and the notices
   are written under EMERGENCY; who is told — every active key holder with EMERGENCY, the
   chief first — is read under EMERGENCY, not FAMILY, and each account on that list is read
   through `key_holder` with a READ line, for a name and a language. The medicines are read
   only when the key holds MEDICINES; otherwise they are unknown and the shaky-and-sweaty
   row is suppressed, visibly. So:
   - a **caregiver** (RECORDS, no FAMILY) raises the flag, tells the family, and writes the
     moment to the record; she cannot compute State, so no card row is written and she is
     shown the same lines;
   - the **helper** (no RECORDS) raises the flag and tells the family; nothing is written to
     the record — no artefact, no event, no fact, no card row — and the flag names no
     artefact. Her words are heard in memory only. `tests/test_not_feeling_well.py` holds both.

7. **A flag and its notices survive a refusal later in the same request.** Flags are written
   through `app.safety.red_flags.write_flag_kept(session, context, …)`: the audited door, and
   a keeper registered with `app.db.keep_on_refusal` — the mechanism REFUSED audit lines use.
   If anything further on is refused (a template that fails the standard, a stale State, a
   door), `unit_of_work` rolls the savepoint back and replays the keeper, which writes the
   same flag again (same id, same moment), the artefact row it names if that went too (its
   bytes are in the object store), and their WRITE lines. The notices that go with it are
   kept the same way (`keep_row`). Tested: a red flag, then a refusal → the flag row is there.

8. **The transcriber is pinned to a region.** The `Transcriber` port carries `region`;
   `capture` calls `guard_region` before a byte of audio is handed over, and the adapter
   checks again in `transcribe`. The fixture adapter declares the region it serves. A
   mismatch is `OutOfRegion`, and nothing is stored.

9. **Every voice note rests on the RECORDING consent.** E16 (#108) made it a rule of the store:
   `store_artifact` asks for `RECORDING` as well as `HOLD_HEALTH_RECORD` for every VOICE
   artefact, the patient's own included — which supersedes this ADR's first answer ("his own
   voice note is his words on his own record"). `capture` asks for it before a byte is kept
   or heard, whoever pressed, so the helper's voice note (which is heard and not kept) is held
   to it too. Typed words need no recording consent. The only RECORDING wording today is for a
   visit ("When you see the doctor, Nura listens."), and there is no route to give it for a
   voice note, so until the operator and counsel settle the words the button takes typed
   words over HTTP and a voice note is refused (`ConsentWithheld`, 403) — nothing kept, nothing
   heard. Checkpoint 14 shows the refusal and then types.

10. **Reads the safety layer makes of its own writes go through the door.** The symptom log
    reads the fact it has just written back through `audited_read`, under the fact's own scope
    (`scope_for_subject("symptom")`, RECORDS), with a READ line; the patient's own account, for
    the check-in notice, is read through `app.safety.people.owner_of` under PROFILE, with a
    READ line.

11. **A line that fails the standard is withheld from the emergency card, not the card.** The
    emergency card is composed line by line; a line that `NotPlainWords` refuses is left out
    and logged, and the rest of the card is shown. A card the stranger is holding is never
    taken away whole for one bad template. (The what-to-do card still refuses whole: its
    lines are few and each carries an instruction.)

12. **The not-feeling-well card carries the boundary; the emergency card does not infer.**
    E16's `render_from_state(surface=, boundary=)` refuses a row of an inferring surface
    without its line. The what-to-do card is `Surface.NOT_FEELING_WELL`: the lines he sees open
    with the boundary's reassurance — "Mei knows now." (`told` is the person the card names:
    whoever is on duty, else the chief) or "You did right to say so." when nobody is named —
    then the decision row, then "Nura wrote down how you feel." and the closing "This is not a
    doctor's advice." / "Ask Dr Tan." (the doctor on the label, else "your doctor"). The row
    stores the decision ids in `line_ids` and the boundary text in `boundary`. The red-flag row
    no longer says "Mei knows already." itself: the boundary's opening line is that reassurance.
    The emergency card is **not** an inferring surface: it restates the record — a projection
    of facts, medicines, contacts and a date — for a stranger, works nothing out, and carries
    its own disclaimer line ("This card is not a doctor's advice."). It names no `Surface` and
    its `boundary` column stays empty; adding it to the register would put "Ask your doctor."
    on a card handed to a paramedic.

## Consequences

- Every role can hand over the card; a viewer or helper still cannot read a reading, a
  note or a visit. The emergency-only path is audited under EMERGENCY, so the owner sees
  exactly who rendered the card and when (`emergency_card` rows) and whose name was read to
  put on it (`person` READ lines).
- A stale card for an emergency-only key is a 409 until the owner or the chief opens the
  app; the web client's cached last render covers the offline day. The operator may prefer
  a background recompute later; nothing here precludes it.
- `shaky_sweaty` is suppressed and named whenever it cannot be raised: no medicine on record,
  a key that does not open the medicines, or medicines none of which is in
  `SUGAR_MEDICINE_CLASSES` (under pharmacist review; a class the list does not know shows as
  a suppression rather than dropping what he said).
- Anyone with a key can raise a red flag about him. That is the point of decision 6; the
  trail names who pressed, and the flag row carries `raised_by_person_id`.
