"""D3 — a rejected or corrected AI conclusion is recorded (ADR 0019 point 7;
`docs/design/NURA-BUILD-MASTER-SPEC.md` §39): `conclusion_review`, beside the existing
`audit_entry` (`Action.REVIEW`, unchanged shape — no migration needed for that, since
`Action` is a checked string, not a native enum type). Every column here is an enum, an id or
a timestamp, never free text (`app.audit.conclusions`'s own module doc): `response_kind` says
who rejected it (a gate, or a person's "No" or "Fix"); `reason_code` and `rule_id` say which
gate, for a gate's own drop; `resulting_state_id` points at the State this profile stood at
afterwards.

Numbered 0056: 0055 (`whose_paper_and_duplicates`) is Engine B's, on `intake-whose-paper`,
built in parallel — coordinated by number rather than by a shared branch. `down_revision`
below chains onto 0054, the head this branch was cut from, because 0055 does not exist on
this branch's own history yet (it is uncommitted on `intake-whose-paper` at the time this was
written) and `tests/test_migration.py`'s own chain-order property needs every revision it
scans to resolve within the branch it runs on. **Whoever merges this branch with
`intake-whose-paper` must repoint `down_revision` to `"0055_whose_paper_and_duplicates"`** —
an ordinary two-branch migration merge, not a defect in either migration.

Revision ID: 0056_conclusion_review
Revises: 0054_insurance_policy_essentials
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_conclusion_review"
down_revision = "0054_insurance_policy_essentials"
branch_labels = None
depends_on = None

RESPONSE_KIND = sa.Enum(
    "gate_dropped",
    "user_no",
    "user_fix",
    name="conclusion_response_kind",
    native_enum=False,
    length=32,
)
REASON_CODE = sa.Enum(
    "plain_words",
    "conclusion_language",
    "caregiver_voice",
    "no_cite_matched",
    name="conclusion_reason_code",
    native_enum=False,
    length=32,
)


def upgrade() -> None:
    op.create_table(
        "conclusion_review",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "audit_entry_id", sa.Uuid(), sa.ForeignKey("audit_entry.id"), nullable=False
        ),
        sa.Column("response_kind", RESPONSE_KIND, nullable=False),
        sa.Column("reason_code", REASON_CODE, nullable=True),
        sa.Column("rule_id", sa.Integer(), nullable=True),
        sa.Column(
            "resulting_state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=True
        ),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_conclusion_review_profile_id", "conclusion_review", ["profile_id"])
    op.create_index(
        "ix_conclusion_review_audit_entry_id", "conclusion_review", ["audit_entry_id"]
    )
    op.create_index("ix_conclusion_review_at", "conclusion_review", ["at"])


def downgrade() -> None:
    op.drop_index("ix_conclusion_review_at", table_name="conclusion_review")
    op.drop_index("ix_conclusion_review_audit_entry_id", table_name="conclusion_review")
    op.drop_index("ix_conclusion_review_profile_id", table_name="conclusion_review")
    op.drop_table("conclusion_review")
