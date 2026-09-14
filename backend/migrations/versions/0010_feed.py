"""E21: the feed.

Six tables. `source` is the global allowlist: a publisher, its domain, kind, regions and
languages, whether it is allowlisted and where the pharmacist's review stands. `search_job`
is a self-search on one profile: kind, terms, the allowlisted sources it may read, cadence,
reason, status and results. `feed_item` is one card as it was shown: type, section, caps
class, audience, the scope it was built from, the lines (headline, body, voice, why),
priority, format, `autoplay` (always false), the source and cite for a learning card, the
day the caps count and a dedupe key — and `state_id`, the State it was rendered from, not
nullable, the way `RenderedFromState` promises. `feed_engagement` is what one person did
with one card, tied to the item and to the memory Event it was written as. `feed_page` is
the last page rendered for one person, for the offline launch. `red_flag` is one red flag
raised on one profile: his word, the SYMPTOM event it was said in, who was told, and, for
the two flags that depend on a fact, why it was suppressed.

`event_kind` gains `engagement` and `feeling` is a new checked string; both are non-native
enums with no database constraint, so there is no column change for them.

Follows E04's medicines revision (0009). E05 visits and E19 WhatsApp land as 0010_* beside
this one; the operator repoints the last of them when the heads meet.

Revision ID: 0010_feed
Revises: 0009_medicines
Create Date: 2026-09-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_feed"
down_revision = "0009_medicines"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=32)


CARD_TYPE = _enum(
    "card_type",
    "flag",
    "now",
    "reading",
    "visit",
    "memo",
    "reorder",
    "notice",
    "gate",
    "story",
    "learning",
    "question",
    "duty",
)
FEED_SUPPLY = _enum("feed_supply", "flag", "now", "today", "gate", "story", "learning", "held")
CAPS_CLASS = _enum("caps_class", "flag", "one", "supply", "held")
DELIVER_TO = _enum("deliver_to", "patient", "caregiver", "memo")
CARD_FORMAT = _enum("card_format", "text", "voice_first")
SCOPE = _enum(
    "scope",
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
)
SOURCE_KIND = _enum("source_kind", "regulator", "ministry", "hospital", "society", "video")
REVIEW_STATUS = _enum("source_review_status", "pending", "approved", "rejected")
JOB_KIND = _enum(
    "search_job_kind",
    "explainer",
    "safety",
    "local",
    "food",
    "provider",
    "worth_knowing",
    "seasonal",
)
JOB_STATUS = _enum("search_job_status", "queued", "done", "failed")
ENGAGEMENT_KIND = _enum("engagement_kind", "seen", "heard", "tapped", "dismissed", "shared")
ENGAGEMENT_CHANNEL = _enum("engagement_channel", "app", "whatsapp", "widget")
FEELING = _enum(
    "feeling",
    "fall",
    "chest_tightness",
    "breathless_at_rest",
    "one_sided_swelling",
    "worst_headache",
    "sudden_blurring",
    "confusion",
    "shaky_sweaty",
    "weight_gain",
    "dizzy",
    "cramps",
    "thirsty",
    "tired",
    "aches",
    "headache",
    "fine",
)


def _profile_id() -> sa.Column:
    return sa.Column(
        "profile_id", sa.Uuid(), sa.ForeignKey("profile.id", ondelete="CASCADE"), nullable=False
    )


_INDEXES = (
    ("ix_search_job_profile_id", "search_job", ["profile_id"]),
    ("ix_feed_item_profile_id", "feed_item", ["profile_id"]),
    ("ix_feed_item_state_id", "feed_item", ["state_id"]),
    ("ix_feed_item_day", "feed_item", ["day"]),
    ("ix_feed_item_created_at", "feed_item", ["created_at"]),
    ("ix_feed_engagement_profile_id", "feed_engagement", ["profile_id"]),
    ("ix_feed_engagement_item_id", "feed_engagement", ["item_id"]),
    ("ix_feed_engagement_at", "feed_engagement", ["at"]),
    ("ix_feed_page_profile_id", "feed_page", ["profile_id"]),
    ("ix_feed_page_person_id", "feed_page", ["person_id"]),
    ("ix_feed_page_rendered_at", "feed_page", ["rendered_at"]),
    ("ix_red_flag_profile_id", "red_flag", ["profile_id"]),
    ("ix_red_flag_raised_at", "red_flag", ["raised_at"]),
)


def upgrade() -> None:
    op.create_table(
        "source",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=False, unique=True),
        sa.Column("kind", SOURCE_KIND, nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("allowlisted", sa.Boolean(), nullable=False),
        sa.Column("review_status", REVIEW_STATUS, nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "search_job",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("kind", JOB_KIND, nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("cadence", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.JSON(), nullable=False),
        sa.Column("status", JOB_STATUS, nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_search_job_profile_id_id"),
    )
    op.create_table(
        "feed_item",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        # Every card names the State it was rendered from. Not nullable: the promise is here.
        sa.Column("state_id", sa.Uuid(), sa.ForeignKey("state_snapshot.id"), nullable=False),
        sa.Column("type", CARD_TYPE, nullable=False),
        sa.Column("supply", FEED_SUPPLY, nullable=False),
        sa.Column("caps_class", CAPS_CLASS, nullable=False),
        sa.Column("deliver_to", DELIVER_TO, nullable=False),
        sa.Column("scope", SCOPE, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("format", CARD_FORMAT, nullable=False),
        sa.Column("headline", sa.String(length=200), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("voice", sa.JSON(), nullable=False),
        sa.Column("why", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("autoplay", sa.Boolean(), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("source.id"), nullable=True),
        sa.Column("cite", sa.JSON(), nullable=True),
        sa.Column("search_job_id", sa.Uuid(), sa.ForeignKey("search_job.id"), nullable=True),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_feed_item_profile_id_id"),
        sa.UniqueConstraint("profile_id", "dedupe_key", name="uq_feed_item_dedupe"),
    )
    op.create_table(
        "feed_engagement",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("item_id", sa.Uuid(), sa.ForeignKey("feed_item.id"), nullable=False),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("kind", ENGAGEMENT_KIND, nullable=False),
        sa.Column("channel", ENGAGEMENT_CHANNEL, nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_feed_engagement_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "item_id"],
            ["feed_item.profile_id", "feed_item.id"],
            name="fk_feed_engagement_item_profile",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id", "event_id"],
            ["event.profile_id", "event.id"],
            name="fk_feed_engagement_event_profile",
        ),
    )
    op.create_table(
        "feed_page",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("audience", DELIVER_TO, nullable=False),
        sa.Column("item_ids", sa.JSON(), nullable=False),
        sa.Column("cursor", sa.String(length=200), nullable=True),
        sa.Column("next_cursor", sa.String(length=200), nullable=True),
        sa.Column("quiet", sa.Boolean(), nullable=False),
        sa.Column("held_by_caps", sa.JSON(), nullable=False),
        sa.Column("rendered_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "id", name="uq_feed_page_profile_id_id"),
    )
    op.create_table(
        "red_flag",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _profile_id(),
        sa.Column("feeling", FEELING, nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("raised_by_person_id", sa.Uuid(), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("told", sa.JSON(), nullable=False),
        sa.Column("suppressed_because", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("profile_id", "id", name="uq_red_flag_profile_id_id"),
        sa.ForeignKeyConstraint(
            ["profile_id", "event_id"],
            ["event.profile_id", "event.id"],
            name="fk_red_flag_event_profile",
        ),
    )
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    op.drop_table("red_flag")
    op.drop_table("feed_page")
    op.drop_table("feed_engagement")
    op.drop_table("feed_item")
    op.drop_table("search_job")
    op.drop_table("source")
