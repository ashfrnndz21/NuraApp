"""E17-05: nudge and check-in metrics — taps per week, the "Fine today" share, acceptance by
kind — for the owner and his chief, in counts only, every read on his trail."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry, Outcome
from app.clock import FrozenClock
from app.delivery.nudges.engine import hand_over, respond
from app.delivery.nudges.metrics import METRICS_TARGET, NotOwnerOrChief, nudge_metrics
from app.delivery.nudges.models import NudgeKind, ResponseKind
from app.medicines.service import record_dose_taken
from app.reasoning.feelings.service import record_tap
from app.safety.red_flags import Feeling
from tests.family_support import household
from tests.feelings_support import REGISTRY, new_medicine
from tests.support import refused_unit


async def test_taps_the_fine_today_share_and_acceptance_by_kind_per_week(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    home = await household(sg)
    owner, mei = await home.ctx(sg, home.pa), await home.ctx(sg, home.mei)
    added = await new_medicine(sg, owner)
    clock.step(timedelta(days=8))
    await record_dose_taken(sg, context=owner, line_id=added.line.id)
    for word in (Feeling.DIZZY, Feeling.FINE, Feeling.FINE):
        await record_tap(sg, context=owner, word=word, registry=REGISTRY)
    _, nudge = await hand_over(sg, context=owner, registry=REGISTRY)
    await respond(sg, context=owner, nudge_id=nudge.id, kind=ResponseKind.ACCEPTED)

    metrics = await nudge_metrics(sg, context=mei, weeks=2)
    this_week, last_week = metrics.weeks
    assert this_week.week == "2026-W37" and this_week.starts_on.isoformat() == "2026-09-07"
    assert (this_week.taps, this_week.fine_today, this_week.fine_share) == (3, 2, 0.67)
    counts = this_week.nudges[nudge.kind]
    assert (counts.handed_over, counts.accepted, counts.ignored, counts.acceptance) == (
        1,
        1,
        0,
        1.0,
    )
    assert last_week.taps == 0 and last_week.fine_share is None


async def test_ignored_streaks_and_the_kinds_resting(sg: AsyncSession, clock: FrozenClock) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    added = await new_medicine(sg, owner)
    clock.step(timedelta(days=8))
    for _ in range(2):
        await record_dose_taken(sg, context=owner, line_id=added.line.id)
        await hand_over(sg, context=owner, registry=REGISTRY)
        clock.step(timedelta(days=1))
    metrics = await nudge_metrics(sg, context=owner)
    assert metrics.ignored_streaks[NudgeKind.RECOGNITION] == 2
    assert metrics.resting == (NudgeKind.RECOGNITION,)
    assert metrics.weeks[0].nudges[NudgeKind.RECOGNITION].ignored == 2


async def test_the_metrics_are_the_owners_and_his_chiefs_and_the_refusal_is_on_his_trail(
    sg: AsyncSession,
) -> None:
    home = await household(sg)
    kit = await home.ctx(sg, home.kit)
    async with refused_unit(sg, NotOwnerOrChief):
        await nudge_metrics(sg, context=kit)
    refused = (
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.target == METRICS_TARGET, AuditEntry.outcome == Outcome.REFUSED
            )
        )
    ).all()
    assert [entry.refused_because for entry in refused] == ["NotOwnerOrChief"]
    await nudge_metrics(sg, context=await home.ctx(sg, home.mei))
    allowed = (
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.target == METRICS_TARGET, AuditEntry.outcome == Outcome.ALLOWED
            )
        )
    ).all()
    assert len(allowed) == 1
