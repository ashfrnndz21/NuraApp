"""A consult recording sent in chunks as it is made, so a long visit survives a dropped
connection (#129).

Visit day (#128) sent the whole recording once, on Stop: a connection that dropped at Stop lost
it, and a page the phone put to sleep lost everything. Now the phone opens an upload as the
microphone opens and sends the audio in numbered chunks while it listens. A chunk that did not
arrive is sent again, from where the server says it got to, once the connection is back. On
Stop the chunks are put together here, in the region, into the one recording `record_consult`
keeps: the same bytes a single upload would have sent, so the same words heard, the same
speakers and the same clips.

#128's rules hold at every step:

- **Nothing is kept until the doctor's yes.** A chunk waits in the region's object store under
  `consult-uploads/<profile>/<upload>/<n>` and is nothing more: no artefact, no transcript, no
  card, and no route serves a chunk back. Only an upload the doctor said yes to (`POST …/yes`)
  may be finished, and finishing is `record_consult`, with the gate, the checks on the audio
  and the RECORDING consent asked again where the bytes land.
- **A no keeps nothing.** "Dr Tan said no", or the page left before he answered, throws away
  every chunk already sent (`discard_upload`). What the phone could not throw away, the server
  does (`discard_stale`, run by the trigger engine every five minutes): an upload the doctor
  did not answer within `ANSWER_WITHIN`, one not finished within `FINISH_WITHIN`, and one on a
  profile where no RECORDING consent is in force any more. A lapsed upload takes nothing more
  from the moment it lapses, before the sweep reaches it. Closing the account (#143) throws
  away every upload still open on the profile at once, and the sweep of a closing profile
  does it again for a chunk that landed as it closed.
- **In the region, under the recording's consent.** Every chunk is read against its cap as it
  arrives (`read_capped`, `MAX_CHUNK_BYTES`), asks the gate again (`may_record`) and lands in
  the region's store (`guard_region`); the whole stays under `MAX_CONSULT_BYTES`.
- **Only the family hears it.** Nothing here plays anything. The recording it ends in is heard
  through the artefact door like any consult (`OnlyTheFamilyHears`).
- **Only the phone that opened it.** The person who opened an upload is the only one who adds
  to it, says the doctor's yes on it, finishes it or throws it away (`NotYourUpload`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import and_, or_, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import active_consents
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.ingestion.consult import (
    CONSULT_CONTENT_TYPES,
    MAX_CONSULT_BYTES,
    MAX_CONSULT_SECONDS,
    ConsultTooLong,
    NotAConsultRecording,
    record_consult,
)
from app.ingestion.models import ConsultRecording, ConsultSegment, ConsultUpload
from app.ingestion.objects import ObjectStore
from app.ingestion.speakers import SpeakerSeparator
from app.ingestion.transcribe import Transcriber
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.visits.guard import may_change_visits
from app.reasoning.visits.models import SummaryItem, VisitSummary
from app.reasoning.visits.questions import require_visit
from app.reasoning.visits.summary import Summariser, summary_items
from app.regions import guard_region
from app.safety.recording import may_record

UPLOAD = ConsultUpload.__tablename__

MAX_CHUNK_BYTES = 1024 * 1024
"""One chunk, at most. The recorder's opus is about 8 kB a second; the phone sends what it has
every thirty seconds, and after a dropped connection what waited in pieces of 256 kB."""
ANSWER_WITHIN = timedelta(minutes=15)
"""The doctor answers the notice in its first seconds. An upload with no yes a quarter of an
hour after it opened was never answered: it is thrown away, as on a no."""
FINISH_WITHIN = timedelta(seconds=MAX_CONSULT_SECONDS) + timedelta(hours=1)
"""A visit is at most ninety minutes; an hour on top for the connection to come back. An upload
not finished by then is thrown away: nothing is kept that the phone did not say Stop to."""
MAX_CHUNKS = 1000
"""The most chunks one recording is sent in: ninety minutes at one every thirty seconds, with
room for the pieces a dropped connection leaves. More is refused as a visit's cap is."""
LET_GO_AGAIN = timedelta(minutes=15)
"""A chunk can land as its upload is thrown away. The sweep lets go of the chunks of an upload
thrown away in the last quarter hour once more, so none is left behind."""


class Because(StrEnum):
    """Why an upload was thrown away."""

    NO = "no"
    """The doctor said no."""
    LEFT = "left"
    """The page was left before the doctor answered."""
    NO_ANSWER = "no_answer"
    UNFINISHED = "unfinished"
    NO_CONSENT = "no_consent"
    WHOLE = "whole"
    """The phone sent the whole recording at once instead (#128's route): the server said this
    upload could end in no recording."""
    CLOSING = "closing"
    """Its owner closed his account (#143): nothing more of the visit is kept."""


FROM_THE_PHONE = frozenset({Because.NO, Because.LEFT, Because.WHOLE})
"""The reasons the phone gives. The others are the server's own."""


class NoSuchUpload(Refusal):
    """No upload by that id for this visit on this profile."""


class NotYourUpload(Refusal):
    """Only the person who opened an upload sends to it, finishes it or throws it away."""


class UploadClosed(Refusal):
    """This upload was put together, thrown away, or waited too long: nothing more joins it."""


class ChunkTooLarge(Refusal):
    """One chunk of a recording is not this big."""


class ChunkOutOfOrder(Refusal):
    """Chunks come in order: the next one is the one after the last the server has."""


class NotTheChunkSent(Refusal):
    """A chunk sent again is the same bytes as the first time."""


class ChunkCutShort(Refusal):
    """The connection dropped before the chunk was whole: nothing of it was kept."""


class NoYesFromTheDoctor(Refusal):
    """A recording is kept only after the doctor said yes."""


def chunk_key(profile_id: uuid.UUID, upload_id: uuid.UUID, position: int) -> str:
    return f"consult-uploads/{profile_id}/{upload_id}/{position:06d}"


def lapsed(upload: ConsultUpload, now: datetime) -> Because | None:
    """Why this open upload can no longer finish, by the clock alone; None while it can."""
    opened = as_utc(upload.opened_at)
    if upload.doctor_said_yes_at is None and now >= opened + ANSWER_WITHIN:
        return Because.NO_ANSWER
    if now >= opened + FINISH_WITHIN:
        return Because.UNFINISHED
    return None


def is_open(upload: ConsultUpload, now: datetime | None = None) -> bool:
    """Whether the upload still takes chunks: not put together, not thrown away, not lapsed."""
    if upload.discarded_at is not None or upload.finished_at is not None:
        return False
    return lapsed(upload, now or utcnow()) is None


async def _mine(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID, upload_id: uuid.UUID
) -> ConsultUpload:
    found = await audited_read(
        session,
        ConsultUpload,
        context,
        Scope.VISITS,
        where=(ConsultUpload.id == upload_id, ConsultUpload.appointment_id == appointment_id),
    )
    if not found:
        raise NoSuchUpload(f"no upload {upload_id} for visit {appointment_id}")
    upload = found[0]
    if upload.started_by_person_id != context.person_id:
        raise NotYourUpload("only the person who opened an upload sends to it")
    return upload


def _still_open(upload: ConsultUpload) -> None:
    if not is_open(upload):
        raise UploadClosed(f"upload {upload.id} takes nothing more")


async def _noted(
    session: AsyncSession, context: KeyContext, upload: ConsultUpload, channel: Channel
) -> None:
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.VISITS,
        target=UPLOAD,
        target_id=upload.id,
        rows=1,
        channel=channel,
    )


async def _let_go(store: ObjectStore, upload: ConsultUpload) -> None:
    # One past the count: a chunk whose bytes landed but whose count did not (its request
    # failed after the write, or it arrived as the upload closed) is let go too.
    for position in range(upload.chunks + 1):
        await store.delete(chunk_key(upload.profile_id, upload.id, position))


async def _claim(session: AsyncSession, upload: ConsultUpload, **values: object) -> bool:
    """End an upload still open, in one statement that asks that it still is: two Stops, or a
    Stop and the sweep, never both end one upload, since the second finds it ended and changes
    nothing. False when another got there first. The row is read again either way. A claim
    made by a request that then fails is undone with the rest of that request (`app.db`)."""
    claimed = cast(
        CursorResult[Any],
        await session.execute(
            update(ConsultUpload)
            .where(
                ConsultUpload.id == upload.id,
                ConsultUpload.profile_id == upload.profile_id,
                ConsultUpload.finished_at.is_(None),
                ConsultUpload.discarded_at.is_(None),
            )
            .values(**values)
        ),
    )
    await session.refresh(upload)
    return claimed.rowcount == 1


async def _throw_away(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    upload: ConsultUpload,
    because: Because,
    channel: Channel = Channel.APP,
) -> bool:
    """Every chunk of it gone from the store, and the row says so and why. Nothing else of it
    was ever kept. False, with nothing done, when a Stop or another throw ended it first."""
    if not await _claim(session, upload, discarded_at=utcnow(), discarded_because=because.value):
        return False
    await _let_go(store, upload)
    await _noted(session, context, upload, channel)
    return True


# --- the phone's calls -------------------------------------------------------------------------


@audited(Action.WRITE, Scope.VISITS, UPLOAD)
async def open_upload(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    content_type: str,
    started_at: datetime,
    store: ObjectStore,
) -> ConsultUpload:
    """An upload for this visit's recording, opened as the microphone opens: the same door
    and the same gate as the notice and the single upload, before a byte is sent."""
    may_change_visits(context)
    check = await may_record(session, context)
    guard_region(held_in=store.region, asked_from=context.region)
    kind = content_type.strip().lower().split(";", 1)[0]
    if kind not in CONSULT_CONTENT_TYPES:
        raise NotAConsultRecording(f"{content_type} is not a recorder's audio")
    visit = await require_visit(session, context=context, appointment_id=appointment_id)
    return await audited_write(
        session,
        ConsultUpload,
        context,
        Scope.VISITS,
        appointment_id=visit.appointment.id,
        consent_id=check.consent_id,
        started_by_person_id=context.person_id,
        content_type=kind,
        started_at=as_utc(started_at),
        opened_at=utcnow(),
        chunks=0,
        received_bytes=0,
    )


@audited(Action.READ, Scope.VISITS, UPLOAD)
async def upload_status(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID, upload_id: uuid.UUID
) -> ConsultUpload:
    """How far an upload has come: what the phone asks after a dropped connection."""
    return await _mine(session, context=context, appointment_id=appointment_id, upload_id=upload_id)


@audited(Action.WRITE, Scope.VISITS, UPLOAD)
async def add_chunk(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    upload_id: uuid.UUID,
    position: int,
    data: bytes,
    store: ObjectStore,
) -> ConsultUpload:
    """Chunk `position`, in the region, under the recording's consent. The next one is taken;
    one the server already has, sent again the same, changes nothing (its answer was lost)."""
    may_change_visits(context)
    await may_record(session, context)
    guard_region(held_in=store.region, asked_from=context.region)
    upload = await _mine(
        session, context=context, appointment_id=appointment_id, upload_id=upload_id
    )
    _still_open(upload)
    if not data:
        raise NotAConsultRecording("a chunk has bytes in it")
    if len(data) > MAX_CHUNK_BYTES:
        raise ChunkTooLarge(f"a chunk is at most {MAX_CHUNK_BYTES} bytes")
    if position >= MAX_CHUNKS:
        raise ConsultTooLong(f"a recording is sent in at most {MAX_CHUNKS} chunks")
    key = chunk_key(context.profile_id, upload.id, position)
    if position < upload.chunks:
        if await store.get(key) != data:
            raise NotTheChunkSent(f"chunk {position} was other bytes")
        return upload
    if position != upload.chunks:
        raise ChunkOutOfOrder(f"the next chunk is {upload.chunks}")
    if upload.received_bytes + len(data) > MAX_CONSULT_BYTES:
        raise ConsultTooLong(f"a recording is at most {MAX_CONSULT_BYTES} bytes")
    if position == 0 and not CONSULT_CONTENT_TYPES[upload.content_type](data):
        raise NotAConsultRecording(f"the bytes are not {upload.content_type}")
    await store.put(key, data)
    upload.chunks = position + 1
    upload.received_bytes = upload.received_bytes + len(data)
    await session.flush()
    return upload


@audited(Action.WRITE, Scope.VISITS, UPLOAD)
async def doctor_said_yes(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID, upload_id: uuid.UUID
) -> ConsultUpload:
    """The doctor said yes: from now on the recording may be kept, on Stop. Said twice, once."""
    may_change_visits(context)
    upload = await _mine(
        session, context=context, appointment_id=appointment_id, upload_id=upload_id
    )
    _still_open(upload)
    if upload.doctor_said_yes_at is None:
        upload.doctor_said_yes_at = utcnow()
        await session.flush()
        await _noted(session, context, upload, Channel.APP)
    return upload


@audited(Action.WRITE, Scope.VISITS, UPLOAD)
async def discard_upload(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    upload_id: uuid.UUID,
    because: Because,
    store: ObjectStore,
) -> ConsultUpload:
    """A no, or the page left before the doctor answered: every chunk already sent is thrown
    away. Thrown away twice, once; one already put together stays the recording it became."""
    upload = await _mine(
        session, context=context, appointment_id=appointment_id, upload_id=upload_id
    )
    if upload.discarded_at is not None:
        # Thrown away before: let go once more, for a chunk that landed after (the phone's
        # second DELETE, sent when a chunk on its way has landed).
        await _let_go(store, upload)
    elif upload.finished_at is None:
        await _throw_away(session, context=context, store=store, upload=upload, because=because)
    return upload


@dataclass(frozen=True, slots=True)
class Finished:
    """What an upload became: the recording kept, who spoke when, and its card."""

    recording: ConsultRecording
    segments: Sequence[ConsultSegment]
    summary: VisitSummary | None
    items: Sequence[SummaryItem]
    summary_refused: str | None


@audited(Action.WRITE, Scope.VISITS, UPLOAD)
async def finish_upload(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    upload_id: uuid.UUID,
    duration_s: float,
    store: ObjectStore,
    transcriber: Transcriber,
    separator: SpeakerSeparator | None,
    summariser: Summariser,
    registry: DrugRegistry,
) -> Finished:
    """Stop: the chunks put together, in order, into the one recording `record_consult` keeps,
    then let go. Only after the doctor's yes. Stop sent again after its answer was lost gives
    back what the first one kept."""
    may_change_visits(context)
    upload = await _mine(
        session, context=context, appointment_id=appointment_id, upload_id=upload_id
    )
    if upload.recording_id is not None:
        return await _what_it_became(session, context=context, upload=upload)
    _still_open(upload)
    if upload.doctor_said_yes_at is None:
        raise NoYesFromTheDoctor("the doctor has not said yes to this recording")
    guard_region(held_in=store.region, asked_from=context.region)
    # Claimed first: a second Stop, or the sweep, now finds it ended.
    if not await _claim(session, upload, finished_at=utcnow()):
        if upload.recording_id is not None:
            return await _what_it_became(session, context=context, upload=upload)
        raise UploadClosed(f"upload {upload.id} takes nothing more")
    pieces = [
        await store.get(chunk_key(context.profile_id, upload.id, position))
        for position in range(upload.chunks)
    ]
    data = b"".join(pieces)
    if len(data) != upload.received_bytes:
        raise NotAConsultRecording("the chunks sent are not all here")
    outcome = await record_consult(
        session,
        context=context,
        appointment_id=upload.appointment_id,
        data=data,
        content_type=upload.content_type,
        duration_s=duration_s,
        started_at=upload.started_at,
        store=store,
        transcriber=transcriber,
        separator=separator,
        summariser=summariser,
        registry=registry,
    )
    upload.recording_id = outcome.recording.id
    await session.flush()
    await _noted(session, context, upload, Channel.APP)
    await _let_go(store, upload)
    return Finished(
        recording=outcome.recording,
        segments=outcome.segments,
        summary=outcome.summary,
        items=outcome.items,
        summary_refused=outcome.summary_refused,
    )


async def _what_it_became(
    session: AsyncSession, *, context: KeyContext, upload: ConsultUpload
) -> Finished:
    found = await audited_read(
        session,
        ConsultRecording,
        context,
        Scope.VISITS,
        where=(ConsultRecording.id == upload.recording_id,),
    )
    if not found:
        raise UploadClosed(f"upload {upload.id} takes nothing more")
    recording = found[0]
    segments = await audited_read(
        session,
        ConsultSegment,
        context,
        Scope.VISITS,
        where=(ConsultSegment.recording_id == recording.id,),
    )
    cards = await audited_read(
        session,
        VisitSummary,
        context,
        Scope.VISITS,
        where=(VisitSummary.recording_artifact_id == recording.artifact_id,),
    )
    card = max(cards, key=lambda one: (as_utc(one.created_at), str(one.id))) if cards else None
    items = (
        await summary_items(session, context=context, summary_id=card.id)
        if card is not None
        else ()
    )
    return Finished(
        recording=recording,
        segments=sorted(segments, key=lambda one: one.position),
        summary=card,
        items=items,
        summary_refused=None,
    )


# --- the sweep ---------------------------------------------------------------------------------


async def discard_stale(
    session: AsyncSession,
    *,
    context: KeyContext,
    store: ObjectStore,
    channel: Channel = Channel.SYSTEM,
    closing: bool = False,
) -> list[ConsultUpload]:
    """Every open upload of this profile that can no longer finish, thrown away: no yes within
    `ANSWER_WITHIN`, not finished within `FINISH_WITHIN`, or no RECORDING consent in force on
    the profile (asked where the key reaches the agreements; the engine's does). On a closing
    account (`closing`, #143) every open upload, whatever its clock. And, once more, the
    chunks of one thrown away or put together in the last `LET_GO_AGAIN`, for a chunk that
    landed as it closed. What it threw away."""
    if not context.allows(Scope.VISITS):
        return []
    guard_region(held_in=store.region, asked_from=context.region)
    now = utcnow()
    uploads = await audited_read(
        session,
        ConsultUpload,
        context,
        Scope.VISITS,
        where=(
            or_(
                and_(ConsultUpload.finished_at.is_(None), ConsultUpload.discarded_at.is_(None)),
                ConsultUpload.discarded_at > now - LET_GO_AGAIN,
                ConsultUpload.finished_at > now - LET_GO_AGAIN,
            ),
        ),
        channel=channel,
    )
    if not uploads:
        return []
    agreed: bool | None = None
    if not closing and context.allows(Scope.FAMILY):
        agreed = any(
            row.purpose is ConsentPurpose.RECORDING
            for row in await active_consents(session, context=context)
        )
    thrown: list[ConsultUpload] = []
    for upload in uploads:
        if upload.discarded_at is not None or upload.finished_at is not None:
            await _let_go(store, upload)
            continue
        because = (
            Because.CLOSING
            if closing
            else lapsed(upload, now) or (Because.NO_CONSENT if agreed is False else None)
        )
        if because is not None and await _throw_away(
            session,
            context=context,
            store=store,
            upload=upload,
            because=because,
            channel=channel,
        ):
            thrown.append(upload)
    return thrown


__all__ = [
    "ANSWER_WITHIN",
    "FINISH_WITHIN",
    "FROM_THE_PHONE",
    "MAX_CHUNKS",
    "MAX_CHUNK_BYTES",
    "UPLOAD",
    "Because",
    "ChunkCutShort",
    "ChunkOutOfOrder",
    "ChunkTooLarge",
    "Finished",
    "NoSuchUpload",
    "NoYesFromTheDoctor",
    "NotTheChunkSent",
    "NotYourUpload",
    "UploadClosed",
    "add_chunk",
    "chunk_key",
    "discard_stale",
    "discard_upload",
    "doctor_said_yes",
    "finish_upload",
    "is_open",
    "open_upload",
    "upload_status",
]
