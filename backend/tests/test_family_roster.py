"""E12-03: the duty roster and task assignment.

    Tasks assignable to siblings and helper; roster drives escalation and logistics.

On-duty resolution across midnight and time zones, on the patient's wall clock; a task's
done is the doer's own tap, audited; a task in red words is refused before it is kept.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.family.common import NotAChief, NotPlainWords
from app.family.models import RosterSlot
from app.family.roster import (
    AlreadyDone,
    NotOnThisProfile,
    NotTheDoer,
    add_slot,
    add_task,
    end_slot,
    mark_task_done,
    my_tasks,
    roster,
    slot_covers,
    task_done_draft,
    task_done_draft_for,
    tasks,
    who_is_on_duty,
)
from app.keys.confirm import confirm
from app.keys.scopes import KeyRole, Scope
from app.regions import REGION_TZ, Region
from tests.family_support import MONDAY, household

SGT = REGION_TZ[Region.SG]


def _slot(**values: object) -> RosterSlot:
    base: dict[str, object] = {
        "person_id": uuid.uuid4(),
        "role": KeyRole.CAREGIVER,
        "weekdays": [4],  # Friday
        "from_time": time(22, 0),
        "to_time": time(6, 0),
    }
    return RosterSlot(**{**base, **values})  # type: ignore[arg-type]


def test_a_slot_past_midnight_covers_the_small_hours_of_the_next_day() -> None:
    friday_night = _slot()
    assert slot_covers(friday_night, datetime(2026, 9, 11, 22, 0, tzinfo=SGT))  # Fri 22:00
    assert slot_covers(friday_night, datetime(2026, 9, 12, 3, 0, tzinfo=SGT))  # Sat 03:00
    assert not slot_covers(friday_night, datetime(2026, 9, 11, 21, 59, tzinfo=SGT))
    assert not slot_covers(friday_night, datetime(2026, 9, 12, 6, 0, tzinfo=SGT))  # Sat 06:00
    assert not slot_covers(friday_night, datetime(2026, 9, 13, 3, 0, tzinfo=SGT))  # Sun 03:00
    # A slot for every day in a date range, with no weekdays named.
    fortnight = _slot(
        weekdays=None,
        starts_on=date(2026, 9, 14),
        ends_on=date(2026, 9, 27),
        from_time=time(8, 0),
        to_time=time(20, 0),
    )
    assert slot_covers(fortnight, datetime(2026, 9, 20, 12, 0, tzinfo=SGT))
    assert not slot_covers(fortnight, datetime(2026, 9, 13, 12, 0, tzinfo=SGT))
    assert not slot_covers(fortnight, datetime(2026, 9, 20, 20, 0, tzinfo=SGT))


async def test_who_is_on_duty_reads_the_patients_wall_clock(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    await add_slot(
        sg,
        context=mei,
        person_id=h.mei.id,
        role=KeyRole.CHIEF,
        weekdays=[0, 1, 2, 3, 4],
        from_time=time(8, 0),
        to_time=time(20, 0),
    )
    weekend = await add_slot(
        sg,
        context=mei,
        person_id=h.kit.id,
        role=KeyRole.CAREGIVER,
        weekdays=[5, 6],
        from_time=time(0, 0),
        to_time=time(23, 59),
    )
    assert len(await roster(sg, context=mei)) == 2

    # Saturday 17:00 UTC is Sunday 01:00 on Pa's wall: the weekend, so Kit.
    sunday_small_hours = datetime(2026, 9, 12, 17, 0, tzinfo=UTC)
    assert [d.person_id for d in await who_is_on_duty(sg, context=mei, at=sunday_small_hours)] == [
        h.kit.id
    ]
    # The same instant written on a Californian clock is the same answer.
    pacific = sunday_small_hours.astimezone(timezone(timedelta(hours=-7)))
    assert [d.person_id for d in await who_is_on_duty(sg, context=mei, at=pacific)] == [h.kit.id]
    # Monday 10:00 on his wall (the frozen clock): Mei, by the clock, with no `at` given.
    assert [d.person_id for d in await who_is_on_duty(sg, context=mei)] == [h.mei.id]
    # Monday 21:00 on his wall: nobody.
    assert await who_is_on_duty(sg, context=mei, at=datetime(2026, 9, 14, 13, 0, tzinfo=UTC)) == []

    await end_slot(sg, context=mei, slot_id=weekend.id)
    assert await who_is_on_duty(sg, context=mei, at=sunday_small_hours) == []
    # A caregiver key without the family scope does not read the roster.
    from app.keys.context import OutOfScope

    siti = await h.ctx(sg, h.siti)
    with pytest.raises(OutOfScope):
        await who_is_on_duty(sg, context=siti)
    kit = await h.ctx(sg, h.kit)
    with pytest.raises(NotAChief):
        await add_slot(
            sg,
            context=kit,
            person_id=h.kit.id,
            role=KeyRole.CAREGIVER,
            weekdays=[0],
            from_time=time(8, 0),
            to_time=time(9, 0),
        )


async def test_a_task_is_done_by_the_person_it_names_and_by_nobody_else(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    task = await add_task(
        sg,
        context=mei,
        what="buy the water pill",
        assigned_person_id=h.siti.id,
        due_at=MONDAY + timedelta(days=1),
    )
    assert task.what == "buy the water pill" and not task.is_done

    # The chief cannot tap it for her: the draft is hers to mint, and the tap hers to make.
    with pytest.raises(NotTheDoer):
        await task_done_draft_for(sg, context=mei, task_id=task.id)
    with pytest.raises(NotTheDoer):
        await mark_task_done(
            sg,
            context=mei,
            task_id=task.id,
            confirmation_id=(await confirm(sg, mei, task_done_draft(task.id))).id,
        )
    # Kit, a caregiver, is not the doer either.
    kit = await h.ctx(sg, h.kit)
    with pytest.raises(NotTheDoer):
        await task_done_draft_for(sg, context=kit, task_id=task.id)

    # Siti holds a helper key — no family scope — and still sees and closes her own task.
    siti = await h.ctx(sg, h.siti)
    assert Scope.FAMILY not in siti.scopes
    assert [t.id for t in await my_tasks(sg, context=siti)] == [task.id]
    draft = await task_done_draft_for(sg, context=siti, task_id=task.id)
    yes = await confirm(sg, siti, draft)
    done = await mark_task_done(sg, context=siti, task_id=task.id, confirmation_id=yes.id)
    assert done.done_by_person_id == h.siti.id and done.done_at == MONDAY
    with pytest.raises(AlreadyDone):
        await task_done_draft_for(sg, context=siti, task_id=task.id)

    # On the trail in her name, and the refused taps in theirs.
    pa = await h.ctx(sg, h.pa)
    lines = await read_audit(sg, context=pa)
    assert any(
        e.actor_person_id == h.siti.id
        and e.action is Action.WRITE
        and e.target == "task"
        and e.target_id == task.id
        and e.outcome is Outcome.ALLOWED
        for e in lines
    )
    refused = {
        (e.actor_person_id, e.refused_because) for e in lines if e.outcome is Outcome.REFUSED
    }
    assert (h.mei.id, "NotTheDoer") in refused and (h.kit.id, "NotTheDoer") in refused
    assert [t.is_done for t in await tasks(sg, context=mei)] == [True]
    assert await tasks(sg, context=mei, open_only=True) == []


async def test_a_task_reaches_him_so_it_is_in_plain_words_and_names_someone_on_the_profile(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    with pytest.raises(NotPlainWords) as refused:
        await add_task(sg, context=mei, what="follow-up with Dr Tan", assigned_person_id=h.kit.id)
    assert refused.value.findings
    stranger = uuid.uuid4()
    with pytest.raises(NotOnThisProfile):
        await add_task(sg, context=mei, what="drive Pa on Thursday", assigned_person_id=stranger)
    kit = await h.ctx(sg, h.kit)
    with pytest.raises(NotAChief):
        await add_task(sg, context=kit, what="buy the water pill", assigned_person_id=h.siti.id)
    pa = await h.ctx(sg, h.pa)
    names = {
        e.refused_because for e in await read_audit(sg, context=pa) if e.outcome is Outcome.REFUSED
    }
    assert {"NotPlainWords", "NotOnThisProfile", "NotAChief"} <= names
