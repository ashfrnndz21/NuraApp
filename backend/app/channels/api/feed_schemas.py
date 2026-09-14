"""The feed's request and response shapes, apart from `schemas.py` so the parallel stories
(E04, E05) do not collide in one file."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.delivery.feed.models import (
    EngagementChannel,
    EngagementKind,
    JobKind,
    JobStatus,
    ReviewStatus,
    SearchJob,
    Source,
    SourceKind,
)
from app.delivery.feed.rank import Page, item_json
from app.safety.red_flags import Feeling, Flag


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
    day: str
    created_at: datetime
    expires_at: datetime


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
    cadence: str = Field(default="on_change", max_length=32)
    reason: str = Field(default="asked by hand", max_length=200)


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

    @classmethod
    def of(cls, job: SearchJob) -> SearchJobOut:
        return cls(
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


class FeelingIn(BaseModel):
    """A tap on the feeling cloud: one word from its fixed set."""

    word: Feeling


class FeelingOut(BaseModel):
    event_id: uuid.UUID
    word: Feeling
    red_flag: bool
    flag_id: uuid.UUID | None
    told: list[uuid.UUID]
    suppressed_because: str | None

    @classmethod
    def of(cls, event_id: uuid.UUID, word: Feeling, flag: Flag | None) -> FeelingOut:
        return cls(
            event_id=event_id,
            word=word,
            red_flag=flag is not None,
            flag_id=None if flag is None else flag.id,
            told=[] if flag is None else [uuid.UUID(one) for one in flag.told],
            suppressed_because=None if flag is None else flag.suppressed_because,
        )
