"""E17-03 and E11-07: the smart nudge engine.

The acceptance lines: one nudge a day per profile; never at night; none on a day with a red
flag; a kind he ignored twice rests for a week; every nudge carries why; dismissals feed
ranking; a commitment quotes his own words and adds no target. The clock is frozen at
Thursday 3 September 2026, 16:00 on Pa's wall in Singapore, and stepped by days.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import as_utc, utcnow
from app.delivery.feed.models import CapsClass
from app.delivery.feed.rank import in_quiet_hours
from app.delivery.nudges import handoff
from app.delivery.nudges import strings as said
from app.delivery.nudges.engine import NothingToHandOver, hand_over, plan_nudges, respond
from app.delivery.nudges.handoff import Commitment, NudgeDraft, NudgePlan
from app.delivery.nudges.models import Nudge, NudgeKind, ResponseKind
from app.family.thread import post_message
from app.keys.context import KeyContext, OutOfScope
from app.medicines.service import record_dose_taken
from app.reasoning.feelings.service import answer_tap, record_tap
from app.reasoning.feelings.words import Answer
from app.reasoning.visits.memos import write_memo
from app.reasoning.visits.models import MemoKind, MemoSource
from app.regions import REGION_TZ, Region
from app.safety.plain_words import verify
from app.safety.red_flags import Feeling
from app.state.service import current_state
from tests.family_support import Household, household
from tests.feelings_support import REGISTRY, blood_pressure, new_medicine, visit_with
from tests.support import refused_unit
from tests.test_boundary import FORBIDDEN

SG = REGION_TZ[Region.SG]
TOMORROW = date(2026, 9, 4)


async def _home(session: AsyncSession) -> tuple[Household, KeyContext]:
    home = await household(session)
    return home, await home.ctx(session, home.pa)


async def _plan(session: AsyncSession, context: KeyContext, day: date | None = None) -> NudgePlan:
    return await plan_nudges(session, context=context, registry=REGISTRY, day=day)


def _held(plan: NudgePlan) -> dict[NudgeKind, str]:
    return {held.kind: held.because for held in plan.held}


async def _taken(session: AsyncSession, context: KeyContext, line_id: uuid.UUID) -> None:
    await record_dose_taken(session, context=context, line_id=line_id, anchor="breakfast")


async def _a_week_on(session: AsyncSession, owner: KeyContext, clock: FrozenClock) -> uuid.UUID:
    """A medicine that is no longer new: the week is steady, and recognition leads."""
    added = await new_medicine(session, owner)
    clock.step(timedelta(days=8))
    return added.line.id


async def test_a_visit_tomorrow_is_anticipated_and_the_rest_wait_one_a_day(
    sg: AsyncSession,
) -> None:
    _, owner = await _home(sg)
    visit = await visit_with(sg, owner, at=datetime(2026, 9, 5, 2, 0, tzinfo=UTC))
    added = await new_medicine(sg, owner)
    await _taken(sg, owner, added.line.id)
    plan = await _plan(sg, owner, TOMORROW)
    assert plan.none_because is None
    [draft] = plan.drafts
    assert draft.kind is NudgeKind.ANTICIPATION
    assert draft.lines == (
        "You see Dr Tan tomorrow, Saturday 5 September.",
        "Please bring all your tablets.",
    )
    assert draft.why == "You see this because your visit is tomorrow."
    assert draft.reason == {"code": "visit_tomorrow", "appointment_id": str(visit.id)}
    assert draft.cap_class is CapsClass.ONE
    assert draft.send_after == datetime(2026, 9, 4, 10, 0, tzinfo=SG)
    assert draft.expires_at == datetime(2026, 9, 5, 0, 0, tzinfo=SG)
    assert _held(plan) == {NudgeKind.CHECK_IN: "one_a_day", NudgeKind.RECOGNITION: "one_a_day"}


async def test_with_his_blood_pressure_book_he_is_asked_to_bring_it(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    await visit_with(sg, owner, at=datetime(2026, 9, 5, 2, 0, tzinfo=UTC))
    await blood_pressure(sg, owner, 138)
    [draft] = (await _plan(sg, owner, TOMORROW)).drafts
    assert draft.lines[1] == "Please bring your blood pressure book."


async def test_none_on_a_day_with_a_red_flag(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    added = await new_medicine(sg, owner)
    await _taken(sg, owner, added.line.id)
    await record_tap(sg, context=owner, word=Feeling.CHEST_TIGHTNESS, registry=REGISTRY)
    today = await _plan(sg, owner)
    assert today.none_because == "red_flag" and today.drafts == () and today.held == ()
    assert [d.kind for d in (await _plan(sg, owner, TOMORROW)).drafts] == [NudgeKind.RECOGNITION]


async def test_never_at_night(sg: AsyncSession, clock: FrozenClock) -> None:
    _, owner = await _home(sg)
    added = await new_medicine(sg, owner)
    await _taken(sg, owner, added.line.id)
    clock.set(datetime(2026, 9, 3, 14, 0, tzinfo=UTC))  # 22:00 in Singapore
    assert (await _plan(sg, owner)).none_because == "night"
    tomorrow = await _plan(sg, owner, TOMORROW)
    assert tomorrow.drafts and tomorrow.drafts[0].send_after == datetime(
        2026, 9, 4, 10, 0, tzinfo=SG
    )
    clock.set(datetime(2026, 9, 4, 3, 30, tzinfo=UTC))  # 11:30: after his check-in time
    later = await _plan(sg, owner)
    assert later.drafts[0].send_after == datetime(2026, 9, 4, 11, 30, tzinfo=SG)
    for draft in (*tomorrow.drafts, *later.drafts):
        assert not in_quiet_hours(as_utc(draft.send_after).astimezone(SG))


async def test_the_red_flag_day_is_his_day_on_his_wall(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(datetime(2026, 9, 2, 20, 0, tzinfo=UTC))  # 04:00 on Thursday 3 September, his wall
    _, owner = await _home(sg)
    added = await new_medicine(sg, owner)
    await _taken(sg, owner, added.line.id)
    await record_tap(sg, context=owner, word=Feeling.CHEST_TIGHTNESS, registry=REGISTRY)
    assert (await _plan(sg, owner)).none_because == "red_flag"
    tomorrow = await _plan(sg, owner, TOMORROW)
    assert tomorrow.drafts and tomorrow.drafts[0].expires_at == datetime(
        2026, 9, 5, 0, 0, tzinfo=SG
    )


async def test_one_a_day_counts_the_one_already_handed_over(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    _, owner = await _home(sg)
    line = await _a_week_on(sg, owner, clock)
    await _taken(sg, owner, line)
    _, nudge = await hand_over(sg, context=owner, registry=REGISTRY)
    assert nudge.kind is NudgeKind.RECOGNITION
    again = await _plan(sg, owner)
    assert again.drafts == () and _held(again) == {NudgeKind.PRESENCE: "one_a_day"}
    async with refused_unit(sg, NothingToHandOver):
        await hand_over(sg, context=owner, registry=REGISTRY)


async def test_a_kind_ignored_twice_rests_for_a_week(sg: AsyncSession, clock: FrozenClock) -> None:
    _, owner = await _home(sg)
    line = await _a_week_on(sg, owner, clock)
    for _ in range(2):
        await _taken(sg, owner, line)
        _, nudge = await hand_over(sg, context=owner, registry=REGISTRY)
        assert nudge.kind is NudgeKind.RECOGNITION
        clock.step(timedelta(days=1))  # it expired at midnight with nothing done with it
    await _taken(sg, owner, line)
    plan = await _plan(sg, owner)
    assert _held(plan)[NudgeKind.RECOGNITION] == "resting_after_two_ignored"
    assert [d.kind for d in plan.drafts] == [NudgeKind.PRESENCE]
    clock.step(timedelta(days=7))
    await _taken(sg, owner, line)
    assert [d.kind for d in (await _plan(sg, owner)).drafts] == [NudgeKind.RECOGNITION]


async def test_a_dismissal_moves_that_kind_down_his_day(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    _, owner = await _home(sg)
    line = await _a_week_on(sg, owner, clock)
    await _taken(sg, owner, line)
    _, nudge = await hand_over(sg, context=owner, registry=REGISTRY)
    await respond(sg, context=owner, nudge_id=nudge.id, kind=ResponseKind.DISMISSED)
    clock.step(timedelta(days=1))
    await _taken(sg, owner, line)
    plan = await _plan(sg, owner)
    assert [d.kind for d in plan.drafts] == [NudgeKind.PRESENCE]
    recognition = next(h for h in plan.held if h.kind is NudgeKind.RECOGNITION)
    assert recognition.because == "one_a_day" and recognition.priority == 75


async def test_a_check_in_follows_a_change_he_has_not_answered(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    added = await new_medicine(sg, owner)
    [draft] = (await _plan(sg, owner)).drafts
    assert draft.kind is NudgeKind.CHECK_IN
    assert draft.lines == (
        "Your blood pressure tablet is new since Thursday 3 September.",
        "How are you feeling today?",
    )
    assert draft.reason["code"] == "state_change" and draft.reason["line_id"] == str(added.line.id)
    await record_tap(sg, context=owner, word=Feeling.FINE, registry=REGISTRY)
    assert NudgeKind.CHECK_IN not in {d.kind for d in (await _plan(sg, owner)).drafts}


async def test_a_watched_feeling_is_asked_about_again_a_week_later(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    _, owner = await _home(sg)
    tapped = await record_tap(sg, context=owner, word=Feeling.LOW, registry=REGISTRY)
    answered = await answer_tap(
        sg, context=owner, tap_id=tapped.tap.id, answer=Answer.TODAY, registry=REGISTRY
    )
    assert answered.note is not None
    clock.step(timedelta(days=7))
    plan = await _plan(sg, owner)
    check_in = [d for d in plan.drafts if d.kind is NudgeKind.CHECK_IN] or [
        h for h in plan.held if h.kind is NudgeKind.CHECK_IN
    ]
    assert check_in and check_in[0].reason == {"code": "watched", "note_id": str(answered.note.id)}


async def test_presence_says_who_in_his_family_wrote_today(sg: AsyncSession) -> None:
    home, owner = await _home(sg)
    await post_message(sg, context=await home.ctx(sg, home.mei), text="See you on Saturday, Pa.")
    [draft] = (await _plan(sg, owner)).drafts
    assert draft.kind is NudgeKind.PRESENCE
    assert draft.lines == ("Mei wrote in the family messages today.",)
    assert draft.why == "You see this because Mei wrote today."
    assert "Saturday" not in " ".join(draft.lines), "the family's words stay in the thread"


async def test_his_morning_tablets_every_day_this_week_is_a_pattern(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    _, owner = await _home(sg)
    added = await new_medicine(sg, owner)
    for _ in range(7):
        await _taken(sg, owner, added.line.id)
        clock.step(timedelta(days=1))
    plan = await _plan(sg, owner)
    pattern = [h for h in plan.held if h.kind is NudgeKind.PATTERN]
    assert pattern and pattern[0].reason == {"code": "morning_taken", "days": 7, "of": 7}


@pytest.fixture
def his_memo() -> Iterator[uuid.UUID]:
    """A memo from his last visit, as E05's source will give it: his words, exactly."""
    memo_id = uuid.uuid4()

    async def source(session: AsyncSession, *, context: KeyContext) -> Sequence[Commitment]:
        return [Commitment(memo_id, "Less salt at lunch.", "en", utcnow() - timedelta(days=1))]

    handoff.commitment_sources.append(source)
    yield memo_id
    handoff.commitment_sources.remove(source)


async def test_a_commitment_quotes_his_own_words_and_adds_no_target(
    sg: AsyncSession, his_memo: uuid.UUID
) -> None:
    _, owner = await _home(sg)
    await new_medicine(sg, owner)
    await record_tap(sg, context=owner, word=Feeling.FINE, registry=REGISTRY)
    [draft] = (await _plan(sg, owner)).drafts
    assert draft.kind is NudgeKind.COMMITMENT
    assert draft.lines == (
        "You said you would do this:",
        "Less salt at lunch.",
        "How did it go today?",
    )
    assert draft.memo_id == his_memo and draft.reason == {"code": "memo", "memo_id": str(his_memo)}
    assert draft.why == "You see this because you said you would do it."


async def test_a_memo_from_the_visit_loop_is_quoted_once_exactly_as_it_was_filed(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    _, owner = await _home(sg)
    await new_medicine(sg, owner)
    await record_tap(sg, context=owner, word=Feeling.FINE, registry=REGISTRY)
    memo = await write_memo(
        sg,
        context=owner,
        kind=MemoKind.ACTION,
        key="lighter_dinners",
        slots={},
        source=MemoSource.PERSON,
    )
    assert memo.text == "Every evening, eat a lighter dinner."
    [draft] = (await _plan(sg, owner)).drafts
    assert draft.kind is NudgeKind.COMMITMENT and draft.memo_id == memo.id
    assert draft.lines == ("You said you would do this:", memo.text, "How did it go today?")
    await hand_over(sg, context=owner, registry=REGISTRY)
    clock.step(timedelta(days=9))
    await record_tap(sg, context=owner, word=Feeling.FINE, registry=REGISTRY)
    again = await _plan(sg, owner)
    assert NudgeKind.COMMITMENT not in {d.kind for d in again.drafts} | {
        h.kind for h in again.held
    }, "a memo is quoted once"


async def test_hand_over_writes_it_from_state_and_gives_it_to_delivery(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    await new_medicine(sg, owner)
    taken: list[tuple[uuid.UUID, NudgeDraft]] = []

    class Delivery:
        async def take(
            self, session: AsyncSession, *, context: KeyContext, nudge: Nudge, draft: NudgeDraft
        ) -> None:
            taken.append((nudge.id, draft))

    delivery = Delivery()
    handoff.deliveries.append(delivery)
    try:
        _, nudge = await hand_over(sg, context=owner, registry=REGISTRY)
    finally:
        handoff.deliveries.remove(delivery)
    assert nudge.kind is NudgeKind.CHECK_IN
    assert nudge.state_id == (await current_state(sg, context=owner)).id
    assert nudge.boundary is None, "a nudge infers nothing and carries no boundary line"
    assert [nudge_id for nudge_id, _ in taken] == [nudge.id]
    assert taken[0][1].lines == tuple(nudge.lines)
    await sg.refresh(nudge)
    assert as_utc(nudge.expires_at) == taken[0][1].expires_at, "stored as the moment it is, in UTC"
    assert as_utc(nudge.send_after) == taken[0][1].send_after


async def test_a_plan_needs_the_owners_key_or_a_chiefs(sg: AsyncSession) -> None:
    home, _ = await _home(sg)
    siti = await home.ctx(sg, home.siti)
    async with refused_unit(sg, OutOfScope):
        await plan_nudges(sg, context=siti, registry=REGISTRY)


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_every_line_passes_plain_words_and_none_scolds(language: str) -> None:
    lines = [line for code, line in said.catalogue() if code == language]
    failing = [f for line in lines for f in verify(line, language, "line") if f.severity == "fail"]
    assert failing == []
    assert [line for line in lines if FORBIDDEN[language].search(line)] == []
    if language == "en":
        scolding = ("missed", "forgot", "late", "streak", "in a row", "should", "failed", "again?")
        assert [line for line in lines if any(word in line.lower() for word in scolding)] == []
    for count in (0, 1, 41):
        assert said.recognition_lines(count, language)[-1] == said.LINES[language]["recognition"][1]
