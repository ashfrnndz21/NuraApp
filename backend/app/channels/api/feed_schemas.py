"""The feed's request and response shapes, apart from `schemas.py` so the parallel stories
(E04, E05) do not collide in one file."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.channels.api.voice_schemas import VoiceScriptOut
from app.delivery.feed.area import AreaView
from app.delivery.feed.engagement import QUEUE_LIMIT, Flushed, Queued
from app.delivery.feed.find import Result
from app.delivery.feed.models import (
    PLAYS,
    EngagementChannel,
    EngagementKind,
    JobKind,
    JobStatus,
    ReviewStatus,
    SearchJob,
    Source,
    SourceKind,
)
from app.delivery.feed.rank import Page, Sent, item_json
from app.reasoning.signals import SignalFamily, SignalUse


class FeedItemOut(BaseModel):
    """One card as the client renders it. `autoplay` is always false; `rendered_from_state`
    is the snapshot every card names; `why` is the structured reason with its plain line.
    `boundary` is the line a card of an inferring surface is shown under (E16-01, a learning
    card or a notice), the same words its body and voice end on; null on a card that shows
    the record back."""

    item_id: uuid.UUID
    type: str
    supply: str
    status: str
    rendered_from_state: uuid.UUID
    language: str
    format: str
    headline: str
    body: list[str]
    voice: list[str]
    why: dict[str, Any]
    priority: int
    caps_class: str
    scope: str
    deliver_to: str
    autoplay: bool
    source_id: uuid.UUID | None
    cite: dict[str, Any] | None
    boundary: str | None = None
    voice_script: VoiceScriptOut
    """The card as it is said (E22-03), computed from `voice` and nothing else: the digest is
    what its pre-rendered audio is kept under."""
    day: str
    created_at: datetime
    expires_at: datetime
    number: str | None = None
    """The card grammar (E11-03): the one number the card shows, as digits, or null."""
    direction: str | None = None
    """up, down or same beside the number, or null."""
    colour: str | None = None
    """The State wash the card sits on: stable, watch or act. Never red."""
    action: str | None = None
    """The card's one action: taken, hear, keep_going, call, ask_to_order, open, ask_the_doctor."""
    category: str | None = None
    """For today's top three (E11-02): alert, reminder or insight."""
    search_job_id: str | None = None
    """The watch that found this card, when a search made it; None for his own record's."""


class FeedPageOut(BaseModel):
    audience: str
    items: list[FeedItemOut]
    cursor: str | None
    next_cursor: str | None
    quiet: bool
    held_by_caps: dict[str, int]

    @classmethod
    def of(cls, page: Page) -> FeedPageOut:
        return cls(
            audience=page.audience.value,
            items=[
                FeedItemOut(**item_json(item, page.status.get(item.id, "generated")))
                for item in page.items
            ],
            cursor=page.cursor,
            next_cursor=page.next_cursor,
            quiet=page.quiet,
            held_by_caps=page.held_by_caps,
        )


class EngagementIn(BaseModel):
    event: EngagementKind
    channel: EngagementChannel = EngagementChannel.APP


class EngagementOut(BaseModel):
    engagement_id: uuid.UUID
    item_id: uuid.UUID
    event: EngagementKind
    channel: EngagementChannel
    at: datetime


class SourceOut(BaseModel):
    source_id: uuid.UUID
    name: str
    domain: str
    kind: SourceKind
    regions: list[str]
    languages: list[str]
    allowlisted: bool
    review_status: ReviewStatus

    @classmethod
    def of(cls, source: Source) -> SourceOut:
        return cls(
            source_id=source.id,
            name=source.name,
            domain=source.domain,
            kind=source.kind,
            regions=list(source.regions),
            languages=list(source.languages),
            allowlisted=source.allowlisted,
            review_status=source.review_status,
        )


class SearchJobIn(BaseModel):
    kind: JobKind
    terms: list[str] = Field(min_length=1, max_length=8)
    source_ids: list[uuid.UUID] | None = None
    cadence: str | None = Field(default=None, max_length=32)
    """How often it runs; the kind's own when not named (`search.DEFAULT_CADENCE`)."""
    reason: str = Field(default="asked by hand", max_length=200)


class SearchJobPatchIn(BaseModel):
    """Pause a watch (false) or resume it (true)."""

    enabled: bool


class SearchJobOut(BaseModel):
    job_id: uuid.UUID
    kind: JobKind
    terms: list[str]
    source_ids: list[uuid.UUID]
    cadence: str
    reason: dict[str, Any]
    status: JobStatus
    results: dict[str, Any]
    enabled: bool
    created_at: datetime
    last_run_at: datetime | None
    label: str = ""
    """What it watches for, in the reader's words ("Dengue near Air Itam")."""
    sources: list[str] = []
    """The names of the allowlisted sources it reads."""

    @classmethod
    def of(cls, job: SearchJob, *, label: str = "", sources: Sequence[str] = ()) -> SearchJobOut:
        return cls(
            label=label,
            sources=list(sources),
            job_id=job.id,
            kind=job.kind,
            terms=list(job.terms),
            source_ids=[uuid.UUID(one) for one in job.source_ids],
            cadence=job.cadence,
            reason=dict(job.reason),
            status=job.status,
            results=dict(job.results),
            enabled=job.enabled,
            created_at=job.created_at,
            last_run_at=job.last_run_at,
        )


class QueuedIn(BaseModel):
    """One event from the phone's queue (E11-08). `seconds` is how much of a clip or a voice
    note played, on a play or a replay only: no event carries time spent in the feed."""

    client_id: uuid.UUID
    item_id: uuid.UUID
    event: EngagementKind
    at: AwareDatetime
    channel: EngagementChannel = EngagementChannel.APP
    seconds: float | None = Field(default=None, ge=0, le=600)

    @model_validator(mode="after")
    def seconds_only_on_a_play(self) -> QueuedIn:
        if self.seconds is not None and self.event not in PLAYS:
            raise ValueError("only a play or a replay says how many seconds played")
        return self

    def queued(self) -> Queued:
        return Queued(
            client_id=self.client_id,
            item_id=self.item_id,
            kind=self.event,
            at=self.at,
            channel=self.channel,
            seconds=self.seconds,
        )


class EventsIn(BaseModel):
    events: list[QueuedIn] = Field(max_length=QUEUE_LIMIT)


class SkippedOut(BaseModel):
    client_id: uuid.UUID
    because: str


class EventsOut(BaseModel):
    """Which events were written, and which were not and why: the phone drops both from its
    queue (a skipped event is never sent again)."""

    written: list[uuid.UUID]
    skipped: list[SkippedOut]

    @classmethod
    def of(cls, flushed: Flushed) -> EventsOut:
        return cls(
            written=[row.client_id for row in flushed.written if row.client_id is not None],
            skipped=[SkippedOut(client_id=one, because=why) for one, why in flushed.skipped],
        )


class SentOut(BaseModel):
    """One card of "Sent to Pa this week": the card as the feed answers it, with its status
    among sent, opened, played, dismissed, held. No count of anything."""

    item: FeedItemOut

    @classmethod
    def of(cls, sent: Sent) -> SentOut:
        return cls(item=FeedItemOut(**item_json(sent.item, sent.status)))


class AreaIn(BaseModel):
    """Set his area, or clear it (`area: None`). Once the graph is his, this is his own
    write and takes his own yes: `confirmation_id` from `POST /profiles/{id}/confirmations`
    with subject `area` and this same `area` (#184). Before his claim the steward sets it on
    the declared basis without one, and `confirmation_id` is not asked for on that path."""

    area: str | None = Field(default=None, max_length=40)
    confirmation_id: uuid.UUID | None = None


class AreaOut(BaseModel):
    area: str | None
    districts: list[str]
    may_set: bool

    @classmethod
    def of(cls, view: AreaView) -> AreaOut:
        return cls(area=view.area, districts=list(view.districts), may_set=view.may_set)


class SignalOut(BaseModel):
    family: SignalFamily
    on: bool
    fact_id: str | None


class SignalsOut(BaseModel):
    signals: list[SignalOut]
    may_set: bool

    @classmethod
    def of(cls, uses: Sequence[SignalUse], *, may_set: bool) -> SignalsOut:
        return cls(
            signals=[SignalOut(family=use.family, on=use.on, fact_id=use.fact_id) for use in uses],
            may_set=may_set,
        )


class SignalIn(BaseModel):
    on: bool


class ResultOut(BaseModel):
    title: str
    publisher: str | None
    url: str | None
    published_at: str | None
    lines: list[str]
    boundary: str | None
    media: str | None
    provider_id: str | None
    next_visit_at: str | None

    @classmethod
    def of(cls, found: Result) -> ResultOut:
        return cls(
            title=found.title,
            publisher=found.publisher,
            url=found.url,
            published_at=found.published_at,
            lines=list(found.lines),
            boundary=found.boundary,
            media=found.media,
            provider_id=found.provider_id,
            next_visit_at=found.next_visit_at,
        )


class FindIn(BaseModel):
    """What the ask bar searches for, and where: in the body, never the URL."""

    q: str = Field(min_length=1, max_length=200)
    where: str = Field(max_length=16)
    language: str | None = Field(default=None, max_length=8)


class FindOut(BaseModel):
    where: str
    results: list[ResultOut]
