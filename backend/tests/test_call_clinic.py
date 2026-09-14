"""E13-02: the not-feeling-well decision table, with its call-the-clinic row, as a matrix.

    Three steps; guidance is rest, call clinic or go now; family notified.

The table is four rows, top row wins: a red flag (the ambulance), call the clinic today, a
tablet with no Taken ("Ask Dr Tan before you take…"), rest. Call the clinic applies to a
symptom that is not a red flag, said "quite a lot" / "a lot" (or "very"), or lasting a day or
more, or on the licensed monograph of a medicine started in the last fourteen days — the rule
the feeling cloud reads (E17). Every combination of what the table reads is below, with the
row that wins. The red-flag row is first and unchanged; every card, whatever its row, ends
"Nura does not decide what is wrong."; nothing is a diagnosis or a dose instruction.

    red flag | how much    | how long             | new medicine | no Taken | wins
    ---------+-------------+----------------------+--------------+----------+------------
    yes      | any         | any                  | any          | any      | red flag
    no       | quite/very  | any                  | any          | any      | call clinic
    no       | any         | a day or more        | any          | any      | call clinic
    no       | any         | any                  | yes          | any      | call clinic
    no       | none/little | none/under a day     | no           | yes      | no Taken
    no       | none/little | none/under a day     | no           | no       | rest
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.safety_strings import render
from app.clock import FrozenClock
from app.identity.models import Person
from app.keys.scopes import KeyRole
from app.medicines.service import active_lines, record_dose_taken
from app.regions import Region
from app.safety.boundary import URGENT_CLOSING
from app.safety.models import WhatToDoKind
from app.safety.not_feeling_well import (
    A_DAY_OR_MORE,
    DECISION_TABLE,
    Situation,
    compose,
    decide,
    not_feeling_well,
    within_the_boundary,
)
from app.safety.plain_words import verify
from app.safety.symptoms import Duration
from tests.delivery_support import via_for
from tests.medicines_support import add, label
from tests.safety_support import REGISTRY, assert_plain, let_in, pa, transcriber_for, water_pill

LANGUAGES = ("en", "ms", "zh")
SEVERITIES = (None, 1, 2, 3)
DURATIONS: tuple[Duration | None, ...] = (None, *Duration)
DAY_OR_MORE = {"since_yesterday", "few_days", "about_a_week", "longer"}
"""The spec's "lasting a day or more", written out here rather than read from the module."""

MEI = Person(display_name="Mei", language="en")
NOT_TAKEN = object()
"""A tablet nobody tapped Taken on: the table reads only whether there is one."""

FORBIDDEN = ("mg", "tablet", "stop", "start", "double", "half", "skip", "drink", "you have")
"""No card names an amount, tells him to start, stop or change a medicine, or diagnoses."""


def _spec(red: bool, severity: int | None, duration: Duration | None, new: bool, missed: bool) -> WhatToDoKind:
    if red:
        return WhatToDoKind.RED_FLAG
    if (severity or 0) >= 2 or (duration is not None and duration.value in DAY_OR_MORE) or new:
        return WhatToDoKind.CALL_CLINIC
    return WhatToDoKind.MISSED_DOSE if missed else WhatToDoKind.REST


MATRIX = list(
    itertools.product((True, False), SEVERITIES, DURATIONS, (True, False), (True, False))
)


@pytest.mark.parametrize(("red", "severity", "duration", "new", "missed"), MATRIX)
def test_every_combination_and_the_row_that_wins(
    red: bool, severity: int | None, duration: Duration | None, new: bool, missed: bool
) -> None:
    situation = Situation(
        red_flag=red,
        heard=True,
        missed=NOT_TAKEN if missed else None,  # type: ignore[arg-type]
        chief=MEI,
        others_told=True,
        region=Region.SG,
        severity=severity,
        lasting=duration in A_DAY_OR_MORE,
        new_medicine=new,
    )
    decision = decide(situation)
    assert decision.kind is _spec(red, severity, duration, new, missed)
    if decision.kind is WhatToDoKind.RED_FLAG:
        # First and unchanged: the ambulance, then the chief; no check-in.
        assert decision.line_ids == ("nfw.call_995", "nfw.then_call_chief")
        assert not decision.check_in
    elif decision.kind is WhatToDoKind.CALL_CLINIC:
        assert decision.line_ids[0] == "nfw.call_clinic" and decision.check_in
        assert ("nfw.ask_before" in decision.line_ids) is missed
    else:
        assert "nfw.call_clinic" not in decision.line_ids


def test_the_matrix_reaches_every_row_and_the_red_flag_is_first() -> None:
    assert [row[0] for row in DECISION_TABLE] == [
        WhatToDoKind.RED_FLAG,
        WhatToDoKind.CALL_CLINIC,
        WhatToDoKind.MISSED_DOSE,
        WhatToDoKind.REST,
    ]
    assert {_spec(*combination) for combination in MATRIX} == set(WhatToDoKind)
    assert {one.value for one in A_DAY_OR_MORE} == DAY_OR_MORE


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(("red", "clinic", "missed"), list(itertools.product((True, False), repeat=3)))
def test_every_card_ends_on_nura_does_not_decide_and_says_no_dose(
    language: str, red: bool, clinic: bool, missed: bool
) -> None:
    situation = Situation(
        red_flag=red,
        heard=True,
        missed=NOT_TAKEN if missed else None,  # type: ignore[arg-type]
        chief=MEI,
        others_told=True,
        region=Region.SG,
        severity=2 if clinic else None,
    )
    decision = decide(situation)
    lines = within_the_boundary(
        compose(decision, language=language, chief=MEI, missed_medicine=None, doctor="Dr Tan"),
        language=language,
        doctor="Dr Tan",
        told="Mei",
        urgent=decision.kind is WhatToDoKind.RED_FLAG,
    )
    assert lines[-1].text == URGENT_CLOSING[language]
    for line in lines:
        assert [f for f in verify(line.text, language) if f.severity == "fail"] == [], line
        if language == "en":
            assert not any(word in line.text.lower() for word in FORBIDDEN), line


def test_the_clinic_is_always_a_doctors_and_never_the_chiefs() -> None:
    assert render("nfw.call_clinic", "en", doctor="Dr Tan") == "Call Dr Tan's clinic today."
    decision = decide(
        Situation(
            red_flag=False, heard=True, missed=None, chief=MEI, others_told=True,
            region=Region.SG, lasting=True,
        )
    )
    said = compose(decision, language="en", chief=MEI, missed_medicine=None, doctor=None)
    assert said[0].text == "Call your doctor's clinic today."
    assert not any("Mei's" in line.text for line in said)


# --- the button, end to end ---------------------------------------------------------------


class _Store:
    region = Region.SG

    def __init__(self) -> None:
        self.kept: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.kept[key] = data

    async def get(self, key: str) -> bytes:
        return self.kept[key]


async def _press(session: AsyncSession, context, words: str):
    return await not_feeling_well(
        session,
        context=context,
        store=_Store(),
        transcriber=transcriber_for(context.region),
        registry=REGISTRY,
        via=via_for(context.region),
        words=words,
    )


async def test_quite_a_lot_calls_the_clinic_and_keeps_the_tablet_lines(sg: AsyncSession) -> None:
    """16:00: the water pill's breakfast window closed with no Taken. "Dizzy, quite a lot":
    call Dr Tan's clinic today (the doctor on the label), with the two tablet lines."""
    owner = await pa(sg, phone="+6591110061")
    await water_pill(sg, owner)
    await let_in(sg, owner, phone="+6592220061", name="Mei", role=KeyRole.CHIEF)
    done = await _press(sg, owner, "dizzy, quite a lot")
    assert done.kind is WhatToDoKind.CALL_CLINIC
    assert [line.text for line in done.lines] == [
        "Mei knows now.",
        "Call Dr Tan's clinic today.",
        "Nura has no note that you took the water pill today.",
        "Ask Dr Tan before you take the water pill.",
        "Sit down and rest now.",
        "Mei will call you today.",
        "Nura will ask you again in 2 hours.",
        "Nura wrote down how you feel.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
        "Nura does not decide what is wrong.",
    ]
    assert_plain(done.lines)
    assert done.check_in_at is not None and done.red_flags == []


async def test_a_day_or_more_calls_the_clinic_and_a_little_today_is_rest(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110062")
    made = await water_pill(sg, owner)
    assert made.line is not None
    await record_dose_taken(sg, context=owner, line_id=made.line.id, anchor="breakfast", amount=1)
    lasting = await _press(sg, owner, "tired since yesterday")
    assert lasting.kind is WhatToDoKind.CALL_CLINIC
    # No doctor in his directory and no tablet row: "your doctor", never a relative.
    assert [line.text for line in lasting.lines][:2] == [
        "You did right to say so.",
        "Call your doctor's clinic today.",
    ]
    assert lasting.lines[-1].text == "Nura does not decide what is wrong."
    little = await _press(sg, owner, "a little tired this morning")
    assert little.kind is WhatToDoKind.REST
    assert little.lines[-1].text == "Nura does not decide what is wrong."


async def test_a_watch_out_of_a_medicine_started_in_the_last_fourteen_days_calls_the_clinic(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """Amlodipine's licensed monograph lists "dizzy when you stand up" (`dizzy_standing`):
    started today, "dizzy" is a call to Dr Tan's clinic — the doctor on its label. Fifteen
    days on, the same word is not."""
    assert "dizzy_standing" in REGISTRY.monograph("amlodipine").watch_out_ids
    owner = await pa(sg, phone="+6591110063")
    made = await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD", prescriber="Dr Lim"))
    assert made.line is not None
    await record_dose_taken(sg, context=owner, line_id=made.line.id, anchor="breakfast", amount=1)
    done = await _press(sg, owner, "dizzy")
    assert done.kind is WhatToDoKind.CALL_CLINIC
    assert done.lines[1].text == "Call Dr Lim's clinic today."
    assert done.lines[-2].text == "Ask Dr Lim."
    # 06:00 fifteen days on: the breakfast window is not open yet, and the medicine is not new.
    clock.set(datetime(2026, 9, 17, 22, 0, tzinfo=UTC))
    later = await _press(sg, owner, "dizzy")
    assert later.kind is WhatToDoKind.REST


async def test_the_red_flag_row_stays_first_whatever_else_is_said(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110064")
    await water_pill(sg, owner)
    await let_in(sg, owner, phone="+6592220064", name="Mei", role=KeyRole.CHIEF)
    done = await _press(sg, owner, "chest pain, a lot, since yesterday")
    assert done.kind is WhatToDoKind.RED_FLAG
    assert [line.text for line in done.lines] == [
        "Mei knows now.",
        "Call the ambulance now on 995.",
        "After that, call Mei.",
        "Nura does not decide what is wrong.",
    ]
    lines = await active_lines(sg, context=owner, registry=REGISTRY)
    assert len(lines) == 1  # nothing here changes a medicine
