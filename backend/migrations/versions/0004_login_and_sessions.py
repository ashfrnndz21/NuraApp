"""E00-09: login challenges, sessions, and the note.

A login challenge holds the hash of a one-time code, never the code; a session holds the
hash of its token, never the token. The note table is the one short text column the graph
allows, because a note is the patient's own words, chosen, for himself.

This revision also introduces the `profile` scope — the profile row itself, which every key
holds — and writes it into the scopes of every key cut before it existed, so that no holder
loses the face of the graph he already opens.

Revision ID: 0004_login_and_sessions
Revises: 0003_memory
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_login_and_sessions"
down_revision = "0003_memory"
branch_labels = None
depends_on = None

REGION = sa.Enum("SG", "MY", name="region", native_enum=False, length=32)
LOGIN_CHANNEL = sa.Enum("phone", "email", name="login_channel", native_enum=False, length=32)
PROFILE_SCOPE = "profile"


def _keys() -> sa.TableClause:
    return sa.table("key", sa.column("id", sa.Uuid()), sa.column("scopes", sa.JSON()))


def _rewrite_scopes(*, add: bool) -> None:
    """Put `profile` into, or take it out of, every key's scope list. Row by row, in
    Python, so the same code runs on SQLite and on Postgres."""
    bind = op.get_bind()
    keys = _keys()
    for key_id, scopes in bind.execute(sa.select(keys.c.id, keys.c.scopes)).all():
        held = list(scopes)
        if add and PROFILE_SCOPE not in held:
            held = sorted([*held, PROFILE_SCOPE])
        elif not add and PROFILE_SCOPE in held:
            held = [scope for scope in held if scope != PROFILE_SCOPE]
        else:
            continue
        bind.execute(keys.update().where(keys.c.id == key_id).values(scopes=held))


def upgrade() -> None:
    op.create_table(
        "login_challenge",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("region", REGION, nullable=False),
        sa.Column("channel", LOGIN_CHANNEL, nullable=False),
        sa.Column("phone_e164", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        # sha256 of "<challenge id>:<secret>". The secret itself is never written down.
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=True),
    )
    op.create_index("ix_login_challenge_phone_e164", "login_challenge", ["phone_e164"])
    op.create_index("ix_login_challenge_email", "login_challenge", ["email"])

    op.create_table(
        "session",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("region", REGION, nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        # sha256 of the token that was handed over once on verify.
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_person_id", "session", ["person_id"])

    op.create_table(
        "note",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The patient's own words, at most 280 characters. See app/notes/models.py.
        sa.Column("text", sa.String(length=280), nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_note_profile_id", "note", ["profile_id"])
    op.create_index("ix_note_written_at", "note", ["written_at"])

    _rewrite_scopes(add=True)


def downgrade() -> None:
    _rewrite_scopes(add=False)
    op.drop_index("ix_note_written_at", table_name="note")
    op.drop_index("ix_note_profile_id", table_name="note")
    op.drop_table("note")
    op.drop_index("ix_session_person_id", table_name="session")
    op.drop_table("session")
    op.drop_index("ix_login_challenge_email", table_name="login_challenge")
    op.drop_index("ix_login_challenge_phone_e164", table_name="login_challenge")
    op.drop_table("login_challenge")
