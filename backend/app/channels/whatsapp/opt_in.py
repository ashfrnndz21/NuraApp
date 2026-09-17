"""A key holder's own answers at the key-accept step (#143), about one profile.

Two questions, in words bound by version (`app.consent.opt_in_words`): may Nura message them
on WhatsApp, and will they join the family's group there, where everyone in it sees their
number. The group answer decides: nobody but the patient is put in the family's group without
their own yes, and a no takes them out at once (`app.channels.whatsapp.group`). The WhatsApp
answer is kept going forward and does not yet decide anything — Meta asks each recipient's
own opt-in before real data, and that rule is its own issue. A red-flag notice to a key
holder never waits on either.

Since #163 a no is kept to (`said_no`): nobody who answered no is sent a WhatsApp message
Nura starts — not even a red-flag notice, which reaches them by app push and on their family
page instead (`app.delivery.triggers.deliver`). A reply to a message they wrote to the number
themselves still answers them there.

Since #148, Meta's own rule: each recipient's own opt-in, not the absence of a no. `said_yes`
is the one a send checks — no answer at all is not read as a yes, the same as an explicit no,
though `newest_answer` tells the two apart so the chief can see who has not been asked yet
(`app.delivery.reach`) rather than who refused. A red-flag notice waits on neither more than
any other WhatsApp message does: someone who has not opted in reaches it by app push and on
their family page instead, exactly as someone who said no does.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_read, audited_write
from app.audit.models import Channel
from app.channels.strings import language_of
from app.consent.opt_in_words import OPT_IN_VERSION
from app.consent.service import NotTheCurrentWording
from app.db import Base, ProfileScoped, as_utc, frozen, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import _row_of_profile


class WhatsAppOptIn(ProfileScoped, Base):
    """One pair of answers, by the person they are about, for this profile. The newest
    stands; the rows are never edited, so every answer ever given is on the record."""

    __tablename__ = "whatsapp_opt_in"
    __table_args__ = (_row_of_profile("whatsapp_opt_in"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("key.id"), default=None)
    """The key the answer was given on; none for the patient's own. An answer counts only on
    its key: a key closed and cut again is asked again."""
    said_yes: Mapped[bool] = mapped_column(Boolean)
    """His answer to "Nura may message you on WhatsApp."."""
    joins_group: Mapped[bool] = mapped_column(Boolean)
    """His answer to "Do you want to join the family group on WhatsApp? Everyone in it can see your number."."""
    wording_version: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16))
    said_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(WhatsAppOptIn)


async def record_opt_in(
    session: AsyncSession,
    *,
    context: KeyContext,
    messages: bool,
    joins_group: bool,
    wording_version: str,
    language: str,
) -> WhatsAppOptIn:
    """The caller's own answers about himself, to today's words, under the face of the
    graph every key opens. Words that are not today's are refused before anything is kept."""
    if wording_version != OPT_IN_VERSION:
        raise NotTheCurrentWording(
            f"the key-accept questions are answered at version {OPT_IN_VERSION}"
        )
    return await audited_write(
        session,
        WhatsAppOptIn,
        context,
        Scope.PROFILE,
        person_id=context.person_id,
        key_id=context.key_id,
        said_yes=messages,
        joins_group=joins_group,
        wording_version=wording_version,
        language=language_of(language),
    )


async def answers_of(session: AsyncSession, *, context: KeyContext) -> WhatsAppOptIn | None:
    """The caller's own newest answers on this key, to today's words, or none before he has
    answered them. Two at the same instant: the one that says no to the group."""
    rows = await audited_read(
        session,
        WhatsAppOptIn,
        context,
        Scope.PROFILE,
        where=(
            WhatsAppOptIn.person_id == context.person_id,
            WhatsAppOptIn.wording_version == OPT_IN_VERSION,
            WhatsAppOptIn.key_id.is_(None)
            if context.key_id is None
            else WhatsAppOptIn.key_id == context.key_id,
        ),
    )
    if not rows:
        return None
    return max(rows, key=lambda row: (as_utc(row.said_at), not row.joins_group))


async def newest_answer(
    session: AsyncSession,
    *,
    context: KeyContext,
    person_id: uuid.UUID,
    channel: Channel = Channel.APP,
) -> WhatsAppOptIn | None:
    """This person's newest answer about this profile, any wording and any key: none before
    he has ever answered. Two at the same instant: the one that says no."""
    rows = await audited_read(
        session,
        WhatsAppOptIn,
        context,
        Scope.PROFILE,
        where=(WhatsAppOptIn.person_id == person_id,),
        channel=channel,
    )
    if not rows:
        return None
    return max(rows, key=lambda row: (as_utc(row.said_at), not row.said_yes))


async def said_no(
    session: AsyncSession,
    *,
    context: KeyContext,
    person_id: uuid.UUID,
    channel: Channel = Channel.APP,
) -> bool:
    """Whether this person's newest answer about this profile says no to WhatsApp messages from
    Nura (#163). Any wording and any key: a no stands until they say yes, and is never read as a
    yes because the words or the key changed since. No answer at all is not a no (#148)."""
    newest = await newest_answer(session, context=context, person_id=person_id, channel=channel)
    return newest is not None and not newest.said_yes


async def said_yes(
    session: AsyncSession,
    *,
    context: KeyContext,
    person_id: uuid.UUID,
    channel: Channel = Channel.APP,
) -> bool:
    """Whether this person's newest answer about this profile is an explicit yes to WhatsApp
    messages from Nura (#148, Meta's per-recipient opt-in). No answer at all is not read as a
    yes — the same rule a no already had (#163) — so a send needs this, not merely `not
    said_no`. Told apart from `said_no` by `newest_answer` returning None: absence is not
    refusal, and the chief is shown the two differently (`app.delivery.reach`)."""
    newest = await newest_answer(session, context=context, person_id=person_id, channel=channel)
    return newest is not None and newest.said_yes
