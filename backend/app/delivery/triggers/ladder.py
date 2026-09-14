"""The escalation ladder (E11-06): Dad, then the helper, then the caregiver on duty, then the chief.

An action nobody answered climbs. A dose not tapped by the end of its window goes to him
first, then — each rung after its wait — to the helper, to whoever the roster puts on duty
(`who_is_on_duty`), and to the chief, and it stops the moment someone answers: a Taken tap
from anyone, on any channel. So the third ask about a tablet goes to the roster, not to him.
A red flag does not start with him — he raised it, or he is the one in trouble — and it does
not wait on the helper's rung either: it goes straight to the roster, whoever is on duty at
once and the chief after a few minutes if nobody has answered, and it is never capped and
never held for the quiet hours (`rules.RULES[FLAG]`).

A rung is a `Delivery` row, audited as a SHARE when it reached a person; nobody is on a rung
whose key does not cover the part it is about — the medicines for a dose, the emergency card
for a flag — "only me" taken out. A rung with nobody on it is skipped and costs no wait.

`escalate_flag` is the one door a red flag is escalated through, and the ladder is the one
record of who is told: the WhatsApp thread calls it the moment a flag is heard, the feeling
cloud the moment one is tapped, the not-feeling-well button and the symptom log (E13/E14) the
moment one is said; the five-minute engine run is only the net under it. E19's `Escalation`
rows and E13's per-person red-flag notices are no longer written: a ladder rung and its
`Delivery` row are what they were.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.audit.models import Action, Channel
from app.audit.trail import record
from app.channels.whatsapp.outbound.send import Delivered, send
from app.channels.whatsapp.templates import language_of
from app.db import as_utc, utcnow
from app.delivery.strings import theirs
from app.delivery.triggers.deliver import (
    Firing,
    Message,
    Recipient,
    Run,
    Via,
    deliver,
    open_run,
)
from app.delivery.triggers.models import (
    LADDER_STEP,
    Delivery,
    DeliveryOutcome,
    DeliverySettings,
    Ladder,
    Subject,
    TriggerType,
)
from app.delivery.triggers.rules import config_of
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.roster import who_is_on_duty
from app.identity.models import Person
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.medicines.service import today as doses_today
from app.medicines.strings import ANCHOR_WORDS, PLAIN_NAME
from app.memory.models import Provider, ProviderKind
from app.regions import REGION_TZ
from app.safety.boundary import YOUR_DOCTOR
from app.safety.red_flags import FLAG_WINDOW, Flag

PATIENT, HELPER, ON_DUTY, CHIEF, KEY_HOLDER = "patient", "helper", "on_duty", "chief", "key_holder"
RUNG_OF = {PATIENT: 0, HELPER: 1, ON_DUTY: 2, CHIEF: 3, KEY_HOLDER: 4}
"""The rung each standing is on: the third rung, whoever is on it, is the roster."""

DOSE_RUNGS: tuple[tuple[str, int], ...] = ((PATIENT, 0), (HELPER, 30), (ON_DUTY, 30), (CHIEF, 30))
"""Him when the window closes; the helper half an hour later; whoever is on duty half an hour
after that; the chief half an hour after that. The minutes are after the rung before."""
FLAG_RUNGS: tuple[tuple[str, int], ...] = ((ON_DUTY, 0), (CHIEF, 5), (KEY_HOLDER, 5))
"""Whoever the roster puts on duty (the helper or a caregiver), at once; the chief five
minutes later if nobody has answered; then everyone else whose key holds the emergency card.
With nobody on duty, the chief is asked at once; with no chief either, everyone else is."""


class NotOnTheLadder(Refusal):
    """Only someone the ladder asked, whose key covers it, answers it."""


@dataclass(frozen=True, slots=True)
class Escalated:
    """What `escalate_flag` did: the ladder, and who has been reached so far."""

    ladder: Ladder | None
    told: tuple[uuid.UUID, ...]
    """Who a message reached, now."""
    asked: tuple[uuid.UUID, ...]
    """Who the ladder called first — the flag leads their feed, and a message went to them
    by the first channel that could carry it (none, where none could)."""
    deliveries: tuple[Delivery, ...]


# --- who stands where -------------------------------------------------------------------------


async def people_standing(run: Run, standing: str, scope: Scope) -> list[Person]:
    """Everyone with this standing on the profile now, whose key covers `scope`."""
    people: list[Person] = []
    if standing == PATIENT:
        if run.patient is not None:
            people = [run.patient]
    elif standing == ON_DUTY:
        for duty in await who_is_on_duty(run.session, context=run.acting, at=run.at):
            person = await run.person(duty.person_id)
            if person is not None:
                people.append(person)
    else:
        role = {HELPER: KeyRole.HELPER, CHIEF: KeyRole.CHIEF}.get(standing)
        for key in await run.live_keys():
            if role is not None and key.role is not role:
                continue
            person = await run.person(key.holder_person_id)
            if person is not None:
                people.append(person)
    return [person for person in people if scope in await run.scopes_of(person)]


async def rungs_for(
    run: Run, spec: Sequence[tuple[str, int]], scope: Scope, exclude: Sequence[uuid.UUID]
) -> list[dict[str, Any]]:
    """The calling order: each person once, at the first rung they stand on; a rung with
    nobody on it is skipped and adds no wait."""
    rungs: list[dict[str, Any]] = []
    seen = set(exclude)
    offset: int | None = None
    for standing, gap in spec:
        people = [p for p in await people_standing(run, standing, scope) if p.id not in seen]
        if not people:
            continue
        offset = 0 if offset is None else offset + gap
        for person in people:
            seen.add(person.id)
            rungs.append(
                {
                    "rung": RUNG_OF[standing],
                    "person_id": str(person.id),
                    "standing": standing,
                    "after_minutes": offset,
                }
            )
    return rungs


# --- the ladder row ---------------------------------------------------------------------------


async def start(
    run: Run,
    *,
    subject: Subject,
    scope: Scope,
    dedupe_key: str,
    spec: Sequence[tuple[str, int]],
    exclude: Sequence[uuid.UUID],
    started_at: datetime,
    line_id: uuid.UUID | None = None,
    anchor: str | None = None,
    flag_id: uuid.UUID | None = None,
) -> Ladder:
    """The ladder for this action, started now — or the one it already has."""
    for ladder in await run.ladders():
        if ladder.dedupe_key == dedupe_key:
            return ladder
    rungs = await rungs_for(run, spec, scope, exclude)
    row = await audited_write(
        run.session,
        Ladder,
        run.acting,
        scope,
        channel=Channel.SYSTEM,
        subject=subject,
        scope=scope,
        dedupe_key=dedupe_key,
        day=as_utc(started_at).astimezone(REGION_TZ[run.acting.region]).date().isoformat(),
        line_id=line_id,
        anchor=anchor,
        flag_id=flag_id,
        rungs=rungs,
        started_at=as_utc(started_at),
        next_rung=0,
    )
    (await run.ladders()).append(row)
    return row


async def _move(
    session: AsyncSession,
    context: KeyContext,
    ladder: Ladder,
    *,
    channel: Channel = Channel.SYSTEM,
    **changes: Any,
) -> None:
    """The one way a ladder changes: its rung, its answer, its close. Written down."""
    session.info[LADDER_STEP] = ladder.id
    try:
        for name, value in changes.items():
            setattr(ladder, name, value)
        await session.flush()
    finally:
        session.info.pop(LADDER_STEP, None)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=ladder.scope,
        target=Ladder.__tablename__,
        target_id=ladder.id,
        rows=1,
        channel=channel,
    )


async def close(
    session: AsyncSession,
    context: KeyContext,
    ladder: Ladder,
    because: str,
    *,
    by: uuid.UUID | None = None,
    channel: Channel = Channel.SYSTEM,
) -> None:
    if not ladder.is_open:
        return
    moment = utcnow()
    changes: dict[str, Any] = {"closed_at": moment, "closed_because": because}
    if by is not None:
        changes |= {"acknowledged_at": moment, "acknowledged_by_person_id": by}
    await _move(session, context, ladder, channel=channel, **changes)


def tapped_by(
    run: Run, taps: Sequence[Any], generic_of: dict[uuid.UUID, str], generic: str, day: str,
    anchor: str | None,
) -> uuid.UUID | None:
    """Who tapped Taken for this medicine at this anchor on this day of his, if anyone."""
    zone = REGION_TZ[run.acting.region]
    for tap in taps:
        if generic_of.get(tap.line_id) != generic:
            continue
        if as_utc(tap.taken_at).astimezone(zone).date().isoformat() != day:
            continue
        if tap.anchor is None or anchor is None or tap.anchor == anchor:
            return uuid.UUID(str(tap.by_person_id))
    return None


async def _answered(run: Run, ladder: Ladder) -> uuid.UUID | None:
    if ladder.subject is Subject.FLAG:
        return ladder.acknowledged_by_person_id
    taps, generic_of = await run.taps()
    if ladder.line_id is None or ladder.line_id not in generic_of:
        return None
    return tapped_by(run, taps, generic_of, generic_of[ladder.line_id], ladder.day, ladder.anchor)


Say = Callable[[Recipient], Message]


async def climb(run: Run, ladder: Ladder, say: Say, type: TriggerType) -> None:
    """Ask every rung that is due and has not been asked; stop at an answer; lapse at the end
    of the dose's day, or a day after the flag."""
    if not ladder.is_open:
        return
    answered_by = await _answered(run, ladder)
    if answered_by is not None:
        await close(run.session, run.acting, ladder, "answered", by=answered_by)
        return
    started = as_utc(ladder.started_at)
    over = (ladder.subject is Subject.DOSE and ladder.day < run.day) or (
        ladder.subject is Subject.FLAG and run.at - started >= FLAG_WINDOW
    )
    if over:
        await close(run.session, run.acting, ladder, "lapsed")
        return
    elapsed = (run.at - started).total_seconds() / 60
    reached = ladder.next_rung
    for step in ladder.rungs:
        if step["after_minutes"] > elapsed:
            continue
        person = await run.person(uuid.UUID(step["person_id"]))
        if person is None:
            continue
        to = Recipient(person, step["standing"])
        firing = Firing(
            type=type,
            dedupe_key=f"{ladder.dedupe_key}:r{step['rung']}",
            why={"ladder_id": str(ladder.id), "rung": step["rung"], "action": ladder.dedupe_key},
        )
        await deliver(run, firing, to, say(to), rung=step["rung"], ladder=ladder)
        reached = max(reached, int(step["rung"]) + 1)
    if reached != ladder.next_rung:
        await _move(run.session, run.acting, ladder, next_rung=reached)


# --- what each rung says --------------------------------------------------------------------------


def medicine_words(registry: DrugRegistry, generic: str, language: str) -> str:
    """His words for a medicine, from the licensed monograph's plain-name id."""
    return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]


def dose_message(run: Run, ladder: Ladder, generic: str) -> Say:
    """Him: "Have you had your blood pressure tablet with breakfast?". Anyone else: "Pa has
    not said Taken for Pa's blood pressure tablet with breakfast yet."."""
    registry = run.via.providers.drug_registry
    anchor = ladder.anchor or "breakfast"

    async def check_on(person: Person) -> Delivered:
        lang = language_of(person.language)
        return await send(
            run.session,
            context=run.acting,
            to_person=person,
            kind="dose_check",
            params={
                "name": run.profile.display_name,
                "medicine": theirs(
                    medicine_words(registry, generic, lang), run.profile.display_name, lang
                ),
                "anchor": ANCHOR_WORDS[lang][anchor],
            },
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=lang,
            state=await run.state(),
        )

    async def ask_him(person: Person) -> Delivered:
        lang = run.language
        return await send(
            run.session,
            context=run.acting,
            to_person=person,
            kind="dose_reminder",
            params={
                "name": run.profile.display_name,
                "medicine": medicine_words(registry, generic, lang),
                "anchor": ANCHOR_WORDS[lang][anchor],
            },
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=lang,
            state=await run.state(),
        )

    def say(to: Recipient) -> Message:
        if to.standing == PATIENT:
            return Message(whatsapp=ask_him, stand_in=check_on)
        return Message(whatsapp=check_on)

    return say


async def _doctor(run: Run, language: str) -> str:
    providers = await audited_read(
        run.session, Provider, run.acting, Scope.VISITS, channel=Channel.SYSTEM
    )
    for kind in (ProviderKind.DOCTOR, ProviderKind.CLINIC, ProviderKind.HOSPITAL):
        for provider in providers:
            if provider.kind is kind:
                return provider.name
    return YOUR_DOCTOR[language]


def flag_message(run: Run, flag: Flag) -> Say:
    """The approved red-flag notice: "This one we do not wait for. Mei said Pa is not well.
    Call Dr Tan today." In the reader's language, naming who said it."""

    async def notice(person: Person) -> Delivered:
        lang = language_of(person.language)
        raiser = await run.person(flag.raised_by_person_id)
        return await send(
            run.session,
            context=run.acting,
            to_person=person,
            kind="red_flag_notice",
            params={
                "name": run.profile.display_name,
                "who": raiser.display_name if raiser is not None else run.profile.display_name,
                "doctor": await _doctor(run, lang),
            },
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=lang,
            state=await run.state(),
        )

    return lambda to: Message(whatsapp=notice)


# --- red flags -------------------------------------------------------------------------------------


async def flag_ladder(run: Run, flag: Flag, *, exclude: Sequence[uuid.UUID]) -> Ladder:
    """The ladder for one flag: straight to the roster, him and whoever already knows left
    out. It starts the moment the flag was raised, or now if that is earlier."""
    skip = [*exclude, flag.raised_by_person_id]
    if run.profile.owner_person_id is not None:
        skip.append(run.profile.owner_person_id)
    return await start(
        run,
        subject=Subject.FLAG,
        scope=Scope.EMERGENCY,
        dedupe_key=f"flag:{flag.id}",
        spec=FLAG_RUNGS,
        exclude=skip,
        started_at=min(as_utc(flag.raised_at), run.at),
        flag_id=flag.id,
    )


async def escalate_flag(
    session: AsyncSession,
    context: KeyContext,
    flag: Flag,
    *,
    told_already: Sequence[uuid.UUID] = (),
    via: Via,
    at: datetime | None = None,
) -> Escalated:
    """The one door a red flag is escalated through (E11-06).

    `context` is the key of whoever raised it, on the flag's profile; `told_already` is who
    has already had the word by some other way (the poster, who knows; E13's notice). The
    ladder itself runs as the profile's owner, the way his Level 0 day does, so whoever
    raised it — a helper whose key does not open the family list — can start it. The first
    rung goes at once, whatever the hour and whatever anyone's cap; later rungs go from the
    engine's run. `at` is the moment it was said (the message's own time); now when not given.
    A flag held back for a missing fact is not escalated (`red_flags`): it waits for the
    caregiver in her list. Returns the ladder and who has been reached so far.
    """
    if flag.profile_id != context.profile_id:
        raise NotOnTheLadder("the flag is on another profile")
    if flag.suppressed_because is not None:
        return Escalated(ladder=None, told=(), asked=(), deliveries=())
    run = await open_run(session, via=via, profile_id=context.profile_id, at=at or utcnow())
    ladder = await flag_ladder(run, flag, exclude=told_already)
    await climb(run, ladder, flag_message(run, flag), TriggerType.FLAG)
    reached = tuple(
        sent.delivery.to_person_id
        for sent in run.report
        if sent.delivery.outcome is DeliveryOutcome.SENT and sent.delivery.to_person_id is not None
    )
    asked = tuple(
        uuid.UUID(step["person_id"]) for step in ladder.rungs if step["after_minutes"] == 0
    )
    return Escalated(
        ladder=ladder,
        told=reached,
        asked=asked,
        deliveries=tuple(sent.delivery for sent in run.report),
    )


async def acknowledge_flag(
    session: AsyncSession,
    *,
    context: KeyContext,
    ladder_id: uuid.UUID | None = None,
    channel: Channel = Channel.APP,
) -> Ladder | None:
    """Someone the flag's ladder reached says they have it: the ladder stops. The newest open
    flag ladder that reached this person, or the one named; `NotOnTheLadder` when the named
    one never reached them. Under the emergency scope: a key without it answers nothing."""
    where: list[Any] = [Ladder.subject == Subject.FLAG, Ladder.closed_at.is_(None)]
    if ladder_id is not None:
        where.append(Ladder.id == ladder_id)
    ladders = await audited_read(
        session, Ladder, context, Scope.EMERGENCY, where=tuple(where), channel=channel
    )
    if not ladders:
        if ladder_id is not None:
            raise NotOnTheLadder(f"no open flag ladder {ladder_id} here")
        return None
    reached = await audited_read(
        session,
        Delivery,
        context,
        Scope.EMERGENCY,
        where=(
            Delivery.ladder_id.in_([ladder.id for ladder in ladders]),
            Delivery.to_person_id == context.person_id,
            Delivery.outcome == DeliveryOutcome.SENT,
        ),
        channel=channel,
    )
    theirs_ = {row.ladder_id for row in reached}
    mine = [ladder for ladder in ladders if ladder.id in theirs_]
    if not mine:
        if ladder_id is not None:
            raise NotOnTheLadder("the ladder never reached this person")
        return None
    newest = max(mine, key=lambda ladder: as_utc(ladder.started_at))
    await close(session, context, newest, "answered", by=context.person_id, channel=channel)
    return newest


# --- doses -----------------------------------------------------------------------------------------


async def acknowledge_dose(
    session: AsyncSession,
    *,
    context: KeyContext,
    line_id: uuid.UUID,
    anchor: str | None,
    day: str,
    channel: Channel = Channel.APP,
) -> list[Ladder]:
    """A Taken tap answers the ladder for that tablet at once, whoever tapped."""
    ladders = await audited_read(
        session,
        Ladder,
        context,
        Scope.MEDICINES,
        where=(Ladder.subject == Subject.DOSE, Ladder.closed_at.is_(None), Ladder.day == day),
        channel=channel,
    )
    closed: list[Ladder] = []
    for ladder in ladders:
        if ladder.line_id == line_id and (anchor is None or ladder.anchor == anchor):
            await close(session, context, ladder, "answered", by=context.person_id, channel=channel)
            closed.append(ladder)
    return closed


@dataclass(frozen=True, slots=True)
class DoseAsked:
    line_id: uuid.UUID
    anchor: str
    generic: str


async def dose_for_reply(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    at: datetime | None = None,
    channel: Channel = Channel.WHATSAPP,
) -> DoseAsked | None:
    """Which tablet a "Taken" or "given" reply is about: the one the ladder last asked this
    person about that day; else the one whose window is open at that moment and has no Taken
    yet; else none — and then nothing is written down. `at` is when the reply was sent (the
    message's own time, as the provider stamps it); now when not given."""
    zone = REGION_TZ[context.region]
    moment = as_utc(at) if at is not None else utcnow()
    local = moment.astimezone(zone)
    day = local.date().isoformat()
    ladders = await audited_read(
        session,
        Ladder,
        context,
        Scope.MEDICINES,
        where=(Ladder.subject == Subject.DOSE, Ladder.closed_at.is_(None), Ladder.day == day),
        channel=channel,
    )
    asked = [
        ladder
        for ladder in ladders
        if ladder.line_id is not None
        and ladder.anchor is not None
        and any(step["person_id"] == str(context.person_id) for step in ladder.rungs)
    ]
    slots = await doses_today(session, context=context, registry=registry)
    generic_of = {slot.line.id: slot.line.generic for slot in slots}
    if asked:
        newest = max(asked, key=lambda ladder: as_utc(ladder.started_at))
        assert newest.line_id is not None and newest.anchor is not None
        generic = generic_of.get(newest.line_id)
        if generic is not None:
            return DoseAsked(line_id=newest.line_id, anchor=newest.anchor, generic=generic)
    settings = await audited_read(
        session,
        DeliverySettings,
        context,
        Scope.PROFILE,
        order_by=(DeliverySettings.set_at.desc(),),
        limit=1,
        channel=channel,
    )
    config = config_of(settings[0] if settings else None)
    for slot in slots:
        if slot.taken:
            continue
        opens, closes = config.window(local.date(), slot.anchor, zone)
        if opens <= local < closes:
            return DoseAsked(line_id=slot.line.id, anchor=slot.anchor, generic=slot.line.generic)
    return None


__all__ = [
    "DOSE_RUNGS",
    "FLAG_RUNGS",
    "DoseAsked",
    "Escalated",
    "NotOnTheLadder",
    "acknowledge_dose",
    "acknowledge_flag",
    "climb",
    "dose_for_reply",
    "escalate_flag",
    "time",
]
