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
    POST /profiles/{id}/conversations                      start a new conversation thread
    GET  /profiles/{id}/conversations/{cid}                the thread, every turn on it
    POST /profiles/{id}/conversations/{cid}/turns/stream   a turn on that thread, streamed

The yeses — for a visit, a step of its status, and hanging a paper — are minted at `POST
/profiles/{id}/confirmations` with subjects `appointment`, `appointment_status` and `attach`
(`app.channels.api.profiles`), and spent once here.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime

from app.audit.models import Action
from app.audit.trail import record as record_audit
from app.channels.about_him import Reader, reader_of
from app.channels.api.delivery import via_of
from app.channels.api.deps import Context, Db, providers_of, session_scope
from app.channels.api.feelings_schemas import FeelingOut
from app.channels.api.refusals import refused
from app.channels.api.schemas import utc
from app.channels.api.sse_pump import stream_with_background_pump
from app.channels.api.timeline_schemas import (
    AnswerOut,
    AppointmentIn,
    AppointmentOut,
    AskIn,
    AttachIn,
    AttachmentOut,
    ChangesOut,
    ConversationOut,
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
    TurnOut,
)
from app.db import utcnow
from app.delivery.timeline_strings import ASK_STEP_NAMES, ASK_STEPS
from app.errors import Refusal
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.keys.scopes import Scope
from app.memory.attach import attach_to_appointment, attach_to_episode
from app.memory.changes import last_look, mark_looked, what_changed
from app.memory.providers import directory, provider_history, write_chief_note
from app.memory.spine import add_provider, book_appointment, change_appointment_status
from app.memory.timeline import MAX_PAGE, PAGE_SIZE, episode_view, language_for, timeline
from app.memory.working import open_episode
from app.reasoning.feelings.service import record_tap
from app.safety.red_flags import detect
from app.search.ask import AskStep, recall
from app.search.asker import AnswerDelta
from app.search.conversation import (
    conversation_by_id,
    current_conversation,
    memory_for,
    record_turn,
    start_new_conversation,
    turn_view,
    turns_of,
)
from app.search.narrate import NarratedStep, Narrator, narrate_step_label

router = APIRouter(prefix="/profiles", tags=["timeline"])


def _sse(payload: dict[str, object]) -> bytes:
    """One Server-Sent Event: a `data:` line of JSON, blank line after. Never buffered —
    written to the wire the instant the real work behind it finishes (docs/design-direction.md
    'Conversation, waiting and thinking')."""
    return f"data: {json.dumps(payload)}\n\n".encode()


async def _refusal_event(request: Request, refusal: Refusal) -> bytes:
    """A refusal mid-stream, in the same shape the non-streaming routes answer it in
    (`app.channels.api.refusals.refused`) — reused, not duplicated, so the two can never say
    a refusal two different ways. The stream's 200 has already gone out by the time a
    generator can raise (SSE has no later chance at a status code), so the refusal travels as
    an event instead and the web client turns it back into the same `Refused` it would get
    from a plain call (`web/src/api/client.ts`)."""
    response = await refused(request, refusal)
    body = json.loads(bytes(response.body))
    return _sse({"type": "refusal", "status": response.status_code, **body})

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
        panel=body.panel,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
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
    request: Request,
    context: Context,
    session: Db,
    language: str | None = Language,
    peek: bool = Query(default=False),
) -> ChangesOut:
    """What changed since the caller last looked — or everything, on a first look — and what
    is still waiting. Reading it is looking: the look is written down, on the trail, and the
    next read counts from it — unless `peek=true` (#207), for a tile that draws itself every
    time a screen renders (her Home) rather than a screen she came to read this on (the
    Record's own "what changed"). A peek answers the same question with the same words, under
    the same scope, but writes nothing: it marks no look, so it leaves no entry on his trail,
    and the next marking read still counts from wherever it last did."""
    last = await last_look(session, context=context)
    found = await what_changed(
        session,
        context=context,
        since=None if last is None else last.looked_at,
        seen=None if last is None else last.appointments,
        registry=providers_of(request).drug_registry,
        language=language,
    )
    if peek:
        looked_at = utcnow() if last is None else last.looked_at
    else:
        looked_at = (await mark_looked(session, context=context)).looked_at
    return (await reader_of(session, context, language)).model(ChangesOut.of(found, looked_at))


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


def _step_event_now(step: AskStep, steps_so_far: list[NarratedStep], lang: str, reader: Reader) -> bytes:
    """One `AskStep` off `recall_stream`, in his words (or the caregiver's twin, by his
    name): the label the trace shows while it works, and the short name the collapsed "What
    Nura looked at" line joins. `key` is a part of `app.search.ask.STEP_KEYS` — never a row,
    never a value off his record, so a step carries nothing beyond which part was read and how
    many things it held (`step.count`).

    Sent at once, with the catalogue's own label — a step is never held back for a narrator
    (`app.search.narrate.narrate_step_label`'s own docstring), however long a Claude-backed
    one takes to answer. `steps_so_far` is every step already streamed this ask, oldest first,
    appended to here, so a narrator asked about this step later sees the whole trace so far,
    not just the newest one."""
    label = reader.says(ASK_STEPS[lang][step.key])
    steps_so_far.append(NarratedStep(key=step.key, label=label, count=step.count))
    return _sse(
        {
            "type": "step",
            "key": step.key,
            "label": label,
            "name": ASK_STEP_NAMES[lang][step.key],
        }
    )


async def _narrate_step_later(
    queue: asyncio.Queue[bytes | object],
    narrator: Narrator,
    steps_so_far: Sequence[NarratedStep],
    step: AskStep,
    label: str,
    lang: str,
    reader: Reader,
) -> None:
    """Awaited in the background, never in the stream's own path (`_step_event_now` already
    sent the step, with its catalogue label, before this is even scheduled). Puts a
    `step_label` follow-up on `queue` only when the narrator actually had something different
    to say; an older web client that has never seen this event type simply ignores it
    (`web/src/screens/Ask.tsx`, `Thinking.tsx`)."""
    new_label = await narrate_step_label(
        narrator, steps_so_far, step.key, label, language=lang, reader=reader
    )
    if new_label is not None:
        await queue.put(_sse({"type": "step_label", "key": step.key, "label": new_label}))


async def _stream_turn(
    session: Any,
    context: Any,
    body: AskIn,
    request: Request,
    outside: Any,
    queue: asyncio.Queue[bytes | object],
    conversation: Any,
) -> None:
    """One turn, streamed onto `conversation` (W2): `ask_stream` and `turn_stream` share this
    — the only difference between them is which conversation they resolve before calling it
    (the current one, or one named by id). See `ask_stream`'s own docstring for the event
    contract; this adds nothing to it beyond `history` (conversation memory, so a follow-up
    can resolve "that") going in, and `record_turn` writing the finished answer onto the
    thread once it survives every check."""
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
        answer_out = AnswerOut.red_only(FeelingOut.of(tapped), body.mode)
        await queue.put(_sse({"type": "answer", "answer": answer_out.model_dump(mode="json")}))
        return
    lang = await language_for(session, context, body.language)
    reader = await reader_of(session, context, body.language)
    history = await memory_for(
        session, context=context, store=outside.object_store, conversation=conversation
    )
    steps_so_far: list[NarratedStep] = []
    reached_out = False
    narration_tasks: list[asyncio.Task[None]] = []
    async for event in outside.asker.ask_stream(
        session,
        context=context,
        question=body.question,
        mode=body.mode,
        retriever=outside.retriever,
        store=outside.object_store,
        registry=outside.drug_registry,
        language=body.language,
        history=history,
    ):
        if isinstance(event, AskStep):
            if outside.narrator.external_processor is not None and not reached_out:
                # Written before the first narration call, once per ask: a reach
                # that sends the trace's step ids and counts outside the region,
                # distinct from the ASK read itself (ADR 0017, mirroring
                # `app.ingestion.review.review_artifact`'s EXTERNAL_MODEL_PROCESSOR
                # line for the extractor). The agent asker's own reach, when it is
                # the one running, writes its own line the same way, inside
                # `ClaudeAsker.ask_stream` itself.
                await record_audit(
                    session,
                    context=context,
                    action=Action.SHARE,
                    scope=Scope.ASK,
                    target=EXTERNAL_MODEL_PROCESSOR,
                    rows=1,
                    shared_with_label=outside.narrator.external_processor,
                )
                reached_out = True
            await queue.put(_step_event_now(event, steps_so_far, lang, reader))
            # A snapshot of the trace so far: `steps_so_far` keeps growing after
            # this, and a narrator asked about an earlier step must still see the
            # trace as it stood when that step was streamed, not a later one.
            snapshot = list(steps_so_far)
            label = snapshot[-1].label
            narration_tasks.append(
                asyncio.create_task(
                    _narrate_step_later(
                        queue, outside.narrator, snapshot, event, label, lang, reader
                    )
                )
            )
        elif isinstance(event, AnswerDelta):
            await queue.put(_sse({"type": "answer_delta", "text": event.text}))
        else:
            await record_turn(
                session,
                context=context,
                store=outside.object_store,
                conversation=conversation,
                question_artifact_id=event.question_artifact_id,
                answer=event,
            )
            answer_out = AnswerOut.of(event).model_copy(update={"conversation_id": conversation.id})
            await queue.put(_sse({"type": "answer", "answer": answer_out.model_dump(mode="json")}))
    if narration_tasks:
        # Nothing here delayed a step, a tool call or the answer — every one of
        # those already went out above. This only delays the stream's own close,
        # so a still-running narration's `step_label` still reaches the wire
        # instead of being cancelled the instant the answer is sent.
        await asyncio.gather(*narration_tasks, return_exceptions=True)


@router.post("/{profile_id}/ask/stream")
async def ask_stream(body: AskIn, request: Request, context: Context) -> StreamingResponse:
    """`POST /{id}/ask`, streamed (docs/design-direction.md 'Conversation, waiting and
    thinking'): a `step` event the instant each real part of his record is read
    (`outside.asker.ask_stream` — the rule-based retriever by default, or the agent asker on a
    declared demo, `NURA_ASKER=claude`), zero or more `answer_delta` events as the agent
    asker's own finished answer is sent (never sent by the rule-based one, whose answer has
    always arrived whole), then an `answer` event — the same `AnswerOut` the plain route gives.
    An older web client that has never seen `answer_delta` simply ignores it and still gets
    every `step` and the final `answer`, unchanged. The red-flag path is unchanged and streams
    nothing: it is answered before any part of the record is looked up, same as `ask` above,
    so there is nothing to trace.

    Zero or more `step_label` events may follow any `step`, whenever — even after the final
    `answer` — a Claude-backed narrator (`NURA_NARRATOR=claude`) actually rephrases that step's
    label; the narrator's own call runs in the background (`_narrate_step_later`,
    `app.search.narrate.narrate_step_label`) and never holds the step itself, a tool call or
    the answer back, however long it takes (`app.llm.narrate.NARRATE_DEADLINE_S`). An older web
    client that has never seen `step_label` simply ignores it.

    W2: this always writes onto the asker's own current conversation
    (`app.search.conversation.current_conversation`) — the thread that continues across days
    until he starts a new one — the same as `POST .../conversations/{cid}/turns/stream` does
    for a named thread. A caller that only ever wants the plain answer, never the thread,
    still gets exactly that; the conversation is kept regardless.

    Opens its own session (`session_scope`), never `Depends(db)`: FastAPI closes a `yield`
    dependency the moment this function returns the `StreamingResponse` object, well before
    Starlette actually drives the pump to send the body — a session from `Depends(db)` would
    already be closed by the time a step tried to read with it (`app.channels.api.deps.
    session_scope`)."""
    outside = providers_of(request)

    async def pump(queue: asyncio.Queue[bytes | object]) -> None:
        try:
            async with session_scope(request) as session:
                conversation = await current_conversation(session, context=context)
                await _stream_turn(session, context, body, request, outside, queue, conversation)
        except Refusal as refusal:
            await queue.put(await _refusal_event(request, refusal))

    return StreamingResponse(stream_with_background_pump(pump), media_type="text/event-stream")


@router.post("/{profile_id}/conversations", status_code=status.HTTP_201_CREATED)
async def new_conversation(context: Context, session: Db) -> ConversationOut:
    """His own "New conversation" (W2): close whichever thread is open now, if any, and start
    a fresh one, empty."""
    conversation = await start_new_conversation(session, context=context)
    return ConversationOut(
        conversation_id=conversation.id,
        started_at=utc(conversation.started_at),
        last_turn_at=utc(conversation.last_turn_at),
        closed_at=None,
        summary=None,
        turns=[],
    )


@router.get("/{profile_id}/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, request: Request, context: Context, session: Db
) -> ConversationOut:
    """The thread (W2): every turn on it, oldest first, read back from the two artefacts each
    one points at — never a row's own words."""
    outside = providers_of(request)
    conversation = await conversation_by_id(session, context=context, conversation_id=conversation_id)
    turns = await turns_of(session, context=context, conversation=conversation)
    out_turns = []
    for turn in turns:
        question, answer_lines, honest = await turn_view(
            session, context=context, store=outside.object_store, turn=turn
        )
        out_turns.append(
            TurnOut(
                turn_id=turn.id,
                created_at=utc(turn.created_at),
                mode=turn.mode,
                language=turn.language,
                question=question,
                answered=turn.answered,
                answer_lines=answer_lines,
                honest=honest,
            )
        )
    return ConversationOut(
        conversation_id=conversation.id,
        started_at=utc(conversation.started_at),
        last_turn_at=utc(conversation.last_turn_at),
        closed_at=None if conversation.closed_at is None else utc(conversation.closed_at),
        summary=conversation.summary,
        turns=out_turns,
    )


@router.post("/{profile_id}/conversations/{conversation_id}/turns/stream")
async def turn_stream(
    conversation_id: uuid.UUID, body: AskIn, request: Request, context: Context
) -> StreamingResponse:
    """`POST /{id}/ask/stream`, on a named thread instead of the current one (W2): the same
    event contract as `ask_stream`, refused (`NoSuchConversation`) for a conversation this key
    did not start or that is not on this profile."""
    outside = providers_of(request)

    async def pump(queue: asyncio.Queue[bytes | object]) -> None:
        try:
            async with session_scope(request) as session:
                conversation = await conversation_by_id(
                    session, context=context, conversation_id=conversation_id
                )
                await _stream_turn(session, context, body, request, outside, queue, conversation)
        except Refusal as refusal:
            await queue.put(await _refusal_event(request, refusal))

    return StreamingResponse(stream_with_background_pump(pump), media_type="text/event-stream")
