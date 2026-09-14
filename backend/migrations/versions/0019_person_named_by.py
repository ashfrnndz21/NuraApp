"""W3 (E12 invite): a person's name can be somebody else's word for him, until he gives his own.

The owner lets in a number that is not an account yet, and the words he agrees to name that
person: the name he typed is kept on the account made for the number, with who typed it, so
that the person's own name replaces it when he signs in (`app.identity.login`). The column is
nullable: every account made before this, and every one a person made himself, has none.

Revision ID: 0019_person_named_by
Revises: 0012_visits
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_person_named_by"
down_revision = "0012_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("person") as person:
        person.add_column(sa.Column("named_by_person_id", sa.Uuid(), nullable=True))
        person.create_foreign_key(
            "fk_person_named_by_person_id_person", "person", ["named_by_person_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("person") as person:
        person.drop_constraint("fk_person_named_by_person_id_person", type_="foreignkey")
        person.drop_column("named_by_person_id")
