"""Stand-in rows of profile data, so the floor of the platform can be tested above nothing.

The real tables of the health graph — Artifact, Event, Fact — arrive with E00-03. `Note` is
a test-only table with the same shape: it carries `ProfileScoped` and it is reached only
through `app.audit.access`, which is how those tables will be reached — the scope check and
the audit line in the same call.

`RenderedCard` is the same idea one layer up. The real Card and FeedItem arrive with E21;
this is a table of something shown to a person, carrying `RenderedFromState` exactly as they
will, so E00-04 can hold them to naming the State they were rendered from.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.db import Base, ProfileScoped, enum_column
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.state.models import RenderedFromState
from app.state.service import StateView, render_from_state


class Note(ProfileScoped, Base):
    __tablename__ = "test_note"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    body: Mapped[str] = mapped_column(String(500))


async def add_note(
    session: AsyncSession,
    context: KeyContext,
    *,
    scope: Scope,
    body: str,
    now: datetime | None = None,
) -> Note:
    return await audited_write(session, Note, context, scope, now=now, scope=scope, body=body)


async def read_notes(
    session: AsyncSession,
    context: KeyContext,
    *,
    scope: Scope,
    now: datetime | None = None,
) -> Sequence[Note]:
    return await audited_read(session, Note, context, scope, where=(Note.scope == scope,), now=now)


class RenderedCard(RenderedFromState, ProfileScoped, Base):
    """A stand-in for the cards of E21: something shown to a person, so it names its State."""

    __tablename__ = "test_rendered_card"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    kind: Mapped[str] = mapped_column(String(40))


async def render_card(
    session: AsyncSession,
    context: KeyContext,
    *,
    state: StateView | None = None,
    scope: Scope = Scope.READINGS,
    kind: str = "reading",
    now: datetime | None = None,
) -> RenderedCard:
    return await render_from_state(
        session, RenderedCard, context, scope, state=state, now=now, scope=scope, kind=kind
    )
