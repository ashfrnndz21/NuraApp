"""A person's own yes or no to Nura messaging them on WhatsApp about a profile (#143).

Recorded from the step where someone accepts the key a patient cut for them ("Nura may message
you on WhatsApp"). It is kept going forward and does not yet decide anything: Meta asks each
recipient's own opt-in before real data, and that rule is its own issue. A red-flag notice to
a key holder never waits on it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_write
from app.db import Base, ProfileScoped, frozen, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import _row_of_profile


class WhatsAppOptIn(ProfileScoped, Base):
    """One answer, by the person it is about, for this profile. The newest one stands."""

    __tablename__ = "whatsapp_opt_in"
    __table_args__ = (_row_of_profile("whatsapp_opt_in"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    said_yes: Mapped[bool] = mapped_column(Boolean)
    said_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(WhatsAppOptIn)


async def record_opt_in(
    session: AsyncSession, *, context: KeyContext, said_yes: bool
) -> WhatsAppOptIn:
    """The caller's own answer about himself, under the face of the graph every key opens."""
    return await audited_write(
        session, WhatsAppOptIn, context, Scope.PROFILE, person_id=context.person_id, said_yes=said_yes
    )
