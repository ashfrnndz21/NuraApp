"""The confirm: evidence that a person said yes, not a name a caller passes.

Nothing changes a medicine, books anything or sends anything without an explicit confirm from
a person. The surface shows the person a draft (`app.drafts`) and turns the yes into a row
here: who said it (only ever the person asking), a digest of exactly what was shown, when it
stops being good, on which channel. The service that acts recomputes the digest from what it
is about to write, and uses the row once — the actor must be the person who said yes, the
digest must match, the yes must be fresh and unspent, and the person must still be able to
open the profile by the clock. Every failure is refused in the same words to the person who
reached, and no line is ever written as anyone else. The clock is `app.clock`, never an
argument: a yes cannot be minted for later or spent in the past.

Single use is atomic: the spend is `UPDATE … SET consumed_at = now WHERE id = ? AND
consumed_at IS NULL`, and anything but one row changed is a refusal. Two requests racing on
one tap both read an unspent row; only one update lands, and the other is refused. That
conditional update is the concurrency guard; there is no check-then-set.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, ForeignKey, String, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, utcnow
from app.drafts import (
    AttachDraft,
    ClaimDraft,
    CloseDraft,
    ConfirmSubject,
    CountCorrectionDraft,
    Draft,
    DriveDraft,
    FactDraft,
    KeyChangeDraft,
    OnlyMeDraft,
    OrderDraft,
    ProposalDraft,
    PushDraft,
    ReviewDraft,
    RoutineDraft,
    TaskDoneDraft,
    digest_of,
)
from app.errors import Refusal
from app.keys.context import KeyContext, holds_the_profile
from app.keys.scopes import Scope, scope_for_subject

__all__ = ["CONFIRM_WINDOW", "ConfirmSubject", "Confirmation", "confirm", "consume_confirmation"]

CONFIRM_WINDOW = timedelta(minutes=10)
"""How long a yes is good for. A confirm is for the thing in front of the person now."""


def scope_of(draft: Draft) -> Scope:
    """The scope of the act: a fact's is from its subject, a visit's is the visits scope, a
    claim's is the face of the graph — whose it is — which is all a claimant holds, and a
    review card's is the record, where the card and the photo it came from are kept (the
    facts it then writes each check their own subject's scope). A question and a post-visit
    summary hang off a visit, so theirs is the visits scope too. Narrowing a key and marking
    a part "only me" are the family list's (E12); a task's done is the doer's own footing on
    the graph, which every key holds; a message to the patient is a send. Hanging an
    artefact off an episode or a visit (E03) is an arrangement of the record, where the
    artefact is kept."""
    if isinstance(draft, CloseDraft):
        return Scope.PROFILE
    if isinstance(draft, FactDraft):
        return scope_for_subject(draft.subject)
    if isinstance(draft, ClaimDraft):
        return Scope.PROFILE
    if isinstance(draft, ReviewDraft | AttachDraft):
        return Scope.RECORDS
    if isinstance(draft, KeyChangeDraft | OnlyMeDraft | DriveDraft | OrderDraft):
        # Who drives him, and who orders more of a medicine, is a task on the family list
        # (E05-03, E04-05, E12-03).
        return Scope.FAMILY
    if isinstance(draft, TaskDoneDraft):
        return Scope.PROFILE
    if isinstance(draft, PushDraft):
        return Scope.SEND
    if isinstance(draft, CountCorrectionDraft):
        # Tablets found at home are a supply on the line: the medicines' (E04-05).
        return Scope.MEDICINES
    if isinstance(draft, RoutineDraft):
        # The day is read where the helper reads today's tablets (E10).
        return Scope.MEDICINES
    if isinstance(draft, ProposalDraft):
        # A calendar proposal becomes a visit on the spine (E18-02).
        return Scope.VISITS
    # A visit's booking, its status, a question for it and its summary are all the visits'.
    return Scope.VISITS


class Confirmation(ProfileScoped, Base):
    """One yes, from one person, for one thing, good for ten minutes, used once."""

    __tablename__ = "confirmation"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    subject: Mapped[ConfirmSubject] = mapped_column(enum_column(ConfirmSubject, "confirm_subject"))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    # sha256 of the canonical JSON of the draft the person saw (`app.drafts.digest_of`).
    content_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    consumed_at: Mapped[datetime | None] = mapped_column(default=None)
    via_channel: Mapped[Channel] = mapped_column("channel", enum_column(Channel, "audit_channel"))


# A yes takes one change: being spent. Never extended, never un-spent, never re-aimed.
frozen(Confirmation, except_for=frozenset({"consumed_at"}))


class NotAConfirmerHere(Refusal):
    """The yes offered is not from the person acting, on this profile, for this act."""


class NotWhatWasConfirmed(Refusal):
    """The yes was for something else: what is about to be written is not what was shown."""


class AlreadySpent(Refusal):
    """This yes was already used. A confirm is used once."""


class ConfirmationExpired(Refusal):
    """This yes is too old. A confirm is for the thing in front of the person now."""


async def confirm(
    session: AsyncSession,
    context: KeyContext,
    draft: Draft,
    *,
    channel: Channel = Channel.APP,
) -> Confirmation:
    """Write down that the person asking said yes to exactly this draft.

    A person confirms only as themselves: there is no way to name anyone else here. The
    row's id is not written to the trail (`name_the_row=False`), so it cannot be read back
    and spent by someone who was not shown the draft.
    """
    moment = utcnow()
    return await audited_write(
        session,
        Confirmation,
        context,
        scope_of(draft),
        channel=channel,
        name_the_row=False,
        person_id=context.person_id,
        subject=draft.confirm_subject,
        subject_id=draft.subject_id,
        content_digest=digest_of(draft),
        created_at=moment,
        expires_at=moment + CONFIRM_WINDOW,
        via_channel=channel,
    )


async def consume_confirmation(
    session: AsyncSession,
    context: KeyContext,
    confirmation_id: uuid.UUID,
    draft: Draft,
) -> Confirmation:
    """Use a yes, once, for exactly `draft` — what the service is about to write.

    On this profile, from the person acting, for this kind of act and this thing, with the
    same digest, unspent, fresh by the clock, and from a person who can still open the
    profile now. The spend is one conditional UPDATE; one row changed, or it is refused.
    """
    moment = utcnow()
    scope = scope_of(draft)
    found = await audited_read(
        session, Confirmation, context, scope, where=(Confirmation.id == confirmation_id,)
    )
    if not found:
        raise NotAConfirmerHere("no such yes on this profile for this act")
    yes = found[0]
    if yes.person_id != context.person_id:
        raise NotAConfirmerHere("no such yes on this profile for this act")
    if yes.subject != draft.confirm_subject or yes.subject_id != draft.subject_id:
        raise NotAConfirmerHere("no such yes on this profile for this act")
    if yes.content_digest != digest_of(draft):
        raise NotWhatWasConfirmed("this yes was for something else")
    if yes.consumed_at is not None:
        raise AlreadySpent("this yes was already used")
    if moment >= as_utc(yes.expires_at):
        raise ConfirmationExpired("this yes is too old")
    if not await holds_the_profile(session, profile_id=context.profile_id, person_id=yes.person_id):
        raise NotAConfirmerHere("no such yes on this profile for this act")

    spent = cast(
        CursorResult[Any],
        await session.execute(
            update(Confirmation)
            .where(Confirmation.id == yes.id, Confirmation.consumed_at.is_(None))
            .values(consumed_at=moment)
        ),
    )
    if spent.rowcount != 1:
        raise AlreadySpent("this yes was already used")
    await session.refresh(yes)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=scope,
        target=Confirmation.__tablename__,
        rows=1,
    )
    return yes
