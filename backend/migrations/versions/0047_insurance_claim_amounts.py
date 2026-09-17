"""The insurance ledger (T2): three amounts on a claim already on the spine
(`0046_insurance_policies_claims`) — what was claimed, what the insurer paid, what he paid
himself, all in minor units (cents/sen) so no line ever carries a rounded fraction.

`insurance_claim` already carries its status and the visit and policy it sits under
(`app.insurance.claim`); it did not carry a single amount, so the ledger
(`app.insurance.ledger`) had nothing to sum. All three columns are nullable: a claim is filed
before its amount is always known, an insurer's payout before it is approved, and what he
paid himself before the claim is settled — a claim sits in the ledger the whole time, the
amounts filling in as `app.insurance.claim.file_a_claim` and `change_claim_status` learn them,
each on its own yes.

Chained onto `0046_insurance_policies_claims`, the newest migration on `main` as of this
branch; the operator re-chains at merge time if another PR lands first, same as `0046`
itself did.

Revision ID: 0047_insurance_claim_amounts
Revises: 0046_insurance_policies_claims
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_insurance_claim_amounts"
down_revision = "0046_insurance_policies_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insurance_claim", sa.Column("claimed_amount_cents", sa.Integer(), nullable=True)
    )
    op.add_column(
        "insurance_claim", sa.Column("paid_by_insurer_cents", sa.Integer(), nullable=True)
    )
    op.add_column(
        "insurance_claim", sa.Column("paid_by_patient_cents", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("insurance_claim", "paid_by_patient_cents")
    op.drop_column("insurance_claim", "paid_by_insurer_cents")
    op.drop_column("insurance_claim", "claimed_amount_cents")
