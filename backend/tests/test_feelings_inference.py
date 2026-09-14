"""E17-02: a tap plus one question back, read against his medicines, his blood pressure and
this week — into a note of at most two things to tell the doctor, the boundary line last.

The acceptance line: red flags open not-feeling-well and notify the roster at once, before
anything else; every inference names its reason. Never a diagnosis, never start, stop or
change. The clock is frozen at Thursday 3 September 2026, 16:00 on Pa's wall.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.triggers.models import Ladder
from app.keys.context import KeyContext, OutOfScope
from app.memory.models import EventKind
from app.reasoning.feelings import strings
from app.reasoning.feelings.models import FeelingNote, NoteOutcome
from app.reasoning.feelings.service import (
    AlreadyAnswered,
    Answered,
    NotAnAnswer,
    answer_tap,
    record_tap,
)
from app.reasoning.feelings.words import Answer, FollowUp
from app.safety.boundary import Surface, boundary_line, is_boundary_line
from app.safety.models import WhatToDoKind
from app.safety.red_flags import Feeling, Flag
from app.state.models import Posture
from app.state.service import current_state
from tests.family_support import Household, household
from tests.feelings_support import (
    REGISTRY,
    STORE,
    TRANSCRIBER,
    VIA,
    blood_pressure,
    happened,
    new_medicine,
    visit_with,
)
from tests.support import refused_unit
from tests.test_boundary import FORBIDDEN


async def _home(session: AsyncSession) -> tuple[Household, KeyContext]:
    home = await household(session)
    return home, await home.ctx(session, home.pa)


async def _said(
    session: AsyncSession, context: KeyContext, word: Feeling, answer: Answer
) -> Answered:
    tapped = await record_tap(
        session, context=context, word=word, registry=REGISTRY, store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    return await answer_tap(
        session,
        context=context,
        tap_id=tapped.tap.id,
        answer=answer,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )


async def _notes(session: AsyncSession) -> list[FeelingNote]:
    return list((await session.scalars(select(FeelingNote))).all())


async def test_a_tap_asks_when_it_began_and_is_read_against_a_new_medicine(
    sg: AsyncSession,
) -> None:
    _, owner = await _home(sg)
    await visit_with(sg, owner, at=utcnow() + timedelta(days=5))
    added = await new_medicine(sg, owner)
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.DIZZY,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert tapped.question is not None and tapped.question.follow_up is FollowUp.SINCE_WHEN
    assert tapped.question.words == "When did it begin?"
    assert [a for a, _ in tapped.question.answers] == [
        Answer.TODAY,
        Answer.YESTERDAY,
        Answer.FEW_DAYS,
        Answer.WEEK_OR_MORE,
    ]
    assert tapped.tap.emphasised and {r["code"] for r in tapped.tap.reasons} == {
        "base",
        "new_medicine",
    }

    answered = await answer_tap(
        sg,
        context=owner,
        tap_id=tapped.tap.id,
        answer=Answer.YESTERDAY,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    note = answered.note
    assert note is not None and answered.red is None
    assert note.headline == "Things to tell Dr Tan"
    assert note.lines == [
        "Tell Dr Tan you feel dizzy since yesterday.",
        "This can come from your blood pressure tablet, new since Thursday 3 September.",
    ]
    assert note.then == "Nura will keep this for your visit to Dr Tan."
    assert note.boundary == boundary_line(Surface.FEELING_INFERENCE, "en", doctor="Dr Tan")
    assert is_boundary_line(Surface.FEELING_INFERENCE, note.boundary)
    assert note.voice[-3:] == [
        "Nura noticed this in how you said you feel.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    ]
    assert note.outcome is NoteOutcome.FOR_THE_DOCTOR and note.state_id is not None
    assert note.reasons == [
        {
            "code": "new_medicine",
            "shown": True,
            "line_id": str(added.line.id),
            "generic": "amlodipine",
            "watch_out": "dizzy_standing",
        }
    ]


async def test_without_a_visit_the_doctor_on_the_label_is_named(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    await new_medicine(sg, owner)
    note = (await _said(sg, owner, Feeling.SWOLLEN_ANKLES, Answer.NO)).note
    assert note is not None
    assert note.headline == "Things to tell Dr Tan"
    assert note.lines[0] == "Tell Dr Tan about your swollen ankles today."
    assert note.then == "Nura will keep this for your next visit."


async def test_the_same_word_as_yesterday_asks_whether_it_is_more(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    _, owner = await _home(sg)
    await _said(sg, owner, Feeling.DIZZY, Answer.TODAY)
    clock.step(timedelta(days=1))
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.DIZZY,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert tapped.question is not None
    assert tapped.question.follow_up is FollowUp.MORE_THAN_YESTERDAY
    assert tapped.question.words == "Is it more than yesterday?"
    answered = await answer_tap(
        sg,
        context=owner,
        tap_id=tapped.tap.id,
        answer=Answer.MORE,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert answered.note is not None
    assert answered.note.lines == [
        "Tell your doctor you feel dizzy and that it is worse than yesterday."
    ]


async def test_a_direction_in_his_blood_pressure_is_named_by_its_facts(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    facts = [
        await blood_pressure(sg, owner, top, at=utcnow() - timedelta(days=2 - n))
        for n, top in enumerate((130, 139, 151))
    ]
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.HEADACHE,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert tapped.question is not None and tapped.question.follow_up is FollowUp.WORST_EVER
    assert tapped.question.words == "Is it the worst headache of your life?"
    answered = await answer_tap(
        sg,
        context=owner,
        tap_id=tapped.tap.id,
        answer=Answer.NO,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    note = answered.note
    assert note is not None
    assert note.lines == [
        "Tell your doctor about the headache today.",
        "Your last 3 blood pressure numbers went up each time.",
    ]
    assert note.reasons[0]["code"] == "reading_trend"
    assert note.reasons[0]["fact_ids"] == [str(fact.id) for fact in facts]


async def test_a_visit_this_week_is_named(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    visit = await happened(sg, owner, EventKind.VISIT, utcnow() - timedelta(days=2), "saw Dr Lim")
    note = (await _said(sg, owner, Feeling.TIRED, Answer.FEW_DAYS)).note
    assert note is not None
    assert note.lines == [
        "Tell your doctor you feel tired for a few days now.",
        "You went to see a doctor on Tuesday 1 September.",
    ]
    assert note.reasons == [{"code": "visit", "shown": True, "visit_id": str(visit.id)}]


async def test_nothing_to_read_it_against_is_watched_and_asked_again(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    note = (await _said(sg, owner, Feeling.LOW, Answer.TODAY)).note
    assert note is not None
    assert note.lines == ["Tell your doctor you feel low today."]
    assert note.then == "Nura will ask you again in a week."
    assert note.outcome is NoteOutcome.WATCH and note.reasons == []


async def test_at_most_two_things_to_tell_and_every_reason_kept(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    await happened(sg, owner, EventKind.VISIT, utcnow() - timedelta(days=1), "saw Dr Lim")
    await new_medicine(sg, owner)
    for n, top in enumerate((130, 139, 151)):
        await blood_pressure(sg, owner, top, at=utcnow() - timedelta(days=2 - n))
    note = (await _said(sg, owner, Feeling.DIZZY, Answer.YESTERDAY)).note
    assert note is not None and len(note.lines) == 2
    assert [(r["code"], r["shown"]) for r in note.reasons] == [
        ("new_medicine", True),
        ("reading_trend", False),
        ("visit", False),
    ]


async def test_a_red_word_goes_to_the_red_flag_path_first_and_makes_no_note(
    sg: AsyncSession,
) -> None:
    home, owner = await _home(sg)
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.CHEST_TIGHTNESS,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert tapped.question is None and tapped.red is not None
    flag = tapped.red.flag
    assert flag.feeling is Feeling.CHEST_TIGHTNESS and flag.suppressed_because is None
    assert set(flag.told) == {str(home.mei.id), str(home.kit.id), str(home.siti.id)}
    # The ladder is the one record of who is told (E11-06, ADR 0005): the roster first, and
    # the card counts who it asked at once.
    ladder = tapped.red.escalation
    assert ladder is not None and ladder.flag_id == flag.id
    assert ladder.rungs[0]["person_id"] == str(home.mei.id)
    first = {rung["person_id"] for rung in ladder.rungs if rung["after_minutes"] == 0}
    assert tapped.red.notices == len(first) >= 1
    assert tapped.red.opens == "not_feeling_well"
    # The whole button, server-side: the urgent what-to-do card, and the day's posture act.
    card = tapped.red.card
    assert card.kind is WhatToDoKind.RED_FLAG and card.card_id is not None
    assert card.posture is Posture.ACT
    assert (await current_state(sg, context=owner)).posture is Posture.ACT
    assert tapped.lines[0] == "Mei knows now."
    assert any("995" in line for line in tapped.lines)
    assert tapped.lines[-1] == "Nura does not decide what is wrong."
    assert "Ask your doctor." not in tapped.lines
    assert tapped.tap.red and tapped.tap.follow_up is None and tapped.tap.flag_id == flag.id
    assert await _notes(sg) == []
    assert len((await sg.scalars(select(Ladder))).all()) == 1


async def test_heavier_is_named_to_the_button_not_heard_back_from_the_words(
    sg: AsyncSession,
) -> None:
    """Weight gain has no words in the red-flag table (it is a fact rule), so the tap names it."""
    _, owner = await _home(sg)
    held = await record_tap(
        sg,
        context=owner,
        word=Feeling.WEIGHT_GAIN,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert held.red is not None and held.red.flag.feeling is Feeling.WEIGHT_GAIN
    assert held.red.flag.suppressed_because == "no_recent_discharge_on_record"
    await happened(
        sg, owner, EventKind.DISCHARGE, utcnow() - timedelta(days=1), "home from hospital"
    )
    raised = await record_tap(
        sg,
        context=owner,
        word=Feeling.WEIGHT_GAIN,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert raised.red is not None and raised.red.flag.suppressed_because is None
    assert raised.red.card.kind is WhatToDoKind.RED_FLAG
    assert await _notes(sg) == []


async def test_a_yes_that_tells_the_red_variant_apart_takes_the_red_flag_path(
    sg: AsyncSession,
) -> None:
    _, owner = await _home(sg)
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.BREATHLESS,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert tapped.red is None and tapped.question is not None
    assert tapped.question.follow_up is FollowUp.AT_REST
    answered = await answer_tap(
        sg,
        context=owner,
        tap_id=tapped.tap.id,
        answer=Answer.YES,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert answered.note is None and answered.red is not None
    assert answered.red.flag.feeling is Feeling.BREATHLESS_AT_REST
    assert answered.tap.flag_id == answered.red.flag.id
    assert await _notes(sg) == []


async def test_a_helpers_key_starts_the_red_path_and_nothing_else(sg: AsyncSession) -> None:
    home, _ = await _home(sg)
    siti = await home.ctx(sg, home.siti)
    tapped = await record_tap(
        sg, context=siti, word=Feeling.FALL, registry=REGISTRY, store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert tapped.red is not None and tapped.red.flag.feeling is Feeling.FALL
    assert len((await sg.scalars(select(Flag))).all()) == 1
    async with refused_unit(sg, OutOfScope):
        await record_tap(
            sg,
            context=siti,
            word=Feeling.TIRED,
            registry=REGISTRY,
            store=STORE,
            transcriber=TRANSCRIBER,
            via=VIA,
        )


async def test_a_tap_asks_one_thing_once_and_takes_only_its_own_answers(sg: AsyncSession) -> None:
    _, owner = await _home(sg)
    first = await _said(sg, owner, Feeling.TIRED, Answer.TODAY)
    async with refused_unit(sg, AlreadyAnswered):
        await answer_tap(
            sg,
            context=owner,
            tap_id=first.tap.id,
            answer=Answer.YESTERDAY,
            registry=REGISTRY,
            store=STORE,
            transcriber=TRANSCRIBER,
            via=VIA,
        )
    pain = await record_tap(
        sg,
        context=owner,
        word=Feeling.PAIN,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    async with refused_unit(sg, NotAnAnswer):
        await answer_tap(
            sg,
            context=owner,
            tap_id=pain.tap.id,
            answer=Answer.YES,
            registry=REGISTRY,
            store=STORE,
            transcriber=TRANSCRIBER,
            via=VIA,
        )
    fine = await record_tap(
        sg,
        context=owner,
        word=Feeling.FINE,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert fine.question is None
    assert fine.lines == ("That is good to hear.", "Nura will ask again when something changes.")
    async with refused_unit(sg, NotAnAnswer):
        await answer_tap(
            sg,
            context=owner,
            tap_id=fine.tap.id,
            answer=Answer.TODAY,
            registry=REGISTRY,
            store=STORE,
            transcriber=TRANSCRIBER,
            via=VIA,
        )


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_no_line_starts_stops_or_changes_a_medicine_or_names_a_condition(language: str) -> None:
    lines = [line for code, line in strings.catalogue() if code == language]
    lines += list(strings.WHEN[language].values())
    offending = [line for line in lines if FORBIDDEN[language].search(line)]
    assert offending == []
