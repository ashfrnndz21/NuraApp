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
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import RecordConsent, Sharing, grant_consent
from app.consent.texts import current_version
from app.db import Base, ProfileScoped, enum_column, unit_of_work
from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.scopes import ALL_SCOPES, Scope
from app.state.models import RenderedFromState
from app.state.service import StateView, render_from_state


@asynccontextmanager
async def refused_unit(session: AsyncSession, expect: type[Refusal]) -> AsyncIterator[None]:
    """One unit of work that ends in a refusal, run the way a channel runs a request.

    A thin wrapper over `app.db.unit_of_work`: the body must raise `expect`, the boundary
    rolls the savepoint back and replays the refused lines, and the refusal is swallowed
    here so the test can look at what is left. Anything else raised, or nothing raised, is a
    failed test.
    """
    try:
        async with unit_of_work(session):
            yield
    except expect:
        return
    raise AssertionError(f"expected {expect.__name__}, nothing was refused")


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
) -> Note:
    return await audited_write(session, Note, context, scope, scope=scope, body=body)


async def read_notes(
    session: AsyncSession,
    context: KeyContext,
    *,
    scope: Scope,
) -> Sequence[Note]:
    return await audited_read(session, Note, context, scope, where=(Note.scope == scope,))


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
) -> RenderedCard:
    return await render_from_state(
        session, RenderedCard, context, scope, state=state, scope=scope, kind=kind
    )


OPENING_CONSENT = RecordConsent(
    text_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
    language="en",
    captured_via=ConsentChannel.APP,
)
"""What every test's Pa agrees to when he opens his record: today's English words, in the app."""


async def agree_to_family_sharing(
    session: AsyncSession,
    owner: KeyContext,
    holder: Person,
    *,
    scopes: Iterable[Scope] = ALL_SCOPES,
    relationship: str | None = None,
) -> Consent:
    """The owner lets one person in, to these parts; that person's key rests on this."""
    return await grant_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_PERSON,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="en",
        sharing=Sharing(
            holder=holder, scopes=frozenset(scopes) - {Scope.PROFILE}, relationship=relationship
        ),
    )
