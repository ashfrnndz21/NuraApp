"""The duty roster and the tasks (E12-03).

A `RosterSlot` says when one person is on duty, on the clock on the patient's wall; a
`Task` is one thing for one person to do. `who_is_on_duty` answers the escalation ladder
(E11, E19) and the feed's caregiver gate card: who is on duty at this moment, across
midnight and across the causeway. A task is done when the person it names taps it — the
yes is minted and spent by the doer, and the service refuses anyone else — and that tap is
on the trail in the doer's name.

The roster and the tasks are read and written under the family scope by the owner and the
chief. A person also reads the tasks that name her, and closes them, under the footing
every key holds (`Scope.PROFILE`): the helper whose key opens only the medicines still
sees "buy the water pill" with her name on it, and nothing else on the roster.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.drafts import TaskDoneDraft
from app.errors import Refusal
from app.family.common import NotPlainWords, a_chief
from app.family.models import TASK_DONE_IN_PROGRESS, Errand, RosterSlot, Task
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext, holds_the_profile
from app.keys.scopes import KeyRole, Scope
from app.memory.models import short_label
from app.regions import REGION_TZ
from app.safety.plain_words import verify

ROSTER_TARGET = RosterSlot.__tablename__
TASK_TARGET = Task.__tablename__


class NotOnThisProfile(Refusal):
    """A person on the roster, or given a task, holds a key to the profile or owns it."""


class NotADuty(Refusal):
    """A slot names at least one weekday or a date range, with a start and an end time."""


class NoSuchSlot(Refusal):
    """There is no such slot on this roster."""


class NoSuchTask(Refusal):
    """There is no such task on this profile."""


class NotTheDoer(Refusal):
    """A task is done by the person it names, and by nobody else."""


class AlreadyDone(Refusal):
    """This task is already done."""


async def _on_this_profile(
    session: AsyncSession, context: KeyContext, person_id: uuid.UUID
) -> None:
    if not await holds_the_profile(session, profile_id=context.profile_id, person_id=person_id):
        raise NotOnThisProfile(f"person {person_id} holds nothing on this profile")


# --- the roster ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OnDuty:
    slot_id: uuid.UUID
    person_id: uuid.UUID
    role: KeyRole


def _covers_day(slot: RosterSlot, day: date) -> bool:
    if slot.weekdays is not None and day.weekday() not in slot.weekdays:
        return False
    if slot.starts_on is not None and day < slot.starts_on:
        return False
    return not (slot.ends_on is not None and day > slot.ends_on)


def slot_covers(slot: RosterSlot, local: datetime) -> bool:
    """Whether this slot is on duty at `local`, a moment on the patient's wall clock.

    A slot whose end is at or before its start runs past midnight: it covers its own day
    from the start onwards, and the next day up to the end. So Friday 22:00 to 06:00 is on
    duty at Saturday 03:00 because Friday is one of its days, and not at Saturday 07:00.
    """
    now = local.time().replace(tzinfo=None)
    today = local.date()
    if slot.from_time < slot.to_time:
        return _covers_day(slot, today) and slot.from_time <= now < slot.to_time
    starts_today = _covers_day(slot, today) and now >= slot.from_time
    started_yesterday = _covers_day(slot, today - timedelta(days=1)) and now < slot.to_time
    return starts_today or started_yesterday


@audited(Action.WRITE, Scope.FAMILY, ROSTER_TARGET)
async def add_slot(
    session: AsyncSession,
    *,
    context: KeyContext,
    person_id: uuid.UUID,
    role: KeyRole,
    from_time: time,
    to_time: time,
    weekdays: Sequence[int] | None = None,
    starts_on: date | None = None,
    ends_on: date | None = None,
) -> RosterSlot:
    """Put one person on duty: these weekdays or these dates, between these times of his day."""
    a_chief(context)
    if weekdays is None and starts_on is None and ends_on is None:
        raise NotADuty("a slot names weekdays or a date range")
    if weekdays is not None and (not weekdays or any(d not in range(7) for d in weekdays)):
        raise NotADuty("weekdays are 0 (Monday) to 6 (Sunday)")
    if starts_on is not None and ends_on is not None and ends_on < starts_on:
        raise NotADuty("a date range ends after it starts")
    if from_time == to_time:
        raise NotADuty("a slot starts and ends at different times")
    await _on_this_profile(session, context, person_id)
    return await audited_write(
        session,
        RosterSlot,
        context,
        Scope.FAMILY,
        person_id=person_id,
        role=role,
        weekdays=sorted(set(weekdays)) if weekdays is not None else None,
        starts_on=starts_on,
        ends_on=ends_on,
        from_time=from_time.replace(tzinfo=None),
        to_time=to_time.replace(tzinfo=None),
        added_by_person_id=context.person_id,
        added_at=utcnow(),
    )


@audited(Action.WRITE, Scope.FAMILY, ROSTER_TARGET)
async def end_slot(session: AsyncSession, *, context: KeyContext, slot_id: uuid.UUID) -> RosterSlot:
    """Take a slot off the roster. The row stays, ended."""
    a_chief(context)
    found = await audited_read(
        session, RosterSlot, context, Scope.FAMILY, where=(RosterSlot.id == slot_id,)
    )
    if not found:
        raise NoSuchSlot(f"no slot {slot_id} on this roster")
    slot = found[0]
    if slot.ended_at is None:
        slot.ended_at = utcnow()
        await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=ROSTER_TARGET,
        target_id=slot.id,
        rows=1,
    )
    return slot


async def roster(session: AsyncSession, *, context: KeyContext) -> list[RosterSlot]:
    """Every open slot, oldest first."""
    moment = utcnow()
    found = await audited_read(session, RosterSlot, context, Scope.FAMILY)
    return sorted(
        (slot for slot in found if slot.is_open(moment)), key=lambda slot: as_utc(slot.added_at)
    )


async def who_is_on_duty(
    session: AsyncSession, *, context: KeyContext, at: datetime | None = None
) -> list[OnDuty]:
    """Who is on duty at `at` (now, by the clock, when not given), in roster order.

    `at` is any instant; it is read on the patient's wall clock (`REGION_TZ` of the
    profile's region), so a slot for his evenings means his evenings wherever the caller
    is. The escalation ladder and the caregiver gate card call this.
    """
    moment = at or utcnow()
    local = as_utc(moment).astimezone(REGION_TZ[context.region])
    return [
        OnDuty(slot_id=slot.id, person_id=slot.person_id, role=slot.role)
        for slot in await roster(session, context=context)
        if slot_covers(slot, local)
    ]


# --- the tasks -------------------------------------------------------------------------------


@audited(Action.WRITE, Scope.FAMILY, TASK_TARGET)
async def add_task(
    session: AsyncSession,
    *,
    context: KeyContext,
    what: str,
    assigned_person_id: uuid.UUID,
    due_at: datetime | None = None,
    language: str = "en",
    appointment_id: uuid.UUID | None = None,
    errand: Errand | None = None,
    medication_line_id: uuid.UUID | None = None,
) -> Task:
    """Give one person one thing to do. `what` is a label in plain words — it reaches him
    in the digest and the trail — so it passes the verifier as a phrase before it is kept.

    Except an order task's (`Errand.ORDER`, E04-05): its label names his medicine as its box
    does ("order more amlodipine 5 mg for Pa", licensed drug data the family buys by), for
    the one who buys it, and it never reaches him — the digest says an order task in its own
    words, which name no medicine (`app.family.thread`), and the family's list is not on his
    screens. The only caller that makes one is `app.medicines.reorder.ask_to_order`.

    A task that is part of a visit's logistics names the visit and the errand (E05-03); the
    only caller that does is `app.reasoning.visits.logistics.assign_driver`, on the chief's
    yes. An order task names the medicine line (E04-05); the only caller that does is
    `app.medicines.reorder.ask_to_order`, on his yes. The visit and the line are on this
    profile, or the table refuses them."""
    a_chief(context)
    label = short_label(what)
    if errand is not Errand.ORDER:
        failures = [str(f) for f in verify(label, language, "phrase") if f.severity == "fail"]
        if failures:
            raise NotPlainWords(failures)
    await _on_this_profile(session, context, assigned_person_id)
    return await audited_write(
        session,
        Task,
        context,
        Scope.FAMILY,
        what=label,
        assigned_person_id=assigned_person_id,
        due_at=due_at,
        created_by_person_id=context.person_id,
        created_at=utcnow(),
        appointment_id=appointment_id,
        errand=errand,
        medication_line_id=medication_line_id,
    )


async def tasks(
    session: AsyncSession, *, context: KeyContext, open_only: bool = False
) -> list[Task]:
    """Every task on the profile, oldest first; `open_only` for the ones not done."""
    found = await audited_read(session, Task, context, Scope.FAMILY)
    return sorted(
        (task for task in found if not (open_only and task.is_done)),
        key=lambda task: as_utc(task.created_at),
    )


async def my_tasks(session: AsyncSession, *, context: KeyContext) -> list[Task]:
    """The tasks that name the person asking, under the footing every key holds."""
    found = await audited_read(
        session,
        Task,
        context,
        Scope.PROFILE,
        where=(Task.assigned_person_id == context.person_id,),
    )
    return sorted(found, key=lambda task: as_utc(task.created_at))


def task_done_draft(task_id: uuid.UUID) -> TaskDoneDraft:
    return TaskDoneDraft(task_id=task_id)


@audited(Action.READ, Scope.PROFILE, TASK_TARGET)
async def task_done_draft_for(
    session: AsyncSession, *, context: KeyContext, task_id: uuid.UUID
) -> TaskDoneDraft:
    """The draft a doer mints a yes for: her own task, not yet done. Anyone else's tap
    finds no task (`NotTheDoer`); the read is under the footing every key holds."""
    found = await audited_read(
        session,
        Task,
        context,
        Scope.PROFILE,
        where=(Task.id == task_id, Task.assigned_person_id == context.person_id),
    )
    if not found:
        raise NotTheDoer(f"no task {task_id} names person {context.person_id}")
    if found[0].is_done:
        raise AlreadyDone(f"task {task_id} is already done")
    return task_done_draft(found[0].id)


@audited(Action.WRITE, Scope.PROFILE, TASK_TARGET)
async def mark_task_done(
    session: AsyncSession, *, context: KeyContext, task_id: uuid.UUID, confirmation_id: uuid.UUID
) -> Task:
    """The doer's own tap. The task is read as one of hers — the row names the person
    asking — so anyone else's tap finds no task; the yes is hers alone, for this task, and
    spent last; the row records who and when, once."""
    found = await audited_read(
        session,
        Task,
        context,
        Scope.PROFILE,
        where=(Task.id == task_id, Task.assigned_person_id == context.person_id),
    )
    if not found:
        raise NotTheDoer(f"no task {task_id} names person {context.person_id}")
    task = found[0]
    if task.is_done:
        raise AlreadyDone(f"task {task_id} is already done")
    await consume_confirmation(session, context, confirmation_id, task_done_draft(task.id))
    moment = utcnow()
    session.info[TASK_DONE_IN_PROGRESS] = task.id
    try:
        task.done_at = moment
        task.done_by_person_id = context.person_id
        await session.flush()
    finally:
        session.info.pop(TASK_DONE_IN_PROGRESS, None)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=TASK_TARGET,
        target_id=task.id,
        rows=1,
    )
    return task
