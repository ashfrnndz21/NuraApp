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

The words themselves are a table too (`RED_FLAG_WORDS`, `detect`): the same nine flags heard in
free text on WhatsApp (E19-05), in the three languages a family here writes in. `Escalation`
is the ladder written beside a flag raised there — the owner, then the chief keys, then every
other live key, in calling order — for E11 to walk; `roster_for` reads it off the keys table.

The not-feeling-well button and the symptom log (E13/E14) hear the same words (`detect`) and
raise the same flag, on the SYMPTOM event `record_the_moment` writes under the emergency scope.
Their flag is written through `write_flag_kept`: `raise_flag`, and a keeper on the session
(`app.db.keep_on_refusal`, the mechanism refused audit lines use) that writes the flag, the
event it rests on and their lines on the trail again if something later in the same request
is refused and the unit of work is rolled back. "This one we do not wait for" has to survive
a template that fails, a State that is stale, or a door that refuses further on; `keep_row`
does the same for the notices and the ladder written beside the flag.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited, audited_read, audited_write, record_share
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, keep_on_refusal, utcnow
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.memory.models import (
    Event,
    EventKind,
    SourceChannel,
    _row_of_profile,
    _tied_to_profile,
)
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

RED_FLAG_WORDS: Mapping[Feeling, tuple[str, ...]] = {
    Feeling.CHEST_TIGHTNESS: (
        r"chest (?:is )?(?:tight|pain|hurt|hurts|pressure)",
        r"tight(?:ness)? in (?:his|her|my|the) chest",
        r"sakit dada",
        r"dada (?:saya |dia )?(?:sakit|sesak|ketat|berat)",
        r"胸[口]?(?:痛|闷|紧)",
        r"pain in (?:his|her|my|the) chest",
        r"heart pain",
        r"心口(?:痛|闷)",
    ),
    Feeling.BREATHLESS_AT_REST: (
        r"breathless",
        r"cannot breathe",
        r"can'?t breathe",
        r"short of breath",
        r"hard to breathe",
        r"sesak nafas",
        r"susah bernafas",
        r"(?:喘不过气|呼吸困难|气喘)",
        r"tak boleh bernafas",
        r"\bsemput\b",
        r"透不过气",
    ),
    Feeling.ONE_SIDED_SWELLING: (
        r"one (?:leg|arm|foot|side) (?:is )?swollen",
        r"swollen on one side",
        r"(?:left|right) (?:leg|foot|arm) (?:is )?(?:swollen|swelling)",
        r"(?:kaki|tangan) (?:sebelah|kiri|kanan) bengkak",
        r"(?:一边|一只)(?:腿|脚|手)肿",
        r"sebelah (?:kaki|tangan) bengkak",
        r"bengkak sebelah",
    ),
    Feeling.WORST_HEADACHE: (
        r"worst headache",
        r"headache (?:ever|like never)",
        r"sakit kepala (?:teruk|paling)",
        r"(?:头痛得?|头很痛)(?:厉害|从来没有|最)",
    ),
    Feeling.SUDDEN_BLURRING: (
        r"suddenly (?:blur|blurry|cannot see|can'?t see)",
        r"(?:blur|blurry|blurred) (?:vision|eyes?|eyesight)",
        r"cannot see (?:properly|well|suddenly)",
        r"mata (?:kabur|tiba-tiba kabur)",
        r"tiba-tiba (?:kabur|tak nampak)",
        r"(?:突然|忽然)?(?:看不清|眼睛模糊|视线模糊)",
        r"kabur tiba-tiba",
    ),
    Feeling.FALL: (
        r"\bfell\b",
        r"\bfall(?:en|s)?\b",
        r"\bfalling\b",
        r"\bjatuh\b",
        r"terjatuh",
        r"(?:跌倒|摔倒|摔了|跌了|摔跤)",
        r"\btergolek\b",
    ),
    Feeling.CONFUSION: (
        r"\bconfused\b",
        r"not making sense",
        r"does ?n[o']t (?:recognise|recognize|know) (?:me|us|anyone)",
        r"\bkeliru\b",
        r"tak (?:kenal|ingat) (?:kami|saya|orang)",
        r"(?:糊涂|认不出|说话不清|神志不清)",
        r"\bconfusion\b",
        r"(?:don'?t|do not) know where (?:i|he|she) (?:am|is)",
        r"\bkebingungan\b",
    ),
    Feeling.SHAKY_SWEATY: (
        r"shak(?:y|ing) and sweat(?:y|ing)",
        r"sweat(?:y|ing) and shak(?:y|ing)",
        r"trembling and sweating",
        r"menggigil dan berpeluh",
        r"berpeluh dan menggigil",
        r"(?:发抖|手抖).{0,4}(?:出汗|冒汗)|(?:出汗|冒汗).{0,4}(?:发抖|手抖)",
    ),
}
"""The rule's words, matched anywhere in a message, case-insensitively. Whole words for the
short English ones, so that "fell" is a fall and "fellow" is not."""

_PATTERNS: tuple[tuple[Feeling, re.Pattern[str]], ...] = tuple(
    (rule, re.compile(pattern, re.IGNORECASE))
    for rule, patterns in RED_FLAG_WORDS.items()
    for pattern in patterns
)


def detect(text: str | None) -> Feeling | None:
    """The first red flag the words of a message match, or None: the same `Feeling` a tap on
    the cloud raises, heard in free text on WhatsApp (E19-05). The weight rule is a fact, not a
    word, so it is not in the table."""
    if not text:
        return None
    for rule, pattern in _PATTERNS:
        if pattern.search(text):
            return rule
    return None


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


class Escalation(ProfileScoped, Base):
    """Who is told about a flag, in what order, and who has been told so far.

    `roster` is a list of `{"person_id", "standing"}` in calling order: the owner, then the
    chief keys, then every other live key, the poster left out (they know). `told` is the
    person ids that have had the in-thread word. Person ids only; no names, no words.
    """

    __tablename__ = "safety_escalation"
    __table_args__ = (
        _row_of_profile("safety_escalation"),
        _tied_to_profile("safety_escalation", "flag_id", FLAG_TARGET),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("red_flag.id"), index=True)
    roster: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    told: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(Flag)
frozen(Escalation)

FLAG_WINDOW = timedelta(hours=24)
"""How long a raised flag leads the feed: the same day, whatever the hour."""


def is_red(feeling: Feeling) -> bool:
    return feeling in RED_FLAGS


async def _missing_fact(
    session: AsyncSession, *, context: KeyContext, feeling: Feeling
) -> str | None:
    """For the two flags that depend on the record: what is missing, or None."""
    if not context.allows(Scope.RECORDS):
        # The fact is the record's and this key does not open it (a helper, a neighbour): to
        # this key it is missing, so the flag is written suppressed and named rather than
        # refused, and the caregiver sees it was considered (safety.md).
        if feeling is Feeling.SHAKY_SWEATY:
            return "no_sugar_condition_on_record"
        if feeling is Feeling.WEIGHT_GAIN:
            return "no_recent_discharge_on_record"
        return None
    if feeling is Feeling.SHAKY_SWEATY:
        facts = await current_facts(session, context=context, attribute=CONTROL)
        if not any(fact.subject in SUGAR_CONDITIONS for fact in facts):
            return "no_sugar_condition_on_record"
    if feeling is Feeling.WEIGHT_GAIN:
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


async def _live_keys(session: AsyncSession, *, context: KeyContext) -> Sequence[Key]:
    """Every key on the profile: through the family door when the raiser holds it (the owner,
    a chief), and read off the table otherwise — the way `roster_for` and
    `app.keys.context.holds_the_profile` do — so that a helper who saw him fall can raise the
    flag that tells the family. Person ids only; the off-table read is written down."""
    if context.allows(Scope.FAMILY):
        return await list_keys(session, context=context)
    keys = list(await session.scalars(select(Key).where(Key.profile_id == context.profile_id)))
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.EMERGENCY,
        target=Key.__tablename__,
        rows=len(keys),
        channel=Channel.SYSTEM,
    )
    return keys


@audited(Action.WRITE, Scope.EMERGENCY, FLAG_TARGET)
async def record_the_moment(
    session: AsyncSession,
    *,
    context: KeyContext,
    feeling: Feeling,
    occurred_at: datetime,
    source_channel: SourceChannel,
    channel: Channel = Channel.APP,
) -> Event:
    """The SYMPTOM event a flag heard in free text rests on, written under the emergency scope.

    `raise_flag` needs an event, and `record_event` writes one under the record's scope. A
    helper's key holds the emergency scope and not the record (`ROLE_SCOPES`), and a helper
    who saw him fall is the one whose word must start the ladder — so the moment is written
    here, behind the same door as the flag: a key without the emergency scope is refused at
    it, by name, before anything is written. The event is a moment and the flag's word, no
    content; what was said is the message artefact, kept under the same scope.
    """
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.EMERGENCY,
        channel=channel,
    )
    return await audited_write(
        session,
        Event,
        context,
        Scope.EMERGENCY,
        channel=channel,
        kind=EventKind.SYMPTOM,
        occurred_at=occurred_at,
        source_channel=source_channel,
        label=feeling.value,
        recorded_at=utcnow(),
    )


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
        for key in await _live_keys(session, context=context):
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


async def roster_for(
    session: AsyncSession, *, context: KeyContext, channel: Channel = Channel.WHATSAPP
) -> list[dict[str, str]]:
    """The calling order for this profile: owner, chief keys, other live keys; the poster out.

    The keys table is read here directly, the way `app.keys.context.holds_the_profile`
    reads it: this is a yes-or-no about who is *named* on the profile, never a read of what
    the graph holds, and the escalation must not depend on the poster's key covering the
    family list — a helper who sees him fall is the one whose word starts the ladder. The
    read is still written down, as a system read of the key table on this profile.
    """
    moment = utcnow()
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # the context was resolved from this row
    keys = list(
        await session.scalars(
            select(Key).where(Key.profile_id == context.profile_id).order_by(Key.granted_at)
        )
    )
    live = [key for key in keys if key.is_active(moment)]
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.EMERGENCY,
        target=Key.__tablename__,
        rows=len(live),
        channel=Channel.SYSTEM,
    )
    order: list[dict[str, str]] = []
    seen: set[uuid.UUID] = {context.person_id}
    if profile.owner_person_id is not None and profile.owner_person_id not in seen:
        order.append({"person_id": str(profile.owner_person_id), "standing": "owner"})
        seen.add(profile.owner_person_id)
    for role in (KeyRole.CHIEF, None):
        for key in live:
            if key.holder_person_id in seen:
                continue
            if role is not None and key.role is not role:
                continue
            if role is None and key.role is KeyRole.CHIEF:
                continue
            order.append(
                {
                    "person_id": str(key.holder_person_id),
                    "standing": "chief" if key.role is KeyRole.CHIEF else key.role.value,
                }
            )
            seen.add(key.holder_person_id)
    return order


async def escalate(
    session: AsyncSession,
    *,
    context: KeyContext,
    flag: Flag,
    roster: Sequence[Mapping[str, str]],
    told: Sequence[uuid.UUID],
    channel: Channel = Channel.WHATSAPP,
) -> Escalation:
    """Write down the ladder for this flag and who has had the word so far."""
    return await audited_write(
        session,
        Escalation,
        context,
        Scope.EMERGENCY,
        channel=channel,
        flag_id=flag.id,
        roster=[dict(step) for step in roster],
        told=[str(person_id) for person_id in told],
        created_at=utcnow(),
    )


# --- a flag that stays written (E13/E14) ------------------------------------------------------

FLAG_SCOPE = Scope.EMERGENCY
"""The door a flag is written through: the one every role holds, because the person who hears
the words — a helper, a neighbour — must be able to raise the flag whoever he is."""


def _columns(row: Any) -> dict[str, Any]:
    """The column values of a row, for writing the same row again after a rollback."""
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


async def write_flag_kept(
    session: AsyncSession,
    context: KeyContext,
    *,
    feeling: Feeling,
    event: Event,
    channel: Channel = Channel.APP,
) -> Flag:
    """Raise the flag on the SYMPTOM event it was said in (`raise_flag`), and keep it.

    A keeper is registered on the session (`app.db.keep_on_refusal`): if the unit of work this
    flag was written in is rolled back on a later refusal, the channel replays the keeper,
    which writes the event the flag rests on and the flag again — the same ids, the same
    moment — with their WRITE lines and a share line for each person on `told`. On success
    the keeper is dropped: the rows are already there.
    """
    flag = await raise_flag(
        session, context=context, feeling=feeling, event_id=event.id, channel=channel
    )
    event_values = _columns(event)
    flag_values = _columns(flag)

    async def keep(again: AsyncSession) -> None:
        if await again.get(Event, event_values["id"]) is None:
            again.add(Event(**event_values))
            await again.flush()
            await record(
                again,
                context=context,
                action=Action.WRITE,
                scope=FLAG_SCOPE,
                target=Event.__tablename__,
                target_id=event_values["id"],
                rows=1,
                channel=channel,
            )
        if await again.get(Flag, flag_values["id"]) is None:
            again.add(Flag(**flag_values))
            await again.flush()
            await record(
                again,
                context=context,
                action=Action.WRITE,
                scope=FLAG_SCOPE,
                target=FLAG_TARGET,
                target_id=flag_values["id"],
                rows=1,
                channel=channel,
            )
            for person in flag_values["told"]:
                await record_share(
                    again,
                    context=context,
                    scope=Scope.EMERGENCY,
                    target=FLAG_TARGET,
                    channel=channel,
                    shared_with_person_id=uuid.UUID(person),
                    target_id=flag_values["id"],
                )

    keep_on_refusal(session, keep)
    return flag


def keep_row(session: AsyncSession, context: KeyContext, row: Any, *, scope: Scope) -> None:
    """Keep one already-written row the way `write_flag_kept` keeps the flag: written again,
    with its WRITE line, if the unit it was written in is rolled back. For the notices and
    the ladder that go with a flag."""
    values = _columns(row)
    model = type(row)

    async def keep(again: AsyncSession) -> None:
        if await again.get(model, values["id"]) is None:
            again.add(model(**values))
            await again.flush()
            await record(
                again,
                context=context,
                action=Action.WRITE,
                scope=scope,
                target=model.__tablename__,
                target_id=values["id"],
                rows=1,
            )

    keep_on_refusal(session, keep)


__all__ = [
    "FLAG_SCOPE",
    "FLAG_TARGET",
    "FLAG_WINDOW",
    "RED_FLAGS",
    "RED_FLAG_WORDS",
    "Escalation",
    "Feeling",
    "Flag",
    "NotAFeeling",
    "SourceChannel",
    "detect",
    "escalate",
    "is_red",
    "keep_row",
    "open_flags",
    "raise_flag",
    "record_the_moment",
    "roster_for",
    "write_flag_kept",
]
