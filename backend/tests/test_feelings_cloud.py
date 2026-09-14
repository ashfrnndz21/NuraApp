"""E17-01: the feeling cloud on Today — base words, weighted by State, a reason for each.

The acceptance line: words re-rank within a second of a State change; the strip disappears
after a tap or "Fine today". The clock is frozen at Thursday 3 September 2026, 16:00 on Pa's
wall in Singapore, and stepped where a test needs another day.
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.strings import FEELINGS
from app.keys.context import KeyContext
from app.memory.models import EventKind
from app.reasoning.feelings import strings
from app.reasoning.feelings.cloud import Cloud, compose_cloud
from app.reasoning.feelings.service import record_tap
from app.reasoning.feelings.words import (
    ANSWERS,
    BASE,
    Answer,
    FollowUp,
    ReasonCode,
    Weight,
    inferable_words,
)
from app.safety.plain_words import verify
from app.safety.red_flags import Feeling
from tests.family_support import household
from tests.feelings_support import (
    REGISTRY,
    STORE,
    TRANSCRIBER,
    VIA,
    blood_pressure,
    happened,
    new_medicine,
)
from tests.medicines_support import pa


async def _cloud(session: AsyncSession, context: KeyContext, language: str | None = None) -> Cloud:
    return await compose_cloud(session, context=context, registry=REGISTRY, language=language)


def _words(cloud: Cloud) -> list[Feeling]:
    return [word.word for word in cloud.words]


def _reasons(cloud: Cloud, feeling: Feeling) -> set[ReasonCode]:
    return {r.code for word in cloud.words if word.word is feeling for r in word.reasons}


async def _owner(session: AsyncSession) -> KeyContext:
    home = await household(session)
    return await home.ctx(session, home.pa)


async def test_every_cloud_carries_the_base_words_with_fine_today_last(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    cloud = await _cloud(sg, owner)
    assert _words(cloud) == list(BASE)
    assert all(word.weight == Weight.BASE for word in cloud.words)
    assert cloud.words[-1].word is Feeling.FINE and cloud.words[-1].label == "Fine today"
    assert [w.word for w in cloud.words if w.red] == [Feeling.CHEST_TIGHTNESS]
    assert cloud.show is False and cloud.because == "no_change", "shown only after a change"
    assert cloud.prompt == ("How are you feeling today?",)
    assert cloud.state_id is not None, "the cloud names the State it was weighed from"


async def test_a_new_medicine_brings_forward_the_words_its_licensed_monograph_lists(
    sg: AsyncSession,
) -> None:
    owner = await _owner(sg)
    added = await new_medicine(sg, owner)  # amlodipine: dizzy_standing, swollen_ankles
    cloud = await _cloud(sg, owner)
    first = cloud.words[:2]
    assert [word.word for word in first] == [Feeling.DIZZY, Feeling.SWOLLEN_ANKLES]
    assert all(word.weight == Weight.EMPHASISED for word in first)
    dizzy = next(r for r in first[0].reasons if r.code is ReasonCode.NEW_MEDICINE)
    assert dizzy.ids == {
        "line_id": str(added.line.id),
        "generic": "amlodipine",
        "watch_out": "dizzy_standing",
    }
    assert cloud.show is True and cloud.because == "changed"
    assert cloud.prompt == (
        "Your blood pressure tablet is new since Thursday 3 September.",
        "How are you feeling today?",
    )


async def test_only_the_registrys_own_watch_outs_bring_a_word(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    await new_medicine(sg, owner, "metformin", "500 mg")  # tummy_upset only
    cloud = await _cloud(sg, owner)
    assert cloud.words[0].word is Feeling.STOMACH_UPSET
    assert _reasons(cloud, Feeling.DIZZY) == {ReasonCode.BASE}
    assert Feeling.SWOLLEN_ANKLES not in _words(cloud)


async def test_a_medicine_is_new_for_a_fortnight_and_then_brings_nothing(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await _owner(sg)
    await new_medicine(sg, owner)
    clock.step(timedelta(days=15))
    cloud = await _cloud(sg, owner)
    assert _reasons(cloud, Feeling.DIZZY) == {ReasonCode.BASE}
    assert Feeling.SWOLLEN_ANKLES not in _words(cloud)


async def test_the_words_re_rank_within_a_second_of_a_state_change(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    before = await _cloud(sg, owner)
    assert before.words[0].word is Feeling.TIRED
    await new_medicine(sg, owner)
    started = time.perf_counter()
    after = await _cloud(sg, owner)
    assert time.perf_counter() - started < 1.0
    assert after.words[0].word is Feeling.DIZZY
    assert after.state_id != before.state_id, "the new medicine moved State, and the cloud with it"


async def test_his_blood_pressure_going_up_three_times_brings_headache_and_dizzy(
    sg: AsyncSession,
) -> None:
    owner = await _owner(sg)
    facts = [
        await blood_pressure(sg, owner, top, at=utcnow() - timedelta(days=2 - n))
        for n, top in enumerate((132, 140, 148))
    ]
    cloud = await _cloud(sg, owner)
    assert _words(cloud)[:2] == [Feeling.DIZZY, Feeling.HEADACHE]
    trend = next(r for r in cloud.words[0].reasons if r.code is ReasonCode.READING_TREND)
    assert trend.ids == {"fact_ids": [str(fact.id) for fact in facts]}
    assert cloud.prompt[0] == "Your last 3 blood pressure numbers went up each time."
    # A number that comes down ends the direction: nothing here judges how high any was.
    await blood_pressure(sg, owner, 138)
    assert ReasonCode.READING_TREND not in _reasons(await _cloud(sg, owner), Feeling.DIZZY)


async def test_the_first_week_home_from_hospital_comes_forward_every_day(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await _owner(sg)
    await happened(
        sg, owner, EventKind.DISCHARGE, utcnow() - timedelta(days=2), "home from hospital"
    )
    cloud = await _cloud(sg, owner)
    assert _words(cloud)[:4] == [
        Feeling.BREATHLESS,
        Feeling.SWOLLEN_ANKLES,
        Feeling.WEIGHT_GAIN,
        Feeling.CONFUSION,
    ]
    assert cloud.show is True and cloud.because == "after_discharge"
    await record_tap(
        sg,
        context=owner,
        word=Feeling.FINE,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    assert (await _cloud(sg, owner)).because == "tapped_today"
    clock.step(timedelta(days=1))
    assert (await _cloud(sg, owner)).show is True, "day one to seven after a discharge"


async def test_his_own_words_from_the_last_month_come_back(sg: AsyncSession) -> None:
    owner = await _owner(sg)
    await record_tap(
        sg,
        context=owner,
        word=Feeling.CRAMPS,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    cloud = await _cloud(sg, owner)
    cramps = next(word for word in cloud.words if word.word is Feeling.CRAMPS)
    assert cramps.weight == Weight.ADDED
    assert {r.code for r in cramps.reasons} == {ReasonCode.SAID_BEFORE}


async def test_the_strip_goes_after_a_tap_or_fine_today_and_comes_back_after_a_change(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await _owner(sg)
    await new_medicine(sg, owner)
    assert (await _cloud(sg, owner)).show is True
    await record_tap(
        sg,
        context=owner,
        word=Feeling.FINE,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )
    gone = await _cloud(sg, owner)
    assert gone.show is False and gone.because == "tapped_today"
    clock.step(timedelta(days=1))
    still = await _cloud(sg, owner)
    assert still.show is False and still.because == "no_change_since_last_tap"
    await new_medicine(sg, owner, "atorvastatin", "20 mg")  # muscle_ache
    back = await _cloud(sg, owner)
    assert back.show is True and back.because == "changed"
    assert back.words[0].word is Feeling.ACHES


async def test_the_words_are_in_his_language(sg: AsyncSession) -> None:
    his = await pa(sg)  # Malay
    await new_medicine(sg, his)
    cloud = await _cloud(sg, his)
    assert cloud.language == "ms" and cloud.words[0].label == "Pening"
    assert cloud.prompt == (
        "Ubat tekanan darah anda baru sejak Khamis 3 September.",
        "Apa khabar hari ini?",
    )
    chinese = await _cloud(sg, his, "zh")
    assert chinese.words[0].label == "头晕" and chinese.words[-1].label == "今天还好"


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_every_word_and_line_passes_plain_words(language: str) -> None:
    failing = []
    for code, line in strings.catalogue():
        if code != language:
            continue
        kind = "headline" if line in strings.NOTE_HEADLINE.values() else "line"
        failing.extend(f for f in verify(line, code, kind) if f.severity == "fail")
    for table in (strings.WORDS, strings.ANSWER_WORDS, strings.WHEN):
        for words in table[language].values():  # type: ignore[attr-defined]
            failing.extend(f for f in verify(words, language, "phrase") if f.severity == "fail")
    assert failing == []


def test_every_word_has_its_words_in_every_language() -> None:
    for code in ("en", "ms", "zh"):
        assert set(strings.WORDS[code]) == set(Feeling)
        assert set(FEELINGS[code]) >= {feeling.value for feeling in Feeling}
        assert set(strings.TELL[code]) == set(inferable_words())
        assert set(strings.QUESTIONS[code]) == set(FollowUp)
        assert set(strings.ANSWER_WORDS[code]) == set(Answer)
        assert set(strings.WHEN[code]) == set(Answer) - {Answer.YES}
    assert set(ANSWERS) == set(FollowUp)
