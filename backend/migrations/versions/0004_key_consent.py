"""E00-02: the key names the consent it was cut under.

`key` was shipped in 0001 with a free-text `basis`. The basis of a key is now the consent
row it rests on — who agreed, for whom, on what footing, to which words — so `consent_id`
replaces it. The shipped table is altered here in batch, never by editing 0001. The column
is nullable for keys cut before consent was recorded; `grant_key` always sets it.

This revision was the merge point of the consent and memory heads until the consent
revision was moved after the memory stores; neither shipped, so it carries this work now.

Revision ID: 0004_key_consent
Revises: 0003_consent
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_key_consent"
down_revision = "0003_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("key") as key:
        key.add_column(sa.Column("consent_id", sa.Uuid(), nullable=True))
        key.create_foreign_key("fk_key_consent_id_consent", "consent", ["consent_id"], ["id"])
        key.drop_column("basis")


def downgrade() -> None:
    with op.batch_alter_table("key") as key:
        key.add_column(sa.Column("basis", sa.String(length=64), nullable=False, server_default=""))
        key.drop_constraint("fk_key_consent_id_consent", type_="foreignkey")
        key.drop_column("consent_id")
