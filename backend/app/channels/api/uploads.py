"""Every upload is read against its cap as it arrives, never after (#133).

A body that does not say how long it is — chunked, no Content-Length — used to be read whole
before its size was checked, so a client could make the server hold as much as it liked.
`read_capped` is the one reader every upload goes through: it refuses at once when the body
declares more than the cap, counts the bytes as they come, and refuses with the route's own
413 the moment the count passes the cap. What it has read waits in a spooled temporary file
(in memory up to `SPOOL_IN_MEMORY`, then on the disk of the process, which runs in the
region it serves), and a refused upload's spool is closed and gone: nothing of it is kept.

The consult recording's body is its bytes, so the route reads it with `read_capped` itself,
inside the guard that writes the refusal on the trail. The other uploads are JSON with the
bytes in base64, and FastAPI reads a JSON body whole before the route or any dependency
runs; so `UploadCaps`, an ASGI layer in front of the app, reads those bodies with the same
helper against a cap sized for the base64 of the route's limit (`base64_body`), and hands
the route the body it read. The route's own check on the decoded bytes still runs after it.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from starlette.requests import ClientDisconnect, Request
from starlette.types import ASGIApp, Message, Receive, Send
from starlette.types import Scope as AsgiScope

from app.channels.api.refusals import refused
from app.errors import Refusal
from app.family.documents import DocumentTooLarge
from app.ingestion import notes, voice
from app.ingestion.connectors.calendar import MAX_ICS_BYTES, CalendarTooLarge
from app.ingestion.documents import MAX_PDF_BYTES, PdfTooLarge
from app.ingestion.notes import NoteTooLarge
from app.ingestion.photos import MAX_PHOTO_BYTES, PhotoTooLarge
from app.ingestion.voice import VoiceNoteTooLong
from app.reasoning.visits.summary import MAX_TRANSCRIPT_BYTES, TranscriptTooLarge

SPOOL_IN_MEMORY = 1024 * 1024
"""How much of an upload waits in memory before the rest goes to a temporary file."""
JSON_ROOM = 64 * 1024
"""Room in a JSON upload for everything beside the bytes: the type, the time, a label."""


@dataclass(frozen=True, slots=True)
class Cap:
    """The most one route takes over the wire, and the refusal it answers with past it."""

    limit: int
    refusal: type[Refusal]

    def refused(self) -> Refusal:
        return self.refusal(f"an upload here is at most {self.limit} bytes")


def base64_body(decoded: int) -> int:
    """The largest JSON body that can carry `decoded` bytes as base64, with `JSON_ROOM`."""
    return 4 * -(-decoded // 3) + JSON_ROOM


async def read_capped(
    chunks: AsyncIterator[bytes], cap: Cap, *, declared: str | None = None
) -> bytes:
    """The whole body, read against `cap` as it arrives; the route's refusal past it.

    A body declared longer than the cap is refused before a byte is read. Otherwise each
    chunk is counted before it is kept, and the first one that takes the count past the cap
    is refused and the spool thrown away with everything before it."""
    if declared is not None and declared.isdigit() and int(declared) > cap.limit:
        raise cap.refused()
    count = 0
    with tempfile.SpooledTemporaryFile(max_size=SPOOL_IN_MEMORY) as spool:
        async for chunk in chunks:
            count += len(chunk)
            if count > cap.limit:
                raise cap.refused()
            spool.write(chunk)
        spool.seek(0)
        return spool.read()


_PROFILE = r"/profiles/[^/]+"

JSON_UPLOADS: tuple[tuple[str, Cap], ...] = (
    (rf"{_PROFILE}/photos", Cap(base64_body(MAX_PHOTO_BYTES), PhotoTooLarge)),
    (rf"{_PROFILE}/photos/stream", Cap(base64_body(MAX_PHOTO_BYTES), PhotoTooLarge)),
    (rf"{_PROFILE}/readings/photo", Cap(base64_body(MAX_PHOTO_BYTES), PhotoTooLarge)),
    (rf"{_PROFILE}/biography/papers", Cap(base64_body(MAX_PHOTO_BYTES), PhotoTooLarge)),
    (rf"{_PROFILE}/imports", Cap(base64_body(MAX_PDF_BYTES), PdfTooLarge)),
    (rf"{_PROFILE}/imports/stream", Cap(base64_body(MAX_PDF_BYTES), PdfTooLarge)),
    (rf"{_PROFILE}/events/[^/]+/notes", Cap(base64_body(notes.MAX_VOICE_BYTES), NoteTooLarge)),
    (rf"{_PROFILE}/documents", Cap(base64_body(MAX_PHOTO_BYTES), DocumentTooLarge)),
    (rf"{_PROFILE}/thread/photos", Cap(base64_body(MAX_PHOTO_BYTES), PhotoTooLarge)),
    (rf"{_PROFILE}/not-feeling-well", Cap(base64_body(voice.MAX_VOICE_BYTES), VoiceNoteTooLong)),
    (
        rf"{_PROFILE}/not-feeling-well/stream",
        Cap(base64_body(voice.MAX_VOICE_BYTES), VoiceNoteTooLong),
    ),
    (rf"{_PROFILE}/symptoms", Cap(base64_body(voice.MAX_VOICE_BYTES), VoiceNoteTooLong)),
    (
        rf"{_PROFILE}/appointments/[^/]+/transcript",
        Cap(base64_body(MAX_TRANSCRIPT_BYTES), TranscriptTooLarge),
    ),
    (rf"{_PROFILE}/connectors/[^/]+/scan", Cap(base64_body(MAX_ICS_BYTES), CalendarTooLarge)),
)
"""Every route that takes bytes as base64 in a JSON body, and its cap. A test holds this to
the routes: a new one whose body carries bytes is refused a place in the app without a line
here (`tests/test_upload_cap.py`)."""


def cap_for(method: str, path: str, prefixes: Sequence[str] = ("",)) -> Cap | None:
    """The cap on this call's body, if it is a JSON upload; None for anything else."""
    if method != "POST":
        return None
    for prefix in prefixes:
        if prefix and not path.startswith(prefix + "/"):
            continue
        rest = path[len(prefix) :]
        for pattern, cap in JSON_UPLOADS:
            if re.fullmatch(pattern, rest):
                return cap
    return None


async def _body(receive: Receive) -> AsyncIterator[bytes]:
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            raise ClientDisconnect()
        yield message.get("body", b"")
        if not message.get("more_body", False):
            return


class UploadCaps:
    """Reads a JSON upload's body with `read_capped` before the app sees it, and answers the
    route's 413 itself when it is over; every other call passes through untouched."""

    def __init__(self, app: ASGIApp, prefixes: Sequence[str] = ("",)) -> None:
        self.app = app
        self.prefixes = tuple(prefixes)

    async def __call__(self, scope: AsgiScope, receive: Receive, send: Send) -> None:
        cap = (
            cap_for(scope["method"], scope["path"], self.prefixes)
            if scope["type"] == "http"
            else None
        )
        if cap is None:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        try:
            body = await read_capped(
                _body(receive), cap, declared=None if declared is None else declared.decode()
            )
        except ClientDisconnect:
            return
        except Refusal as refusal:
            response = await refused(Request(scope), refusal)
            await response(scope, receive, send)
            return
        handed = False

        async def replay() -> Message:
            nonlocal handed
            if not handed:
                handed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
