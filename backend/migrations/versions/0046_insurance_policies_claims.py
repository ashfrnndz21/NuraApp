"""E13-03: the fuller insurance record — policies and claims — beside the one field the
emergency card already keeps (`insurer`, E13-01, untouched by this migration).

Two tables. `policy`: insurer, policy reference, type, who and what it covers in his own
words, start and renewal dates, the premium's due date, status, and whether the insurer
works by guarantee letter — a history, like the insurer, tied to its own lineage
(`supersedes_id`) rather than to the whole profile, because a profile holds more than one
policy at once. `insurance_claim`: a claim against one policy, for one visit already on the
spine, with the insurer's own claim number where there is one, and its own status column,
moved only through `app.insurance.claim.change_claim_status`.

Both are read and written under `Scope.MONEY` (`app.insurance.policy`, the owner's decision):
the door already reserved for "your insurance letters" and already preset to nobody but a
chief.

Renumbered onto the shared chain at merge time: PR #225's `0044_consent_role_window` landed
on main first, and PR #235's `0045_scheduled_call` has now landed on top of it, so this
chains onto `0045`, the actual head, rather than the `0044` this once pointed at while
`0045` was still off main. The revision id is also shortened from the original
`0040_insurance_policies_and_claims` (34 characters): `alembic_version.version_num`
is `varchar(32)`, and the longer id failed both the `image` and `backend-postgres` CI jobs
with `StringDataRightTruncationError`.

Revision ID: 0046_insurance_policies_claims
Revises: 0045_scheduled_call
Create Date: 2026-09-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_insurance_policies_claims"
down_revision = "0045_scheduled_call"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


POLICY_TYPE = _enum(
    "policy_type", "hospital", "outpatient", "critical_illness", "government_scheme"
)
POLICY_STATUS = _enum("policy_status", "active", "lapsed", "cancelled")
INSURANCE_CLAIM_STATUS = _enum(
    "insurance_claim_status",
    "submitted",
    "in_review",
    "approved",
    "partially_approved",
    "rejected",
    "paid",
)


def upgrade() -> None:
    op.create_table(
        "policy",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("insurer_name", sa.String(length=120), nullable=False),
        sa.Column("policy_reference", sa.String(length=40), nullable=True),
        sa.Column("policy_type", POLICY_TYPE, nullable=False),
        sa.Column("covered", sa.String(length=120), nullable=True),
        sa.Column("covers", sa.String(length=400), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("premium_due_date", sa.Date(), nullable=True),
        sa.Column("status", POLICY_STATUS, nullable=False),
        sa.Column(
            "guarantee_letter", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("supersedes_id", sa.Uuid(), sa.ForeignKey("policy.id"), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("set_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "confirmation_id", sa.Uuid(), sa.ForeignKey("confirmation.id"), nullable=False
        ),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_policy_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "supersedes_id"],
            ["policy.profile_id", "policy.id"],
            name="fk_policy_supersedes_profile",
        ),
    )
    op.create_index("ix_policy_profile_id", "policy", ["profile_id"])
    op.create_index("ix_policy_set_at", "policy", ["set_at"])

    op.create_table(
        "insurance_claim",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("policy.id"), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), sa.ForeignKey("appointment.id"), nullable=False),
        sa.Column("claim_reference", sa.String(length=40), nullable=True),
        sa.Column("status", INSURANCE_CLAIM_STATUS, nullable=False),
        sa.Column("filed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column(
            "confirmation_id", sa.Uuid(), sa.ForeignKey("confirmation.id"), nullable=False
        ),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status_changed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True
        ),
        sa.Column(
            "status_changed_confirmation_id",
            sa.Uuid(),
            sa.ForeignKey("confirmation.id"),
            nullable=True,
        ),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_insurance_claim_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "policy_id"],
            ["policy.profile_id", "policy.id"],
            name="fk_insurance_claim_policy_profile",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "appointment_id"],
            ["appointment.profile_id", "appointment.id"],
            name="fk_insurance_claim_appointment_profile",
        ),
    )
    op.create_index("ix_insurance_claim_profile_id", "insurance_claim", ["profile_id"])
    op.create_index("ix_insurance_claim_policy_id", "insurance_claim", ["policy_id"])
    op.create_index("ix_insurance_claim_appointment_id", "insurance_claim", ["appointment_id"])
    op.create_index("ix_insurance_claim_filed_at", "insurance_claim", ["filed_at"])


def downgrade() -> None:
    op.drop_index("ix_insurance_claim_filed_at", table_name="insurance_claim")
    op.drop_index("ix_insurance_claim_appointment_id", table_name="insurance_claim")
    op.drop_index("ix_insurance_claim_policy_id", table_name="insurance_claim")
    op.drop_index("ix_insurance_claim_profile_id", table_name="insurance_claim")
    op.drop_table("insurance_claim")
    op.drop_index("ix_policy_set_at", table_name="policy")
    op.drop_index("ix_policy_profile_id", table_name="policy")
    op.drop_table("policy")
