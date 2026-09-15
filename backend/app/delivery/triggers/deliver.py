"""One message to one person, or the reason it did not go (E00-05, E11-05).

`deliver` is where every trigger ends, and the checks run in this order: whether it already
reached the person (nothing goes twice; a rule true all day is said once a day, and the
second time is held by the cap), whether the person's key covers what it speaks of (nobody
is told what their key does not open), the quiet hours (an alert ignores them), the cap for
its type (an alert has none), and then the channel list, where the first channel that can
carry it wins: an app push when the person has a device; a WhatsApp template when they have
a number and may be sent it (`_no_whatsapp`); the caregiver on duty when the patient himself
could not be reached. Whatever the answer, one `Delivery` row records the attempt and its
rule, and a delivery that reached a person is a SHARE on the trail, under the scope of what
it spoke of.

An alert — a red flag — is not "the first that works" and follows no setting (#162): it goes
by every channel the person can be reached on, a row for each, and the notice on their family
page (`DeliveryChannel.IN_APP`) is written whatever else carried it. When nothing reached
their phone, a NO_CHANNEL row says so beside the notice: the chief sees who could not be
reached, and the ladder moves on at once (`ladder.climb`).

Who may be sent WhatsApp (#163): the patient on his own agreement; anyone else on the key his
agreement to let them in rests on, and — for anything but a red flag — only while his WhatsApp
agreement stands. Someone who answered no to WhatsApp at the key-accept step is sent none,
red flags included: those reach them by app push and on their family page.

Everything here runs as Nura itself with the reach of the profile's owner (the steward before a
claim): the patient's graph, sent about the patient on his agreement, and every line on the
trail is the system's (no actor, the system channel), which his trail folds into one line a
day. A `Run` is one evaluation at one moment: it reads what it needs once and remembers.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write, record_share
from app.audit.models import Channel
from app.channels.api.deps import Providers
from app.channels.whatsapp.config import BusinessNumber, business_number_for
from app.channels.whatsapp.opt_in import said_no
from app.channels.whatsapp.outbound.send import Delivered
from app.channels.whatsapp.templates import language_of
from app.consent.models import ConsentPurpose
from app.consent.service import active_consents
from app.consent.texts import current_version
from app.db import as_utc
from app.delivery.push import NoDevice
from app.delivery.strings import PUSH_LINE
from app.delivery.triggers.models import (
    Delivery,
    DeliveryChannel,
    DeliveryOutcome,
    DeliverySettings,
    Ladder,
    TriggerType,
)
from app.delivery.triggers.rules import RULES, Config, config_of, is_alert
from app.errors import Refusal
from app.family.roster import who_is_on_duty
from app.identity.models import Person, Profile, Stewardship
from app.keys.context import (
    KeyContext,
    as_the_system,
    holds_the_profile,
    resolve_key_context,
)
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.medicines.models import DoseTaken, MedicationLine
from app.regions import REGION_TZ
from app.routines.breakfast import breakfast_time
from app.routines.service import current_routine
from app.settings import Settings
from app.state.service import StateView, current_state

LOOK_BACK = timedelta(days=8)
"""How far back a run reads its own deliveries: the longest dedupe (a week's pattern) and a
day to spare."""


class NoOneToActFor(Refusal):
    """The profile has neither an owner nor a steward holding it: nobody's graph to send from."""


@dataclass(frozen=True, slots=True)
class Via:
    """The channels one process sends through: its settings, its providers, its number."""

    settings: Settings
    providers: Providers
    number: BusinessNumber

    @classmethod
    def of(cls, settings: Settings, providers: Providers) -> Via:
        return cls(settings=settings, providers=providers, number=business_number_for(settings))


@dataclass(frozen=True, slots=True)
class Recipient:
    person: Person
    standing: str
    """patient, helper, on_duty, chief or key_holder: why this person is on the list."""


@dataclass(frozen=True, slots=True)
class Firing:
    """One trigger that fired: its type, what makes it the same trigger again, and why."""

    type: TriggerType
    dedupe_key: str
    why: Mapping[str, Any]
    per_day: bool = False
    """A rule that stays true all day (the reorder date reached) is said once a day: the
    second time that day is held by the cap, and the hold is written down once."""


Say = Callable[[Person], Awaitable[Delivered]]


@dataclass(frozen=True, slots=True)
class Message:
    """How to say one trigger's message on WhatsApp: to its person, and to a stand-in."""

    whatsapp: Say
    stand_in: Say | None = None
    """The same thing said to whoever stands in for the patient (the caregiver channel), or
    None when it is his alone to hear."""
    channels: tuple[DeliveryChannel, ...] | None = None
    """This message's own list, when it asked for one; otherwise the type's."""


@dataclass(frozen=True, slots=True)
class Sent:
    """One row a run wrote, with who it was to and the words, for the run's report."""

    delivery: Delivery
    to_name: str | None
    text: str | None


@dataclass(slots=True)
class Run:
    """One evaluation of one profile at one moment. Reads what it needs once."""

    session: AsyncSession
    via: Via
    profile: Profile
    patient: Person | None
    acting: KeyContext
    config: Config
    at: datetime
    report: list[Sent] = field(default_factory=list)
    _state: StateView | None = None
    _whatsapp: bool | None = None
    _deliveries: list[Delivery] | None = None
    _keys: list[Key] | None = None
    _ladders: list[Ladder] | None = None
    _taps: tuple[list[DoseTaken], dict[uuid.UUID, str]] | None = None
    _scopes: dict[uuid.UUID, frozenset[Scope]] = field(default_factory=dict)
    _said_no: dict[uuid.UUID, bool] = field(default_factory=dict)
    said_language: str | None = None
    """His language as his settings say it (`his_language`), read once for the run."""

    @property
    def local(self) -> datetime:
        return self.at.astimezone(REGION_TZ[self.acting.region])

    @property
    def day(self) -> str:
        return self.local.date().isoformat()

    @property
    def language(self) -> str:
        """His language: his settings' (the one read, `onboarding.settings.his_language`)."""
        return language_of(self.said_language or self.profile.language)

    def language_for(self, person: Person) -> str:
        """The language to say something to this person in: his for him, anyone else's own."""
        if self.patient is not None and person.id == self.patient.id:
            return self.language
        return language_of(person.language)

    async def state(self) -> StateView:
        if self._state is None:
            self._state = await current_state(self.session, context=self.acting)
        return self._state

    def forget_state(self) -> None:
        """Something this run did moved State (the morning card's refresh): read it again."""
        self._state = None

    async def whatsapp_agreed(self) -> bool:
        """Whether the patient's WHATSAPP consent is in force, to today's words."""
        if self._whatsapp is None:
            wanted = current_version(ConsentPurpose.WHATSAPP)
            rows = await active_consents(self.session, context=self.acting)
            self._whatsapp = any(
                row.purpose is ConsentPurpose.WHATSAPP and row.text_version == wanted
                for row in rows
            )
        return self._whatsapp

    async def said_no_to_whatsapp(self, person: Person) -> bool:
        """Whether this person answered no to WhatsApp messages from Nura (#163)."""
        if person.id not in self._said_no:
            self._said_no[person.id] = await said_no(
                self.session, context=self.acting, person_id=person.id, channel=Channel.SYSTEM
            )
        return self._said_no[person.id]

    async def deliveries(self) -> list[Delivery]:
        if self._deliveries is None:
            self._deliveries = list(
                await audited_read(
                    self.session,
                    Delivery,
                    self.acting,
                    Scope.SEND,
                    where=(Delivery.due_at > self.at - LOOK_BACK,),
                    channel=Channel.SYSTEM,
                )
            )
        return self._deliveries

    async def ladders(self) -> list[Ladder]:
        """The ladders of the last two days, open or closed: what is climbing, and which
        actions already had one."""
        if self._ladders is None:
            self._ladders = list(
                await audited_read(
                    self.session,
                    Ladder,
                    self.acting,
                    Scope.SEND,
                    where=(Ladder.started_at > self.at - timedelta(days=2),),
                    channel=Channel.SYSTEM,
                )
            )
        return self._ladders

    async def taps(self) -> tuple[list[DoseTaken], dict[uuid.UUID, str]]:
        """The Taken taps of the last week, and each line's generic: a tap belongs to the
        medicine, not to the version of the line (as `medicines.service.today` reads it)."""
        if self._taps is None:
            lines = await audited_read(
                self.session, MedicationLine, self.acting, Scope.MEDICINES, channel=Channel.SYSTEM
            )
            taken = await audited_read(
                self.session,
                DoseTaken,
                self.acting,
                Scope.MEDICINES,
                where=(DoseTaken.taken_at > self.at - LOOK_BACK,),
                channel=Channel.SYSTEM,
            )
            self._taps = (list(taken), {line.id: line.generic for line in lines})
        return self._taps

    async def live_keys(self) -> list[Key]:
        if self._keys is None:
            keys = await list_keys(self.session, context=self.acting)
            self._keys = sorted(
                (key for key in keys if key.is_active(self.at)), key=lambda k: as_utc(k.granted_at)
            )
        return self._keys

    async def person(self, person_id: uuid.UUID) -> Person | None:
        return await self.session.get(Person, person_id)

    async def scopes_of(self, person: Person) -> frozenset[Scope]:
        """What this person's key opens on this profile now, "only me" taken out; everything
        for the owner; nothing for someone who holds nothing."""
        if person.id not in self._scopes:
            if person.id == self.profile.owner_person_id:
                self._scopes[person.id] = ALL_SCOPES
            elif not await holds_the_profile(
                self.session, profile_id=self.profile.id, person_id=person.id
            ):
                self._scopes[person.id] = frozenset()
            else:
                context = await resolve_key_context(
                    self.session,
                    region=self.acting.region,
                    person_id=person.id,
                    profile_id=self.profile.id,
                    while_closing=True,
                )
                self._scopes[person.id] = context.scopes
        return self._scopes[person.id]


async def _his_language(session: AsyncSession, context: KeyContext) -> str:
    # Imported here: `app.onboarding` wires its plan at import, and the plan reaches delivery.
    from app.onboarding.settings import his_language

    return await his_language(session, context=context)


async def open_run(session: AsyncSession, *, via: Via, profile_id: uuid.UUID, at: datetime) -> Run:
    """A run for this profile at this moment, acting as its owner — or, before he claims
    it, as the steward holding it for him (there is then no patient to send to)."""
    profile = await session.get(Profile, profile_id)
    if profile is None or profile.region is not via.settings.region:
        raise NoOneToActFor(f"no profile {profile_id} here")
    patient: Person | None = None
    if profile.owner_person_id is not None:
        patient = await session.get(Person, profile.owner_person_id)
        acting_id = profile.owner_person_id
    else:
        steward = await session.scalar(
            select(Stewardship).where(
                Stewardship.profile_id == profile.id, Stewardship.closed_at.is_(None)
            )
        )
        if steward is None:
            raise NoOneToActFor(f"profile {profile_id} has nobody to act for it")
        acting_id = steward.steward_person_id
    # Nura's own reach, with the reach of the person it acts for: its reads and writes are
    # the system's on the trail, never the patient's (`keys.context.as_the_system`).
    acting = as_the_system(
        await resolve_key_context(
            session,
            region=via.settings.region,
            person_id=acting_id,
            profile_id=profile.id,
            while_closing=True,
        )
    )
    settings = await audited_read(
        session,
        DeliverySettings,
        acting,
        Scope.PROFILE,
        order_by=(DeliverySettings.set_at.desc(),),
        limit=1,
        channel=Channel.SYSTEM,
    )
    routine = await current_routine(session, context=acting)
    breakfast = await breakfast_time(session, context=acting)
    return Run(
        said_language=await _his_language(session, acting),
        session=session,
        via=via,
        profile=profile,
        patient=patient,
        acting=acting,
        config=config_of(settings[0] if settings else None, routine, breakfast),
        at=as_utc(at),
    )


def _about(
    run: Run, firing: Firing, person_id: uuid.UUID, rows: Sequence[Delivery]
) -> list[Delivery]:
    """Earlier rows of this firing for this person: to them, or meant for them."""
    found = [
        row
        for row in rows
        if row.dedupe_key == firing.dedupe_key
        and (row.to_person_id == person_id or row.for_person_id == person_id)
    ]
    if firing.per_day:
        found = [row for row in found if row.day == run.day]
    return found


async def stand_in_for(
    run: Run, scope: Scope, *, exclude: Sequence[uuid.UUID] = ()
) -> Recipient | None:
    """Who stands in for the patient now: whoever the roster puts on duty, else the first
    chief — the first whose key covers `scope`."""
    for duty in await who_is_on_duty(run.session, context=run.acting, at=run.at):
        if duty.person_id in exclude:
            continue
        person = await run.person(duty.person_id)
        if person is not None and scope in await run.scopes_of(person):
            return Recipient(person, "on_duty")
    for key in await run.live_keys():
        if key.role is not KeyRole.CHIEF or key.holder_person_id in exclude:
            continue
        person = await run.person(key.holder_person_id)
        if person is not None and scope in await run.scopes_of(person):
            return Recipient(person, "chief")
    return None


async def _no_whatsapp(run: Run, person: Person, type: TriggerType) -> str | None:
    """Why this person cannot be sent this on WhatsApp, if they cannot. His WhatsApp agreement
    is for messages to him (#143); anyone else is told under the key his agreement to let
    them in rests on, whose scope was checked for this message before any channel — and, for
    anything but an alert, only while his agreement stands (#163). Nobody who said no to
    WhatsApp is sent it, an alert included. The send door checks the same (`send`)."""
    if not person.phone_e164:
        return "no number"
    to_him = run.patient is not None and person.id == run.patient.id
    if to_him:
        return None if await run.whatsapp_agreed() else "not agreed"
    if await run.said_no_to_whatsapp(person):
        return "said no"
    if not is_alert(type) and not await run.whatsapp_agreed():
        return "not agreed"
    return None


async def write(
    run: Run,
    firing: Firing,
    to: Recipient | None,
    outcome: DeliveryOutcome,
    *,
    via: DeliveryChannel | None = None,
    template_name: str | None = None,
    message_id: uuid.UUID | None = None,
    reason: str | None = None,
    passed_over: Sequence[str] = (),
    rung: int | None = None,
    ladder: Ladder | None = None,
    for_person: Person | None = None,
    text: str | None = None,
    row_id: uuid.UUID | None = None,
) -> Delivery:
    """The row for one attempt, and the SHARE when it reached a person."""
    rule = RULES[firing.type]
    row = await audited_write(
        run.session,
        Delivery,
        run.acting,
        rule.scope,
        channel=Channel.SYSTEM,
        id=row_id or uuid.uuid4(),
        trigger_kind=rule.kind,
        trigger_type=firing.type,
        category=rule.category,
        scope=rule.scope,
        rule=rule.rule,
        dedupe_key=firing.dedupe_key,
        why=dict(firing.why),
        to_person_id=None if to is None else to.person.id,
        for_person_id=None if for_person is None else for_person.id,
        standing=None if to is None else to.standing,
        rung=rung,
        ladder_id=None if ladder is None else ladder.id,
        via=via,
        template_name=template_name,
        outcome=outcome,
        reason=reason,
        passed_over=list(passed_over),
        message_id=message_id,
        day=run.day,
        due_at=run.at,
    )
    if outcome is DeliveryOutcome.SENT and to is not None:
        await record_share(
            run.session,
            context=run.acting,
            scope=rule.scope,
            target=Delivery.__tablename__,
            # WhatsApp only for what went there; a push and the in-app notice are the app's.
            channel=Channel.WHATSAPP
            if via in (DeliveryChannel.WHATSAPP, DeliveryChannel.CAREGIVER)
            else Channel.APP,
            shared_with_person_id=to.person.id,
            target_id=row.id,
        )
    (await run.deliveries()).append(row)
    run.report.append(
        Sent(delivery=row, to_name=None if to is None else to.person.display_name, text=text)
    )
    return row


async def deliver(
    run: Run,
    firing: Firing,
    to: Recipient,
    message: Message,
    *,
    rung: int | None = None,
    ladder: Ladder | None = None,
) -> Delivery | None:
    """Send one trigger's message to one person, or write down why not. None when it had
    already reached them (or its hold was already written down) and nothing new happened."""
    rule = RULES[firing.type]
    earlier = _about(run, firing, to.person.id, await run.deliveries())

    async def hold(outcome: DeliveryOutcome, reason: str) -> Delivery | None:
        if any(row.outcome is outcome for row in earlier):
            return None
        return await write(run, firing, to, outcome, reason=reason, rung=rung, ladder=ladder)

    if any(row.outcome is DeliveryOutcome.SENT for row in earlier):
        return await hold(DeliveryOutcome.CAPPED, "once a day") if firing.per_day else None
    if rule.scope not in await run.scopes_of(to.person):
        return await hold(DeliveryOutcome.NO_SCOPE, f"key does not cover {rule.scope.value}")
    if rule.quiet and run.config.is_quiet(run.local):
        return await hold(DeliveryOutcome.QUIET, "quiet hours")
    cap = run.config.cap_for(firing.type)
    if cap is not None:
        sent_today = [
            row
            for row in await run.deliveries()
            if row.day == run.day
            and row.trigger_type is firing.type
            and row.to_person_id == to.person.id
            and row.outcome is DeliveryOutcome.SENT
        ]
        if len(sent_today) >= cap:
            return await hold(DeliveryOutcome.CAPPED, f"{cap} a day")

    if is_alert(firing.type):
        return await _every_way(run, firing, to, message, rung=rung, ladder=ladder)
    passed: list[str] = []
    for channel in message.channels or run.config.channels_for(firing.type):
        if channel is DeliveryChannel.APP_PUSH:
            pushed = await _by_push(run, firing, to, passed, rung=rung, ladder=ladder)
            if pushed is not None:
                return pushed
            continue
        if channel is DeliveryChannel.WHATSAPP:
            said = await _by_whatsapp(run, firing, to, message, passed, rung=rung, ladder=ladder)
            if said is not None:
                return said
            continue
        if channel is not DeliveryChannel.CAREGIVER:
            continue
        # The caregiver: what the patient could not be reached with goes to who stands in.
        if message.stand_in is None or to.standing != "patient":
            passed.append("caregiver: not for this message")
            continue
        stand_in = await stand_in_for(run, rule.scope, exclude=(to.person.id,))
        if stand_in is None:
            passed.append("caregiver: nobody to stand in")
            continue
        why_not = await _no_whatsapp(run, stand_in.person, firing.type)
        if why_not is not None:
            passed.append(f"caregiver: {why_not}")
            continue
        try:
            sent = await message.stand_in(stand_in.person)
        except Refusal as refusal:
            passed.append(f"caregiver: {type(refusal).__name__}")
            continue
        return await write(
            run,
            firing,
            stand_in,
            DeliveryOutcome.SENT,
            via=channel,
            template_name=sent.template_name,
            message_id=sent.message_id,
            reason=f"for the {to.standing}",
            passed_over=passed,
            rung=rung,
            ladder=ladder,
            for_person=to.person,
            text=sent.text,
        )
    if any(row.outcome is DeliveryOutcome.NO_CHANNEL for row in earlier):
        return None
    return await write(
        run, firing, to, DeliveryOutcome.NO_CHANNEL, passed_over=passed, rung=rung, ladder=ladder
    )


async def _by_push(
    run: Run,
    firing: Firing,
    to: Recipient,
    passed: list[str],
    *,
    rung: int | None,
    ladder: Ladder | None,
) -> Delivery | None:
    """The app push, when the person has a device: its row. Else None, and `passed` says why."""
    push = run.via.providers.push
    if not await push.reachable(run.session, run.acting, to.person.id):
        passed.append("app_push: no device")
        return None
    line = PUSH_LINE[run.language_for(to.person)]
    # The push says only the line and an id the app opens: the card on his feed, or the
    # nudge (`GET /profiles/{id}/nudges?day=`), when the trigger names one; else this
    # delivery's own row. No health word rides it.
    row_id = uuid.uuid4()
    ref = str(firing.why.get("feed_item_id") or firing.why.get("nudge_id") or row_id)
    try:
        await push.push(run.session, run.acting, to.person.id, line, ref=ref)
    except NoDevice:
        # Every device the push service knew of has gone (404, 410): the next channel.
        passed.append("app_push: gone")
        return None
    return await write(
        run,
        firing,
        to,
        DeliveryOutcome.SENT,
        via=DeliveryChannel.APP_PUSH,
        passed_over=list(passed),
        rung=rung,
        ladder=ladder,
        text=line,
        row_id=row_id,
    )


async def _by_whatsapp(
    run: Run,
    firing: Firing,
    to: Recipient,
    message: Message,
    passed: list[str],
    *,
    rung: int | None,
    ladder: Ladder | None,
) -> Delivery | None:
    """The WhatsApp message, when this person may be sent it: its row. Else None, and
    `passed` says why."""
    why_not = await _no_whatsapp(run, to.person, firing.type)
    if why_not is not None:
        passed.append(f"whatsapp: {why_not}")
        return None
    try:
        sent = await message.whatsapp(to.person)
    except Refusal as refusal:
        passed.append(f"whatsapp: {type(refusal).__name__}")
        return None
    return await write(
        run,
        firing,
        to,
        DeliveryOutcome.SENT,
        via=DeliveryChannel.WHATSAPP,
        template_name=sent.template_name,
        message_id=sent.message_id,
        passed_over=list(passed),
        rung=rung,
        ladder=ladder,
        text=sent.text,
    )


async def _every_way(
    run: Run,
    firing: Firing,
    to: Recipient,
    message: Message,
    *,
    rung: int | None,
    ladder: Ladder | None,
) -> Delivery:
    """An alert, every way this person can be reached (#162): the app push when they have a
    device and WhatsApp where they may be sent it, a row for each; then, whatever carried it,
    the notice on their family page, which is what their "I'm on it" answers. When no phone
    was reached, a NO_CHANNEL row says so first. No setting changes any of it. The first row
    that reached their phone, else the notice."""
    passed: list[str] = []
    carried: list[Delivery] = []
    for channel in run.config.channels_for(firing.type):
        row: Delivery | None = None
        if channel is DeliveryChannel.APP_PUSH:
            row = await _by_push(run, firing, to, passed, rung=rung, ladder=ladder)
        elif channel is DeliveryChannel.WHATSAPP:
            row = await _by_whatsapp(run, firing, to, message, passed, rung=rung, ladder=ladder)
        if row is not None:
            carried.append(row)
    if not carried:
        await write(
            run,
            firing,
            to,
            DeliveryOutcome.NO_CHANNEL,
            passed_over=passed,
            rung=rung,
            ladder=ladder,
        )
    notice = await write(
        run,
        firing,
        to,
        DeliveryOutcome.SENT,
        via=DeliveryChannel.IN_APP,
        reason="on their family page",
        passed_over=passed,
        rung=rung,
        ladder=ladder,
    )
    return carried[0] if carried else notice
