"""The tables of the feed.

Every row here is the profile's (`ProfileScoped`) except `Source`, which is the global
allowlist. A `FeedItem` carries `RenderedFromState`, so the schema itself refuses a card that
names no State (`app.state.models`). Items are immutable: what he was shown is what he was
shown; what he did with it is an `Engagement` row beside it, and the item's status is read
from those, never written onto the item.

Lines on an item are content by design — the spec's `headline`, `body`, `why` — and every
one of them passed the plain-words verifier before the row was written (`items.create_item`).
`why` is structured beside its plain sentence: the fact ids, the event, the source, the gap
or the memo the card was built from, so "why am I seeing this" is answerable by id.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.keys.scopes import Scope
from app.memory.models import _row_of_profile, _tied_to_profile
from app.state.models import RenderedFromState

LINE_LENGTH = 200
"""The most one line of a card may hold. A line, in his words; never a document."""


class CardType(StrEnum):
    """What kind of card this is. Each type sits in one section of the supply (`SUPPLY_OF`)."""

    FLAG = "flag"
    """This one we do not wait for: a red flag, first, unaffected by caps or quiet hours."""
    NOW = "now"
    """The one thing today: the tablets, the visit, or a quiet day."""
    READING = "reading"
    """His own number back to him: one number, one direction, one sentence."""
    VISIT = "visit"
    """A visit inside the week: who, which day, what to bring."""
    MEMO = "memo"
    """What was agreed at the last visit (E05 writes the memo; the card repeats it)."""
    REORDER = "reorder"
    """A medicine running low (E04 works the date out; the card repeats it)."""
    NOTICE = "notice"
    """A safety notice from a regulator matching a medicine. Sent to him only when it matches
    the batch on his pack and there is something to do; otherwise held for the caregiver."""
    GATE = "gate"
    """That is all that is new. Keep going?"""
    STORY = "story"
    """A recall card from his own record: a number from before, a paper, his own words."""
    LEARNING = "learning"
    """An evergreen explainer from an allowlisted source, compressed to the part for him."""
    QUESTION = "question"
    """Something found that could change treatment, rewritten as a question for the doctor
    and held for the memo; never in the patient's feed."""
    DUTY = "duty"
    """The caregiver's gate: who holds a key today."""


class Supply(StrEnum):
    """The sections of the feed, in order. `rank` walks them top to bottom."""

    FLAG = "flag"
    NOW = "now"
    TODAY = "today"
    GATE = "gate"
    STORY = "story"
    LEARNING = "learning"
    HELD = "held"
    """Not a section he sees: doctor questions for the memo, notices with nothing to do."""


SUPPLY_OF: dict[CardType, Supply] = {
    CardType.FLAG: Supply.FLAG,
    CardType.NOW: Supply.NOW,
    CardType.READING: Supply.TODAY,
    CardType.VISIT: Supply.TODAY,
    CardType.MEMO: Supply.TODAY,
    CardType.REORDER: Supply.TODAY,
    CardType.NOTICE: Supply.TODAY,
    CardType.GATE: Supply.GATE,
    CardType.DUTY: Supply.GATE,
    CardType.STORY: Supply.STORY,
    CardType.LEARNING: Supply.LEARNING,
    CardType.QUESTION: Supply.HELD,
}

SUPPLY_ORDER: tuple[Supply, ...] = (
    Supply.FLAG,
    Supply.NOW,
    Supply.TODAY,
    Supply.GATE,
    Supply.STORY,
    Supply.LEARNING,
)
"""Now → today's cards → the gate → his story → learning; a flag ahead of all of it."""


class CapsClass(StrEnum):
    """How the daily caps treat a card."""

    FLAG = "flag"
    """Never capped, never quiet: it goes first whatever the hour."""
    ONE = "one"
    """One of its kind a day, and one of the two new cards a day (`rank.DAILY_CAP`)."""
    SUPPLY = "supply"
    """Not capped: the now card, the gate, and everything past the gate."""
    HELD = "held"
    """Never delivered to the patient: routed to the caregiver's list or the memo."""


CAPS_OF: dict[CardType, CapsClass] = {
    CardType.FLAG: CapsClass.FLAG,
    CardType.NOW: CapsClass.SUPPLY,
    CardType.READING: CapsClass.ONE,
    CardType.VISIT: CapsClass.ONE,
    CardType.MEMO: CapsClass.ONE,
    CardType.REORDER: CapsClass.ONE,
    CardType.NOTICE: CapsClass.ONE,
    CardType.GATE: CapsClass.SUPPLY,
    CardType.DUTY: CapsClass.SUPPLY,
    CardType.STORY: CapsClass.SUPPLY,
    CardType.LEARNING: CapsClass.SUPPLY,
    CardType.QUESTION: CapsClass.HELD,
}


class DeliverTo(StrEnum):
    """Whose feed the item is for (docs/health-feed-spec.md §2)."""

    PATIENT = "patient"
    CAREGIVER = "caregiver"
    MEMO = "memo"


class CardFormat(StrEnum):
    TEXT = "text"
    VOICE_FIRST = "voice_first"
    """Two text cards went unopened, so the voice script leads and the text follows."""


class FeedItem(RenderedFromState, ProfileScoped, Base):
    """One card, as it was shown, with the State it was rendered from.

    `headline`, `body` and `voice` are the lines he reads and hears, in `language`, verified
    before the row was written. `why` is the structured reason (`items.Why`) with its plain
    sentence inside. `scope` is the part of the record the card was built from, so a key
    that does not cover that part does not see the card. `day` is the local date the card
    was made for, which is what the daily caps count. `dedupe_key` is what stops the same
    card being made twice for the same day. `autoplay` is a column so the promise is in the
    schema: it is always false.
    """

    __tablename__ = "feed_item"
    __table_args__ = (
        _row_of_profile("feed_item"),
        UniqueConstraint("profile_id", "dedupe_key", name="uq_feed_item_dedupe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    type: Mapped[CardType] = mapped_column(enum_column(CardType, "card_type"))
    supply: Mapped[Supply] = mapped_column(enum_column(Supply, "feed_supply"))
    caps_class: Mapped[CapsClass] = mapped_column(enum_column(CapsClass, "caps_class"))
    deliver_to: Mapped[DeliverTo] = mapped_column(enum_column(DeliverTo, "deliver_to"))
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    language: Mapped[str] = mapped_column(String(16))
    format: Mapped[CardFormat] = mapped_column(enum_column(CardFormat, "card_format"))
    headline: Mapped[str] = mapped_column(String(LINE_LENGTH))
    body: Mapped[list[str]] = mapped_column(JSON)
    voice: Mapped[list[str]] = mapped_column(JSON)
    why: Mapped[dict[str, Any]] = mapped_column(JSON)
    priority: Mapped[int] = mapped_column(Integer)
    autoplay: Mapped[bool] = mapped_column(Boolean, default=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source.id"), default=None)
    cite: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    """For a learning card: the page it came from — url, title, published_at, the passage."""
    search_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("search_job.id"), default=None
    )
    day: Mapped[str] = mapped_column(String(10), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column()


frozen(FeedItem)


class SourceKind(StrEnum):
    REGULATOR = "regulator"
    MINISTRY = "ministry"
    HOSPITAL = "hospital"
    SOCIETY = "society"
    VIDEO = "video"


class ReviewStatus(StrEnum):
    """Where the pharmacist's review of a source stands. Only APPROVED is used."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Source(Base):
    """One allowlisted publisher. Global, not profile data: the same list for everyone.

    `allowlisted` and `review_status` are both checked before a source is searched or a
    card cites it; a source is added by the pharmacist's review, never by a search result.
    """

    __tablename__ = "source"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[SourceKind] = mapped_column(enum_column(SourceKind, "source_kind"))
    regions: Mapped[list[str]] = mapped_column(JSON)
    languages: Mapped[list[str]] = mapped_column(JSON)
    allowlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "source_review_status")
    )
    added_at: Mapped[datetime] = mapped_column(default=utcnow)


class JobKind(StrEnum):
    EXPLAINER = "explainer"
    SAFETY = "safety"
    LOCAL = "local"
    FOOD = "food"
    PROVIDER = "provider"
    WORTH_KNOWING = "worth_knowing"
    SEASONAL = "seasonal"


class JobStatus(StrEnum):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"


class SearchJob(ProfileScoped, Base):
    """A self-search the engine runs on his behalf: what for, where, how often, and why.

    `source_ids` is the allowlist scope of the job — only these are searched — and every one
    of them was allowlisted when the job was made. `results` is what the run found, by
    outcome: the items made, and what was rejected and why (uncited, wrong language, a
    treatment change rerouted as a question). The row takes one change: a run.
    """

    __tablename__ = "search_job"
    __table_args__ = (_row_of_profile("search_job"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[JobKind] = mapped_column(enum_column(JobKind, "search_job_kind"))
    terms: Mapped[list[str]] = mapped_column(JSON)
    source_ids: Mapped[list[str]] = mapped_column(JSON)
    cadence: Mapped[str] = mapped_column(String(32))
    reason: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[JobStatus] = mapped_column(enum_column(JobStatus, "search_job_status"))
    results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(default=None)


frozen(SearchJob, except_for=frozenset({"status", "results", "last_run_at"}))


class EngagementKind(StrEnum):
    """What a person did with a card. Posted by the client, never inferred."""

    SEEN = "seen"
    HEARD = "heard"
    TAPPED = "tapped"
    DISMISSED = "dismissed"
    """"Not for me": the kind of card is held back for the rest of the day."""
    SHARED = "shared"
    """Shared to the family thread."""


class EngagementChannel(StrEnum):
    APP = "app"
    WHATSAPP = "whatsapp"
    WIDGET = "widget"


class Engagement(ProfileScoped, Base):
    """One thing one person did with one card, at one moment, on one channel.

    Tied to the item on the same profile. `event_id` is the memory Event it was written as
    (`EventKind.ENGAGEMENT`), so a preference Fact can rest on it.
    """

    __tablename__ = "feed_engagement"
    __table_args__ = (
        _row_of_profile("feed_engagement"),
        _tied_to_profile("feed_engagement", "item_id", "feed_item"),
        _tied_to_profile("feed_engagement", "event_id", "event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feed_item.id"), index=True)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    kind: Mapped[EngagementKind] = mapped_column(enum_column(EngagementKind, "engagement_kind"))
    # The column is `channel`; the attribute is `via` so it does not collide with the audit
    # channel keyword every audited write takes.
    via: Mapped[EngagementChannel] = mapped_column(
        "channel", enum_column(EngagementChannel, "engagement_channel")
    )
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


frozen(Engagement)


class FeedPage(ProfileScoped, Base):
    """The last page rendered for one person: what the app keeps for an offline launch.

    A list of item ids in the order they were shown, the cursor it was shown under and the
    next one, and whether the quiet hours held anything back. `GET …/feed/cached` reads it.
    """

    __tablename__ = "feed_page"
    __table_args__ = (_row_of_profile("feed_page"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    audience: Mapped[DeliverTo] = mapped_column(enum_column(DeliverTo, "deliver_to"))
    item_ids: Mapped[list[str]] = mapped_column(JSON)
    cursor: Mapped[str | None] = mapped_column(String(200), default=None)
    next_cursor: Mapped[str | None] = mapped_column(String(200), default=None)
    quiet: Mapped[bool] = mapped_column(Boolean, default=False)
    held_by_caps: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    rendered_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


frozen(FeedPage)
