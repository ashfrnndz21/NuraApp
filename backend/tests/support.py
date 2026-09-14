"""A stand-in row of profile data, so scope enforcement can be tested before there is any.

The real tables of the health graph — Artifact, Event, Fact — arrive with E00-03. `Note` is
a test-only table with the same shape: it carries `ProfileScoped` and it is reached only
through `scoped_select` and `scoped_new`, exactly as those tables will be.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column
from app.keys.context import KeyContext
from app.keys.repository import scoped_new, scoped_select
from app.keys.scopes import Scope


class Note(ProfileScoped, Base):
    __tablename__ = "test_note"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    body: Mapped[str] = mapped_column(String(500))


async def add_note(
    session: AsyncSession, context: KeyContext, *, scope: Scope, body: str
) -> Note:
    note = scoped_new(Note, context, scope, scope=scope, body=body)
    session.add(note)
    await session.flush()
    return note


async def read_notes(
    session: AsyncSession, context: KeyContext, *, scope: Scope
) -> Sequence[Note]:
    result = await session.scalars(scoped_select(Note, context, scope).where(Note.scope == scope))
    return result.all()
