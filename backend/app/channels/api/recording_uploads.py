"""A consult recording sent in chunks as it is made (#129), over HTTP. The rules are in
`app.ingestion.chunks`.

    POST   /profiles/{id}/appointments/{appt}/recording/uploads                      open one as the microphone opens
    GET    /profiles/{id}/appointments/{appt}/recording/uploads/{upload}             how far it has come
    PUT    /profiles/{id}/appointments/{appt}/recording/uploads/{upload}/chunks/{n}  one chunk: the recorder's bytes
    POST   /profiles/{id}/appointments/{appt}/recording/uploads/{upload}/yes         the doctor said yes
    POST   /profiles/{id}/appointments/{appt}/recording/uploads/{upload}/finish      Stop: put together and kept
    DELETE /profiles/{id}/appointments/{appt}/recording/uploads/{upload}?because=    a no, or the page left

A chunk's body is its bytes, read against `MAX_CHUNK_BYTES` as it arrives (`read_capped`), inside
the guard that writes a refusal on the trail. A connection that drops mid-chunk keeps nothing of
it (`ChunkCutShort`); the phone asks `GET` where to start again and sends from there.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi import Path as PathPart
from pydantic import AwareDatetime, BaseModel, Field
from starlette.requests import ClientDisconnect

from app.audit.access import audited_guard
from app.audit.models import Action
from app.channels.api.deps import Context, Db, providers_of
from app.channels.api.schemas import ConsultOut, RecordingOut, SummaryOut
from app.channels.api.uploads import Cap, read_capped
from app.ingestion.chunks import (
    MAX_CHUNK_BYTES,
    UPLOAD,
    Because,
    ChunkCutShort,
    ChunkTooLarge,
    add_chunk,
    discard_upload,
    doctor_said_yes,
    finish_upload,
    is_open,
    open_upload,
    upload_status,
)
from app.ingestion.models import ConsultUpload
from app.keys.scopes import Scope

router = APIRouter(prefix="/profiles", tags=["visits"])

UPLOADS = "/{profile_id}/appointments/{appointment_id}/recording/uploads"


class UploadIn(BaseModel):
    content_type: str = Field(min_length=1, max_length=64)
    """The recorder's own container: audio/webm, audio/ogg or audio/mp4, with its codecs."""
    started_at: AwareDatetime
    """When the phone began listening, with its offset (ADR 0009)."""


class UploadOut(BaseModel):
    upload_id: uuid.UUID
    chunks: int
    """How many chunks the server has, in order: the number of the next one to send."""
    received_bytes: int
    """How many bytes they hold: where in the recording the next chunk starts."""
    doctor_said_yes: bool
    open: bool
    """Whether it still takes chunks: False once put together, thrown away or lapsed."""
    max_chunk_bytes: int

    @classmethod
    def of(cls, upload: ConsultUpload) -> UploadOut:
        return cls(
            upload_id=upload.id,
            chunks=upload.chunks,
            received_bytes=upload.received_bytes,
            doctor_said_yes=upload.doctor_said_yes_at is not None,
            open=is_open(upload),
            max_chunk_bytes=MAX_CHUNK_BYTES,
        )


@router.post(UPLOADS, status_code=status.HTTP_201_CREATED)
async def open_one(
    appointment_id: uuid.UUID, body: UploadIn, request: Request, context: Context, session: Db
) -> UploadOut:
    """Open an upload as the microphone opens: a key that does not change the visits is
    refused, then the gate (the RECORDING consent in force), as for the notice."""
    upload = await open_upload(
        session,
        context=context,
        appointment_id=appointment_id,
        content_type=body.content_type,
        started_at=body.started_at,
        store=providers_of(request).object_store,
    )
    return UploadOut.of(upload)


@router.get(f"{UPLOADS}/{{upload_id}}")
async def how_far(
    appointment_id: uuid.UUID, upload_id: uuid.UUID, context: Context, session: Db
) -> UploadOut:
    """How far it has come: the next chunk's number and where in the recording it starts.
    Only the person who opened it (`NotYourUpload`)."""
    return UploadOut.of(
        await upload_status(
            session, context=context, appointment_id=appointment_id, upload_id=upload_id
        )
    )


@router.put(f"{UPLOADS}/{{upload_id}}/chunks/{{position}}")
async def one_chunk(
    appointment_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    position: int = PathPart(ge=0, le=99_999),
) -> UploadOut:
    """Chunk `position`: the recorder's bytes as the body, at most `MAX_CHUNK_BYTES`, refused
    with a 413 as it arrives past that (`ChunkTooLarge`), on the trail. The next one is taken;
    one the server has, sent again the same, changes nothing; any other is `ChunkOutOfOrder`."""
    async with audited_guard(session, context, Action.WRITE, Scope.VISITS, UPLOAD):
        try:
            data = await read_capped(
                request.stream(),
                Cap(MAX_CHUNK_BYTES, ChunkTooLarge),
                declared=request.headers.get("content-length"),
            )
        except ClientDisconnect as gone:
            raise ChunkCutShort("the connection dropped before the chunk was whole") from gone
    upload = await add_chunk(
        session,
        context=context,
        appointment_id=appointment_id,
        upload_id=upload_id,
        position=position,
        data=data,
        store=providers_of(request).object_store,
    )
    return UploadOut.of(upload)


@router.post(f"{UPLOADS}/{{upload_id}}/yes")
async def the_doctor_said_yes(
    appointment_id: uuid.UUID, upload_id: uuid.UUID, context: Context, session: Db
) -> UploadOut:
    """The doctor said yes: the recording may be kept, on Stop."""
    return UploadOut.of(
        await doctor_said_yes(
            session, context=context, appointment_id=appointment_id, upload_id=upload_id
        )
    )


@router.post(f"{UPLOADS}/{{upload_id}}/finish", status_code=status.HTTP_201_CREATED)
async def finish(
    appointment_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    duration_s: float = Query(),
) -> ConsultOut:
    """Stop: the chunks put together in the region into one consult recording, heard, split
    by speaker and read into the post-visit card, as a single upload is. Only after the
    doctor's yes (`NoYesFromTheDoctor`). Sent again, it answers with what the first kept."""
    served = providers_of(request)
    done = await finish_upload(
        session,
        context=context,
        appointment_id=appointment_id,
        upload_id=upload_id,
        duration_s=duration_s,
        store=served.object_store,
        transcriber=served.transcriber,
        separator=served.speaker_separator,
        summariser=served.summariser,
        registry=served.drug_registry,
    )
    return ConsultOut(
        recording=RecordingOut.of(done.recording, list(done.segments)),
        summary=None if done.summary is None else SummaryOut.of(done.summary, done.items),
        summary_refused=done.summary_refused,
    )


@router.delete(f"{UPLOADS}/{{upload_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def throw_away(
    appointment_id: uuid.UUID,
    upload_id: uuid.UUID,
    request: Request,
    context: Context,
    session: Db,
    because: Literal["no", "left", "whole"] = Query(),
) -> Response:
    """The doctor said no, or the page was left before he answered: every chunk already sent
    is thrown away, and nothing of the visit is kept. `whole`: the phone sends the recording
    whole instead, because the server said this upload could end in no recording."""
    await discard_upload(
        session,
        context=context,
        appointment_id=appointment_id,
        upload_id=upload_id,
        because=Because(because),
        store=providers_of(request).object_store,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
