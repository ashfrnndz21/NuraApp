"""W2: Ask becomes a conversation.

Two tables, both tied to their profile the way the memory tables are (0005), both `RowScoped`
(0019) under `Scope.ASK`, both `@monotonic` (0040) for the same reason every "latest wins"
read here already needs one — "current conversation" and "last six turns" are both decisions,
not a listing to browse:

- `conversation`: one person's thread with Nura about one profile, reused across days until
  that person starts a new one (`app.search.conversation.current_conversation`,
  `start_new_conversation`). `summary` is the one free-text column here, and it is deliberate:
  a deterministic, rule-written run of "he asked about X; Nura found Y (cites)" lines for
  turns already folded out of the last six kept verbatim — never a turn's own words.
- `turn`: one question and its answer, on one conversation. No free-text column holds either
  one's words — `question_artifact_id` and `answer_artifact_id` point at MESSAGE artefacts,
  the same reference-only pattern `app.memory.models.Event.artifact_id` already is.

Revision ID: 0050_conversations
Revises: 0049_condition_answers
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050_conversations"
down_revision = "0049_condition_answers"
branch_labels = None
depends_on = None

_TABLES = ("conversation", "turn")


def _sequence_name(table: str) -> str:
    return f"{table}_seq_seq"


def _profile_id() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


def _tied(table: str, column: str, referred: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["profile_id", column],
        [f"{referred}.profile_id", f"{referred}.id"],
        name=f"fk_{table}_{column.removesuffix('_id')}_profile",
    )


def _when(name: str, nullable: bool = False) -> sa.Column[sa.DateTime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


ASK_MODE = sa.Enum("voice", "text", name="ask_mode", native_enum=False, length=32)
SCOPE = sa.Enum(
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
    "profile",
    name="scope",
    native_enum=False,
    length=32,
)

_INDEXES = (
    ("ix_conversation_profile_id", "conversation", ["profile_id"]),
    ("ix_conversation_person_id", "conversation", ["person_id"]),
    ("ix_conversation_started_at", "conversation", ["started_at"]),
    ("ix_conversation_last_turn_at", "conversation", ["last_turn_at"]),
    ("ix_conversation_seq", "conversation", ["seq"]),
    ("ix_turn_profile_id", "turn", ["profile_id"]),
    ("ix_turn_conversation_id", "turn", ["conversation_id"]),
    ("ix_turn_person_id", "turn", ["person_id"]),
    ("ix_turn_created_at", "turn", ["created_at"]),
    ("ix_turn_seq", "turn", ["seq"]),
)


def upgrade() -> None:
    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("written_scope", SCOPE, nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        _when("started_at"),
        _when("last_turn_at"),
        _when("closed_at", nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summarized_through", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.String(length=4000), nullable=True),
        sa.Column("seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("profile_id", "id", name="uq_conversation_profile_id_id"),
    )
    op.create_table(
        "turn",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("written_scope", SCOPE, nullable=False),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversation.id"), nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("mode", ASK_MODE, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("question_artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("answer_artifact_id", sa.Uuid(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        _when("created_at"),
        sa.Column("seq", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("profile_id", "id", name="uq_turn_profile_id_id"),
        _tied("turn", "conversation_id", "conversation"),
        _tied("turn", "question_artifact_id", "artifact"),
        _tied("turn", "answer_artifact_id", "artifact"),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)
    if op.get_bind().dialect.name == "postgresql":
        for table in _TABLES:
            op.execute(f"CREATE SEQUENCE {_sequence_name(table)}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in reversed(_TABLES):
            op.execute(f"DROP SEQUENCE {_sequence_name(table)}")
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("turn")
    op.drop_table("conversation")
