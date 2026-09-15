"""The timeline routes (E03). Every one takes the key context; none is reachable without it.

    GET  /profiles/{id}/timeline                          the spine, the episodes, what hangs off each
    POST /profiles/{id}/episodes                          open an episode
    GET  /profiles/{id}/episodes/{episode_id}             one episode, across its visits
    POST /profiles/{id}/episodes/{episode_id}/attach      hang a paper off it, on a yes
    POST /profiles/{id}/appointments                      write down a visit, on a yes
    POST /profiles/{id}/appointments/{a}/status           one step of its status, on a yes
    POST /profiles/{id}/appointments/{a}/attach           hang a paper off a visit, on a yes
    GET  /profiles/{id}/providers                         the directory
    POST /profiles/{id}/providers                         add to it
    GET  /profiles/{id}/providers/{provider_id}           one provider's history and notes
    POST /profiles/{id}/providers/{provider_id}/notes     the chief's line about the place
    GET  /profiles/{id}/changes                           what changed since you last looked
    POST /profiles/{id}/ask                               recall, with citations

The yeses — for a visit, a step of its status, and hanging a paper — are minted at `POST
/profiles/{id}/confirmations` with subjects `appointment`, `appointment_status` and `attach`
(`app.channels.api.profiles`), and spent once here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status
from pydantic import AwareDatetime

from app.channels.about_him import reader_of
from app.channels.api.delivery import via_of
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.feelings_schemas import FeelingOut
from app.channels.api.timeline_schemas import (
    AnswerOut,
    AppointmentIn,
    AppointmentOut,
    AskIn,
    AttachIn,
    AttachmentOut,
    ChangesOut,
    EpisodeIn,
    EpisodeOut,
    EpisodeViewOut,
    PlaceNoteIn,
    PlaceNoteOut,
    ProviderHistoryOut,
    ProviderIn,
    ProviderOut,
    ProviderSummaryOut,
    StatusIn,
    TimelineOut,
)
from app.memory.attach import attach_to_appointment, attach_to_episode
from app.memory.changes import last_look, mark_looked, what_changed
from app.memory.providers import directory, provider_history, write_chief_note
from app.memory.spine import add_provider, book_appointment, change_appointment_status
from app.memory.timeline import MAX_PAGE, PAGE_SIZE, episode_view, timeline
from app.memory.working import open_episode
from app.reasoning.feelings.service import record_tap
from app.safety.red_flags import detect
from app.search.ask import recall

router = APIRouter(prefix="/profiles", tags=["timeline"])

Language = Query(default=None, min_length=2, max_length=16)


@router.get("/{profile_id}/timeline")
async def get_timeline(
    context: Context,
    session: Db,
    since: AwareDatetime | None = None,
    until: AwareDatetime | None = None,
    cursor: str | None = Query(default=None, max_length=200),
    episode: uuid.UUID | None = None,
    limit: int = Query(default=PAGE_SIZE, ge=1, le=MAX_PAGE),
    language: str | None = Language,
) -> TimelineOut:
    """The last check-up, the last visit and the next visit in his words, then the visits
    and episodes newest first, each with what hangs off it. `?episode=` narrows to one
    episode and its visits; `?cursor=` is the last page's `next_cursor`. Read under the
    visits' scope; every other part under its own, and `withheld` names what the key does
    not reach."""
    page = await timeline(
        session,
        context=context,
        since=since,
        until=until,
        cursor=cursor,
        episode_id=episode,
        limit=limit,
        language=language,
    )
    return (await reader_of(session, context, language)).model(TimelineOut.of(page))


@router.post("/{profile_id}/episodes", status_code=status.HTTP_201_CREATED)
async def start_episode(body: EpisodeIn, context: Context, session: Db) -> EpisodeOut:
    """Something going on, from now. One of each kind open at a time."""
    return EpisodeOut.of(
        await open_episode(session, context=context, kind=body.kind, label=body.label)
    )


@router.get("/{profile_id}/episodes/{episode_id}")
async def get_episode(episode_id: uuid.UUID, context: Context, session: Db) -> EpisodeViewOut:
    """One episode and what hangs off it, with each visit that was part of it."""
    return EpisodeViewOut.of(await episode_view(session, context=context, episode_id=episode_id))


@router.post("/{profile_id}/episodes/{episode_id}/attach", status_code=status.HTTP_201_CREATED)
async def attach_episode(
    episode_id: uuid.UUID, body: AttachIn, context: Context, session: Db
) -> AttachmentOut:
    """Hang a paper off an open episode, on the caller's yes for exactly that."""
    row = await attach_to_episode(
        session,
        context=context,
        artifact_id=body.artifact_id,
        episode_id=episode_id,
        confirmation_id=body.confirmation_id,
    )
    return AttachmentOut.of(row)


@router.post("/{profile_id}/appointments", status_code=status.HTTP_201_CREATED)
async def book(body: AppointmentIn, context: Context, session: Db) -> AppointmentOut:
    """Write down a visit a person arranged. Nothing is booked with a clinic from here."""
    visit = await book_appointment(
        session,
        context=context,
        provider_id=body.provider_id,
        scheduled_at=body.scheduled_at,
        purpose=body.purpose,
        confirmation_id=body.confirmation_id,
        episode_id=body.episode_id,
    )
    return AppointmentOut.of(visit)


@router.post("/{profile_id}/appointments/{appointment_id}/status")
async def move(
    appointment_id: uuid.UUID, body: StatusIn, context: Context, session: Db
) -> AppointmentOut:
    """One step along a visit's path — confirmed, happened, did not happen, cancelled."""
    visit = await change_appointment_status(
        session,
        context=context,
        appointment_id=appointment_id,
        status=body.status,
        confirmation_id=body.confirmation_id,
    )
    return AppointmentOut.of(visit)


@router.post(
    "/{profile_id}/appointments/{appointment_id}/attach", status_code=status.HTTP_201_CREATED
)
async def attach_visit(
    appointment_id: uuid.UUID, body: AttachIn, context: Context, session: Db
) -> AttachmentOut:
    """Hang a paper off a visit — the letter from it — on the caller's yes for exactly that."""
    row = await attach_to_appointment(
        session,
        context=context,
        artifact_id=body.artifact_id,
        appointment_id=appointment_id,
        confirmation_id=body.confirmation_id,
    )
    return AttachmentOut.of(row)


@router.get("/{profile_id}/providers")
async def providers(context: Context, session: Db) -> list[ProviderSummaryOut]:
    """Every provider he has used, with how many visits and the last and next."""
    return [ProviderSummaryOut.of(each) for each in await directory(session, context=context)]


@router.post("/{profile_id}/providers", status_code=status.HTTP_201_CREATED)
async def new_provider(body: ProviderIn, context: Context, session: Db) -> ProviderOut:
    provider = await add_provider(
        session,
        context=context,
        name=body.name,
        kind=body.kind,
        region=body.region or context.region,
        phone_e164=body.phone_e164,
        address=body.address,
    )
    return ProviderOut.of(provider)


@router.get("/{profile_id}/providers/{provider_id}")
async def provider(provider_id: uuid.UUID, context: Context, session: Db) -> ProviderHistoryOut:
    """One provider: its visits, the papers from them, the medicines on its name, and — for
    the owner and his chief — their notes about the place."""
    history = await provider_history(session, context=context, provider_id=provider_id)
    return ProviderHistoryOut.of(history)


@router.post("/{profile_id}/providers/{provider_id}/notes", status_code=status.HTTP_201_CREATED)
async def note_on_provider(
    provider_id: uuid.UUID, body: PlaceNoteIn, request: Request, context: Context, session: Db
) -> PlaceNoteOut:
    """The chief's one line about a place. A line naming a medicine or a condition is refused
    (`NoteNamesHealth`, 400), and so is anyone but the owner or a chief (`NotAChief`, 403)."""
    note = await write_chief_note(
        session,
        context=context,
        provider_id=provider_id,
        text=body.text,
        registry=providers_of(request).drug_registry,
    )
    return PlaceNoteOut.of(note)


@router.get("/{profile_id}/changes")
async def changes(
    request: Request, context: Context, session: Db, language: str | None = Language
) -> ChangesOut:
    """What changed since the caller last looked — or everything, on a first look — and what
    is still waiting. Reading it is looking: the look is written down, on the trail, and the
    next read counts from it."""
    last = await last_look(session, context=context)
    found = await what_changed(
        session,
        context=context,
        since=None if last is None else last.looked_at,
        seen=None if last is None else last.appointments,
        registry=providers_of(request).drug_registry,
        language=language,
    )
    look = await mark_looked(session, context=context)
    return (await reader_of(session, context, language)).model(ChangesOut.of(found, look.looked_at))


@router.post("/{profile_id}/ask")
async def ask(body: AskIn, request: Request, context: Context, session: Db) -> AnswerOut:
    """A question about his own record. The answer is lines made of templates and the values
    they cite, each naming its ids; "Nura does not have that written down" when nothing
    answers; the boundary last. The question is kept as a MESSAGE artefact, by reference."""
    outside = providers_of(request)
    # A red flag in the question takes the red-flag path, exactly as the same word tapped on the
    # feeling cloud: the moment written in his own typed words, the flag raised and kept, the
    # family told, the urgent card said back (red flags escalate first; .claude/rules/safety.md).
    # Nothing is looked up after it, so nothing after it can take the card away: not a key that
    # holds the emergency card but not ask (a helper's), not a lookup that fails. A key without
    # the emergency card is refused as its tap on the button is.
    heard = detect(body.question)
    if heard is not None:
        tapped = await record_tap(
            session,
            context=context,
            word=heard,
            registry=outside.drug_registry,
            store=outside.object_store,
            transcriber=outside.transcriber,
            via=via_of(request),
            language=body.language,
            said=body.question,
        )
        return AnswerOut.red_only(FeelingOut.of(tapped), body.mode)
    answer = await recall(
        session,
        context=context,
        question=body.question,
        mode=body.mode,
        retriever=outside.retriever,
        store=outside.object_store,
        registry=outside.drug_registry,
        language=body.language,
    )
    return AnswerOut.of(answer)
