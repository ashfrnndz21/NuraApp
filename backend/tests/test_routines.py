"""E10-01: the routine builder, rendered per persona.

    Acceptance: medicines, readings, walks, meals, sleep set once; renders to Dad and helper.

The day is set once, on a person's yes, and superseded rather than edited. The dose schedule
is E04's dose codes mapped onto the day's anchors. The patient reads one line per moment in
his words, every line verified; the caregiver reads a dense table; a key without the
readings sees the day with the prompts withheld by name. `due_now` says what hangs on a
moment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.keys.context import KeyContext, OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.routines.models import Routine
from app.routines.service import (
    DEFAULT_ANCHORS,
    NotARoutine,
    NotTheirsToSet,
    Persona,
    check_day,
    due_at,
    due_now,
    render_routine,
    routine_draft_for,
    set_routine,
)
from app.safety.plain_words import verify
from tests.medicines_support import REGISTRY, add, label, let_in, pa
from tests.trio_support import refusals

PA_DAY = {
    "wake": "06:30",
    "breakfast": "07:30",
    "lunch": "12:30",
    "dinner": "18:30",
    "bed": "22:00",
}
PROMPTS = [("blood_pressure", "wake")]
WALKS = ["dinner"]


async def _set(
    session: AsyncSession,
    context: KeyContext,
    anchors: dict[str, str] = PA_DAY,
    prompts: list[tuple[str, str]] = PROMPTS,
    walks: list[str] = WALKS,
    morning: str = "07:00",
) -> Routine:
    draft = await routine_draft_for(
        session,
        context=context,
        anchors=anchors,
        reading_prompts=prompts,
        walks=walks,
        morning_card_at=morning,
    )
    yes = await confirm(session, context, draft)
    return await set_routine(
        session,
        context=context,
        anchors=anchors,
        reading_prompts=prompts,
        walks=walks,
        morning_card_at=morning,
        confirmation_id=yes.id,
    )


async def test_the_day_before_anyone_sets_it_is_the_default_and_says_so(sg: AsyncSession) -> None:
    owner = await pa(sg, language="en")
    view = await render_routine(sg, context=owner, registry=REGISTRY)
    assert view.the.routine is None and view.persona is Persona.PATIENT
    assert view.the.day.as_strings() == dict(DEFAULT_ANCHORS)
    assert list(view.lines) == ["Nura sends your Today page at 7 in the morning."]


async def test_set_once_it_renders_to_him_as_one_line_per_moment_and_to_mei_as_a_table(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, language="en")
    await add(sg, owner, label("amlodipine", "5 mg", "1 biji sekali sehari pagi"))
    await add(sg, owner, label("metformin", "500 mg", "1 tab BD"))
    mei = await let_in(
        sg,
        owner,
        phone="+6591110002",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.MEDICINES, Scope.READINGS, Scope.VISITS},
    )
    await _set(sg, mei)

    his = await render_routine(sg, context=owner, registry=REGISTRY)
    assert list(his.lines) == [
        "Nura sends your Today page at 7 in the morning.",
        "When you wake up, check your blood pressure.",
        "At breakfast, take 1 tablet of your blood pressure tablet and 1 tablet of the sugar tablet.",
        "At dinner, go for a walk, then take 1 tablet of the sugar tablet.",
    ]
    hers = await render_routine(sg, context=mei, registry=REGISTRY)
    assert hers.persona is Persona.CAREGIVER and hers.lines == ()
    table = {row["anchor"]: row for row in hers.table}
    assert [row["anchor"] for row in hers.table] == ["wake", "breakfast", "lunch", "dinner", "bed"]
    assert table["wake"]["at"] == "06:30" and table["wake"]["readings"] == ["blood_pressure"]
    assert [m["generic"] for m in table["breakfast"]["medicines"]] == ["amlodipine", "metformin"]
    assert table["breakfast"]["medicines"][0]["frequency"] == "od"
    assert table["dinner"]["walk"] is True and table["lunch"]["medicines"] == []

    # The same day in his other languages, every line verified.
    for language in ("ms", "zh"):
        lines = (await render_routine(sg, context=owner, registry=REGISTRY, language=language)).lines
        assert len(lines) == 4
        assert not [f for line in lines for f in verify(line, language) if f.severity == "fail"]


async def test_the_helper_sees_the_day_with_the_prompts_withheld_and_cannot_set_it(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    await _set(sg, owner)
    siti = await let_in(
        sg, owner, phone="+6591110003", name="Siti", role=KeyRole.HELPER, scopes={Scope.MEDICINES}
    )
    hers = await render_routine(sg, context=siti, registry=REGISTRY, persona=Persona.CAREGIVER)
    assert Scope.READINGS in hers.the.withheld
    assert all(row["readings"] is None for row in hers.table)
    assert [m["generic"] for m in hers.table[1]["medicines"]] == ["amlodipine"]
    # Rendered to her as his lines, too: the tablets, not the prompts.
    lines = (await render_routine(sg, context=siti, registry=REGISTRY, persona=Persona.PATIENT)).lines
    assert not any("tekanan darah anda." in line for line in lines if line.startswith("Apabila"))
    with pytest.raises(NotTheirsToSet):
        await routine_draft_for(
            sg,
            context=siti,
            anchors=PA_DAY,
            reading_prompts=[],
            walks=[],
            morning_card_at="07:00",
        )
    assert await refusals(sg, owner, "NotTheirsToSet")


async def test_setting_again_supersedes_and_the_yes_binds_to_the_day_as_shown(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    first = await _set(sg, owner)
    later = {**PA_DAY, "wake": "07:00", "breakfast": "08:00"}
    draft = await routine_draft_for(
        sg, context=owner, anchors=later, reading_prompts=PROMPTS, walks=WALKS, morning_card_at="07:30"
    )
    assert draft.supersedes_id == first.id
    yes = await confirm(sg, owner, draft)
    with pytest.raises(NotWhatWasConfirmed):
        await set_routine(
            sg,
            context=owner,
            anchors={**later, "bed": "23:00"},
            reading_prompts=PROMPTS,
            walks=WALKS,
            morning_card_at="07:30",
            confirmation_id=yes.id,
        )
    second = await set_routine(
        sg,
        context=owner,
        anchors=later,
        reading_prompts=PROMPTS,
        walks=WALKS,
        morning_card_at="07:30",
        confirmation_id=yes.id,
    )
    rows = (await sg.scalars(select(Routine))).all()
    assert len(rows) == 2 and second.supersedes_id == first.id
    assert first.superseded_at is not None and second.superseded_at is None
    assert await refusals(sg, owner, "NotWhatWasConfirmed")


async def test_a_day_that_is_not_one_is_refused() -> None:
    with pytest.raises(NotARoutine):
        check_day({**PA_DAY, "lunch": "07:00"}, [], [], "07:00")  # lunch before breakfast
    with pytest.raises(NotARoutine):
        check_day({k: v for k, v in PA_DAY.items() if k != "bed"}, [], [], "07:00")
    with pytest.raises(NotARoutine):
        check_day(PA_DAY, [("cholesterol", "wake")], [], "07:00")
    with pytest.raises(NotARoutine):
        check_day(PA_DAY, [], ["tea"], "07:00")
    with pytest.raises(NotARoutine):
        check_day(PA_DAY, [], [], "7am")


async def test_prompts_for_readings_need_the_readings_scope(sg: AsyncSession) -> None:
    owner = await pa(sg)
    kit = await let_in(
        sg, owner, phone="+6591110004", name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.MEDICINES}
    )
    with pytest.raises(OutOfScope):
        await routine_draft_for(
            sg, context=kit, anchors=PA_DAY, reading_prompts=PROMPTS, walks=[], morning_card_at="07:00"
        )


async def test_a_third_medicine_at_one_moment_starts_a_second_line(sg: AsyncSession) -> None:
    owner = await pa(sg, language="en")
    for generic, strength in (("amlodipine", "5 mg"), ("metformin", "500 mg"), ("atorvastatin", "20 mg")):
        await add(sg, owner, label(generic, strength, "1 tab OD"))
    lines = (await render_routine(sg, context=owner, registry=REGISTRY)).lines
    breakfast = [line for line in lines if line.startswith("At breakfast")]
    assert len(breakfast) == 2
    assert not [f for line in lines for f in verify(line, "en") if f.severity == "fail"]


async def test_due_now_says_what_hangs_on_the_moment(sg: AsyncSession) -> None:
    owner = await pa(sg)
    added = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    await _set(sg, owner)
    # 07:40 in Singapore is 23:40 UTC the day before.
    at_breakfast = await due_now(sg, context=owner, at=datetime(2026, 9, 2, 23, 40, tzinfo=UTC))
    assert at_breakfast is not None and at_breakfast.anchor == "breakfast"
    assert at_breakfast.medicine_line_ids == (added.line.id,)
    at_wake = await due_now(sg, context=owner, at=datetime(2026, 9, 2, 22, 35, tzinfo=UTC))
    assert at_wake is not None and (at_wake.anchor, at_wake.readings) == ("wake", ("blood_pressure",))
    assert await due_now(sg, context=owner, at=datetime(2026, 9, 3, 2, 0, tzinfo=UTC)) is None
    # An anchor is due until the next one comes, if that is sooner than an hour.
    day = check_day({**PA_DAY, "wake": "07:00", "breakfast": "07:20"}, [], [], "07:00")
    local = datetime(2026, 9, 3, 7, 25, tzinfo=ZoneInfo("Asia/Singapore"))
    assert due_at(day, local) == "breakfast"
