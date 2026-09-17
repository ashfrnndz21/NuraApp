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

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, monotonic, utcnow
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
    VISIT_LOGISTICS = "visit_logistics"
    """The day before a visit and on the day: the time, the place, who drives him, what to
    bring (E05-03). Its lines are the logistics card's (`app.reasoning.visits.logistics`)."""
    MEMO = "memo"
    """What was agreed at the last visit (E05 writes the memo; the card repeats it)."""
    REORDER = "reorder"
    """A medicine running low (E04 works the date out; the card repeats it)."""
    NOTICE = "notice"
    """A safety notice from a regulator matching a medicine. Never his card, batch match or
    not (#181, #183): held for the caregiver always, or rerouted to `needs_doctor_look_lines`
    and filed as a real question for the doctor when its words would change treatment (#224,
    #236) — never dropped either way. `app/delivery/feed/items.py` refuses one built for the
    patient. Where the batch on his own pack matches, he gets `RECALL_ACTION` instead — never
    this card's own words about the notice."""
    RECALL_ACTION = "recall_action"
    """A safety notice whose batch matches his own pack (#183): the one card that tells him
    what he can do about the box in his hand today, in his own words, made and reviewed the
    way every other card of his is — never the notice's own compressed words about the
    recall, which stay the caregiver's (`NOTICE`) and are never his to read."""
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
    """Who holds a key today and who is on duty: a card for the caregiver's list, which has
    no gate (docs/health-feed-spec.md §0), so it sits with today's cards, not in the gate's
    place, and carries every side action a card carries."""
    CLIP = "clip"
    """A compressed video (E09-06, spec §2): the 20–30 seconds of an allowlisted video that
    apply to him, narrated in his language with captions — the licensed excerpt the server
    hosts, or the still with the narration where the licence does not allow reuse. Never
    plays by itself."""
    RECAP = "recap"
    """His week in 30 seconds (E11-09): the lines of this week's story cards, narrated with
    captions over a still. It repeats his own record and infers nothing."""
    LOCAL = "local"
    """A local alert (E09-07): an environmental or outbreak bulletin — dengue, haze, heat —
    for his area, made only when a condition or a medicine on his record makes it relevant.
    Says what to do today and ends on the boundary line."""
    SEASONAL = "seasonal"
    """A season coming (spec §2): the fasting month, festive food, travel — food and timing,
    with anything about his tablets as a question for his doctor."""
    FOOD = "food"
    """Food and habit (spec §2): weekly, by his conditions, one concrete choice."""


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
    CardType.VISIT_LOGISTICS: Supply.TODAY,
    CardType.MEMO: Supply.TODAY,
    CardType.REORDER: Supply.TODAY,
    CardType.NOTICE: Supply.TODAY,
    CardType.RECALL_ACTION: Supply.TODAY,
    CardType.GATE: Supply.GATE,
    # The caregiver's list has no gate: the duty card is one of her today cards.
    CardType.DUTY: Supply.TODAY,
    CardType.LOCAL: Supply.TODAY,
    CardType.STORY: Supply.STORY,
    CardType.RECAP: Supply.STORY,
    CardType.LEARNING: Supply.LEARNING,
    CardType.CLIP: Supply.LEARNING,
    CardType.SEASONAL: Supply.LEARNING,
    CardType.FOOD: Supply.LEARNING,
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
    # Not capped: the acceptance is that it is sent the day before and on the day (E05-03),
    # and the daily cap would hold it behind a reading. One a day, by its dedupe key.
    CardType.VISIT_LOGISTICS: CapsClass.SUPPLY,
    CardType.MEMO: CapsClass.ONE,
    CardType.REORDER: CapsClass.ONE,
    CardType.NOTICE: CapsClass.ONE,
    CardType.RECALL_ACTION: CapsClass.ONE,
    CardType.GATE: CapsClass.SUPPLY,
    CardType.DUTY: CapsClass.SUPPLY,
    # Today's local alert is one of the two new cards a day, like any other today card.
    CardType.LOCAL: CapsClass.ONE,
    CardType.STORY: CapsClass.SUPPLY,
    CardType.RECAP: CapsClass.SUPPLY,
    CardType.LEARNING: CapsClass.SUPPLY,
    CardType.CLIP: CapsClass.SUPPLY,
    CardType.SEASONAL: CapsClass.SUPPLY,
    CardType.FOOD: CapsClass.SUPPLY,
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
    """Two text cards went unopened, so the voice script leads and the text follows; or two
    clips went unplayed, so the next one comes as a voice note instead (E11-08)."""
    CLIP = "clip"
    """A still or a licensed excerpt with narration and captions, played on a tap (E11-09)."""


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
    # The card grammar (E11-03, `grammar`): one number, one direction, one colour, one action.
    # Nullable for the rows written before the grammar was a column; every card written
    # since carries its colour and its action, and `create_item` refuses one that breaks it.
    number: Mapped[str | None] = mapped_column(String(24), default=None)
    direction: Mapped[str | None] = mapped_column(String(8), default=None)
    colour: Mapped[str | None] = mapped_column(String(16), default=None)
    action: Mapped[str | None] = mapped_column(String(24), default=None)


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


frozen(SearchJob, except_for=frozenset({"status", "results", "last_run_at", "enabled"}))
"""A run changes its status, results and time; the owner or his chief pauses or resumes it
(`enabled`, "Watching for Pa"). What it searches for and where are fixed when it is made."""


class EngagementKind(StrEnum):
    """What a person did with a card. Posted by the client, never inferred."""

    SEEN = "seen"
    HEARD = "heard"
    TAPPED = "tapped"
    DISMISSED = "dismissed"
    """"Not for me": the kind of card is held back for the rest of the day."""
    SHARED = "shared"
    """Shared to the family thread."""
    OPENED = "opened"
    """The card was on his screen long enough to read. Not a measure of time: once, or not."""
    PLAYED = "played"
    """A clip or a voice note was played, with how many seconds of it played."""
    REPLAYED = "replayed"
    """Played again."""
    ASKED_MORE = "asked_more"
    """He asked about the card (Ask)."""


PLAYS: frozenset[EngagementKind] = frozenset({EngagementKind.PLAYED, EngagementKind.REPLAYED})
"""The only events that carry seconds: how much of a clip or a voice note played. No event
carries time spent in the feed; the feed is not measured by it (spec §0, `test_feed_formats`)."""


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
        UniqueConstraint("profile_id", "client_id", name="uq_feed_engagement_client"),
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
    seconds: Mapped[float | None] = mapped_column(Float, default=None)
    """For a play or a replay only: how many seconds of the clip or voice note played."""
    client_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    """The id the phone gave the event in its queue (`POST …/feed/events`), so an event sent
    twice — the answer lost on the way back — is written once."""


frozen(Engagement)


@monotonic
class FeedPage(ProfileScoped, Base):
    """The last page rendered for one person: what the app keeps for an offline launch.

    A list of item ids in the order they were shown, the cursor it was shown under and the
    next one, and whether the quiet hours held anything back. `GET …/feed/cached` reads the
    newest row — `rendered_at`, tied by `seq` (#192/#218) — as the one cached page.
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
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


frozen(FeedPage)
