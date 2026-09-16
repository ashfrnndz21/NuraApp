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
for a flag — "only me" taken out. A rung with nobody on it is skipped and costs no wait. A
flag's rung goes every way each person on it can be reached, and the notice on their family
page is always written (`deliver`, #162); a flag's rung whose people no phone reached costs no
wait either — the next rung is asked at once, and the chief sees who could not be reached
(`not_reached`).

A voice note Nura could not hear climbs the same way (#173). It is not a flag — nothing was
read in it — but a red word in it could not be read either, so it is treated as one: the
chief first, because it is hers to listen to; whoever is on duty five minutes later if she
has not said she has it; then everyone else whose key holds the emergency card. It stops the
same way a flag's does, on one person saying they have it (`acknowledge_flag`).

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
from app.channels.whatsapp.outbound.send import (
    Delivered,
    NotPlainWords,
    OutsideTheWindow,
    TemplateNotApproved,
    send,
)
from app.db import as_utc, utcnow
from app.delivery.strings import EMERGENCY_NUMBER, theirs
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
    ANSWERED_BY_A_PERSON,
    LADDER_STEP,
    PHONE,
    Delivery,
    DeliveryOutcome,
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
from app.routines.breakfast import breakfast_time
from app.routines.service import current_routine
from app.safety.boundary import YOUR_DOCTOR
from app.safety.red_flags import FLAG_WINDOW, Flag, Step, escalation_now, is_red

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
UNHEARD_RUNGS: tuple[tuple[str, int], ...] = ((CHIEF, 0), (ON_DUTY, 5), (KEY_HOLDER, 5))
"""A voice note Nura could not hear (#173): the chief first, because it is her note to
listen to; whoever is on duty five minutes later if she has not said she has it; then
everyone else whose key holds the emergency card. With no chief, the roster is asked at
once — a rung with nobody on it costs no wait."""


class NotOnTheLadder(Refusal):
    """Only someone the ladder asked, whose key covers it, answers it."""


class SenderNotNamed(Refusal):
    """A voice note nobody could hear, and nobody to say who sent it. The notice would have
    to claim the patient sent it, and he may not have (#173), so it does not go on WhatsApp
    at all: the channel falls through to the app's content-free push, and the notice on the
    family page is written whatever carried it."""


@dataclass(frozen=True, slots=True)
class Escalated:
    """What `escalate_flag` did: the ladder, and who has been reached so far."""

    ladder: Ladder | None
    told: tuple[uuid.UUID, ...]
    """Whose phone a message reached, now: an app push or WhatsApp. The notice on a family
    page is written for everyone asked, and is not counted here."""
    asked: tuple[uuid.UUID, ...]
    """Who the ladder called first — the flag leads their feed and waits on their family page,
    and a message went to them every way that could carry one (none, where none could)."""
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
    note_id: uuid.UUID | None = None,
    note_from_person_id: uuid.UUID | None = None,
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
        note_id=note_id,
        note_from_person_id=note_from_person_id,
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
    run: Run,
    taps: Sequence[Any],
    generic_of: dict[uuid.UUID, str],
    generic: str,
    day: str,
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
    if ladder.subject in ANSWERED_BY_A_PERSON:
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
        ladder.subject in ANSWERED_BY_A_PERSON and run.at - started >= FLAG_WINDOW
    )
    if over:
        await close(run.session, run.acting, ladder, "lapsed")
        return
    elapsed = (run.at - started).total_seconds() / 60
    reached = ladder.next_rung
    # A flag's rung whose people no phone reached moves the ladder on at once: the next
    # rung is due now, and the ones after it keep their gaps from there (#162). Worked out
    # from the rows each run, so every run agrees on it.
    early = 0
    offsets = sorted({int(step["after_minutes"]) for step in ladder.rungs})
    for index, offset in enumerate(offsets):
        if offset - early > elapsed:
            break
        group = [step for step in ladder.rungs if int(step["after_minutes"]) == offset]
        for step in group:
            person = await run.person(uuid.UUID(step["person_id"]))
            if person is None:
                continue
            to = Recipient(person, step["standing"])
            firing = Firing(
                type=type,
                dedupe_key=f"{ladder.dedupe_key}:r{step['rung']}",
                why={
                    "ladder_id": str(ladder.id),
                    "rung": step["rung"],
                    "action": ladder.dedupe_key,
                },
            )
            await deliver(run, firing, to, say(to), rung=step["rung"], ladder=ladder)
            reached = max(reached, int(step["rung"]) + 1)
        later = index + 1 < len(offsets)
        if (
            later
            and ladder.subject in ANSWERED_BY_A_PERSON
            and not await _a_phone_reached(run, ladder, group)
        ):
            early += offsets[index + 1] - offset
    if reached != ladder.next_rung:
        await _move(run.session, run.acting, ladder, next_rung=reached)


async def _a_phone_reached(run: Run, ladder: Ladder, group: Sequence[dict[str, Any]]) -> bool:
    """Whether anyone on this rung was reached on their phone about this ladder, this run or
    an earlier one: an app push, WhatsApp, or the caregiver standing in."""
    people = {step["person_id"] for step in group}
    return any(
        row.ladder_id == ladder.id
        and row.outcome is DeliveryOutcome.SENT
        and row.via in PHONE
        and (str(row.to_person_id) in people or str(row.for_person_id) in people)
        for row in await run.deliveries()
    )


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
        lang = run.language_for(person)
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


TIERED_NOTICE: dict[Step, str] = {
    Step.AMBULANCE: "red_flag_notice_ambulance",
    Step.HOSPITAL_NOW: "red_flag_notice_hospital",
    Step.NUMBER_IF_WORSE: "red_flag_notice_night",
}
"""The notice for a step that is not "call the doctor today" (E19-05): the ambulance tier at any
hour, and a same-day flag out of the doctor's hours — the hospital on his insurance, or the
emergency number."""

URGENT_NOTICE = "red_flag_notice_urgent"
"""States no action of its own: the one WhatsApp fallback once a tier applies (`TIERED_NOTICE`)
and its own template cannot go — not approved, and outside the family member's 24-hour window a
reply cannot go at all. Never "call {doctor} today" or its variants: an urgent alert is never
told at a lower tier than the one it is (#174). Where this is not approved either, no WhatsApp
goes at all, and the delivery's own trail says why; the family still reaches it (#162, #169):
the family page's notice carries the tier, and the app push — its own words fixed and
content-free (`PUSH_LINE`) — only opens it."""


def flag_message(run: Run, flag: Flag) -> Say:
    """The red-flag notice, in the reader's language: "This one we do not wait for. Mei said Pa
    is not well. Call Dr Tan today." When the flag is in the ambulance tier, or it is out of
    the doctor's hours, the notice that says so (`TIERED_NOTICE`: call him now, then the
    ambulance, the hospital's emergency department or the emergency number) — and once a tier
    applies, WhatsApp says only the tier's own words or `URGENT_NOTICE`, never "call {doctor}
    today", which would tell the family a lower urgency than the tier (#174). When he raised
    it himself, "Pa is not feeling well."; when the person who raised it is on more than one
    family's list and has not said which, "It may be about Pa." — each variant only where the
    number approves it, so a flag never waits on Meta."""

    async def notice(person: Person) -> Delivered:
        lang = run.language_for(person)
        raiser = await run.person(flag.raised_by_person_id)
        name = run.profile.display_name
        who = raiser.display_name if raiser is not None else name
        doctor = await _doctor(run, lang)
        approves = run.via.number.approves
        number = EMERGENCY_NUMBER[run.acting.region.value]
        tiered: tuple[str, dict[str, str]] | None = None
        go_now = False  # the ambulance or the hospital now: never traded for a weaker notice
        if flag.feeling is not None and is_red(flag.feeling):
            try:
                step = await escalation_now(
                    run.session,
                    context=run.acting,
                    feeling=flag.feeling,
                    local=run.local,
                    emergency_number=number,
                    channel=Channel.SYSTEM,
                    tiered=run.via.settings.red_flag_tiers,
                )
            except Refusal:
                # Nothing about his directory may keep a flag from the family: the most
                # urgent notice, the ambulance's.
                tiered = (TIERED_NOTICE[Step.AMBULANCE], {"name": name, "emergency_number": number})
                go_now = True
            else:
                go_now = step.step in (Step.AMBULANCE, Step.HOSPITAL_NOW)
                if step.step is Step.HOSPITAL_NOW and step.hospital is not None:
                    tiered = (
                        TIERED_NOTICE[step.step],
                        {"name": name, "hospital": step.hospital, "emergency_number": number},
                    )
                elif step.step in TIERED_NOTICE:
                    tiered = (TIERED_NOTICE[step.step], {"name": name, "emergency_number": number})
        # In order, the first that goes: the ambiguous notice; the tiered one — its template
        # where Meta approved it, else the same words as free text inside the window. When the
        # step is the ambulance or the hospital now, the tiered notice goes before the
        # ambiguous one, which names no ambulance and no hospital (B1 clinical-safety review).
        # Once a tier applies, nothing weaker follows: not the notice he raised himself, not
        # the plain "call {doctor} today" — those are candidates only when no tier applies.
        # A tier that cannot go either way falls to `URGENT_NOTICE`, which says no action of
        # its own; where even that is not approved, no WhatsApp goes at all (#174).
        candidates: list[tuple[str, dict[str, str]]] = []
        told_now: tuple[str, dict[str, str]] | None = None
        if tiered is not None:
            told_now = (tiered[0] if approves(tiered[0]) else f"{tiered[0]}_text", tiered[1])
        if told_now is not None and go_now:
            candidates.append(told_now)
        if flag.ambiguous_profile and approves("red_flag_notice_ambiguous"):
            candidates.append(("red_flag_notice_ambiguous", {"who": who, "name": name}))
        if told_now is not None and not go_now:
            candidates.append(told_now)
        if tiered is None:
            if (
                raiser is not None
                and raiser.id == run.profile.owner_person_id
                and approves("red_flag_notice_self")
            ):
                candidates.append(("red_flag_notice_self", {"name": name, "doctor": doctor}))
            candidates.append(("red_flag_notice", {"name": name, "who": who, "doctor": doctor}))
        elif approves(URGENT_NOTICE):
            candidates.append((URGENT_NOTICE, {"name": name}))
        passed: Refusal | None = None
        for kind, params in candidates:
            try:
                return await send(
                    run.session,
                    context=run.acting,
                    to_person=person,
                    kind=kind,
                    params=params,
                    provider=run.via.providers.whatsapp,
                    number=run.via.number,
                    language=lang,
                    state=await run.state(),
                )
            except (NotPlainWords, OutsideTheWindow, TemplateNotApproved) as refused:
                passed = refused  # the words could not go this way: the next notice
        assert passed is not None
        raise passed

    return lambda to: Message(whatsapp=notice)


# --- a voice note Nura could not hear ---------------------------------------------------------------


UNHEARD_SCOPE = Scope.EMERGENCY
"""What an unheard note speaks of: a red word in it could not be read, so it is the emergency
card, the same as a flag's — a helper's key holds it, and a key without it is told nothing."""


async def unheard_ladder(
    run: Run,
    *,
    dedupe_key: str,
    note_id: uuid.UUID | None,
    from_person_id: uuid.UUID,
) -> Ladder:
    """The ladder for one voice note nobody could hear: the chief, then the roster, then
    everyone else whose key holds the emergency card. Whoever sent it is left off it — they
    know already — and the ladder remembers who that was, so the notice can name them."""
    return await start(
        run,
        subject=Subject.UNHEARD_NOTE,
        scope=UNHEARD_SCOPE,
        dedupe_key=dedupe_key,
        spec=UNHEARD_RUNGS,
        exclude=(from_person_id,),
        started_at=run.at,
        note_id=note_id,
        note_from_person_id=from_person_id,
    )


def unheard_message(run: Run, ladder: Ladder) -> Say:
    """The unheard-note notice, in the reader's language. It carries no word of the note and
    none of its audio: who sent it, that Nura could not hear it, and the one thing to do.

    His own note: where this person's key opens his notes and there is a note to open, she is
    told to listen in the app or to call him; where it does not, or the audio never arrived,
    to call him — the one thing she can actually do. Somebody else's note is never said to be
    his (#173): it names whoever sent it, and the thing to do is to call them, since they are
    the one who knows what they said. Nothing of theirs is kept, so there is never anything
    to listen to. Only a note this run can read as his own is said to be his; with nobody to
    name at all, the notice does not go on WhatsApp rather than guess (`SenderNotNamed`).
    """

    async def notice(person: Person) -> Delivered:
        name = run.profile.display_name
        sender = (
            None
            if ladder.note_from_person_id is None
            else await run.person(ladder.note_from_person_id)
        )
        his = sender is not None and run.patient is not None and sender.id == run.patient.id
        if his:
            opens = ladder.note_id is not None and Scope.NOTES in await run.scopes_of(person)
            kind = "unheard_note_notice" if opens else "unheard_note_notice_call"
            params = {"name": name}
        elif sender is not None and sender.display_name:
            kind, params = "unheard_note_notice_from", {"who": sender.display_name, "name": name}
        else:
            # Nobody to name. Saying the patient sent it would be a claim about him that may
            # not be true, so nothing goes on WhatsApp: the push and the family page still do.
            raise SenderNotNamed(f"ladder {ladder.id} cannot say who sent the note")
        return await send(
            run.session,
            context=run.acting,
            to_person=person,
            kind=kind,
            params=params,
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=run.language_for(person),
            state=await run.state(),
        )

    return lambda to: Message(whatsapp=notice)


async def climb_unheard(run: Run, ladder: Ladder) -> None:
    """One unheard-note ladder, asked as far as it is due. The engine calls this on every
    open one, so a chief who has not said she has it is followed by the next rung (#173)."""
    await climb(run, ladder, unheard_message(run, ladder), TriggerType.VOICE_NOTE_UNHEARD)


# --- red flags -------------------------------------------------------------------------------------


async def flag_ladder(
    run: Run, flag: Flag, *, exclude: Sequence[uuid.UUID], now: bool = False
) -> Ladder:
    """The ladder for one flag: straight to the roster, him and whoever already knows left
    out. Escalated at the moment it was said (`now`), it starts then; picked up by the engine's
    run, it starts when the flag was raised, or at the run if that is earlier."""
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
        started_at=run.at if now else min(as_utc(flag.raised_at), run.at),
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
    ladder = await flag_ladder(run, flag, exclude=told_already, now=True)
    await climb(run, ladder, flag_message(run, flag), TriggerType.FLAG)
    reached = tuple(
        dict.fromkeys(
            sent.delivery.to_person_id
            for sent in run.report
            if sent.delivery.outcome is DeliveryOutcome.SENT
            and sent.delivery.via in PHONE
            and sent.delivery.to_person_id is not None
        )
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
    """Someone the ladder reached says they have it: the ladder stops. The newest open ladder
    of the kind a person answers — a red flag, or a voice note Nura could not hear (#173) —
    that reached this person, or the one named; `NotOnTheLadder` when the named one never
    reached them. Under the emergency scope: a key without it answers nothing."""
    where: list[Any] = [
        Ladder.subject.in_(sorted(ANSWERED_BY_A_PERSON)),
        Ladder.closed_at.is_(None),
    ]
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


async def open_flags_for(session: AsyncSession, *, context: KeyContext) -> list[Ladder]:
    """The open ladders that reached this person and wait on a person's word — a red flag, or
    a voice note Nura could not hear (#173) — newest first: the ones their "I'm on it"
    (`acknowledge_flag`) would stop. Read under the emergency scope, like the acknowledging:
    a key without it answers nothing."""
    ladders = await audited_read(
        session,
        Ladder,
        context,
        Scope.EMERGENCY,
        where=(
            Ladder.subject.in_(sorted(ANSWERED_BY_A_PERSON)),
            Ladder.closed_at.is_(None),
        ),
    )
    if not ladders:
        return []
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
    )
    theirs_ = {row.ladder_id for row in reached}
    return sorted(
        (ladder for ladder in ladders if ladder.id in theirs_),
        key=lambda ladder: as_utc(ladder.started_at),
        reverse=True,
    )


async def not_reached(
    session: AsyncSession, *, context: KeyContext, ladder: Ladder
) -> list[uuid.UUID]:
    """Everyone this flag's ladder asked whose phone nothing reached — only the notice on their
    family page — in the order they were asked. What the chief is shown (#162). Read under the
    emergency scope, like the ladder itself."""
    rows = await audited_read(
        session,
        Delivery,
        context,
        Scope.EMERGENCY,
        where=(Delivery.ladder_id == ladder.id,),
    )
    asked: list[uuid.UUID] = []
    phoned: set[uuid.UUID] = set()
    for row in sorted(rows, key=lambda one: (as_utc(one.recorded_at), one.rung or 0)):
        if row.to_person_id is None:
            continue
        if row.to_person_id not in asked:
            asked.append(row.to_person_id)
        if row.outcome is DeliveryOutcome.SENT and row.via in PHONE:
            phoned.add(row.to_person_id)
    return [person for person in asked if person not in phoned]


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
    """One tablet at one moment of his day, as a "Taken" or "given" reply could mean it."""

    line_id: uuid.UUID
    anchor: str
    generic: str
    strength: str = ""


async def doses_for_reply(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    at: datetime | None = None,
    channel: Channel = Channel.WHATSAPP,
) -> list[DoseAsked]:
    """Every tablet a "Taken" or "given" reply could be about at that moment (#162), never a
    guess among them: each one the ladder has asked this person about that day and is still
    open, and each one whose window is open and has no Taken yet; with neither, every tablet
    at the latest moment today that has passed with none. Earliest moment first. One is
    written down; more than one is asked about, by name, before anything is written
    (`app.channels.whatsapp.inbound`); none, nothing. The moments are his routine's
    (E10-01). `at` is when the reply was sent (the message's own time, as the provider stamps
    it); now when not given."""
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
    lines = {slot.line.id: slot.line for slot in slots}
    config = config_of(
        None,
        await current_routine(session, context=context),
        await breakfast_time(session, context=context),
    )
    found: dict[tuple[uuid.UUID, str], DoseAsked] = {}

    def one(line_id: uuid.UUID, anchor: str) -> None:
        line = lines.get(line_id)
        if line is not None and (line_id, anchor) not in found:
            found[(line_id, anchor)] = DoseAsked(
                line_id=line_id, anchor=anchor, generic=line.generic, strength=line.strength
            )

    for ladder in asked:
        assert ladder.line_id is not None and ladder.anchor is not None
        one(ladder.line_id, ladder.anchor)
    untapped = [slot for slot in slots if not slot.taken]
    for slot in untapped:
        opens, closes = config.window(local.date(), slot.anchor, zone)
        if opens <= local < closes:
            one(slot.line.id, slot.anchor)
    if not found:
        # Late: the tablets at the latest moment today that has passed with no Taken yet.
        passed = [
            slot
            for slot in untapped
            if datetime.combine(local.date(), config.anchor_at(slot.anchor), zone) <= local
        ]
        if passed:
            latest = max(config.anchor_at(slot.anchor) for slot in passed)
            for slot in passed:
                if config.anchor_at(slot.anchor) == latest:
                    one(slot.line.id, slot.anchor)
    order = {(slot.line.id, slot.anchor): index for index, slot in enumerate(slots)}
    return sorted(
        found.values(),
        key=lambda dose: (
            config.anchor_at(dose.anchor),
            order.get((dose.line_id, dose.anchor), len(order)),
        ),
    )


__all__ = [
    "DOSE_RUNGS",
    "FLAG_RUNGS",
    "UNHEARD_RUNGS",
    "DoseAsked",
    "Escalated",
    "NotOnTheLadder",
    "SenderNotNamed",
    "acknowledge_dose",
    "acknowledge_flag",
    "climb",
    "climb_unheard",
    "doses_for_reply",
    "escalate_flag",
    "not_reached",
    "open_flags_for",
    "time",
    "unheard_ladder",
]
