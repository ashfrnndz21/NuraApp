"""Family, sharing and the helper over HTTP (E12).

    PUT  /profiles/{id}/keys/{key_id}          narrow a key: fewer parts, shorter window (yes)
    GET  /family/roles                          the six roles, their default parts and windows
    GET  /profiles/{id}/grants                  every live key as a grant, in his words
    GET  /profiles/{id}/helpers                 who holds a helper key and what she may do
    GET  /profiles/{id}/thread?cursor=          the thread, newest first, a page at a time
    POST /profiles/{id}/thread                  a message (text) or a card (card_kind)
    POST /profiles/{id}/thread/photos           a photo with its words, and the sharer's yes to his story
    GET  /profiles/{id}/thread/photos/{photo}/content   the photo itself, while it is shared
    POST /profiles/{id}/thread/photos/{photo}/take-back the sharer takes it back
    GET  /profiles/{id}/thread/digest?since=    the digest for the caller, verified
    GET  /profiles/{id}/roster                  the open slots
    POST /profiles/{id}/roster                  put someone on duty
    DELETE /profiles/{id}/roster/{slot_id}      take a slot off the roster
    GET  /profiles/{id}/roster/on-duty?at=      who is on duty at a moment
    GET  /profiles/{id}/tasks?mine=&open=       the tasks; `mine` under the footing every key holds
    POST /profiles/{id}/tasks                   give someone a task
    POST /profiles/{id}/tasks/{task_id}/done    the doer's own tap (yes)
    GET  /profiles/{id}/trail                   the trail as he reads it, by day
    GET  /profiles/{id}/privacy                 what is marked only me
    POST /profiles/{id}/privacy                 mark a part only me (owner's yes)
    POST /profiles/{id}/privacy/{scope}/lift    open it again (owner's yes)
    POST /profiles/{id}/pushes/preview          exactly what he will see
    POST /profiles/{id}/pushes                  schedule it (yes); nothing sends here
    GET  /profiles/{id}/pushes                  what is scheduled, and what became of it
    GET  /profiles/{id}/documents               the papers behind a basis, with what they back
    POST /profiles/{id}/documents               upload a PDF or a photo and tag it

Every profile route takes the key context like every other. The yeses are minted at
`POST /profiles/{id}/confirmations` with subjects `key_change`, `only_me`, `task_done` and
`push`.
"""

from __future__ import annotations

import base64
import binascii
import uuid

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import AwareDatetime

from app.channels.about_him import reader_of
from app.channels.api.deps import ClosingContext, Context, CurrentPerson, Db, providers_of
from app.channels.api.schemas import (
    DigestOut,
    DocumentIn,
    DocumentOut,
    GrantOut,
    HelperOut,
    HelpersOut,
    KeyNarrowIn,
    KeyOut,
    LiftOnlyMeIn,
    OnDutyOut,
    OnlyMeIn,
    PrivacyOut,
    PushComposeIn,
    PushIn,
    PushOut,
    PushPreviewOut,
    RolePresetOut,
    RosterSlotIn,
    RosterSlotOut,
    TaskDoneIn,
    TaskIn,
    TaskOut,
    ThreadCardIn,
    ThreadEntryOut,
    ThreadPageOut,
    ThreadPhotoIn,
    ThreadPhotoOut,
    ThreadPostIn,
    TrailDayOut,
)
from app.channels.whatsapp.group import mirror_to_group, sync_group
from app.family.documents import add_document, documents
from app.family.grants import grants, helper_list, role_presets
from app.family.photos import (
    NotAPhoto,
    photo_content,
    photos_on,
    share_photo,
    take_back_photo,
)
from app.family.privacy import lift_only_me, mark_only_me, marked
from app.family.pushes import preview_push, push_states, pushes, schedule_push
from app.family.roster import (
    add_slot,
    add_task,
    end_slot,
    mark_task_done,
    my_tasks,
    roster,
    tasks,
    who_is_on_duty,
)
from app.family.thread import digest, post_card, post_message, read_thread
from app.family.trail import trail
from app.keys.context import only_the_owner_while_closing
from app.keys.grants import narrow_key
from app.keys.scopes import Scope

router = APIRouter(tags=["family"])

# --- grants ----------------------------------------------------------------------------------


@router.put("/profiles/{profile_id}/keys/{key_id}")
async def narrow(
    key_id: uuid.UUID, body: KeyNarrowIn, request: Request, context: Context, session: Db
) -> KeyOut:
    """Narrow a live key in place, on the caller's yes for exactly this change. Wider is
    refused (`WouldWiden`, 403): that is a fresh consent and a new key. A key narrowed out of
    the family's part is a person out of the family's WhatsApp group, now (#143)."""
    narrowed = await narrow_key(
        session,
        context=context,
        key_id=key_id,
        scopes=body.scopes,
        window=body.window,
        confirmation_id=body.confirmation_id,
    )
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return KeyOut.of(narrowed)


@router.get("/family/roles")
async def roles(
    person: CurrentPerson,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    name: str = Query(default="Ash", min_length=1, max_length=120),
) -> list[RolePresetOut]:
    """The six roles as the family screen offers them, said for `name`, in `language`."""
    return [RolePresetOut.of(preset) for preset in role_presets(language, name=name)]


@router.get("/profiles/{profile_id}/grants")
async def grant_list(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> list[GrantOut]:
    """Every live key as a grant, in his words — or, on a key that is not his, about him by
    name (#210): who each holder is to him and the parts their key opens, never said to
    anyone but him as if they were hers."""
    reader = await reader_of(session, context, language)
    return [
        reader.model(GrantOut.of(grant))
        for grant in await grants(session, context=context, language=language)
    ]


@router.get("/profiles/{profile_id}/helpers")
async def helpers(
    context: Context,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> HelpersOut:
    found, lines = await helper_list(session, context=context, language=language)
    return HelpersOut(helpers=[HelperOut.of(helper) for helper in found], lines=lines)


# --- the thread ------------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/thread")
async def thread(
    context: Context,
    session: Db,
    cursor: AwareDatetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> ThreadPageOut:
    entries, next_cursor = await read_thread(session, context=context, cursor=cursor, limit=limit)
    photos = await photos_on(session, context=context, message_ids=[entry.id for entry in entries])
    return ThreadPageOut(
        entries=[ThreadEntryOut.of(entry, photos.get(entry.id)) for entry in entries],
        next_cursor=next_cursor,
    )


@router.post("/profiles/{profile_id}/thread", status_code=status.HTTP_201_CREATED)
async def post(
    body: ThreadPostIn, request: Request, context: Context, session: Db
) -> ThreadEntryOut:
    if isinstance(body, ThreadCardIn):
        return ThreadEntryOut.of(
            await post_card(session, context=context, kind=body.card_kind, task_id=body.task_id)
        )
    entry = await post_message(session, context=context, text=body.text)
    # The family's WhatsApp group mirrors the thread (E11-01): said there too, in her name.
    await mirror_to_group(
        session, context=context, provider=providers_of(request).whatsapp, message=entry
    )
    return ThreadEntryOut.of(entry)


@router.post("/profiles/{profile_id}/thread/photos", status_code=status.HTTP_201_CREATED)
async def share(
    body: ThreadPhotoIn, request: Request, context: Context, session: Db
) -> ThreadEntryOut:
    """A photo shared with the family, with the words it comes with (E12-02), and the sharer's
    own yes or no to its being one of his story cards (E21-05). The family's, under the family
    scope; never one of his papers."""
    try:
        data = base64.b64decode(body.data, validate=True)
    except (binascii.Error, ValueError) as bad:
        raise NotAPhoto("the photo is not base64") from bad
    message, photo = await share_photo(
        session,
        context=context,
        store=providers_of(request).object_store,
        data=data,
        content_type=body.content_type,
        caption=body.caption,
        on_his_feed=body.on_his_feed,
    )
    return ThreadEntryOut.of(message, photo)


@router.get("/profiles/{profile_id}/thread/photos/{photo_id}/content")
async def photo(photo_id: uuid.UUID, request: Request, context: Context, session: Db) -> Response:
    """The photo itself, while its sharer has not taken it back, under the family scope."""
    data, kind = await photo_content(
        session, context=context, store=providers_of(request).object_store, photo_id=photo_id
    )
    return Response(content=data, media_type=kind, headers={"Cache-Control": "private, no-store"})


@router.post("/profiles/{profile_id}/thread/photos/{photo_id}/take-back")
async def take_back(photo_id: uuid.UUID, context: Context, session: Db) -> ThreadPhotoOut:
    """The sharer takes the photo back: from now it is shown to nobody, in the thread or on
    his feed. Only the one who shared it may (`NotTheirsToTakeBack`, 403)."""
    return ThreadPhotoOut.of(await take_back_photo(session, context=context, photo_id=photo_id))


@router.get("/profiles/{profile_id}/thread/digest")
async def thread_digest(
    context: Context,
    session: Db,
    since: AwareDatetime,
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> DigestOut:
    """The thread and the day's cards since `since`, for the caller, in whole sentences."""
    return DigestOut.of(await digest(session, context=context, since=since, language=language))


# --- the roster and the tasks -----------------------------------------------------------------


@router.get("/profiles/{profile_id}/roster")
async def roster_list(context: Context, session: Db) -> list[RosterSlotOut]:
    return [RosterSlotOut.of(slot) for slot in await roster(session, context=context)]


@router.post("/profiles/{profile_id}/roster", status_code=status.HTTP_201_CREATED)
async def roster_add(body: RosterSlotIn, context: Context, session: Db) -> RosterSlotOut:
    return RosterSlotOut.of(
        await add_slot(
            session,
            context=context,
            person_id=body.person_id,
            role=body.role,
            weekdays=body.weekdays,
            starts_on=body.starts_on,
            ends_on=body.ends_on,
            from_time=body.from_time,
            to_time=body.to_time,
        )
    )


@router.delete("/profiles/{profile_id}/roster/{slot_id}")
async def roster_end(slot_id: uuid.UUID, context: Context, session: Db) -> RosterSlotOut:
    return RosterSlotOut.of(await end_slot(session, context=context, slot_id=slot_id))


@router.get("/profiles/{profile_id}/roster/on-duty")
async def on_duty(
    context: Context, session: Db, at: AwareDatetime | None = None
) -> list[OnDutyOut]:
    return [OnDutyOut.of(duty) for duty in await who_is_on_duty(session, context=context, at=at)]


@router.get("/profiles/{profile_id}/tasks")
async def task_list(
    context: Context,
    session: Db,
    mine: bool = Query(default=False),
    open_only: bool = Query(default=False, alias="open"),
) -> list[TaskOut]:
    """Every task (owner and chief), or with `?mine=true` the ones that name the caller,
    which any key holder reads."""
    if mine:
        found = await my_tasks(session, context=context)
        return [TaskOut.of(task) for task in found if not (open_only and task.is_done)]
    return [TaskOut.of(task) for task in await tasks(session, context=context, open_only=open_only)]


@router.post("/profiles/{profile_id}/tasks", status_code=status.HTTP_201_CREATED)
async def task_add(body: TaskIn, person: CurrentPerson, context: Context, session: Db) -> TaskOut:
    return TaskOut.of(
        await add_task(
            session,
            context=context,
            what=body.what,
            assigned_person_id=body.assigned_person_id,
            due_at=body.due_at,
            language=person.language,
        )
    )


@router.post("/profiles/{profile_id}/tasks/{task_id}/done")
async def task_done(task_id: uuid.UUID, body: TaskDoneIn, context: Context, session: Db) -> TaskOut:
    """The doer's own tap, with the yes she minted for it. Anyone else is `NotTheDoer` (403)."""
    return TaskOut.of(
        await mark_task_done(
            session, context=context, task_id=task_id, confirmation_id=body.confirmation_id
        )
    )


# --- the trail and only me ----------------------------------------------------------------------


@router.get("/profiles/{profile_id}/trail")
async def trail_days(
    context: ClosingContext,
    session: Db,
    language: str | None = Query(default=None, min_length=2, max_length=16),
    since: AwareDatetime | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[TrailDayOut]:
    """Who looked at what, in his words, by day, newest first. Owner and chief only."""
    await only_the_owner_while_closing(session, context)  # his trail stays his (#143)
    days = await trail(session, context=context, language=language, since=since, limit=limit)
    return [TrailDayOut.of(day) for day in days]


@router.get("/profiles/{profile_id}/privacy")
async def privacy_list(context: Context, session: Db) -> list[PrivacyOut]:
    return [PrivacyOut.of(row) for row in await marked(session, context=context)]


@router.post("/profiles/{profile_id}/privacy", status_code=status.HTTP_201_CREATED)
async def privacy_mark(
    body: OnlyMeIn, request: Request, context: Context, session: Db
) -> PrivacyOut:
    """The owner keeps one part to himself, on his yes. Every key stops opening it at once —
    and, the family's part kept to himself, nobody else is in the family's WhatsApp group."""
    row = await mark_only_me(
        session, context=context, scope=body.scope, confirmation_id=body.confirmation_id
    )
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return PrivacyOut.of(row)


@router.post("/profiles/{profile_id}/privacy/{scope}/lift")
async def privacy_lift(
    scope: Scope, body: LiftOnlyMeIn, request: Request, context: Context, session: Db
) -> PrivacyOut:
    row = await lift_only_me(
        session, context=context, scope=scope, confirmation_id=body.confirmation_id
    )
    await sync_group(session, context=context, provider=providers_of(request).whatsapp)
    return PrivacyOut.of(row)


# --- the push composer -----------------------------------------------------------------------


@router.post("/profiles/{profile_id}/pushes/preview")
async def push_preview(
    body: PushComposeIn, request: Request, context: Context, session: Db
) -> PushPreviewOut:
    """Exactly what he will see. A line that does not pass plain words is `NotPlainWords`
    (400) with the findings; a line naming a medicine or a dose is `MessageNamesAMedicine`
    (400), by the licensed registry's answer among others (#164)."""
    return PushPreviewOut.of(
        await preview_push(
            session,
            context=context,
            template_id=body.template_id,
            slots=body.slots,
            memo_lines=body.memo_lines,
            language=body.language,
            registry=providers_of(request).drug_registry,
        )
    )


@router.post("/profiles/{profile_id}/pushes", status_code=status.HTTP_201_CREATED)
async def push_schedule(body: PushIn, request: Request, context: Context, session: Db) -> PushOut:
    return PushOut.of(
        await schedule_push(
            session,
            context=context,
            send_at=body.send_at,
            channel=body.channel,
            expires_at=body.expires_at,
            confirmation_id=body.confirmation_id,
            template_id=body.template_id,
            slots=body.slots,
            memo_lines=body.memo_lines,
            language=body.language,
            registry=providers_of(request).drug_registry,
        )
    )


@router.get("/profiles/{profile_id}/pushes")
async def push_list(context: Context, session: Db) -> list[PushOut]:
    """What is scheduled, and what became of each: sent, still waiting, or not sent before
    its end (the delivery log's word, E11)."""
    found = await pushes(session, context=context)
    states = await push_states(session, context=context, rows=found)
    return [PushOut.of(push, states.get(push.id)) for push in found]


# --- documents -------------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/documents")
async def document_list(context: Context, session: Db) -> list[DocumentOut]:
    return [DocumentOut.of(view) for view in await documents(session, context=context)]


@router.post("/profiles/{profile_id}/documents", status_code=status.HTTP_201_CREATED)
async def document_add(
    body: DocumentIn, request: Request, context: Context, session: Db
) -> list[DocumentOut]:
    """Keep a document by reference and tag it; the answer is the document list with it in."""
    await add_document(
        session,
        context=context,
        store=providers_of(request).object_store,
        data=body.as_bytes(),
        content_type=body.content_type,
        tag=body.tag,
        captured_at=body.captured_at,
    )
    return [DocumentOut.of(view) for view in await documents(session, context=context)]
