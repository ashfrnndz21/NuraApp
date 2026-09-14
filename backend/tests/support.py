"""A stand-in row of profile data, so scope enforcement can be tested before there is any.

The real tables of the health graph — Artifact, Event, Fact — arrive with E00-03. `Note` is
a test-only table with the same shape: it carries `ProfileScoped` and it is reached only
through `app.audit.access`, which is how those tables will be reached — the scope check and
the audit line in the same call.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import RecordConsent, Sharing, grant_consent
from app.consent.texts import current_version
from app.db import Base, ProfileScoped, enum_column, take_keepers
from app.errors import Refusal
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.scopes import ALL_SCOPES, Scope


@asynccontextmanager
async def refused_unit(session: AsyncSession, expect: type[Refusal]) -> AsyncIterator[None]:
    """One unit of work that ends in a refusal, run the way a channel runs a request.

    The body runs inside a savepoint. It must raise `expect`; when it does, the savepoint is
    rolled back — everything the body wrote is gone — and then the keepers the trail
    registered (`app.db.keep_on_refusal`) are replayed and flushed, so the refused lines
    land anyway. Anything else raised, or nothing raised, is a failed test.
    """
    savepoint = await session.begin_nested()
    try:
        yield
    except expect:
        await savepoint.rollback()
        for keeper in take_keepers(session):
            await keeper(session)
        await session.flush()
        return
    await savepoint.commit()
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
    now: datetime | None = None,
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
        now=now,
    )
