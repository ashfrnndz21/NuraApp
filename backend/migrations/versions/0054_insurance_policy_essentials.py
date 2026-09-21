"""Insurance policy essentials (package 12a, `app.insurance.policy`): the plan name, what a
policy document itself prints — what it covers, what it does not, its benefits and limits,
and how to claim — plus the end date, waiting period and claims contact when the pages print
them, and which confirmed review card (if any) the essentials were read from. `plan` is its
own column now, never folded into `covers` (the free-text "what it covers" a person or a
chief typed) the way the passport's own display once mislabelled it.

Ten nullable columns on `policy`, `NULL` on every row written before this package and on
any row still typed by hand rather than loaded from a paper. `coverage_items`, `excludes`,
`benefits` and `claim_steps` are JSON lists of `{"text": str, "page": int | None}` — the same
shape `app.insurance.policy.EssentialItem.as_json()` builds, never a number parsed out of a
benefit's printed amount for anything downstream to compute with. `review_card_id` points at
the confirmed `review_card` the essentials came from, when there is one, so "See the policy
itself" can reuse the existing audited artifact route rather than a new one — tied to the
profile with it (`fk_policy_review_card_profile`, a composite `(profile_id, review_card_id)`
key onto `review_card(profile_id, id)`), the same discipline `supersedes_id` already keeps,
so a row can never point at another profile's card even if a caller's own check missed it
(independent review, package 12a fix round, item 7 — the bare single-column key this
migration first shipped could not refuse that). `essentials_cut` is a JSON list naming which
of the four lists above were actually longer than `app.insurance.policy.ESSENTIAL_LIST_CAP`
and so cut, `NULL` when none were (fix round, item 4) — never left for a reader to guess from
a list's length happening to equal the cap.

The current model could not hold a list at all — `covers`/`covered` are single short strings
— so this migration was necessary, not a choice; it adds columns only, touches no existing
one, and is reversible on SQLite (`batch_alter_table`) the same way `0053_paper_insight`
already is.

Revision ID: 0054_insurance_policy_essentials
Revises: 0053_paper_insight
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0054_insurance_policy_essentials"
down_revision = "0053_paper_insight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("policy") as batch:
        batch.add_column(sa.Column("plan", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("coverage_items", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("excludes", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("benefits", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("claim_steps", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ends_on", sa.Date(), nullable=True))
        batch.add_column(sa.Column("waiting_period", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("claims_contact", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("review_card_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("essentials_cut", sa.JSON(), nullable=True))
        batch.create_foreign_key(
            "fk_policy_review_card", "review_card", ["review_card_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_policy_review_card_profile",
            "review_card",
            ["profile_id", "review_card_id"],
            ["profile_id", "id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("policy") as batch:
        batch.drop_constraint("fk_policy_review_card_profile", type_="foreignkey")
        batch.drop_constraint("fk_policy_review_card", type_="foreignkey")
        batch.drop_column("essentials_cut")
        batch.drop_column("review_card_id")
        batch.drop_column("claims_contact")
        batch.drop_column("waiting_period")
        batch.drop_column("ends_on")
        batch.drop_column("claim_steps")
        batch.drop_column("benefits")
        batch.drop_column("excludes")
        batch.drop_column("coverage_items")
        batch.drop_column("plan")
