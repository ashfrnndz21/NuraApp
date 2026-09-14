"""Writing a note and reading them back, under `Scope.NOTES` and through the audit doors."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.notes.models import NOTE_LENGTH, Note


class NotANote(Refusal):
    """A note is a line of at most 280 characters. This was empty, or longer than that."""


async def write_note(
    session: AsyncSession,
    *,
    context: KeyContext,
    text: str,
) -> Note:
    line = text.strip()
    if not line or len(line) > NOTE_LENGTH:
        raise NotANote(f"a note is a line of at most {NOTE_LENGTH} characters")
    return await audited_write(session, Note, context, Scope.NOTES, text=line, written_at=utcnow())


async def list_notes(
    session: AsyncSession, *, context: KeyContext, now: datetime | None = None
) -> Sequence[Note]:
    """Every note on the profile, oldest first."""
    found = await audited_read(session, Note, context, Scope.NOTES)
    return sorted(found, key=lambda note: as_utc(note.written_at))
