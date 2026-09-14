"""Red flags: the words that skip the queue (E19-05, `.claude/rules/safety.md`).

    Red flags (chest tightness, breathlessness at rest, one-sided swelling, worst-ever
    headache, sudden blurring, a fall, confusion, shaky-and-sweaty on sugar medicines,
    1 kg or more in two days after a heart discharge) bypass planning and ranking:
    escalate immediately.

`RED_FLAG_WORDS` is that sentence as a word table, in the three languages a family here
writes in; `detect` reads a message against it and names the rule that matched, or none.
Nothing here judges a number: the weight rule depends on two facts and a discharge and is
reasoning's to compute, not a word to spot, so it is not in the table. `raise_flag` writes
the `Flag` — before anything else that message does — and `escalate` writes the
`Escalation` naming the roster in order: the owner, then the chief keys, then everyone
else holding a key. The roster itself (who is called first, quiet hours, the panel
hospital) is E11/E12; here it is the order the keys table gives.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import KeyRole, Scope
from app.memory.models import SourceChannel, _row_of_profile, _tied_to_profile


class RedFlag(StrEnum):
    CHEST_TIGHTNESS = "chest_tightness"
    BREATHLESS_AT_REST = "breathless_at_rest"
    ONE_SIDED_SWELLING = "one_sided_swelling"
    WORST_HEADACHE = "worst_headache"
    SUDDEN_BLURRING = "sudden_blurring"
    FALL = "fall"
    CONFUSION = "confusion"
    SHAKY_AND_SWEATY = "shaky_and_sweaty"


RED_FLAG_WORDS: Mapping[RedFlag, tuple[str, ...]] = {
    RedFlag.CHEST_TIGHTNESS: (
        r"chest (?:is )?(?:tight|pain|hurt|hurts|pressure)",
        r"tight(?:ness)? in (?:his|her|my|the) chest",
        r"sakit dada",
        r"dada (?:sakit|sesak|ketat)",
        r"胸[口]?(?:痛|闷|紧)",
    ),
    RedFlag.BREATHLESS_AT_REST: (
        r"breathless",
        r"cannot breathe",
        r"can'?t breathe",
        r"short of breath",
        r"hard to breathe",
        r"sesak nafas",
        r"susah bernafas",
        r"(?:喘不过气|呼吸困难|气喘)",
    ),
    RedFlag.ONE_SIDED_SWELLING: (
        r"one (?:leg|arm|foot|side) (?:is )?swollen",
        r"swollen on one side",
        r"(?:left|right) (?:leg|foot|arm) (?:is )?(?:swollen|swelling)",
        r"(?:kaki|tangan) (?:sebelah|kiri|kanan) bengkak",
        r"(?:一边|一只)(?:腿|脚|手)肿",
    ),
    RedFlag.WORST_HEADACHE: (
        r"worst headache",
        r"headache (?:ever|like never)",
        r"sakit kepala (?:teruk|paling)",
        r"(?:头痛得?|头很痛)(?:厉害|从来没有|最)",
    ),
    RedFlag.SUDDEN_BLURRING: (
        r"suddenly (?:blur|blurry|cannot see|can'?t see)",
        r"(?:blur|blurry|blurred) (?:vision|eyes?|eyesight)",
        r"cannot see (?:properly|well|suddenly)",
        r"mata (?:kabur|tiba-tiba kabur)",
        r"tiba-tiba (?:kabur|tak nampak)",
        r"(?:突然|忽然)?(?:看不清|眼睛模糊|视线模糊)",
    ),
    RedFlag.FALL: (
        r"\bfell\b",
        r"\bfall(?:en|s)?\b",
        r"\bfalling\b",
        r"\bjatuh\b",
        r"terjatuh",
        r"(?:跌倒|摔倒|摔了|跌了|摔跤)",
    ),
    RedFlag.CONFUSION: (
        r"\bconfused\b",
        r"not making sense",
        r"does ?n[o']t (?:recognise|recognize|know) (?:me|us|anyone)",
        r"\bkeliru\b",
        r"tak (?:kenal|ingat) (?:kami|saya|orang)",
        r"(?:糊涂|认不出|说话不清|神志不清)",
    ),
    RedFlag.SHAKY_AND_SWEATY: (
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

_PATTERNS: tuple[tuple[RedFlag, re.Pattern[str]], ...] = tuple(
    (rule, re.compile(pattern, re.IGNORECASE))
    for rule, patterns in RED_FLAG_WORDS.items()
    for pattern in patterns
)


def detect(text: str | None) -> RedFlag | None:
    """The first red-flag rule the words of a message match, or None."""
    if not text:
        return None
    for rule, pattern in _PATTERNS:
        if pattern.search(text):
            return rule
    return None


class Flag(ProfileScoped, Base):
    """A red flag raised on this profile: which rule, by whose words, when, from where.

    Written before anything else the message does, so a refusal further along cannot take
    it down. Carries no words: the message that raised it is an artefact the thread names.
    """

    __tablename__ = "safety_flag"
    __table_args__ = (_row_of_profile("safety_flag"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rule: Mapped[RedFlag] = mapped_column(enum_column(RedFlag, "red_flag_rule"))
    raised_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    raised_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    source_channel: Mapped[SourceChannel] = mapped_column(
        enum_column(SourceChannel, "source_channel")
    )


class Escalation(ProfileScoped, Base):
    """Who is told about a flag, in what order, and who has been told so far.

    `roster` is a list of `{"person_id", "standing"}` in calling order: the owner, then the
    chief keys, then every other live key, the poster left out (they know). `told` is the
    person ids that have had the in-thread word. Person ids only; no names, no words.
    """

    __tablename__ = "safety_escalation"
    __table_args__ = (
        _row_of_profile("safety_escalation"),
        _tied_to_profile("safety_escalation", "flag_id", "safety_flag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("safety_flag.id"), index=True)
    roster: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    told: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


frozen(Flag)
frozen(Escalation)


async def raise_flag(
    session: AsyncSession,
    *,
    context: KeyContext,
    rule: RedFlag,
    source_channel: SourceChannel,
    channel: Channel = Channel.WHATSAPP,
) -> Flag:
    """Write the flag, first. Under the emergency scope, which every role but a clinic holds:
    a red flag posted by anyone on the family list lands."""
    return await audited_write(
        session,
        Flag,
        context,
        Scope.EMERGENCY,
        channel=channel,
        rule=rule,
        raised_by_person_id=context.person_id,
        raised_at=utcnow(),
        source_channel=source_channel,
    )


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
