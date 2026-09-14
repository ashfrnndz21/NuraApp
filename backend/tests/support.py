"""A stand-in row of profile data, so scope enforcement can be tested before there is any.

The real tables of the health graph — Artifact, Event, Fact — arrive with E00-03. `Note` is
a test-only table with the same shape: it carries `ProfileScoped` and it is reached only
through `app.audit.access`, which is how those tables will be reached — the scope check and
the audit line in the same call.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import RecordConsent, grant_consent
from app.consent.texts import current_version
from app.db import Base, ProfileScoped, enum_column
from app.keys.context import KeyContext
from app.keys.scopes import Scope


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
    session: AsyncSession, owner: KeyContext, *, now: datetime | None = None
) -> Consent:
    """The owner's consent to sharing with family, which every key cut on his graph rests on."""
    return await grant_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_FAMILY,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        now=now,
    )
