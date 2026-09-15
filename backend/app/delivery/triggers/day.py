"""The two rules that close his day on WhatsApp: the check-in and the family notice (E11-01,
E19-03).

    Dad can complete a full day without opening the app.

Two rules of the engine (#121), kept in a module of their own:

- **The check-in** (`check_in_time_reached`): "How are you feeling today?" to him, at his
  check-in time — his settings' (`app.onboarding.settings.reach_of`, the one settings read,
  asked the way the nudge planner asks it: `app.delivery.nudges.engine.check_in_time`), else
  10:00 — once a day, by his own channel list, never in the quiet hours. His "OK", "tired" or
  "pain" back is written down by the inbound path (`inbound._check_in_open`). It does not go
  when he has already said how he is today, nor when the day's check-in nudge asked it: he is
  asked once.
- **The family notice** (`evening_family_notice`): in the evening, to each chief, how many
  things Nura wrote down about him this week — a count, never what they say — on a day
  something was written down. Each chief's count is only what her own key opens, "only me"
  taken out (`Run.scopes_of`), so a count never says a part of his record exists to someone
  it is closed to.

Neither goes on a day with an open red flag (`app.safety.red_flags.open_flags`, the flags that
lead his feed, those held back for a missing fact aside): the flag's own ladder is what
reaches people then, and a question about how he feels, or a count, does not sit beside it.
That hold is written down once a day. Everything else is `deliver`'s: the one cap per person
per day, the quiet hours, the key's scope and the recipient's own channels.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from app.channels.whatsapp.outbound.send import Delivered, send
from app.db import as_utc
from app.delivery.nudges.models import NudgeKind
from app.delivery.triggers.deliver import Firing, Message, Recipient, Run, _about, deliver, write
from app.delivery.triggers.ladder import PATIENT
from app.delivery.triggers.models import DeliveryOutcome, TriggerType
from app.identity.models import Person
from app.keys.scopes import KeyRole, scope_for_subject
from app.memory.semantic import current_facts
from app.regions import REGION_TZ
from app.safety.red_flags import open_flags

CHECK_IN_LATEST = timedelta(hours=3)
"""A check-in not sent by three hours after his check-in time is dropped, never sent late."""
NOTICE_AT = time(20, 0)
"""The family notice: eight in the evening on his wall clock, before the quiet hours."""
NOTICE_LATEST = timedelta(hours=3)
WEEK = timedelta(days=7)
"""The count is of this week, as the approved words say: the last seven days."""

A_FLAG_IS_OPEN = "a red flag is open"
HE_SAID_TODAY = "he said how he is today"
THE_NUDGE_ASKED = "the check-in nudge asked it"


async def run_day(run: Run) -> None:
    """The check-in and the family notice, when their hour has come."""
    await check_in(run)
    await family_notice(run)


async def a_flag_is_open(run: Run) -> bool:
    """Whether a red flag leads his feed now: raised inside its day, not held back."""
    return any(
        flag.suppressed_because is None
        for flag in await open_flags(run.session, context=run.acting)
    )


async def _done_today(run: Run, firing: Firing, person: Person) -> bool:
    """Whether this firing already reached the person today, or its hold was written. The
    run's list holds the rows it read and every row it wrote since (`deliver.write`)."""
    earlier = _about(run, firing, person.id, await run.deliveries())
    return any(
        row.outcome in (DeliveryOutcome.SENT, DeliveryOutcome.SKIPPED) for row in earlier
    )


async def check_in(run: Run) -> None:
    if run.patient is None:
        return
    # Imported here: the planner reads delivery's cap, and delivery reads the planner.
    from app.delivery.nudges.engine import check_in_time

    at = await check_in_time(run.session, context=run.acting)
    due = datetime.combine(run.local.date(), at, REGION_TZ[run.acting.region])
    if not due <= run.at < due + CHECK_IN_LATEST:
        return
    firing = Firing(
        type=TriggerType.CHECK_IN,
        dedupe_key=f"check_in:{run.day}",
        why={"check_in_at": at.isoformat(timespec="minutes")},
    )
    him = Recipient(run.patient, PATIENT)
    if await _done_today(run, firing, run.patient):
        return
    if await a_flag_is_open(run):
        await write(run, firing, him, DeliveryOutcome.SKIPPED, reason=A_FLAG_IS_OPEN)
        return
    if await _he_said_today(run):
        await write(run, firing, him, DeliveryOutcome.SKIPPED, reason=HE_SAID_TODAY)
        return
    if await _the_nudge_asked_today(run):
        await write(run, firing, him, DeliveryOutcome.SKIPPED, reason=THE_NUDGE_ASKED)
        return

    async def say(person: object) -> Delivered:
        assert isinstance(person, Person)
        return await send(
            run.session,
            context=run.acting,
            to_person=person,
            kind="feeling_check_in",
            params={"name": run.profile.display_name},
            provider=run.via.providers.whatsapp,
            number=run.via.number,
            language=run.language,
            state=await run.state(),
        )

    await deliver(run, firing, him, Message(whatsapp=say))


async def _he_said_today(run: Run) -> bool:
    """Whether a feeling of his was written down today, on his wall clock: in the app's
    cloud, or on WhatsApp to an earlier question."""
    told = await current_facts(
        run.session, context=run.acting, subject="feeling", attribute="reported"
    )
    zone = REGION_TZ[run.acting.region]
    return any(as_utc(fact.asserted_at).astimezone(zone).date() == run.local.date() for fact in told)


async def _the_nudge_asked_today(run: Run) -> bool:
    """Whether the day's smart nudge (E17-03) that reached him today was the check-in."""
    assert run.patient is not None
    return any(
        row.trigger_type is TriggerType.NUDGE
        and row.outcome is DeliveryOutcome.SENT
        and row.day == run.day
        and row.to_person_id == run.patient.id
        and (row.why or {}).get("kind") == NudgeKind.CHECK_IN.value
        for row in await run.deliveries()
    )


async def family_notice(run: Run) -> None:
    if run.patient is None:
        return
    zone = REGION_TZ[run.acting.region]
    today = run.local.date()
    due = datetime.combine(today, NOTICE_AT, zone)
    if not due <= run.at < due + NOTICE_LATEST:
        return
    started = datetime.combine(today, time(0), zone)
    written = [
        fact
        for fact in await current_facts(run.session, context=run.acting)
        if as_utc(fact.asserted_at) > run.at - WEEK
    ]
    told: set[object] = set()
    for key in await run.live_keys():
        if key.role is not KeyRole.CHIEF or key.holder_person_id in told:
            continue
        told.add(key.holder_person_id)
        chief = await run.person(key.holder_person_id)
        if chief is None:
            continue
        opens = await run.scopes_of(chief)
        hers = [fact for fact in written if scope_for_subject(fact.subject) in opens]
        if not any(as_utc(fact.asserted_at) >= started for fact in hers):
            continue  # nothing new today that her key opens: nothing to tell her
        firing = Firing(
            type=TriggerType.FAMILY_NOTICE,
            dedupe_key=f"family_notice:{run.day}",
            why={"count": len(hers), "days": WEEK.days},
        )
        to = Recipient(chief, "chief")
        if await _done_today(run, firing, chief):
            continue
        if await a_flag_is_open(run):
            await write(run, firing, to, DeliveryOutcome.SKIPPED, reason=A_FLAG_IS_OPEN)
            continue

        async def say(person: object, count: int = len(hers)) -> Delivered:
            assert isinstance(person, Person)
            return await send(
                run.session,
                context=run.acting,
                to_person=person,
                kind="family_digest",
                params={"name": run.profile.display_name, "count": str(count)},
                provider=run.via.providers.whatsapp,
                number=run.via.number,
                language=run.language_for(person),
                state=await run.state(),
            )

        await deliver(run, firing, to, Message(whatsapp=say))


__all__ = ["CHECK_IN_LATEST", "NOTICE_AT", "check_in", "family_notice", "run_day"]
