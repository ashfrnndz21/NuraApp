"""board-fidelity-round-2: a home-care category on the provider directory.

Services' home-care grid (the concept board, "Care services": Nursing at home, Physio,
Meals, Transport) is backed by the same `provider` table the doctors-and-clinics directory
already uses, not a second table — a provider is still a provider. This adds one nullable
column, `category` (`app.memory.models.HomeCareCategory`: `nursing`, `physio`, `meals`,
`transport`), null for every existing row and for every provider added through the ordinary
directory API, and set only by the demo seed's four home-care tiles.

Chained onto `0047_insurance_claim_amounts` (#260), which landed on `main` first; this
branch started against `0046_insurance_policies_claims` and is re-chained here at merge
time, the same practice `0046` and `0047_insurance_claim_amounts` themselves already used.

Revision ID: 0048_provider_category
Revises: 0047_insurance_claim_amounts
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_provider_category"
down_revision = "0047_insurance_claim_amounts"
branch_labels = None
depends_on = None

HOME_CARE_CATEGORY = sa.Enum(
    "nursing", "physio", "meals", "transport", name="home_care_category", native_enum=False, length=32
)


def upgrade() -> None:
    with op.batch_alter_table("provider") as batch:
        batch.add_column(sa.Column("category", HOME_CARE_CATEGORY, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("provider") as batch:
        batch.drop_column("category")
