"""#206: a drug match is scored, not just found; the score is kept with the line.

`medication_line.registry_confidence`: how sure the licensed registry was that its match is
this product (`DrugMatch.confidence`) — 1.0 for a registration number, or a name whose
strength and form both belonged to the matched product; a line is never written below
`app.ingestion.models.CONFIDENCE_THRESHOLD` (`app.medicines.service._one_product`), the same
floor a document field and a WhatsApp voice transcript are already held to. Nullable: a line
written before this column existed carries none — it predates the score, not the product.

Revision ID: 0036_drug_match_confidence
Revises: 0035_consult_upload
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_drug_match_confidence"
down_revision = "0035_consult_upload"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("medication_line") as batch:
        batch.add_column(sa.Column("registry_confidence", sa.Float(), nullable=True))
        batch.create_check_constraint(
            "ck_medication_line_registry_confidence",
            "registry_confidence >= 0 AND registry_confidence <= 1",
        )


def downgrade() -> None:
    with op.batch_alter_table("medication_line") as batch:
        batch.drop_constraint("ck_medication_line_registry_confidence", type_="check")
        batch.drop_column("registry_confidence")
