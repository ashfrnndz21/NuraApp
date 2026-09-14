"""`run_due`: every trigger due for one profile at one moment, and what became of each (E00-05).

No scheduler lives here, on purpose: the engine is a function of a profile and a moment, so a
test, the checkpoint (`POST /dev/run-triggers`) and the deployment's scheduler all call the
same thing. In a deployment the scheduler is the region's own — EventBridge Scheduler, or cron
on the in-region worker — and calls it for every profile pinned to the region:

    */5 * * * *    for each profile in the region: run_due(profile, at=now)

A red flag does not wait for it: it is escalated the moment it is raised (`escalate_flag`,
from the WhatsApp thread and the feeling cloud); the five-minute run is the net under that —
the rungs after the first, and a flag whose first word could not go.

The order is the safety order: flags first, before anything is ranked or capped; then the
ladders of untapped tablets; then the morning card, the reorder, the pattern, and the events.
Every trigger that fires writes its rule on every `Delivery` row it makes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.audit.models import Channel
from app.channels.whatsapp.outbound.level0 import compose_morning, run_visit_card, send_morning
from app.channels.whatsapp.outbound.send import Delivered, send
from app.channels.whatsapp.templates import language_of
from app.db import as_utc, utcnow
from app.delivery.strings import theirs
from app.delivery.triggers.deliver import (
    Firing,
    Message,
    Recipient,
    Run,
    Sent,
    Via,
    _about,
    deliver,
    open_run,
    stand_in_for,
    write,
)
from app.delivery.triggers.ladder import (
    DOSE_RUNGS,
    PATIENT,
    climb,
    dose_message,
    flag_ladder,
    flag_message,
    medicine_words,
    start,
    tapped_by,
)
from app.delivery.triggers.models import DeliveryChannel, DeliveryOutcome, Subject, TriggerType
from app.delivery.triggers.rules import MORNING_LATEST
from app.errors import Refusal
from app.family.models import PushChannel, ScheduledPush
from app.ingestion.models import ReviewCard
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Dose, Frequency
from app.medicines.service import LineView, active_lines
from app.medicines.strings import say_date
from app.memory.spine import upcoming_appointments
from app.regions import REGION_TZ
from app.safety.red_flags import open_flags

PATTERN_DAYS = 7
PATTERN_AT_LEAST = 3
"""Three untapped tablets in seven days: a count the family is told, never a diagnosis."""


def _line_start(words: str) -> str:
    """His words for a thing, at the start of a line: "The water pill runs out on …"."""
    return words[:1].upper() + words[1:]


class NothingToSay(Refusal):
    """The thing the message was about is no longer there."""


@dataclass(frozen=True, slots=True)
class Report:
    """What one run did: every Delivery row it wrote, in order."""

    at: datetime
    day: str
    sent: tuple[Sent, ...]


async def run_due(
    session: AsyncSession,
    *,
    via: Via,
    profile_id: uuid.UUID,
    at: datetime | None = None,
) -> Report:
    """Evaluate every trigger for this profile at `at` (now when not given)."""
    run = await open_run(session, via=via, profile_id=profile_id, at=at or utcnow())
    await _flags(run)
    if run.patient is not None and run.acting.allows(Scope.MEDICINES):
        lines = await active_lines(
            session,
            context=run.acting,
            registry=via.providers.drug_registry,
            language=run.language,
        )
        await _doses(run, lines)
        await _morning(run)
        await _reorder(run, lines)
        await _pattern(run, lines)
    await _visit_tomorrow(run)
    await _papers(run)
    await _family_messages(run)
    return Report(at=run.at, day=run.day, sent=tuple(run.report))


# --- alerts first ----------------------------------------------------------------------------------


async def _flags(run: Run) -> None:
    """Every open flag not held back: its ladder, started if it has none, climbed."""
    for flag in await open_flags(run.session, context=run.acting):
        if flag.suppressed_because is not None:
            continue
        ladder = await flag_ladder(run, flag, exclude=())
        await climb(run, ladder, flag_message(run, flag), TriggerType.FLAG)


# --- tablets ---------------------------------------------------------------------------------------


def _scheduled(view: LineView) -> Sequence[str]:
    dose = Dose.from_json(view.line.dose)
    if dose.frequency in (Frequency.WEEKLY, Frequency.PRN):
        return ()
    return [anchor.value for anchor in dose.scheduled_anchors]


async def _doses(run: Run, lines: Sequence[LineView]) -> None:
    """A tablet whose window closed today with no Taken starts its ladder; every open
    ladder climbs (and yesterday's lapse)."""
    taps, generic_of = await run.taps()
    zone = REGION_TZ[run.acting.region]
    today = run.local.date()
    for view in lines:
        for anchor in _scheduled(view):
            opens, closes = run.config.window(today, anchor, zone)
            if run.at < closes or as_utc(view.line.asserted_at) > opens:
                continue
            if tapped_by(run, taps, generic_of, view.line.generic, run.day, anchor) is not None:
                continue
            await start(
                run,
                subject=Subject.DOSE,
                scope=Scope.MEDICINES,
                dedupe_key=f"dose:{view.line.generic}:{anchor}:{run.day}",
                spec=DOSE_RUNGS,
                exclude=(),
                started_at=closes.astimezone(UTC),
                line_id=view.line.id,
                anchor=anchor,
            )
    for ladder in list(await run.ladders()):
        if ladder.subject is not Subject.DOSE or not ladder.is_open or ladder.line_id is None:
            continue
        generic = generic_of.get(ladder.line_id)
        if generic is None:
            continue
        await climb(run, ladder, dose_message(run, ladder, generic), TriggerType.DOSE)


async def _morning(run: Run) -> None:
    """The morning card at the time his routine sets for it (E10-01's `morning_card_at`, tied
    to breakfast), once a day, by his channel (E11-10). Dropped, not sent late, three hours on;
    skipped on a quiet day if he asked."""
    if run.patient is None:
        return
    due = run.config.morning(run.local.date(), REGION_TZ[run.acting.region])
    if not due <= run.at < due + MORNING_LATEST:
        return
    firing = Firing(
        type=TriggerType.MORNING,
        dedupe_key=f"morning:{run.day}",
        why={"morning_card_at": run.config.day.morning_card_at.isoformat(timespec="minutes")},
    )
    earlier = _about(run, firing, run.patient.id, await run.deliveries())
    if any(row.outcome in (DeliveryOutcome.SENT, DeliveryOutcome.SKIPPED) for row in earlier):
        return
    morning = await compose_morning(
        run.session,
        settings=run.via.settings,
        providers=run.via.providers,
        profile_id=run.profile.id,
    )
    run.forget_state()
    firing = Firing(
        type=TriggerType.MORNING,
        dedupe_key=firing.dedupe_key,
        why={**firing.why, "state_id": str(morning.state.id), "quiet_day": morning.quiet},
    )
    him = Recipient(run.patient, PATIENT)
    if morning.quiet and run.config.skip_quiet_days:
        await write(run, firing, him, DeliveryOutcome.SKIPPED, reason="a quiet day, as asked")
        return

    async def say(person: object) -> Delivered:
        return await send_morning(
            run.session, morning, providers=run.via.providers, number=run.via.number
        )

    await deliver(run, firing, him, Message(whatsapp=say))


async def _reorder(run: Run, lines: Sequence[LineView]) -> None:
    """The reorder date reached: the family is told who orders, once a day (E04's count)."""
    assert run.patient is not None
    today = run.local.date()
    for view in lines:
        count = view.count
        if count.basis != "taps" or count.reorder_date is None or count.days_left is None:
            continue
        if count.reorder_date > today:
            continue
        family = await stand_in_for(run, Scope.MEDICINES, exclude=(run.patient.id,))
        if family is None:
            continue
        runs_out = today + timedelta(days=count.days_left)
        firing = Firing(
            type=TriggerType.REORDER,
            dedupe_key=f"reorder:{view.line.id}",
            why={
                "line_id": str(view.line.id),
                "reorder_date": count.reorder_date.isoformat(),
                "days_left": count.days_left,
            },
            per_day=True,
        )
        generic = view.line.generic

        async def say(person: object, generic: str = generic, runs_out: object = runs_out) -> Delivered:
            assert hasattr(person, "language")
            lang = language_of(person.language)
            return await send(
                run.session,
                context=run.acting,
                to_person=person,  # type: ignore[arg-type]
                kind="reorder_family",
                params={
                    "name": run.profile.display_name,
                    "medicine": _line_start(
                        theirs(
                            medicine_words(run.via.providers.drug_registry, generic, lang),
                            run.profile.display_name,
                            lang,
                        )
                    ),
                    "day": say_date(runs_out, lang),  # type: ignore[arg-type]
                },
                provider=run.via.providers.whatsapp,
                number=run.via.number,
                language=lang,
                state=await run.state(),
            )

        await deliver(run, firing, family, Message(whatsapp=say))


async def _pattern(run: Run, lines: Sequence[LineView]) -> None:
    """Three or more tablets with no Taken in seven days: the one on duty is told the count.
    Arithmetic on the taps, never a finding about him."""
    assert run.patient is not None
    taps, generic_of = await run.taps()
    zone = REGION_TZ[run.acting.region]
    today = run.local.date()
    untapped: list[str] = []
    for view in lines:
        for back in range(PATTERN_DAYS):
            day = today - timedelta(days=back)
            for anchor in _scheduled(view):
                opens, closes = run.config.window(day, anchor, zone)
                if closes > run.at or as_utc(view.line.asserted_at) > opens:
                    continue
                if tapped_by(run, taps, generic_of, view.line.generic, day.isoformat(), anchor):
                    continue
                untapped.append(f"{day.isoformat()} {anchor} {view.line.generic}")
    if len(untapped) < PATTERN_AT_LEAST:
        return
    family = await stand_in_for(run, Scope.MEDICINES, exclude=(run.patient.id,))
    if family is None:
        return
    year, week, _ = run.local.isocalendar()
    firing = Firing(
        type=TriggerType.DOSES_UNTAPPED,
        dedupe_key=f"doses_untapped:{year}-W{week:02d}",
        why={"count": len(untapped), "days": PATTERN_DAYS, "untapped": sorted(untapped)[:28]},
    )

    async def say(person: object) -> Delivered:
        assert hasattr(person, "language")
        lang = language_of(person.language)
        return await send(
            run.session,
            context=run.acting,
            to_person=person,  # type: ignore[arg-type]
            kind="doses_count",
            params={"name": run.profile.display_name, "count": str(len(untapped))},
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=lang,
            state=await run.state(),
        )

    await deliver(run, firing, family, Message(whatsapp=say))


# --- events ----------------------------------------------------------------------------------------


async def _visit_tomorrow(run: Run) -> None:
    if run.patient is None or not run.acting.allows(Scope.VISITS):
        return
    coming = await upcoming_appointments(run.session, context=run.acting, at=run.at, limit=1)
    if not coming:
        return
    visit = coming[0]
    zone = REGION_TZ[run.acting.region]
    if as_utc(visit.scheduled_at).astimezone(zone).date() != run.local.date() + timedelta(days=1):
        return
    firing = Firing(
        type=TriggerType.VISIT_TOMORROW,
        dedupe_key=f"visit:{visit.id}",
        why={"appointment_id": str(visit.id)},
    )

    async def say(person: object) -> Delivered:
        sent = await run_visit_card(
            run.session,
            settings=run.via.settings,
            providers=run.via.providers,
            number=run.via.number,
            profile_id=run.profile.id,
        )
        if sent is None:
            raise NothingToSay("the visit is no longer on the spine")
        return sent

    await deliver(run, firing, Recipient(run.patient, PATIENT), Message(whatsapp=say))


async def _papers(run: Run) -> None:
    """A paper read into a review card and waiting for a yes: the chief is told there are
    papers to check, never what they say."""
    if not run.acting.allows(Scope.RECORDS):
        return
    cards = await audited_read(
        run.session,
        ReviewCard,
        run.acting,
        Scope.RECORDS,
        where=(ReviewCard.confirmed_at.is_(None), ReviewCard.created_at > run.at - timedelta(days=1)),
        channel=Channel.SYSTEM,
    )
    if not cards:
        return
    newest = max(cards, key=lambda card: as_utc(card.created_at))
    firing = Firing(
        type=TriggerType.PAPERS,
        dedupe_key=f"papers:{newest.id}",
        why={"review_card_ids": sorted(str(card.id) for card in cards)},
    )

    async def say(person: object) -> Delivered:
        assert hasattr(person, "language")
        lang = language_of(person.language)
        return await send(
            run.session,
            context=run.acting,
            to_person=person,  # type: ignore[arg-type]
            kind="papers_waiting",
            params={"name": run.profile.display_name},
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=lang,
            state=await run.state(),
        )

    for key in await run.live_keys():
        if key.role is not KeyRole.CHIEF:
            continue
        chief = await run.person(key.holder_person_id)
        if chief is not None:
            await deliver(run, firing, Recipient(chief, "chief"), Message(whatsapp=say))


async def _family_messages(run: Run) -> None:
    """A chief's message to him, come due (E12-06): delivered between its moment and its
    end, by the channel she asked for first. The lines are exactly what she previewed."""
    if run.patient is None:
        return
    pushes = await audited_read(
        run.session,
        ScheduledPush,
        run.acting,
        Scope.SEND,
        where=(ScheduledPush.send_at <= run.at, ScheduledPush.expires_at > run.at),
        channel=Channel.SYSTEM,
    )
    for push in pushes:
        composer = await run.person(push.composed_by_person_id)
        first = (
            DeliveryChannel.APP_PUSH
            if push.via_channel is PushChannel.APP
            else DeliveryChannel.WHATSAPP
        )
        channels = (first, *(c for c in (DeliveryChannel.APP_PUSH, DeliveryChannel.WHATSAPP) if c is not first))
        firing = Firing(
            type=TriggerType.FAMILY_MESSAGE,
            dedupe_key=f"family:{push.id}",
            why={"scheduled_push_id": str(push.id), "composed_from_state": str(push.state_id)},
        )

        async def say(person: object, push: ScheduledPush = push, who: str = composer.display_name if composer else "") -> Delivered:
            return await send(
                run.session,
                context=run.acting,
                to_person=person,  # type: ignore[arg-type]
                kind="family_note",
                params={"who": who, "message": "\n".join(push.lines)},
                provider=run.via.providers.whatsapp,
                number=run.via.number,
                language=push.language,
                state=await run.state(),
            )

        await deliver(
            run, firing, Recipient(run.patient, PATIENT), Message(whatsapp=say, channels=channels)
        )


__all__ = ["NothingToSay", "Report", "Via", "run_due"]
