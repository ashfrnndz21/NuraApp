"""The pharmacist's review queue over HTTP (E22-04). Staff only; no profile in any of it.

    GET  /review/status                  the first fifty of each card type, and sources waiting
    GET  /review/queue?kind=&card_type=&verdict=   pending items by default, oldest first
    GET  /review/items/{item}            one item
    POST /review/items/{item}/approve    approve (a source is then allowlisted)
    POST /review/items/{item}/reject     reject, with a reason (a source stays off)
    POST /review/items/{item}/rewrite    a card's lines as the reviewer would have them: a
                                         proposed catalogue change, never production text
    GET  /review/proposals               every rewrite, as the catalogue change it proposes
    POST /review/sources                 propose a publisher: pending, unused until approved

Every route takes `Staffed`: the bearer token must be one on `NURA_REVIEW_STAFF_TOKENS`
(`app.settings`). A patient's session token is not — there is no key context here and no path
from a key to this queue — so it is refused, `NotStaff`, 403, like no token at all. The routes
are outside `/profiles/{id}/` on purpose: nothing here is anyone's record
(docs/adr/0007-the-pharmacist-review-queue.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.channels.api.deps import Db, _bearer, settings_of
from app.delivery.feed.models import CardType, SourceKind
from app.language import review
from app.language.models import ReviewItem, ReviewKind, Verdict
from app.language.review import QueueStatus, Staff

router = APIRouter(prefix="/review", tags=["review"])


async def staff(request: Request) -> Staff:
    """The staff member calling, from the bearer token, or `NotStaff` (403)."""
    return review.staff_for(
        _bearer(request.headers.get("authorization")), settings_of(request).review_staff
    )


Staffed = Annotated[Staff, Depends(staff)]


class ReviewItemOut(BaseModel):
    """One item as the reviewer reads it. There is no profile, person or name in it: a card's
    lines are de-identified before they are stored, and a source is a publisher."""

    item_id: uuid.UUID
    kind: ReviewKind
    card_type: str | None
    sample_number: int | None
    source_id: uuid.UUID | None
    language: str | None
    lines: dict[str, Any]
    catalogue_ids: list[str]
    verdict: Verdict
    reason: str | None
    proposed: dict[str, Any] | None
    decided_by: str | None
    created_at: datetime
    decided_at: datetime | None

    @classmethod
    def of(cls, item: ReviewItem) -> ReviewItemOut:
        return cls(
            item_id=item.id,
            kind=item.kind,
            card_type=item.card_type,
            sample_number=item.sample_number,
            source_id=item.source_id,
            language=item.language,
            lines=dict(item.lines),
            catalogue_ids=list(item.catalogue_ids or []),
            verdict=item.verdict,
            reason=item.reason,
            proposed=item.proposed,
            decided_by=item.decided_by,
            created_at=item.created_at,
            decided_at=item.decided_at,
        )


class TypeStatusOut(BaseModel):
    card_type: str
    sampled: int
    reviewed: int
    pending: int
    approved: int
    rejected: int
    rewritten: int
    first_fifty_reviewed: bool
    flag: bool
    """True until the first fifty of this card type are queued and every one is decided."""


class StatusOut(BaseModel):
    first: int
    card_types: list[TypeStatusOut]
    sources_pending: int

    @classmethod
    def of(cls, found: QueueStatus) -> StatusOut:
        return cls(
            first=found.first,
            sources_pending=found.sources_pending,
            card_types=[
                TypeStatusOut(
                    card_type=t.card_type,
                    sampled=t.sampled,
                    reviewed=t.reviewed,
                    pending=t.pending,
                    approved=t.approved,
                    rejected=t.rejected,
                    rewritten=t.rewritten,
                    first_fifty_reviewed=t.first_fifty_reviewed,
                    flag=t.flag,
                )
                for t in found.card_types
            ],
        )


class ApproveIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RewriteLinesIn(BaseModel):
    headline: str | None = Field(default=None, max_length=200)
    body: list[str] | None = None
    voice: list[str] | None = None
    why: str | None = Field(default=None, max_length=200)


class RewriteIn(BaseModel):
    lines: RewriteLinesIn
    reason: str | None = Field(default=None, max_length=500)


class SourceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    domain: str = Field(
        min_length=4, max_length=120, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9-]+)+$"
    )
    kind: SourceKind
    regions: list[str] = Field(min_length=1)
    languages: list[str] = Field(min_length=1)


class ProposalOut(BaseModel):
    """A rewrite, as the catalogue change it proposes: which line, the words now, the words
    proposed, and the catalogue id where the words now are the catalogue's."""

    item_id: uuid.UUID
    card_type: str | None
    language: str | None
    changes: list[dict[str, Any]]
    reason: str | None
    decided_by: str | None
    decided_at: datetime | None


@router.get("/status")
async def queue_status(who: Staffed, session: Db) -> StatusOut:
    return StatusOut.of(await review.status(session))


@router.get("/queue")
async def the_queue(
    who: Staffed,
    session: Db,
    kind: ReviewKind | None = None,
    card_type: CardType | None = None,
    verdict: str = Query(default="pending", pattern="^(any|pending|approved|rejected|rewritten)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ReviewItemOut]:
    """Pending items by default; `verdict=any` for everything, oldest first."""
    found = await review.queue(
        session,
        kind=kind,
        card_type=card_type,
        verdict=None if verdict == "any" else Verdict(verdict),
        limit=limit,
    )
    return [ReviewItemOut.of(item) for item in found]


@router.get("/items/{item_id}")
async def one_item(item_id: uuid.UUID, who: Staffed, session: Db) -> ReviewItemOut:
    return ReviewItemOut.of(await review.get_item(session, item_id))


@router.post("/items/{item_id}/approve")
async def approve(
    item_id: uuid.UUID, body: ApproveIn, who: Staffed, session: Db
) -> ReviewItemOut:
    decided = await review.decide(
        session, staff=who, item_id=item_id, verdict=Verdict.APPROVED, reason=body.reason
    )
    return ReviewItemOut.of(decided)


@router.post("/items/{item_id}/reject")
async def reject(item_id: uuid.UUID, body: RejectIn, who: Staffed, session: Db) -> ReviewItemOut:
    decided = await review.decide(
        session, staff=who, item_id=item_id, verdict=Verdict.REJECTED, reason=body.reason
    )
    return ReviewItemOut.of(decided)


@router.post("/items/{item_id}/rewrite")
async def rewrite(item_id: uuid.UUID, body: RewriteIn, who: Staffed, session: Db) -> ReviewItemOut:
    decided = await review.decide(
        session,
        staff=who,
        item_id=item_id,
        verdict=Verdict.REWRITTEN,
        reason=body.reason,
        rewrite=body.lines.model_dump(),
    )
    return ReviewItemOut.of(decided)


@router.get("/proposals")
async def the_proposals(who: Staffed, session: Db) -> list[ProposalOut]:
    return [
        ProposalOut(
            item_id=item.id,
            card_type=item.card_type,
            language=item.language,
            changes=list((item.proposed or {}).get("changes", [])),
            reason=item.reason,
            decided_by=item.decided_by,
            decided_at=item.decided_at,
        )
        for item in await review.proposals(session)
    ]


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def propose_source(body: SourceIn, who: Staffed, session: Db) -> ReviewItemOut:
    item = await review.propose_source(
        session,
        staff=who,
        name=body.name,
        domain=body.domain,
        kind=body.kind,
        regions=body.regions,
        languages=body.languages,
    )
    return ReviewItemOut.of(item)
