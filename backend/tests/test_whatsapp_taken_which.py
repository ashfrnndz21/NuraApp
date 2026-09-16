"""#162: a WhatsApp "Taken" that could be about more than one tablet asks which, and writes
nothing until the answer says exactly which.

Pa takes two tablets with breakfast — his blood pressure tablet and the water pill. One
"Taken" used to be written against whichever tablet came first. Now, with more than one open
at that moment (two windows open, or two ladders that asked him), he is asked which, by
number, each tablet in his words with the number on its box and its moment. Only an answer
that says exactly which is written down — "1", "2", "both", or the tablet's own word — and the
ladder stops for those tablets and no other. Siti's "sudah beri" follows the same rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.engine import run_due
from app.delivery.triggers.models import Ladder, Subject
from app.identity.service import register_person
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import DoseTaken, MedicationLine
from app.regions import Region
from tests.medicines_support import add, label
from tests.support import agree_to_family_sharing
from tests.whatsapp_support import PA, SITI, Family, family

MONDAY_6AM = datetime(2026, 9, 13, 22, 0, tzinfo=UTC)
"""06:00 on Monday 14 September, his wall clock."""
BREAKFAST = datetime(2026, 9, 13, 23, 40, tzinfo=UTC)
"""07:40: both breakfast windows open."""
AFTER_BREAKFAST = datetime(2026, 9, 14, 0, 31, tzinfo=UTC)
"""08:31: both windows closed untapped, and a ladder asks him about each."""

ASKED = [
    "Which tablet did you take?",
    "Send 1 for your blood pressure tablet, 5 on the box, with breakfast.",
    "Send 2 for the water pill, 40 on the box, with breakfast.",
    "Send both if you took both.",
]
NOT_SURE = ["I am not sure which tablet you mean.", "I did not write anything down yet."]


async def _two_at_breakfast(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> tuple[Family, MedicationLine, MedicationLine]:
    clock.set(MONDAY_6AM)
    home = await family(sg, tmp_path)
    pressure = await add(sg, home.owner, label("amlodipine", "5 mg", "1 tab OM"))
    water = await add(sg, home.owner, label("frusemide", "40 mg", "1 tab OM"))
    return home, pressure.line, water.line


async def _ladders_after_breakfast(sg: AsyncSession, home: Family, clock: FrozenClock) -> None:
    clock.set(AFTER_BREAKFAST)
    await run_due(
        sg,
        via=Via.of(home.settings, home.providers),
        profile_id=home.profile.id,
        at=AFTER_BREAKFAST,
    )


async def _taps(sg: AsyncSession) -> list[DoseTaken]:
    return list((await sg.scalars(select(DoseTaken))).all())


async def _dose_ladders(sg: AsyncSession) -> dict[object, Ladder]:
    rows = (await sg.scalars(select(Ladder).where(Ladder.subject == Subject.DOSE))).all()
    return {ladder.line_id: ladder for ladder in rows}


def _said(handled: object) -> list[list[str]]:
    return [reply.text.splitlines() for reply in handled.replies]  # type: ignore[attr-defined]


async def test_two_tablets_open_at_breakfast_are_asked_about_and_nothing_is_written(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, _, _ = await _two_at_breakfast(sg, tmp_path, clock)
    clock.set(BREAKFAST)
    asked = await home.inbound(sg, PA, "Taken")
    assert asked.outcome == "which_tablet"
    assert _said(asked) == [ASKED]
    assert await _taps(sg) == []


async def test_a_number_writes_that_tablet_alone_and_stops_its_ladder_alone(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, pressure, water = await _two_at_breakfast(sg, tmp_path, clock)
    await _ladders_after_breakfast(sg, home, clock)
    assert set(await _dose_ladders(sg)) == {pressure.id, water.id}

    asked = await home.inbound(sg, PA, "Taken")
    assert asked.outcome == "which_tablet" and _said(asked) == [ASKED]
    assert await _taps(sg) == []

    answered = await home.inbound(sg, PA, "1")
    assert answered.outcome == "taken"
    assert _said(answered) == [
        [
            "Thank you, I wrote it down.",
            "You took your blood pressure tablet with breakfast.",
            "Mei can see you took it.",
        ]
    ]
    [tap] = await _taps(sg)
    assert tap.line_id == pressure.id and tap.anchor == "breakfast"
    ladders = await _dose_ladders(sg)
    assert ladders[pressure.id].closed_because == "answered"
    assert ladders[water.id].closed_at is None
    # The question is answered once: another "1" is not a second tap.
    again = await home.inbound(sg, PA, "1")
    assert again.outcome != "taken" and len(await _taps(sg)) == 1


async def test_both_writes_both_and_stops_both_ladders(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, pressure, water = await _two_at_breakfast(sg, tmp_path, clock)
    await _ladders_after_breakfast(sg, home, clock)
    await home.inbound(sg, PA, "Taken")
    answered = await home.inbound(sg, PA, "both")
    assert answered.outcome == "taken"
    assert _said(answered) == [
        [
            "Thank you, I wrote it down.",
            "You took your blood pressure tablet and the water pill with breakfast.",
            # Two tablets: "took it" would name only one of them (#173).
            "Mei can see you took them.",
        ]
    ]
    assert {tap.line_id for tap in await _taps(sg)} == {pressure.id, water.id}
    assert all(ladder.closed_because == "answered" for ladder in (await _dose_ladders(sg)).values())


async def test_the_tablets_own_word_answers_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, pressure, water = await _two_at_breakfast(sg, tmp_path, clock)
    clock.set(BREAKFAST)
    await home.inbound(sg, PA, "Taken")
    answered = await home.inbound(sg, PA, "I took the water pill")
    assert answered.outcome == "taken"
    assert _said(answered)[0][1] == "You took the water pill with breakfast."
    [tap] = await _taps(sg)
    assert tap.line_id == water.id
    # The other one is still open: his next "Taken" is about it alone, and is written at once.
    rest = await home.inbound(sg, PA, "Taken")
    assert rest.outcome == "taken"
    assert {tap.line_id for tap in await _taps(sg)} == {pressure.id, water.id}


async def test_an_answer_that_does_not_say_which_writes_nothing_and_asks_again(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, _, water = await _two_at_breakfast(sg, tmp_path, clock)
    clock.set(BREAKFAST)
    await home.inbound(sg, PA, "Taken")
    for unclear in ("the tablet", "3", "0"):
        answer = await home.inbound(sg, PA, unclear)
        assert answer.outcome == "which_tablet", unclear
        assert _said(answer) == [NOT_SURE, ASKED], unclear
    assert await _taps(sg) == []
    answered = await home.inbound(sg, PA, "2")
    assert answered.outcome == "taken"
    [tap] = await _taps(sg)
    assert tap.line_id == water.id


async def test_a_word_that_names_two_tablets_on_the_list_is_not_an_answer(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(MONDAY_6AM)
    home = await family(sg, tmp_path)
    await add(sg, home.owner, label("amlodipine", "5 mg", "1 tab OM"))
    losartan = await add(sg, home.owner, label("losartan", "50 mg", "1 tab OM"))
    clock.set(BREAKFAST)
    asked = await home.inbound(sg, PA, "Taken")
    assert _said(asked) == [
        [
            "Which tablet did you take?",
            "Send 1 for your blood pressure tablet, 5 on the box, with breakfast.",
            "Send 2 for your blood pressure tablet, 50 on the box, with breakfast.",
            "Send both if you took both.",
        ]
    ]
    unclear = await home.inbound(sg, PA, "blood pressure tablet")
    assert unclear.outcome == "which_tablet" and _said(unclear)[0] == NOT_SURE
    assert await _taps(sg) == []
    # Its own name says exactly which, and the read-back tells it apart by its box.
    answered = await home.inbound(sg, PA, "losartan")
    assert answered.outcome == "taken"
    assert _said(answered)[0][1] == (
        "You took your blood pressure tablet, 50 on the box, with breakfast."
    )
    [tap] = await _taps(sg)
    assert tap.line_id == losartan.line.id


async def test_a_name_with_a_no_beside_it_or_two_names_is_not_an_answer(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, _, water = await _two_at_breakfast(sg, tmp_path, clock)
    clock.set(BREAKFAST)
    await home.inbound(sg, PA, "Taken")
    for unclear in (
        "the water pill, not the blood pressure tablet",
        "amlodipine not frusemide",
        "the water pill and the blood pressure tablet",
        "belum pil air",
    ):
        answer = await home.inbound(sg, PA, unclear)
        assert answer.outcome == "which_tablet" and _said(answer)[0] == NOT_SURE, unclear
    assert await _taps(sg) == []
    # "Took both", and a word typed in quotes as the question shows it, are answers.
    answered = await home.inbound(sg, PA, "took both")
    assert answered.outcome == "taken" and len(await _taps(sg)) == 2
    assert water.id in {tap.line_id for tap in await _taps(sg)}


async def test_a_question_whose_tablet_left_the_list_is_asked_again_and_nothing_written(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    import uuid

    from app.audit.access import audited_write
    from app.channels.whatsapp.models import DoseQuestion, WhatsAppThread
    from app.keys.scopes import Scope as Part

    home, _, water = await _two_at_breakfast(sg, tmp_path, clock)
    clock.set(BREAKFAST)
    await home.inbound(sg, PA, "Taken")
    thread = (await sg.scalars(select(WhatsAppThread))).one()
    clock.set(datetime(2026, 9, 13, 23, 41, tzinfo=UTC))
    # As if the first tablet it read out had been stopped since: its line is not on today's list.
    await audited_write(
        sg,
        DoseQuestion,
        home.owner,
        Part.MEDICINES,
        thread_id=thread.id,
        asked_at=datetime(2026, 9, 13, 23, 41, tzinfo=UTC),
        expires_at=datetime(2026, 9, 14, 1, 41, tzinfo=UTC),
        doses=[
            {"line_id": str(uuid.uuid4()), "anchor": "breakfast"},
            {"line_id": str(water.id), "anchor": "breakfast"},
        ],
    )
    stale = await home.inbound(sg, PA, "2")
    assert stale.outcome == "which_tablet"
    assert _said(stale) == [NOT_SURE, ASKED]
    assert await _taps(sg) == []


def test_which_tablet_closes_at_the_end_of_his_day() -> None:
    from app.channels.whatsapp.inbound import _question_closes

    morning = datetime(2026, 9, 13, 23, 40, tzinfo=UTC)  # 07:40 his wall clock
    assert _question_closes(morning, Region.SG) == datetime(2026, 9, 14, 1, 40, tzinfo=UTC)
    late = datetime(2026, 9, 14, 15, 30, tzinfo=UTC)  # 23:30 his wall clock
    assert _question_closes(late, Region.SG) == datetime(2026, 9, 14, 16, 0, tzinfo=UTC)


async def test_the_helpers_sudah_beri_follows_the_same_rule(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home, pressure, water = await _two_at_breakfast(sg, tmp_path, clock)
    siti = await register_person(
        sg, region=Region.SG, display_name="Siti", phone_e164=SITI, language="ms"
    )
    helper = {Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND}
    await agree_to_family_sharing(sg, home.owner, siti, scopes=helper)
    await grant_key(sg, context=home.owner, holder=siti, role=KeyRole.HELPER, scopes=helper)
    await _ladders_after_breakfast(sg, home, clock)

    asked = await home.inbound(sg, SITI, "sudah beri")
    assert asked.outcome == "which_tablet"
    assert _said(asked) == [
        [
            "Ubat yang mana anda sudah beri kepada Pa?",
            "Hantar 1 untuk ubat tekanan darah Pa, kotak bertulis 5, bersama sarapan.",
            "Hantar 2 untuk pil air, kotak bertulis 40, bersama sarapan.",
            "Kalau anda sudah beri semua, hantar semua.",
        ]
    ]
    assert await _taps(sg) == []
    given = await home.inbound(sg, SITI, "2")
    assert given.outcome == "taken"
    assert _said(given) == [["Terima kasih, saya sudah tulis.", "Pa sudah ambil pil air."]]
    [tap] = await _taps(sg)
    assert tap.line_id == water.id and tap.by_person_id == siti.id
    ladders = await _dose_ladders(sg)
    assert ladders[water.id].closed_because == "answered"
    assert ladders[pressure.id].closed_at is None
