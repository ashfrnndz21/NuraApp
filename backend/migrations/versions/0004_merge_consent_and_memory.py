"""Join the two heads built side by side: the consent record (E00-02) and the memory stores
(E00-03). Both revise 0002; this revision has no work of its own, it only gives the chain
one head again so `alembic upgrade head` knows where head is.

Revision ID: 0004_merge
Revises: 0003_consent, 0003_memory
Create Date: 2026-09-14
"""

from __future__ import annotations

revision = "0004_merge"
down_revision = ("0003_consent", "0003_memory")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
