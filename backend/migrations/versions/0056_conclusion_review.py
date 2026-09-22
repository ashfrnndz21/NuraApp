"""D3 — a rejected or corrected AI conclusion is recorded (ADR 0019 point 7;
`docs/design/NURA-BUILD-MASTER-SPEC.md` §39): `conclusion_review`, beside the existing
`audit_entry` (`Action.REVIEW`, unchanged shape — no migration needed for that, since
`Action` is a checked string, not a native enum type). Every column here is an enum, an id or
a timestamp, never free text (`app.audit.conclusions`'s own module doc): `response_kind` says
who rejected it (a gate, or a person's "No" or "Fix"); `reason_code` and `rule_id` say which
gate, for a gate's own drop; `resulting_state_id` points at the State this profile stood at
afterwards.

Numbered 0056: 0055 (`whose_paper_and_duplicates`, PR #330, Engine B on `intake-whose-paper`)
chains onto the same 0054 this branch was cut from and touches `review_card` plus
`ix_artifact_profile_sha256` only — no table this migration creates or touches. `down_revision`
below chains directly onto it, so **PR #331 (this branch) merges after PR #330**, not before:
`nura-runtime` does not carry 0055's own file, so `tests/test_migration.py`'s chain-order and
single-head tests are red on this branch in isolation (there is no earlier revision named
"0055_whose_paper_and_duplicates" for `down_revision` to resolve against) and green again the
moment #330 lands on `redesign` first. Verified by merging `origin/intake-whose-paper` into a
throwaway worktree off this branch and running `tests/test_migration.py` there — passed, no
table overlap.

Revision ID: 0056_conclusion_review
Revises: 0055_whose_paper_and_duplicates
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056_conclusion_review"
down_revision = "0055_whose_paper_and_duplicates"
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
