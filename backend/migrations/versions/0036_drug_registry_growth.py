"""E00-06/E04-03: the registry now answers a product's kind, and a flag keeps its source.

`medication_line.product_kind`: a prescription medicine, a supplement or a TCM remedy, from
the registry's own `DrugMatch.product_kind` at the moment the line was written (E04-03 —
supplements and TCM are now first-class entries in the register, not pretended to be
prescription drugs). Nullable: a line written before this column existed carries none, and is
read as a prescription medicine, the only kind the register held then.

`interaction_flag.source` and `interaction_flag.awaiting_review`: what a pharmacist would
check a flagged pair against, and whether one already had when it was flagged
(`Interaction.source`, `Interaction.review_state`, E04-03). A pair not yet reviewed is still
shown to the patient — never silent — but as a question to ask a pharmacist rather than a
severity or a mechanism nobody has verified yet, and it is queued for the pharmacist review
queue the first time it is actually raised for a person (`app.language.review`). Both are
non-nullable with a default, so an existing row reads as `source=""`, `awaiting_review=False`
— reviewed, the only state a flag could have been written in before this column existed.

Renumbered onto main's head at merge time: main took 0035 for `0035_consult_upload` first, so
this follows it as 0036, not 0035.

Revision ID: 0036_drug_registry_growth
Revises: 0035_consult_upload
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_drug_registry_growth"
down_revision = "0035_consult_upload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("medication_line") as batch:
        batch.add_column(sa.Column("product_kind", sa.String(length=32), nullable=True))
    with op.batch_alter_table("interaction_flag") as batch:
        batch.add_column(
            sa.Column("source", sa.String(length=200), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "awaiting_review", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("interaction_flag") as batch:
        batch.drop_column("awaiting_review")
        batch.drop_column("source")
    with op.batch_alter_table("medication_line") as batch:
        batch.drop_column("product_kind")
