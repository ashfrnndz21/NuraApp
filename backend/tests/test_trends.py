"""E09-01: lab trends with age- and lab-adjusted reference ranges.

    Acceptance: trend per analyte with range band and direction in words.

A trend is a pattern to discuss, never a diagnosis (.claude/rules/safety.md): every line
passes plain words in every language, a word that places the number is only ever beside the
lab's own range, no line names a cause or a treatment, and the boundary line is last. The
range fits him on the day — his age band from the decade he was born in, his sex when the
record holds it, the lab's printed range when the paper names the lab — and the direction
is arithmetic over the last three results. It is rendered from a State checked against the
record, and written as a card carrying the boundary line.
"""

from __future__ import annotations

import itertools
import json
import re
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery import trend_strings as words
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.reasoning.models import Direction, TrendCard
from app.reasoning.ranges import (
    FIXTURE_PATH,
    Band,
    FixtureRanges,
    NoRangeBecause,
    RangeSource,
    Sex,
    age_from_decade,
)
from app.reasoning.trends import NoSuchAnalyte, Point, direction_of, trend, trend_lines
from app.safety.boundary import Surface, boundary_line, boundary_lines
from app.safety.plain_words import verify
from app.state.service import StaleState, current_state, latest_snapshot
from tests.conftest import FROZEN_AT
from tests.medicines_support import add, artefact, label, let_in, pa
from tests.paper import LIPID_PANEL, LIPID_PANEL_2025
from tests.trio_support import confirm_paper, refusals

RANGES = FixtureRanges.load()
LANGUAGES = ("en", "ms", "zh")

# A cause, a medicine, or anything to do but ask — in each language.
NOT_ON_A_TREND: dict[str, re.Pattern[str]] = {
    "en": re.compile(
        r"\b(because|caused?|due to|take|stop|start|tablets?|medicines?|pills?|diet|eat|"
        r"exercise|dose|diagnos\w*|you have)\b",
        re.IGNORECASE,
    ),
    "ms": re.compile(r"\b(sebab|kerana|ubat|makan|ambil|henti|mula|diet|senaman)\b", re.IGNORECASE),
    "zh": re.compile(r"因为|药|吃|停|开始|运动|诊断|您有"),
}


# --- the table -------------------------------------------------------------------------


def test_every_band_names_a_published_source_and_every_analyte_is_on_file() -> None:
    data = json.loads(FIXTURE_PATH.read_text())
    assert {a.id for a in RANGES.analytes()} == {
        "total_cholesterol",
        "ldl",
        "hdl",
        "triglycerides",
        "hba1c",
        "creatinine",
        "egfr",
        "potassium",
        "haemoglobin",
        "tsh",
    }
    for analyte, entry in data["analytes"].items():
        for band in entry["bands"]:
            assert band["source"] in data["sources"], analyte
    assert set(words.NAMES["en"]) == {a.id for a in RANGES.analytes()}
    for language in LANGUAGES:
        assert set(words.NAMES[language]) == set(words.NAMES["en"]), language


def test_the_age_band_is_read_from_the_decade_he_was_born_in() -> None:
    assert age_from_decade(1951, date(2023, 9, 7)) == 68
    assert age_from_decade(1958, date(2023, 9, 7)) == 68  # the decade, never the year
    assert age_from_decade(1951, date(2025, 8, 29)) == 70
    under_70 = RANGES.range_for("tsh", age=68, sex=None, lab=None).range
    in_70s = RANGES.range_for("tsh", age=70, sex=None, lab=None).range
    assert under_70 is not None and in_70s is not None
    assert (under_70.upper, in_70s.upper) == (4.0, 5.9)
    assert in_70s.source_id == "surks-hollowell-2007"
    # An age-specific range with no birth year on the record is no range, and says why.
    assert RANGES.range_for("tsh", age=None, sex=None, lab=None).because is NoRangeBecause.NEEDS_AGE
    # An adult-wide range needs no age.
    assert RANGES.range_for("total_cholesterol", age=None, sex=None, lab=None).range is not None


def test_a_range_by_sex_needs_the_sex_on_the_record() -> None:
    assert RANGES.range_for("creatinine", age=70, sex=None, lab=None).because is (
        NoRangeBecause.NEEDS_SEX
    )
    his = RANGES.range_for("creatinine", age=70, sex=Sex.MALE, lab=None).range
    hers = RANGES.range_for("haemoglobin", age=70, sex=Sex.FEMALE, lab=None).range
    assert his is not None and (his.lower, his.upper) == (60, 110)
    assert hers is not None and (hers.lower, hers.upper) == (12.0, None)


def test_the_labs_printed_range_wins_over_the_guideline() -> None:
    guideline = RANGES.range_for("hdl", age=70, sex=Sex.FEMALE, lab=None).range
    printed = RANGES.range_for("hdl", age=70, sex=Sex.FEMALE, lab="bukit_lab").range
    assert guideline is not None and guideline.source is RangeSource.GUIDELINE
    assert printed is not None and printed.source is RangeSource.LAB
    assert (guideline.lower, printed.lower, printed.lab) == (40, 50, "bukit_lab")
    # A lab with no range for an analyte falls back to the guideline.
    fallback = RANGES.range_for("hba1c", age=70, sex=None, lab="bukit_lab").range
    assert fallback is not None and fallback.source is RangeSource.GUIDELINE


def test_where_a_value_sits_is_arithmetic_against_the_table_as_printed() -> None:
    under = RANGES.range_for("total_cholesterol", age=70, sex=None, lab=None).range
    or_more = RANGES.range_for("egfr", age=70, sex=None, lab=None).range
    between = RANGES.range_for("potassium", age=70, sex=None, lab=None).range
    assert under and or_more and between
    assert [under.band_of(v) for v in (199, 200, 230)] == [Band.IN, Band.ABOVE, Band.ABOVE]
    assert [or_more.band_of(v) for v in (59, 60)] == [Band.BELOW, Band.IN]
    assert [between.band_of(v) for v in (3.4, 3.5, 5.2, 5.3)] == [
        Band.BELOW,
        Band.IN,
        Band.IN,
        Band.ABOVE,
    ]


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], Direction.NONE),
        ([230], Direction.ONE),
        ([230, 212], Direction.DOWN),
        ([200, 230], Direction.UP),
        ([200, 205], Direction.STEADY),
        ([180, 230, 200], Direction.MIXED),
        # Only the last three count: an old high does not make today's fall a rise.
        ([300, 180, 190, 200], Direction.UP),
        ([6.1, 6.4, 6.9], Direction.UP),
    ],
)
def test_the_direction_is_arithmetic_over_the_last_three(
    values: list[float], expected: Direction
) -> None:
    assert direction_of(values) is expected


# --- the words -------------------------------------------------------------------------


def _point(analyte: str, value: float, band: Band, source: RangeSource | None) -> Point:
    found = RANGES.range_for(
        analyte, age=70, sex=Sex.MALE, lab="bukit_lab" if source is RangeSource.LAB else None
    ).range
    if found is not None and source is not None and found.source is not source:
        found = None
    return Point(
        fact_id=uuid.uuid4(),
        artifact_id=uuid.uuid4(),
        event_id=None,
        confirmed_by_person_id=uuid.uuid4(),
        value=value,
        unit=None,
        on=date(2025, 8, 29),
        lab=None,
        age=70,
        range=found if source is not None else None,
        no_range_because=None,
        in_analyte_unit=value,
        band=band if found is not None and source is not None else Band.NOT_COMPARED,
    )


def _every_rendering() -> list[tuple[str, list[str]]]:
    """Every analyte, in every language, against the lab's range, a guideline's and none, in
    every band, with every direction, with a named doctor and without."""
    out = []
    for analyte, language, source, band, direction, doctor in itertools.product(
        [a.id for a in RANGES.analytes()],
        LANGUAGES,
        (RangeSource.LAB, RangeSource.GUIDELINE, None),
        (Band.IN, Band.ABOVE, Band.BELOW),
        (Direction.UP, Direction.DOWN, Direction.STEADY, Direction.MIXED, Direction.ONE),
        ("Dr Tan", None),
    ):
        found = RANGES.analyte(analyte)
        assert found is not None
        earlier = _point(analyte, 10.5, band, source)
        latest = _point(analyte, 230, band, source)
        since = date(2023, 9, 7) if direction is not Direction.ONE else None
        lines = trend_lines(found, [earlier, latest], direction, since, language, doctor)
        out.append((language, lines))
    for language in LANGUAGES:
        found = RANGES.analyte("total_cholesterol")
        assert found is not None
        out.append((language, trend_lines(found, [], Direction.NONE, None, language, None)))
    return out


def test_every_line_in_every_language_passes_plain_words() -> None:
    failures = {
        (language, line, finding.problem)
        for language, lines in _every_rendering()
        for line in lines
        for finding in verify(line, language)
        if finding.severity == "fail"
    }
    assert failures == set()


def test_a_word_that_places_the_number_is_only_ever_beside_the_labs_range() -> None:
    for language, lines in _every_rendering():
        for line in lines:
            placed = any(word in line for word in words.JUDGEMENT_WORDS[language])
            if placed:
                assert words.LAB_RANGE_WORDS[language] in line, (language, line)


def test_against_a_guideline_range_nothing_is_said_about_where_he_sits() -> None:
    found = RANGES.analyte("total_cholesterol")
    assert found is not None
    point = _point("total_cholesterol", 230, Band.ABOVE, RangeSource.GUIDELINE)
    lines = trend_lines(found, [point], Direction.ONE, None, "en", "Dr Tan")
    assert lines == [
        "Your cholesterol was 230 on Friday 29 August 2025.",
        "The usual range for your age is under 200.",
        *boundary_lines(Surface.TREND, "en", doctor="Dr Tan"),
    ]
    printed = _point("total_cholesterol", 230, Band.ABOVE, RangeSource.LAB)
    assert trend_lines(found, [printed], Direction.ONE, None, "en", "Dr Tan")[1:3] == [
        "The range on your blood test is under 200.",
        "It is above the range on your blood test.",
    ]


def test_no_line_names_a_cause_or_a_treatment_and_the_boundary_is_last() -> None:
    for language, lines in _every_rendering():
        assert not NOT_ON_A_TREND[language].search(" ".join(lines)), (language, lines)
        endings = {
            boundary_lines(Surface.TREND, language, doctor=doctor) for doctor in ("Dr Tan", None)
        }
        assert tuple(lines[-3:]) in endings, (language, lines)


# --- rendered from State, through the review card ---------------------------------------


async def test_pa_born_in_1951_his_cholesterol_in_malay_with_range_and_direction(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, language="ms")
    await confirm_paper(sg, owner, LIPID_PANEL)
    await confirm_paper(sg, owner, LIPID_PANEL_2025)

    shown = await trend(sg, context=owner, ranges=RANGES, analyte="total_cholesterol")

    assert shown.language == "ms"
    assert [(p.value, p.on) for p in shown.points] == [
        (230, date(2023, 9, 7)),
        (212, date(2025, 8, 29)),
    ]
    first, latest = shown.points
    # Every result carries its provenance: the paper it was read from, the person who said yes.
    assert all(p.artifact_id is not None and p.confirmed_by_person_id for p in shown.points)
    assert (first.range and first.range.source, first.band) == (RangeSource.GUIDELINE, Band.ABOVE)
    assert (latest.lab, latest.range and latest.range.source) == ("bukit_lab", RangeSource.LAB)
    assert (latest.age, shown.birth_decade, shown.sex) == (70, 1950, Sex.MALE)
    assert (shown.direction, shown.direction_since) == (Direction.DOWN, date(2023, 9, 7))
    assert list(shown.lines) == [
        "Kolesterol anda ialah 212 pada Jumaat 29 Ogos 2025.",
        "Julat pada ujian darah anda ialah bawah 200.",
        "Ia di atas julat pada ujian darah anda.",
        "Ia telah turun sejak Khamis 7 September 2023.",
        "Nura menyusun ujian darah anda mengikut tarikh.",
        "Ini bukan nasihat doktor.",
        "Tanya doktor anda.",
    ]
    # Written as a card, stamped with the State and carrying the boundary line.
    card = (await sg.scalars(select(TrendCard))).one()
    assert card.id == shown.card.id and card.state_id is not None
    assert card.boundary == boundary_line(Surface.TREND, "ms")
    assert card.fact_ids == [str(p.fact_id) for p in shown.points]

    # In English, the same numbers; the doctor is named once the record names one.
    await add(sg, owner, label("amlodipine", "5 mg", "1 tab OD"))
    again = await trend(
        sg, context=owner, ranges=RANGES, analyte="total_cholesterol", language="en"
    )
    assert again.lines[0] == "Your cholesterol was 212 on Friday 29 August 2025."
    assert again.lines[-1] == "Ask Dr Tan."


async def test_an_analyte_with_no_result_says_so_and_an_unknown_one_is_refused(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, language="en")
    shown = await trend(sg, context=owner, ranges=RANGES, analyte="hba1c")
    assert shown.points == () and shown.direction is Direction.NONE
    assert shown.lines[0] == "Your papers do not show your sugar test yet."
    with pytest.raises(NoSuchAnalyte):
        await trend(sg, context=owner, ranges=RANGES, analyte="unobtanium")
    assert await refusals(sg, owner, "NoSuchAnalyte")


async def test_a_caregiver_reads_the_trend_from_the_last_snapshot_that_covers_it(
    sg: AsyncSession,
) -> None:
    """A key that cannot recompute State renders from the last snapshot, and is refused only
    while that snapshot has not folded in every result the trend would show."""
    owner = await pa(sg)
    await confirm_paper(sg, owner, LIPID_PANEL)
    mei = await let_in(
        sg,
        owner,
        phone="+6591110002",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.READINGS, Scope.RECORDS},
    )
    hers = await trend(sg, context=mei, ranges=RANGES, analyte="total_cholesterol")
    assert [p.value for p in hers.points] == [230]
    assert hers.card.boundary == boundary_line(Surface.TREND, "ms")
    assert hers.card.state_id == (await latest_snapshot(sg, context=owner)).id  # type: ignore[union-attr]

    # A new result lands through her own key, which cannot recompute State: the last snapshot
    # has not folded it in, so the trend is refused rather than shown on a State behind it.
    await confirm_paper(sg, mei, LIPID_PANEL_2025)
    with pytest.raises(StaleState):
        await trend(sg, context=mei, ranges=RANGES, analyte="total_cholesterol")
    assert await refusals(sg, owner, "StaleState")

    # The owner reads State, which catches it up; her trend shows both results again.
    await current_state(sg, context=owner)
    again = await trend(sg, context=mei, ranges=RANGES, analyte="total_cholesterol")
    assert [p.value for p in again.points] == [230, 212]
    assert again.direction is Direction.DOWN


async def test_the_birth_decade_is_read_from_the_setting_then_the_lab_header(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, language="en")
    await confirm_paper(sg, owner, LIPID_PANEL_2025)  # the header says 1951
    assert (await trend(sg, context=owner, ranges=RANGES, analyte="hdl")).birth_decade == 1950
    said = await record_event(
        sg,
        context=owner,
        kind=EventKind.MESSAGE,
        occurred_at=FROZEN_AT,
        label="onboarding settings",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        sg,
        context=owner,
        subject="setting",
        attribute="birth_decade",
        value=1960,
        confidence=1.0,
        event_id=said.id,
    )
    shown = await trend(sg, context=owner, ranges=RANGES, analyte="hdl")
    assert shown.birth_decade == 1960 and shown.points[-1].age == 2025 - 1965


async def test_without_a_setting_or_a_year_the_lab_headers_age_gives_the_decade(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, language="en")
    await confirm_paper(sg, owner, LIPID_PANEL)
    paper = await artefact(sg, owner)
    await assert_fact(
        sg,
        context=owner,
        subject="person",
        attribute="age",
        value=72,
        confidence=0.9,
        artifact_id=paper.id,
        valid_from=datetime(2023, 9, 6, 16, 0, tzinfo=UTC),
    )
    # 72 on a paper of 2023: born about 1951, in the 1950s.
    assert (await trend(sg, context=owner, ranges=RANGES, analyte="hdl")).birth_decade == 1950


async def test_a_key_without_that_part_of_the_record_is_refused(sg: AsyncSession) -> None:
    owner = await pa(sg)
    await confirm_paper(sg, owner, LIPID_PANEL)
    siti = await let_in(
        sg, owner, phone="+6591110003", name="Siti", role=KeyRole.HELPER, scopes={Scope.MEDICINES}
    )
    with pytest.raises(OutOfScope):
        await trend(sg, context=siti, ranges=RANGES, analyte="total_cholesterol")
    refused = await refusals(sg, owner, "OutOfScope")
    assert any(entry.scope is Scope.RECORDS and entry.target == "trend_card" for entry in refused)
