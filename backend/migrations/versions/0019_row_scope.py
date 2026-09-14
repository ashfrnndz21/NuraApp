"""Security: every artefact and event row says the scope it was written under.

Scope was checked per table, by the scope the reader named, so rows of different kinds
written into one table under different scopes leaked across: a read of the artefact table
under the record's scope returned the family's WhatsApp messages (written under FAMILY) and
the questions asked of Nura (written under ASK). From here `written_scope` is set by
`app.keys.repository.scoped_new` from the scope of the write, and every read filters on it in
the same expression as the profile filter (`scoped_select`).

The rows already here are given the scope the path that wrote them writes under, decided
from what the row and its neighbours say, one rule at a time, the first that fits:

artefact
  1. ASK — a MESSAGE whose bytes are under `questions/`: `app.search.ask._keep_question`, the
     only writer under that prefix.
  2. FAMILY — a MESSAGE a WhatsApp message of kind `coordination` names
     (`app.channels.whatsapp.inbound._coordination` keeps it under the family's scope).
  3. EMERGENCY — a MESSAGE a WhatsApp message of kind `red_flag` names (`_red_flag`).
  4. RECORDS — a MESSAGE any other WhatsApp message names: a health event, an answer, a
     check-in answer, kept under the record's scope (`_keep_text`'s default).
  5. FAMILY — a MESSAGE nothing above explains. Its source is not known, and this migration
     does not guess one: it takes the narrowest scope a message could have been written
     under. FAMILY is preset to the owner and his chief only; ASK adds caregivers, RECORDS
     caregivers and clinics, EMERGENCY nearly every key. The owner and the chief still read it.
  6. VISITS — a TRANSCRIPT: its only writer is `app.reasoning.visits.summary` (E05), keeping
     a consult (`Recording.CONSULT`), which `store_artifact` writes under the visits scope,
     the scope a consult's consent is asked under (ADR 0003).
  7. RECORDS — every other artefact: a photo, a PDF, a voice, a reading, a screenshot. Their
     only writers are `app.memory.episodic.store_artifact` and the evidence a stewardship is
     opened on (`app.identity.doors`), both under the record's scope; every voice kept so far
     is someone's own note, not a consult.

event
  1. READINGS — a READING: the moment a reading was taken is the readings' part (the
     timeline already read it so); `record_event` writes it there from now on.
  2. MEDICINES — a DOSE_TAKEN (`app.medicines.service.record_dose_taken`).
  3. The artefact's scope — a MESSAGE naming an artefact: the family's message event names
     the family's message, and is written under the same scope (`_coordination`).
  4. FAMILY — a MESSAGE naming no artefact: not known, the narrowest plausible, as above.
  5. EMERGENCY — a SYMPTOM that came in on WhatsApp, names no artefact, and a red flag rests
     on: the moment of a fall said on WhatsApp (`app.safety.red_flags.record_the_moment`).
     A symptom tapped in the app, or a check-in answer, carries a flag or an artefact
     differently and is the record's (rule 6).
  6. RECORDS — every other event: a visit, a discharge, an engagement, a symptom
     (`record_event`, under the record's scope).

A row no rule reaches stops the upgrade rather than take a value nobody chose.

Revision ID: 0019_row_scope
Revises: 0017_trends_routines_calendar
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_row_scope"
down_revision = "0017_trends_routines_calendar"
branch_labels = None
depends_on = None

SCOPE = sa.Enum(
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
    "profile",
    name="scope",
    native_enum=False,
    length=32,
)

TABLES = ("artifact", "event")

_STILL_OPEN = "written_scope IS NULL"

ARTIFACT_RULES: tuple[str, ...] = (
    # 1. A question asked of Nura.
    (
        f"UPDATE artifact SET written_scope = 'ask' WHERE {_STILL_OPEN} "
        "AND kind = 'message' AND storage_key LIKE 'questions/%'"
    ),
    # 2. The family's WhatsApp message.
    (
        f"UPDATE artifact SET written_scope = 'family' WHERE {_STILL_OPEN} AND kind = 'message' "
        "AND id IN (SELECT artifact_id FROM whatsapp_message WHERE kind = 'coordination' "
        "AND artifact_id IS NOT NULL)"
    ),
    # 3. The words of a fall, or another red flag, said on WhatsApp.
    (
        f"UPDATE artifact SET written_scope = 'emergency' WHERE {_STILL_OPEN} AND kind = 'message' "
        "AND id IN (SELECT artifact_id FROM whatsapp_message WHERE kind = 'red_flag' "
        "AND artifact_id IS NOT NULL)"
    ),
    # 4. Any other kept WhatsApp message: a health event, an answer, a check-in answer.
    (
        f"UPDATE artifact SET written_scope = 'records' WHERE {_STILL_OPEN} AND kind = 'message' "
        "AND id IN (SELECT artifact_id FROM whatsapp_message WHERE artifact_id IS NOT NULL)"
    ),
    # 5. A message whose source is not known: the narrowest plausible scope.
    (f"UPDATE artifact SET written_scope = 'family' WHERE {_STILL_OPEN} AND kind = 'message'"),
    # 6. A transcript of a visit: a consult, kept under the visits scope.
    f"UPDATE artifact SET written_scope = 'visits' WHERE {_STILL_OPEN} AND kind = 'transcript'",
    # 7. A photo, a PDF, a voice, a reading, a screenshot: the record's.
    (f"UPDATE artifact SET written_scope = 'records' WHERE {_STILL_OPEN} AND kind <> 'message'"),
)

EVENT_RULES: tuple[str, ...] = (
    # 1. A reading taken.
    (f"UPDATE event SET written_scope = 'readings' WHERE {_STILL_OPEN} AND kind = 'reading'"),
    # 2. A tablet taken.
    (f"UPDATE event SET written_scope = 'medicines' WHERE {_STILL_OPEN} AND kind = 'dose_taken'"),
    # 3. A message naming its artefact: the artefact's scope.
    (
        "UPDATE event SET written_scope = (SELECT artifact.written_scope FROM artifact "
        f"WHERE artifact.id = event.artifact_id) WHERE {_STILL_OPEN} AND kind = 'message' "
        "AND artifact_id IS NOT NULL"
    ),
    # 4. A message naming nothing: the narrowest plausible scope.
    (f"UPDATE event SET written_scope = 'family' WHERE {_STILL_OPEN} AND kind = 'message'"),
    # 5. The moment of a red flag said on WhatsApp.
    (
        f"UPDATE event SET written_scope = 'emergency' WHERE {_STILL_OPEN} AND kind = 'symptom' "
        "AND source_channel = 'whatsapp' AND artifact_id IS NULL "
        "AND id IN (SELECT event_id FROM red_flag)"
    ),
    # 6. Everything else: the record's.
    (f"UPDATE event SET written_scope = 'records' WHERE {_STILL_OPEN}"),
)


def _refuse_if_any(table: str) -> None:
    """Stop rather than give a row a scope no rule chose."""
    left = op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table} WHERE {_STILL_OPEN}"))
    if left:
        raise RuntimeError(
            f"{left} row(s) in {table} match no rule for the scope they were written under; "
            "decide them by hand before upgrading"
        )


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("written_scope", SCOPE, nullable=True))
    for statement in (*ARTIFACT_RULES, *EVENT_RULES):
        op.execute(statement)
    for table in TABLES:
        _refuse_if_any(table)
        with op.batch_alter_table(table) as batch:
            batch.alter_column("written_scope", existing_type=SCOPE, nullable=False)


def downgrade() -> None:
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("written_scope")
