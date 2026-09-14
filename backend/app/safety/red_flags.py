"""Red flags: the things we do not wait for.

The words come from docs/smart-nudges.md §2 and `.claude/rules/safety.md`: chest tightness,
breathlessness at rest, one-sided swelling, worst-ever headache, sudden blurring, a fall,
confusion, shaky-and-sweaty on sugar medicines, a kilo or more in two days after a heart
discharge. A tap on one of them in the feeling cloud, or a word to that effect on any
channel, comes here first — before planning, before ranking, before any cap or quiet hour —
and raises a `Flag`: a row on the profile naming the feeling and the event it was said in,
who was told, and, for the two flags that depend on a fact, whether the fact was there.

A flag that depends on a missing fact is not raised in silence and not raised loudly either:
it is written with `suppressed_because` so the caregiver sees the suppression (safety.md).
Nothing here diagnoses. The card that follows says his words back to him, that this one we
do not wait for, and who to call; it names no condition.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited, audited_read, audited_write, record_share
from app.audit.models import Action, Channel
from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.scopes import Scope
from app.memory.models import EventKind, SourceChannel, _row_of_profile, _tied_to_profile
from app.memory.semantic import current_facts
from app.state.dimensions import AFTER_DISCHARGE_WINDOW, CONTROL


class Feeling(StrEnum):
    """The words on the feeling cloud. The first nine are the red flags."""

    FALL = "fall"
    CHEST_TIGHTNESS = "chest_tightness"
    BREATHLESS_AT_REST = "breathless_at_rest"
    ONE_SIDED_SWELLING = "one_sided_swelling"
    WORST_HEADACHE = "worst_headache"
    SUDDEN_BLURRING = "sudden_blurring"
    CONFUSION = "confusion"
    SHAKY_SWEATY = "shaky_sweaty"
    WEIGHT_GAIN = "weight_gain"
    DIZZY = "dizzy"
    CRAMPS = "cramps"
    THIRSTY = "thirsty"
    TIRED = "tired"
    ACHES = "aches"
    HEADACHE = "headache"
    FINE = "fine"


RED_FLAGS: frozenset[Feeling] = frozenset(
    {
        Feeling.FALL,
        Feeling.CHEST_TIGHTNESS,
        Feeling.BREATHLESS_AT_REST,
        Feeling.ONE_SIDED_SWELLING,
        Feeling.WORST_HEADACHE,
        Feeling.SUDDEN_BLURRING,
        Feeling.CONFUSION,
        Feeling.SHAKY_SWEATY,
        Feeling.WEIGHT_GAIN,
    }
)

SUGAR_CONDITIONS = frozenset({"diabetes", "type_2_diabetes", "type2_diabetes", "blood_sugar"})
"""Subjects a clinician's control word about sugar is recorded under. Shaky-and-sweaty is a
red flag on sugar medicines; without one of these on the record it is suppressed, visibly."""

FLAG_TARGET = "red_flag"


class NotAFeeling(Refusal):
    """The feeling cloud has a fixed set of words. This was not one of them."""


class Flag(ProfileScoped, Base):
    """One red flag raised on one profile: his word, the event it was said in, who was told.

    `suppressed_because` is set when the flag depends on a fact that is not on the record
    (`SUGAR_CONDITIONS`, a discharge inside the window): the flag is written so the
    caregiver sees it was considered, and it does not reach the patient's feed as a flag.
    Escalation is the `told` list and the share lines beside it: every key holder who holds
    the emergency scope at that moment.
    """

    __tablename__ = FLAG_TARGET
    __table_args__ = (
        _row_of_profile(FLAG_TARGET),
        _tied_to_profile(FLAG_TARGET, "event_id", "event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    feeling: Mapped[Feeling] = mapped_column(enum_column(Feeling, "feeling"))
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"))
    raised_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    raised_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    told: Mapped[list[str]] = mapped_column(JSON, default=list)
    suppressed_because: Mapped[str | None] = mapped_column(String(64), default=None)


frozen(Flag)

FLAG_WINDOW = timedelta(hours=24)
"""How long a raised flag leads the feed: the same day, whatever the hour."""


def is_red(feeling: Feeling) -> bool:
    return feeling in RED_FLAGS


async def _missing_fact(
    session: AsyncSession, *, context: KeyContext, feeling: Feeling
) -> str | None:
    """For the two flags that depend on the record: what is missing, or None."""
    if feeling is Feeling.SHAKY_SWEATY:
        facts = await current_facts(session, context=context, attribute=CONTROL)
        if not any(fact.subject in SUGAR_CONDITIONS for fact in facts):
            return "no_sugar_condition_on_record"
    if feeling is Feeling.WEIGHT_GAIN:
        from app.memory.models import Event

        moment = utcnow()
        discharges = await audited_read(
            session,
            Event,
            context,
            Scope.RECORDS,
            where=(
                Event.kind == EventKind.DISCHARGE,
                Event.occurred_at > moment - AFTER_DISCHARGE_WINDOW,
            ),
        )
        if not discharges:
            return "no_recent_discharge_on_record"
    return None


@audited(Action.WRITE, Scope.EMERGENCY, FLAG_TARGET)
async def raise_flag(
    session: AsyncSession,
    *,
    context: KeyContext,
    feeling: Feeling,
    event_id: uuid.UUID,
    channel: Channel = Channel.APP,
) -> Flag:
    """Raise a red flag on the event in which the feeling was said, and tell the family.

    Runs before any ranking or cap: the caller records the SYMPTOM event, calls this, and
    only then does the feed learn of it. Everyone holding a live key with the emergency
    scope is on `told`, with a share line each. `NotAFeeling` for a word that is not red.
    """
    if not is_red(feeling):
        raise NotAFeeling(f"{feeling} is not a red flag")
    suppressed = await _missing_fact(session, context=context, feeling=feeling)
    moment = utcnow()
    told: list[str] = []
    if suppressed is None:
        for key in await list_keys(session, context=context):
            if key.is_active(moment) and Scope.EMERGENCY in key.scopes_held:
                told.append(str(key.holder_person_id))
    flag = await audited_write(
        session,
        Flag,
        context,
        Scope.EMERGENCY,
        channel=channel,
        feeling=feeling,
        event_id=event_id,
        raised_by_person_id=context.person_id,
        raised_at=moment,
        told=told,
        suppressed_because=suppressed,
    )
    for person in told:
        await record_share(
            session,
            context=context,
            scope=Scope.EMERGENCY,
            target=FLAG_TARGET,
            channel=channel,
            shared_with_person_id=uuid.UUID(person),
            target_id=flag.id,
        )
    return flag


@audited(Action.READ, Scope.EMERGENCY, FLAG_TARGET)
async def open_flags(session: AsyncSession, *, context: KeyContext) -> Sequence[Flag]:
    """The flags raised inside the window, newest first, suppressed ones included: the
    caller decides who sees which (`compose`)."""
    moment = utcnow()
    found = await audited_read(
        session,
        Flag,
        context,
        Scope.EMERGENCY,
        where=(Flag.raised_at > moment - FLAG_WINDOW,),
        order_by=(Flag.raised_at.desc(),),
    )
    return [flag for flag in found if as_utc(flag.raised_at) <= moment]


__all__ = [
    "FLAG_TARGET",
    "FLAG_WINDOW",
    "RED_FLAGS",
    "Feeling",
    "Flag",
    "NotAFeeling",
    "SourceChannel",
    "is_red",
    "open_flags",
    "raise_flag",
]
