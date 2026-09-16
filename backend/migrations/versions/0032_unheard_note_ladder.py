"""#173: the ladder a voice note Nura could not hear climbs.

`delivery_ladder.note_id` is the note the ladder is about, when there is one to listen to:
what decides, for each person the ladder asks, whether she is told to listen in the app or
to call him. NULL where the audio never arrived, and on every other ladder. It carries the
profile with it, like every other reference here, so it can only land on the same profile.

`delivery_ladder.note_from_person_id` is who sent that note, so the notice can name them: a
note the helper sent is never said to be the patient's. NULL on every other ladder.

This goes on main's head at the time it is pushed: B1 (#147) landed first and took 0031, so
this is 0032 on top of it. The operator repoints `down_revision` if another story lands
before it again.

Revision ID: 0032_unheard_note_ladder
Revises: 0031_brief_safety
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_unheard_note_ladder"
down_revision = "0031_brief_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("delivery_ladder") as batch:
        batch.add_column(sa.Column("note_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("note_from_person_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_delivery_ladder_note_from_person", "person", ["note_from_person_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_delivery_ladder_note", "event_note", ["note_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_delivery_ladder_note_profile",
            "event_note",
            ["profile_id", "note_id"],
            ["profile_id", "id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("delivery_ladder") as batch:
        batch.drop_constraint("fk_delivery_ladder_note_profile", type_="foreignkey")
        batch.drop_constraint("fk_delivery_ladder_note", type_="foreignkey")
        batch.drop_constraint("fk_delivery_ladder_note_from_person", type_="foreignkey")
        batch.drop_column("note_from_person_id")
        batch.drop_column("note_id")
