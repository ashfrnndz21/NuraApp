"""The feed over HTTP (E21).

    GET  /profiles/{id}/feed?cursor=            one page: now, today, the gate, story, learning
    GET  /profiles/{id}/feed/cached             the last first page rendered for this person
    POST /profiles/{id}/feed/{item}/engagement  seen, heard, tapped, not for me, shared
    GET  /profiles/{id}/sources                 the allowlist (owner, chief)
    POST /profiles/{id}/search-jobs             a self-search, allowlist-scoped (owner, chief)
    GET  /profiles/{id}/search-jobs/{job}       what it found

Every route takes the key context. The owner reads the patient's supply; a chief, caregiver
or steward reads the caregiver's list, narrowed to the parts of the record the key covers.
The feeling cloud's tap is in `app.channels.api.feelings`, with the rest of E17.
`?at=` on the feed is a dev-only way to pretend it is another hour for the quiet-hours check
(`make checkpoint N=8`); on any deployment but a declared dev run it is refused.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status
from pydantic import AwareDatetime

from app.audit.access import audited_profile_read
from app.channels.api.deps import Context, Db, providers_of, settings_of
from app.channels.api.feed_schemas import (
    EngagementIn,
    EngagementOut,
    FeedPageOut,
    SearchJobIn,
    SearchJobOut,
    SourceOut,
)
from app.db import utcnow
from app.delivery.feed.compose import today_for
from app.delivery.feed.engagement import record_engagement
from app.delivery.feed.rank import NotOnADevRun, cached_page, feed_page
from app.delivery.feed.search import Engine, create_job, get_job, list_jobs
from app.delivery.feed.sources import list_sources
from app.delivery.strings import language_for

router = APIRouter(prefix="/profiles", tags=["feed"])


def _engine(request: Request) -> Engine:
    providers = providers_of(request)
    return Engine(
        searcher=providers.searcher,
        compressor=providers.compressor,
        registry=providers.drug_registry,
    )


@router.get("/{profile_id}/feed")
async def feed(
    request: Request,
    context: Context,
    session: Db,
    cursor: str | None = Query(default=None, max_length=200),
    at: AwareDatetime | None = None,
) -> FeedPageOut:
    """One page of the feed. No cursor makes today's cards and answers the first page, which
    is also kept for `…/feed/cached`; a cursor answers the page it names, as of when it was
    minted, so the same cursor is the same page."""
    pretend = None
    if at is not None:
        if not settings_of(request).dev_code_sender:
            raise NotOnADevRun("?at= is for a declared dev run only")
        pretend = at.astimezone(today_for(context).tz) if at.tzinfo else at
    page = await feed_page(
        session, context=context, engine=_engine(request), cursor=cursor, pretend_local=pretend
    )
    return FeedPageOut.of(page)


@router.get("/{profile_id}/feed/cached")
async def cached(context: Context, session: Db) -> FeedPageOut:
    """The last first page rendered for this person, as it was: the offline page."""
    return FeedPageOut.of(await cached_page(session, context=context))


@router.post("/{profile_id}/feed/{item_id}/engagement", status_code=status.HTTP_201_CREATED)
async def engagement(
    item_id: uuid.UUID, body: EngagementIn, context: Context, session: Db
) -> EngagementOut:
    """What the person did with the card. "Not for me" from the owner holds that kind of
    card back for the rest of his day, as a fact State folds in."""
    row = await record_engagement(
        session, context=context, item_id=item_id, kind=body.event, channel=body.channel
    )
    return EngagementOut(
        engagement_id=row.id, item_id=row.item_id, event=row.kind, channel=row.via, at=row.at
    )


@router.get("/{profile_id}/sources")
async def sources(context: Context, session: Db) -> list[SourceOut]:
    """The allowlist for this profile's region. The owner's and his chief's to see."""
    return [SourceOut.of(source) for source in await list_sources(session, context=context)]


@router.post("/{profile_id}/search-jobs", status_code=status.HTTP_201_CREATED)
async def add_search_job(
    body: SearchJobIn, request: Request, context: Context, session: Db
) -> SearchJobOut:
    """Queue a self-search and run it now against the allowlist, through the fixture ports.
    A source named that is not allowlisted is refused (`SourceNotAllowlisted`, 400)."""
    from app.delivery.feed.search import run_job
    from app.state.service import current_state

    job = await create_job(
        session,
        context=context,
        kind=body.kind,
        terms=body.terms,
        source_ids=body.source_ids,
        cadence=body.cadence,
        reason={"asked": body.reason, "by": str(context.person_id)},
    )
    profile = await audited_profile_read(session, context)
    state = await current_state(session, context=context)
    if state.stale is False:
        from app.audit.access import audited_read
        from app.delivery.feed.models import FeedItem
        from app.keys.scopes import Scope

        held = await audited_read(
            session, FeedItem, context, Scope.PROFILE, where=(FeedItem.expires_at > utcnow(),)
        )
        await run_job(
            session,
            context=context,
            job=job,
            engine=_engine(request),
            state=state,
            language=language_for(profile.language),
            day=today_for(context).key,
            doctor=None,
            existing={item.dedupe_key for item in held},
        )
    return SearchJobOut.of(job)


@router.get("/{profile_id}/search-jobs")
async def search_jobs(context: Context, session: Db) -> list[SearchJobOut]:
    return [SearchJobOut.of(job) for job in await list_jobs(session, context=context)]


@router.get("/{profile_id}/search-jobs/{job_id}")
async def search_job(job_id: uuid.UUID, context: Context, session: Db) -> SearchJobOut:
    return SearchJobOut.of(await get_job(session, context=context, job_id=job_id))
