"""The confirm: evidence that a person said yes, not a name a caller passes.

Nothing changes a medicine, books anything or sends anything without an explicit confirm from
a person. The surface collects the yes — a tap, a spoken word — and turns it into a row here:
who said it (only ever the person asking), what it was for, when it stops being good, and on
which channel. The service that acts then consumes that row, once, and records who it named.
So a caregiver cannot confirm as the patient: a confirmation names its creator and nobody
else, a used one is spent, an old one has expired, and one made for a different act does
not fit. Every failure is refused in the same words to the person who reached, and no line
is ever written as the person who was named.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.db import Base, ProfileScoped, as_utc, enum_column, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext, holds_the_profile
from app.keys.scopes import Scope

CONFIRM_WINDOW = timedelta(minutes=10)
"""How long a yes is good for. A confirm is for the thing in front of the person now."""


class ConfirmSubject(StrEnum):
    """What a confirm is for. The scope of the act is the scope the confirm is written under."""

    FACT = "fact"
    APPOINTMENT = "appointment"
    APPOINTMENT_STATUS = "appointment_status"


SCOPE_OF: dict[ConfirmSubject, Scope] = {
    ConfirmSubject.FACT: Scope.RECORDS,
    ConfirmSubject.APPOINTMENT: Scope.VISITS,
    ConfirmSubject.APPOINTMENT_STATUS: Scope.VISITS,
}


class Confirmation(ProfileScoped, Base):
    """One yes, from one person, for one act, good for ten minutes, used once."""

    __tablename__ = "confirmation"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    subject: Mapped[ConfirmSubject] = mapped_column(enum_column(ConfirmSubject, "confirm_subject"))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    consumed_at: Mapped[datetime | None] = mapped_column(default=None)
    via_channel: Mapped[Channel] = mapped_column("channel", enum_column(Channel, "audit_channel"))


class NotAConfirmerHere(Refusal):
    """The confirm offered is not a yes from a person on this profile for this act."""


class ConfirmationSpent(Refusal):
    """This yes was already used. A confirm is used once."""


class ConfirmationExpired(Refusal):
    """This yes is too old. A confirm is for the thing in front of the person now."""


async def confirm(
    session: AsyncSession,
    context: KeyContext,
    *,
    subject: ConfirmSubject,
    subject_id: uuid.UUID | None = None,
    channel: Channel = Channel.APP,
    now: datetime | None = None,
) -> Confirmation:
    """Write down that the person asking said yes, for one act. A person confirms only as
    themselves: there is no way to name anyone else here."""
    moment = now or utcnow()
    return await audited_write(
        session,
        Confirmation,
        context,
        SCOPE_OF[subject],
        channel=channel,
        now=now,
        person_id=context.person_id,
        subject=subject,
        subject_id=subject_id,
        created_at=moment,
        expires_at=moment + CONFIRM_WINDOW,
        via_channel=channel,
    )


async def consume_confirmation(
    session: AsyncSession,
    context: KeyContext,
    confirmation_id: uuid.UUID,
    *,
    subject: ConfirmSubject,
    subject_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> Confirmation:
    """Use a yes, once: it must be on this profile, for this act, unspent, unexpired, and from
    a person who could still open the profile now. The row comes back so the act can record
    who said yes. The actor on every line is the person asking, never the person named."""
    moment = now or utcnow()
    scope = SCOPE_OF[subject]
    found = await audited_read(
        session,
        Confirmation,
        context,
        scope,
        where=(Confirmation.id == confirmation_id,),
        now=now,
    )
    if not found:
        raise NotAConfirmerHere("no such confirm on this profile for this act")
    yes = found[0]
    if yes.subject != subject or yes.subject_id != subject_id:
        raise NotAConfirmerHere("no such confirm on this profile for this act")
    if yes.consumed_at is not None:
        raise ConfirmationSpent("this confirm was already used")
    if moment >= as_utc(yes.expires_at):
        raise ConfirmationExpired("this confirm is too old")
    if not await holds_the_profile(
        session, profile_id=context.profile_id, person_id=yes.person_id, now=moment
    ):
        raise NotAConfirmerHere("no such confirm on this profile for this act")
    yes.consumed_at = moment
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope,
        target=Confirmation.__tablename__,
        target_id=yes.id,
        rows=1,
        now=now,
    )
    return yes
