# ADR 0004 — A row is read under the scope it was written under

**Date** 2026-09-15 · **Status** proposed · **Decided by** the security builder, for the
operator's review

## Context

Scope was enforced per table: `scoped_select(model, context, scope)` checked the scope the
caller named and returned every row of the table on the profile. Two tables hold rows of
different kinds written under different scopes, so rows leaked across:

- the artefact table holds papers (RECORDS), the family's WhatsApp messages (FAMILY), the
  words of a fall (EMERGENCY) and the questions asked of Nura (ASK); a read under RECORDS by a
  key holding RECORDS only returned all of them, by reference;
- the fact table holds medicines (MEDICINES), readings (READINGS) and the rest of the record
  (RECORDS); `GET /profiles/{id}/facts` with no subject returned all three to a RECORDS key.

## Decisions

1. **Artefacts and events say the scope they were written under.** `written_scope` (NOT NULL,
   migration 0019) is set by `scoped_new` from the scope of the write; no caller names it.
   `scoped_select` filters `written_scope IN context.scopes` in the same expression as the
   profile filter, so every reader, through any door, gets rows of the key's scopes only.
2. **A reading taken is written under READINGS, a tablet taken under MEDICINES**
   (`episodic.EVENT_SCOPES`); the timeline already read them so. Everything else
   `record_event` writes is the record's.
3. **Facts are narrowed by their readers, not by `scoped_select`.** A fact's scope is its
   subject's (`scope_for_subject`), and every reader of more than one subject reads one held
   scope at a time (`fact_is_under`, now `keys.scopes.subject_is_under`), including the
   no-subject `current_facts` and `GET /facts`. The fact table's door stays the caller's
   because EMERGENCY's card is one projection across subjects (ADR 0002).
4. **A reference the key may not follow is withheld by name.** A fact, event, medicine line,
   WhatsApp message or trail line is shown under its own scope; the artefact or event it cites
   is shown under that row's own. Where the key does not hold it the id is left out and
   `withheld` names it (`"artifact"`, `"event"`, `"target"`) — never the id, never a silent gap
   (`episodic.withheld_references`). A key holding every scope reads nothing extra to learn so.
5. **The region pin on provenance looks at every row.** `scoped_references` is a predicate,
   never a read: a fact resting on bytes held in another region is served to nobody, whether
   or not the reader may see the artefact.
6. **ADR 0002's projection has its own door.** The card reads the date of the last
   blood-pressure reading, a READINGS row, under EMERGENCY. It does so through
   `audited_projection_read`/`scoped_projection`, and a test fails if anything else calls it.
7. **A full recompute needs every scope a fact can sit under.** `RECOMPUTE_SCOPES` adds
   READINGS and MEDICINES: a chief with one of them marked "only me" would otherwise fold a
   State without it that became the profile's for everyone. The owner and a full chief fold
   exactly what they folded before.
8. **A card cites only what its scope opens.** A story about a paper is a RECORDS card: it is
   made only for an artefact written under RECORDS, and its `why` cites the record's facts.
9. **Cards composed before this are dropped.** 0019 deletes every `feed_item` — a cache made
   again from State on the next read — so no card composed under the old rules keeps a
   citation its reader may not see. With them go the page cache (`feed_page`) and each
   engagement with a card (`feed_engagement`, whose foreign key holds the card); every
   engagement is also an ENGAGEMENT event on the record, which stays with the preference facts
   resting on it. A card he had seen may be shown once more.
10. **No raw read of the three tables outside `app/memory`.** A test fails on `select(Fact)`,
   `select(Artifact)`, `select(Event)`, a `session.get` of them, or a raw reader handed one of
   them, anywhere else; the one exception is the safety rules' read as the system
   (`red_flags._system_read`, ADR 0002), which returns nothing to the caller.

## Backfill (0019)

Each row takes the scope of the path that wrote it, first rule that fits; a message whose
source is unknown takes FAMILY, the narrowest a message could have been written under; a row
no rule reaches stops the upgrade. The rules are in the migration's docstring.

## Consequences

- `tests/test_row_scope.py` walks every read route under `/profiles/{id}/` for every preset
  role and a key narrowed to each single scope; a new route must be registered or the test
  fails.
- A narrower key's read now writes one more line on the trail when it checks which
  references it may follow.
- Every feed card is rendered again after the upgrade (decision 9).
- FastAPI, Starlette and SQLAlchemy are pinned exactly (`backend/pyproject.toml`): the route
  registry test enumerates the app's routes, and a newer FastAPI stores included routers
  differently.
