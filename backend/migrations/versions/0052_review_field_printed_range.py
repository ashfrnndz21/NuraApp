"""E02, defect #3: a review field's own printed range and paper label.

`review_field` gains two columns, both optional and additive:

- `range` (JSON): the result's own printed reference range, when the row on the paper carried
  one — `{"low": number|null, "high": number|null, "text": string}`, the range exactly as
  printed with its bounds parsed where they are unambiguous. Folded from a legacy
  `<analyte>_reference_range` sibling field server-side (`app.ingestion.extract.
  fold_legacy_reference_ranges`) where an older extractor answer, or a fixture, still carries
  the range that way; written directly by a current extractor answer otherwise.
- `label_on_paper` (string): the words printed on the paper for the line, when the extractor
  named them — always present when `attribute` is `"other"` (a line outside the controlled
  vocabulary), optional otherwise. What the web client's `fieldLabel` falls back to ahead of
  its own generic line name.

Neither column changes what a card already shows: both are null on every existing row, and
the confirm flow ignores them entirely.

Revision ID: 0052_review_field_printed_range
Revises: 0051_health_analyst
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0052_review_field_printed_range"
down_revision = "0051_health_analyst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("review_field") as field:
        field.add_column(sa.Column("range", sa.JSON(), nullable=True))
        field.add_column(sa.Column("label_on_paper", sa.String(length=120), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("review_field") as field:
        field.drop_column("label_on_paper")
        field.drop_column("range")
