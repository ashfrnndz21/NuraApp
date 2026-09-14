# ADR 0003 — The recording consent covers other people's voices; a person's own voice note is his record

**Date** 2026-09-14 · **Status** accepted · **Decided by** the operator, for the owner · **Stories** E16-02, E02-06 (and E02-05, E05, E13/E14 when they land)

## Context

E16-02 made `store_artifact` require the RECORDING consent for every VOICE artefact. Its words are about the doctor's room — "When you see the doctor, Nura listens. Nura keeps what you and the doctor say." — because a recording of a visit captures a second person, the doctor, who is not Nura's user; that is what the notice, the printed card and counsel's questions in `docs/trust/recording-consent.md` are for.

E02-06 adds voice notes on any event, and E13/E14 hear "not feeling well" said aloud. Held to the same gate, a patient could not say "I felt fine after my walk" into his own record without first agreeing to words about being listened to at the doctor's — words that do not describe what he is doing, which is the one thing a consent's words must never be wrong about. A caregiver's note on his reading would need his agreement to a doctor's-room recording she is not making.

## Decision

1. **The RECORDING consent gates recordings that capture people other than the account holder**: consult recordings — E02-05's recording surface, E05's consult transcripts. They rest on RECORDING under the visits scope, as `may_record` already asks, as well as on holding the record.
2. **A person's own voice note about himself is his own words**: a note on an event, a not-feeling-well message, a symptom said aloud. It is kept on HOLD_HEALTH_RECORD, exactly like typed text.
3. **A caregiver's voice note on his event is her own words**: kept on his HOLD_HEALTH_RECORD and her key's scope (a shared note under the record's scope; a private note needs the notes scope, which her key does not hold unless he gave it).
4. **Every writer declares which it is, where the bytes enter.** `app.memory.episodic.store_artifact` takes `recording: Recording` — `Recording.CONSULT` or `Recording.OWN_NOTE` — for every VOICE artefact (and a transcript kind when one exists), and refuses a voice without it, or a non-voice with it (`RecordingNotDeclared`, on the trail). There is no default, so no caller can omit the decision.

## Consequences

- `app/ingestion/notes.py` (E02-06) stores voice notes as `Recording.OWN_NOTE`. The recorded spoken yes behind a `VERBAL_RECORDED` consent carries the witness's voice as well as the patient's, so it is `Recording.CONSULT`.
- **E05 (PR #105)**: consult transcripts, and any VOICE artefact of a visit, pass `Recording.CONSULT` when that story merges; a transcript `ArtifactKind` joins `RECORDED_KINDS` the day it exists. **E13/E14 (PR #111)**: a not-feeling-well voice message and a symptom said aloud pass `Recording.OWN_NOTE`.
- `POST /profiles/{id}/consents/recording` stays (E02 added it; E05 adds the same route — the second to merge dedupes). Checkpoint 18's voice note no longer grants it and asserts it is not asked.
- The RECORDING words stay as they are: they describe consult recordings, which is now all they cover. If a future surface records other people outside a visit (a family call), it is a consult for this purpose and the words must first be checked to describe it.
- The trail shows the difference: a consult refused without the consent is a refused read of `consent` under `visits`; an own note has no such line.

**Addendum (E11-04, 2026-09-15).** A card's spoken twin is synthesised speech of Nura's own lines, not a recording of anyone: it is never a VOICE artefact and never an `Artifact` row, so neither `Recording` applies. It is a derived cache object in the region-pinned object store, keyed by the digest of the voice, the language and the words (`voice/<profile_id>/<sha256>`, `app.delivery.voice`).
