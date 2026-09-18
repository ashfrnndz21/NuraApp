"""The feed over HTTP (E21).

    GET  /profiles/{id}/feed?cursor=            one page: now, today, the gate, story, learning
    GET  /profiles/{id}/feed/jobs/status        whether today's self-searches are still to run
    GET  /profiles/{id}/feed/today              today's top three: alert, reminder, insight
    GET  /profiles/{id}/feed/{item}/voice       the card's spoken twin, as audio (E11-04)
    GET  /profiles/{id}/feed/cached             the last first page rendered for this person
    POST /profiles/{id}/feed/{item}/engagement  seen, heard, tapped, not for me, shared
    POST /profiles/{id}/feed/events             the phone's queue: opened, played, replayed, …
    GET  /profiles/{id}/feed/week               "Sent to Pa this week": every card, its status
    GET  /profiles/{id}/feed/{item}/clip/poster      a clip's still (E09-06)
    GET  /profiles/{id}/feed/{item}/clip/captions    its captions, WebVTT, in its language
    GET  /profiles/{id}/feed/{item}/clip/video       its excerpt, where the licence allows one
    GET  /profiles/{id}/sources                 the allowlist (owner, chief)
    GET  /profiles/{id}/search-jobs             "Watching for Pa": each watch, its sources, cadence
    POST /profiles/{id}/search-jobs             a self-search, allowlist-scoped (owner, chief)
    GET  /profiles/{id}/search-jobs/{job}       what it found
    PATCH /profiles/{id}/search-jobs/{job}      pause or resume it
    GET  /profiles/{id}/area                    his area, coarse (owner, chief)
    PUT  /profiles/{id}/area                    set on his yes (owner, steward)
    GET  /profiles/{id}/signals                 "What Nura uses": every family, on or off
    PUT  /profiles/{id}/signals/{family}        switch one on or off (owner, chief)
    POST /profiles/{id}/find                    the ask bar's Web, Videos and Providers filters

Every route takes the key context. The owner reads the patient's supply; a chief, caregiver
or steward reads the caregiver's list, narrowed to the parts of the record the key covers.
The feeling cloud's tap is in `app.channels.api.feelings`, with the rest of E17.
`?at=` on the feed is a dev-only way to pretend it is another hour for the quiet-hours check
(`make checkpoint N=8`); on any deployment but a declared dev run it is refused.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.audit.models import Action
from app.audit.trail import record as record_audit
from app.channels.about_him import Reader, reader_of
from app.channels.api.deps import Context, Db, providers_of, session_scope, settings_of
from app.channels.api.feed_schemas import (
    AreaIn,
    AreaOut,
    EngagementIn,
    EngagementOut,
    EventsIn,
    EventsOut,
    FeedItemOut,
    FeedPageOut,
    FindIn,
    FindOut,
    JobsStatusOut,
    ResultOut,
    SearchJobIn,
    SearchJobOut,
    SearchJobPatchIn,
    SentOut,
    SignalIn,
    SignalsOut,
    SourceOut,
)
from app.channels.api.refusals import refused
from app.channels.api.sse_pump import stream_with_background_pump
from app.delivery.feed.area import read_area, set_area
from app.delivery.feed.clips import clip_captions, clip_poster, clip_video
from app.delivery.feed.compose import around_for, today_for
from app.delivery.feed.engagement import record_engagement, record_events
from app.delivery.feed.find import FindStep, find_stream
from app.delivery.feed.find import find as find_pages
from app.delivery.feed.models import SearchJob
from app.delivery.feed.rank import (
    NotOnADevRun,
    cached_page,
    feed_page,
    item_json,
    sent_this_week,
    top_three,
)
from app.delivery.feed.search import (
    Engine,
    create_job,
    get_job,
    jobs_looking_today,
    list_jobs,
    pause_job,
)
from app.delivery.feed.sources import list_sources, usable_sources
from app.delivery.feed.twin import one_card, spoken_twin
from app.delivery.feed.why_sheet import why_lines
from app.delivery.strings import FIND_STEPS, language_for, watch_label
from app.errors import Refusal
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.signals import (
    SignalFamily,
    current_signal_use,
    set_signal_use,
    signals_may_be_set,
)
from app.search.narrate import NarratedStep, Narrator, narrate_step_label

router = APIRouter(prefix="/profiles", tags=["feed"])
log = logging.getLogger("nura.channels.feed")


def _engine(request: Request) -> Engine:
    providers = providers_of(request)
    return Engine(
        searcher=providers.searcher,
        compressor=providers.compressor,
        registry=providers.drug_registry,
        ranges=providers.reference_ranges,
        voice=providers.voice,
        store=providers.object_store,
        clips=providers.clips,
    )


def _with_why_sheet(out: FeedPageOut, *, context: KeyContext, reader: Reader) -> FeedPageOut:
    """Every card's Why, as this reader hears it (RE-08, docs/recommendation-engine.md §3.3):
    its plain reason, when the reader's key covers the scope the card and its evidence rest
    on, or the line that says a part of the record is withheld — never silent. Runs before
    `Reader.page()`, whose voice twins already turn `why["plain"]` into the caregiver's voice
    and do the same here, the same way, for `why["lines"]`."""
    items = [
        item.model_copy(
            update={
                "why": {
                    **item.why,
                    "lines": list(
                        why_lines(
                            str(item.why.get("plain") or ""),
                            scope=Scope(item.scope),
                            context=context,
                            language=item.language,
                            his=reader.his,
                            patient_name=reader.name,
                        )
                    ),
                }
            }
        )
        for item in out.items
    ]
    return out.model_copy(update={"items": items})


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
    reader = await reader_of(session, context, None)
    return reader.page(_with_why_sheet(FeedPageOut.of(page), context=context, reader=reader))


@router.get("/{profile_id}/feed/jobs/status")
async def feed_jobs_status(context: Context, session: Db) -> JobsStatusOut:
    """Whether the day's self-searches are still to run (docs/design-direction.md,
    'Conversation, waiting and thinking'): the honest "Nura is looking for today's reads"
    line binds to this, a real read of the same jobs `GET /feed` runs inline
    (`app.delivery.feed.search.jobs_looking_today`), never a guess or a timer. A read:
    nothing is written."""
    return JobsStatusOut(looking=await jobs_looking_today(session, context=context, day=today_for(context)))


@router.get("/{profile_id}/feed/today")
async def feed_today(request: Request, context: Context, session: Db) -> FeedPageOut:
    """Today's top three (E11-02): alerts, then reminders, then insights, each with its why."""
    top = FeedPageOut.of(await top_three(session, context=context, engine=_engine(request)))
    reader = await reader_of(session, context, None)
    return reader.page(_with_why_sheet(top, context=context, reader=reader))


@router.get("/{profile_id}/feed/{item_id}/voice")
async def feed_voice(
    item_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Query(default=None, max_length=8),
) -> Response:
    """The card's spoken twin as audio (E11-04): the bytes themselves, with their content type,
    under thirty seconds, from the region's cache when it has been said before. 404 when there
    is no audio for this card in that language (no voice for it yet, too long to say, or not
    the card's language): the phone then says it with its own voice. Played on a tap; nothing
    here plays anything by itself."""
    providers = providers_of(request)
    said = await spoken_twin(
        session,
        context=context,
        item_id=item_id,
        voice=providers.voice,
        store=providers.object_store,
        language=language,
    )
    return Response(
        content=said.spoken.audio,
        media_type=said.spoken.content_type,
        headers={
            "X-Duration-Seconds": f"{said.spoken.duration_seconds:.1f}",
            "X-Voice-Cache": "hit" if said.cached else "miss",
            "Cache-Control": "private",
        },
    )


@router.post("/{profile_id}/feed/events")
async def feed_events(body: EventsIn, context: Context, session: Db) -> EventsOut:
    """The phone's queue of what he did with his cards, flushed on the next connection
    (E11-08): each event written once, at the moment it happened, by the id the phone gave it.
    The answer names what was written and what was skipped and why; the phone forgets both."""
    flushed = await record_events(
        session, context=context, events=[event.queued() for event in body.events]
    )
    return EventsOut.of(flushed)


@router.get("/{profile_id}/feed/week")
async def feed_week(context: Context, session: Db) -> list[SentOut]:
    """Sent to Pa this week (spec §1): every card made for him since Monday, newest first,
    with what became of it — sent, opened, played, dismissed, held — and its source. On a
    key that is not his, said about him by name, the way `GET /feed` already is (#210): a
    card of his with no twin for a line that still speaks to him is not shown to her either."""
    reader = await reader_of(session, context, None)
    found = [SentOut.of(one) for one in await sent_this_week(session, context=context)]
    return reader.sent(found)


@router.get("/{profile_id}/feed/{item_id}/clip/poster")
async def feed_clip_poster(
    item_id: uuid.UUID, request: Request, context: Context, session: Db
) -> Response:
    """A clip's still (E09-06), from this server: no third-party player, no embed."""
    providers = providers_of(request)
    data, kind = await clip_poster(
        session,
        context=context,
        item_id=item_id,
        renderer=providers.clips,
        store=providers.object_store,
    )
    return Response(content=data, media_type=kind, headers={"Cache-Control": "private"})


@router.get("/{profile_id}/feed/{item_id}/clip/captions")
async def feed_clip_captions(item_id: uuid.UUID, context: Context, session: Db) -> Response:
    """A clip's captions as WebVTT, in the card's language: its narration's lines, timed."""
    text = await clip_captions(session, context=context, item_id=item_id)
    return Response(
        content=text, media_type="text/vtt; charset=utf-8", headers={"Cache-Control": "private"}
    )


@router.get("/{profile_id}/feed/{item_id}/clip/video")
async def feed_clip_video(
    item_id: uuid.UUID, request: Request, context: Context, session: Db
) -> Response:
    """A clip's excerpt, kept on this server, only where the publisher's licence allows
    reuse; `NoExcerpt` (404) otherwise, and the phone shows the still with the narration."""
    providers = providers_of(request)
    data, kind = await clip_video(
        session,
        context=context,
        item_id=item_id,
        renderer=providers.clips,
        store=providers.object_store,
    )
    return Response(content=data, media_type=kind, headers={"Cache-Control": "private"})


@router.get("/{profile_id}/feed/cached")
async def cached(context: Context, session: Db) -> FeedPageOut:
    """The last first page rendered for this person, as it was: the offline page."""
    kept = FeedPageOut.of(await cached_page(session, context=context))
    reader = await reader_of(session, context, None)
    return reader.page(_with_why_sheet(kept, context=context, reader=reader))


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

        every = await audited_read(session, FeedItem, context, Scope.PROFILE)
        engine = _engine(request)
        await run_job(
            session,
            context=context,
            job=job,
            engine=engine,
            state=state,
            language=language_for(profile.language),
            around=await around_for(
                session,
                context=context,
                engine=engine,
                state=state,
                day=today_for(context),
                profile=profile,
            ),
            doctor=None,
            existing={item.dedupe_key for item in every},
        )
    return await _job_out(session, context, job, None)


async def _job_out(
    session: AsyncSession, context: KeyContext, job: SearchJob, language: str | None
) -> SearchJobOut:
    """A job with what it watches for in the reader's words, and the sources it reads."""
    profile = await audited_profile_read(session, context)
    names = {
        str(source.id): source.name
        for source in await usable_sources(session, region=context.region)
    }
    return SearchJobOut.of(
        job,
        label=watch_label(
            job.kind.value, list(job.terms), language or profile.language, profile.area
        ),
        sources=sorted({names[one] for one in job.source_ids if one in names}),
    )


@router.get("/{profile_id}/search-jobs")
async def search_jobs(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, max_length=8),
) -> list[SearchJobOut]:
    """Watching for Pa (spec §1): every search the engine runs for him — what for, in the
    reader's words, which allowlisted sources, how often, and whether it is paused."""
    return [
        await _job_out(session, context, job, language)
        for job in await list_jobs(session, context=context)
    ]


@router.get("/{profile_id}/search-jobs/{job_id}")
async def search_job(
    job_id: uuid.UUID,
    context: Context,
    session: Db,
    language: str | None = Query(default=None, max_length=8),
) -> SearchJobOut:
    return await _job_out(
        session, context, await get_job(session, context=context, job_id=job_id), language
    )


@router.patch("/{profile_id}/search-jobs/{job_id}")
async def pause_search_job(
    job_id: uuid.UUID,
    body: SearchJobPatchIn,
    context: Context,
    session: Db,
    language: str | None = Query(default=None, max_length=8),
) -> SearchJobOut:
    """Pause a watch, or resume it. The owner's and his chief's; on the trail."""
    job = await pause_job(session, context=context, job_id=job_id, enabled=body.enabled)
    return await _job_out(session, context, job, language)


@router.get("/{profile_id}/area")
async def area(context: Context, session: Db) -> AreaOut:
    """His area and the towns it may be: for him and the chief who manages his feed."""
    return AreaOut.of(await read_area(session, context=context))


@router.put("/{profile_id}/area")
async def put_area(body: AreaIn, context: Context, session: Db) -> AreaOut:
    """Set his area on his yes — a town from the list or a postcode's first digits, never a
    street — or clear it. Once the graph is his, `body.confirmation_id` must be minted for
    exactly this area (`POST /confirmations`, subject `area`, `AreaNotConfirmed` without
    one). His own key, or the steward's before he claims, which takes no confirmation."""
    return AreaOut.of(
        await set_area(
            session, context=context, area=body.area, confirmation_id=body.confirmation_id
        )
    )


@router.get("/{profile_id}/signals")
async def signals(context: Context, session: Db) -> SignalsOut:
    """"What Nura uses": food, sleep, steps, water, what he asks — each on or off, as he last
    set it or the default (RE-05, docs/recommendation-engine.md §3.6). `may_set` says
    whether this key may switch one; a caregiver reads them, only he or his chief sets them."""
    uses = await current_signal_use(session, context=context)
    return SignalsOut.of(uses, may_set=signals_may_be_set(context))


@router.put("/{profile_id}/signals/{family}")
async def put_signal(
    family: SignalFamily, body: SignalIn, context: Context, session: Db
) -> SignalsOut:
    """Switch one family on or off, confirmed at the tap: his own key, or his chief's
    (`NotTheirsToSetSignals`, 403, for anyone else). The fact and the write are on the trail
    either way; State's preference dimension shows it on the next read."""
    await set_signal_use(session, context=context, family=family, on=body.on)
    uses = await current_signal_use(session, context=context)
    return SignalsOut.of(uses, may_set=True)


@router.post("/{profile_id}/find")
async def find(body: FindIn, request: Request, context: Context, session: Db) -> FindOut:
    """The ask bar's Web, Videos and Providers filters: the allowlisted sources only, said
    in his language with the boundary; his own providers by name. Records is `POST …/ask`.
    A POST so the words he typed about his health are in the body, never in a URL that an
    access log, a proxy or the browser's history keeps. Nothing is written."""
    found = await find_pages(
        session,
        context=context,
        engine=_engine(request),
        words=body.q,
        where=body.where,
        language=body.language,
    )
    return FindOut(where=body.where, results=[ResultOut.of(one) for one in found])


def _sse(payload: dict[str, object]) -> bytes:
    """One Server-Sent Event: a `data:` line of JSON (`app.channels.api.timeline._sse`, the
    same shape — kept local so this route does not import the timeline router)."""
    return f"data: {json.dumps(payload)}\n\n".encode()


async def _narrate_find_step_later(
    queue: asyncio.Queue[bytes | object],
    narrator: Narrator,
    steps: list[NarratedStep],
    key: str,
    label: str,
    language: str,
    reader: Reader,
) -> None:
    """Find's own twin of `app.channels.api.timeline._narrate_step_later`: awaited in the
    background, never in the stream's own path — the one `step` event already went out, with
    its catalogue label, before this is even scheduled."""
    new_label = await narrate_step_label(narrator, steps, key, label, language=language, reader=reader)
    if new_label is not None:
        await queue.put(_sse({"type": "step_label", "key": key, "label": new_label}))


@router.post("/{profile_id}/find/stream")
async def find_pages_stream(body: FindIn, request: Request, context: Context) -> StreamingResponse:
    """`POST /{id}/find`, streamed, for the Web and Videos filters (docs/design-direction.md
    'Conversation, waiting and thinking'): one `step` event the instant the allowlisted
    search is actually running (`find_stream`), then a `results` event — the same list
    `POST /{id}/find` gives. Providers is a directory read and streams straight to its
    results, no step: there is no real stage to say is still in progress.

    Opens its own session (`session_scope`), never `Depends(db)` — see `app.channels.api.
    timeline.ask_stream` for why a stream cannot use a `yield` dependency.

    Zero or more `step_label` events may follow the one `step`, whenever a Claude-backed
    narrator (`NURA_NARRATOR=claude`) actually rephrases its label — in the background, never
    holding the step or the `results` event back, the same redesign `app.channels.api.
    timeline.ask_stream` carries for Ask (`app.search.narrate.narrate_step_label`). An older
    web client that has never seen `step_label` simply ignores it."""
    code = language_for(body.language)
    outside = providers_of(request)
    # FIND_STEPS carries no caregiver twin (its lines are neutral, "Looking online." — see
    # `app.delivery.strings.FIND_STEPS`), so there is no "his voice" to get wrong here the way
    # Ask's steps have; the narrator sees the direct-voice reader.
    reader = Reader(his=True, language=code)

    async def pump(queue: asyncio.Queue[bytes | object]) -> None:
        try:
            async with session_scope(request) as session:
                narration_tasks: list[asyncio.Task[None]] = []
                async for event in find_stream(
                    session, context=context, engine=_engine(request), words=body.q, where=body.where, language=body.language
                ):
                    if isinstance(event, FindStep):
                        label = FIND_STEPS[code][body.where]
                        if outside.narrator.external_processor is not None:
                            # One reach outside the region per streamed search (ADR 0017),
                            # mirroring `app.channels.api.timeline.ask_stream`'s line for Ask.
                            await record_audit(
                                session,
                                context=context,
                                action=Action.SHARE,
                                scope=Scope.ASK,
                                target=EXTERNAL_MODEL_PROCESSOR,
                                rows=1,
                                shared_with_label=outside.narrator.external_processor,
                            )
                        # Sent at once, with the catalogue label — never held back for the
                        # narrator (`_step_event_now`'s own docstring in timeline.py).
                        await queue.put(_sse({"type": "step", "key": event.key, "label": label}))
                        steps = [NarratedStep(key=event.key, label=label)]
                        narration_tasks.append(
                            asyncio.create_task(
                                _narrate_find_step_later(queue, outside.narrator, steps, event.key, label, code, reader)
                            )
                        )
                    else:
                        await queue.put(
                            _sse({"type": "results", "results": [ResultOut.of(one).model_dump(mode="json") for one in event]})
                        )
                if narration_tasks:
                    await asyncio.gather(*narration_tasks, return_exceptions=True)
        except Refusal as refusal:
            response = await refused(request, refusal)
            body_ = json.loads(bytes(response.body))
            await queue.put(_sse({"type": "refusal", "status": response.status_code, **body_}))

    return StreamingResponse(stream_with_background_pump(pump), media_type="text/event-stream")


@router.get("/{profile_id}/feed/{item_id}")
async def feed_card(item_id: uuid.UUID, context: Context, session: Db) -> FeedItemOut:
    """One card by its id, under the card's own scope: what a push opens (`/app/?open=<id>`,
    #143). Not on this profile, or not for this key: refused, and the app falls back to Today."""
    item = await one_card(session, context=context, item_id=item_id)
    return FeedItemOut(**item_json(item, "generated"))
