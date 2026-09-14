"""E01-01: the doors, proxy setup and the claim.

A profile may now have no owner yet: `owner_person_id` becomes nullable, because a graph set
up *for someone* by his phone number is held by a steward until he claims it. The number it
was set up against is `patient_phone_e164`, unique — one graph per number, ever, which is
how two siblings cannot set up two graphs for one father. Graphs already opened by their
owners get the owner's own number written in, so the rule covers them too.

The new `stewardship` table says who holds an unowned graph, on what footing, and — once
closed — who claimed it: the steward's chief key (`key_id`), the agreement to keeping the
record he gave on the patient's behalf (`consent_id`, which carries the document behind a
documented basis), the declared `basis`, and who he said he is to the patient.

Two enums grow a member without a schema change, because every enum here is a checked
string with no database constraint: `consent_basis` gains `patient_asked` (the patient
asked, and his claim is the proof) and `confirm_subject` gains `claim` (the patient's OK).

The downgrade refuses on a database holding a stewarded graph: a graph with no owner cannot
be represented below this revision, and a migration does not pick an owner for it.

Revision ID: 0007_doors_and_stewardship
Revises: 0006_state_snapshot
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_doors_and_stewardship"
down_revision = "0006_state_snapshot"
branch_labels = None
depends_on = None

CONSENT_BASIS = sa.Enum(
    "owner",
    "lpa",
    "medical_letter",
    "verbal_recorded",
    "patient_asked",
    name="consent_basis",
    native_enum=False,
    length=32,
)
PATIENT_PHONE_UNIQUE = "uq_profile_patient_phone_e164"


def _refuse_if_stewarded() -> None:
    """Stop rather than drop, or invent, the owner of a graph nobody has claimed."""
    unowned = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM profile WHERE owner_person_id IS NULL")
    )
    if unowned:
        raise RuntimeError(
            f"{unowned} profile(s) have no owner yet — set up for someone and not claimed — "
            "and below this revision a profile must have one; a migration does not choose "
            "it. Sort them out by hand before downgrading"
        )


def upgrade() -> None:
    with op.batch_alter_table("profile") as profile:
        profile.alter_column("owner_person_id", existing_type=sa.Uuid(), nullable=True)
        profile.add_column(sa.Column("patient_phone_e164", sa.String(length=20), nullable=True))
        profile.create_unique_constraint(PATIENT_PHONE_UNIQUE, ["patient_phone_e164"])
    # A graph its owner opened himself is the graph for his number.
    op.execute(
        "UPDATE profile SET patient_phone_e164 = "
        "(SELECT person.phone_e164 FROM person WHERE person.id = profile.owner_person_id) "
        "WHERE owner_person_id IS NOT NULL"
    )

    op.create_table(
        "stewardship",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("steward_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("key_id", sa.Uuid(), sa.ForeignKey("key.id"), nullable=False),
        sa.Column("consent_id", sa.Uuid(), sa.ForeignKey("consent.id"), nullable=False),
        sa.Column("basis", CONSENT_BASIS, nullable=False),
        sa.Column("relationship", sa.String(length=80), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
    )
    op.create_index("ix_stewardship_profile_id", "stewardship", ["profile_id"])
    op.create_index("ix_stewardship_steward_person_id", "stewardship", ["steward_person_id"])


def downgrade() -> None:
    _refuse_if_stewarded()
    op.drop_index("ix_stewardship_steward_person_id", table_name="stewardship")
    op.drop_index("ix_stewardship_profile_id", table_name="stewardship")
    op.drop_table("stewardship")
    with op.batch_alter_table("profile") as profile:
        profile.drop_constraint(PATIENT_PHONE_UNIQUE, type_="unique")
        profile.drop_column("patient_phone_e164")
        profile.alter_column("owner_person_id", existing_type=sa.Uuid(), nullable=False)
