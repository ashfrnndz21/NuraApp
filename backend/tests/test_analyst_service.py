"""`app.reasoning.analyst.service`: saving the Health Analyst's report and reading it back
narrowed for a key that did not generate it — a section this narrower key cannot cover is
named in `withheld`, never silently missing (`InsightReportOut.withheld`, #271) — and the
caregiver's own reading of the report's words (`app.channels.about_him.Reader`): second-person
by default, said about him by name to a caregiver reading with her own key, "Pa's age" never
"your age" (`app.delivery.analyst_strings`'s `*_THEIRS` twins)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.about_him import Reader
from app.channels.api.analyst import InsightReportOut
from app.delivery import analyst_strings as words
from app.keys.scopes import KeyRole, Scope
from app.reasoning.analyst.port import Report
from app.reasoning.analyst.rule import RuleAnalyst
from app.reasoning.analyst.service import latest_report, save_report
from tests.medicines_support import REGISTRY, label
from tests.medicines_support import add as add_medicine
from tests.safety_support import let_in, pa


async def _saved_report(session: AsyncSession, owner) -> Report:
    report: Report | None = None
    async for event in RuleAnalyst(registry=REGISTRY).report_stream(
        session, context=owner, language="en"
    ):
        if isinstance(event, Report):
            report = event
    assert report is not None
    await save_report(session, context=owner, report=report)
    return report


# --- withheld, named ---------------------------------------------------------------------------


async def test_a_records_only_key_is_told_what_was_withheld(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150151")
    await add_medicine(sg, owner, label("bisoprolol", "2.5 mg", "1 tab OD"))
    await add_medicine(sg, owner, label("atenolol", "50 mg", "1 tab OD"))
    await _saved_report(sg, owner)

    caregiver = await let_in(
        sg,
        owner,
        phone="+6591150152",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.RECORDS},
    )
    row = await latest_report(sg, context=caregiver)

    # Every section a RECORDS-only key cannot cover is named, never left silently out.
    for key in ("what_changed", "medicines_and_supplements", "what_you_pay", "worth_a_look"):
        assert key in row["withheld"]
    # screenings_due sits under RECORDS, which this key does hold: not withheld.
    assert "screenings_due" not in row["withheld"]
    seen_keys = {s["key"] for s in row["sections"]}
    assert seen_keys.isdisjoint(row["withheld"])
    # What is actually shown and what was withheld never name the same section twice.
    assert set(row["withheld"]) <= {
        "what_changed",
        "worth_a_look",
        "medicines_and_supplements",
        "what_you_pay",
    }


async def test_the_owners_own_key_is_never_told_anything_was_withheld(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150153")
    await _saved_report(sg, owner)
    row = await latest_report(sg, context=owner)
    assert row["withheld"] == []


async def test_the_wire_shape_carries_withheld(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150154")
    await _saved_report(sg, owner)
    caregiver = await let_in(
        sg,
        owner,
        phone="+6591150155",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.RECORDS},
    )
    row = await latest_report(sg, context=caregiver)
    out = InsightReportOut.of_row(row)
    assert out.withheld
    assert set(out.withheld) == set(row["withheld"])


# --- the caregiver's voice ----------------------------------------------------------------------


def test_the_caregiver_reader_says_the_trend_line_about_him_by_name() -> None:
    line = words.fill(words.TREND_LINE["en"], name=words.BP_NAME["en"]["systolic"], day="Monday 14 September")
    assert line == "Your top blood pressure number was outside the usual range on Monday 14 September."

    reader = Reader(his=False, name="Pa", language="en")
    heard = reader.says(line)
    assert heard == "Pa's top blood pressure number was outside the usual range on Monday 14 September."
    assert "your" not in heard.lower()


def test_the_caregiver_reader_says_the_screening_why_about_him_by_name() -> None:
    line = words.SCREENING_WHY["en"]
    reader = Reader(his=False, name="Pa", language="en")
    heard = reader.says(line)
    assert heard == "This compares Pa's age and what has been told to Nura with a general guide."
    assert "your" not in heard.lower()


def test_the_caregiver_reader_says_the_withheld_line_about_him_by_name() -> None:
    line = words.fill(words.WITHHELD_LINE["en"], title=words.SECTION_TITLES["en"]["what_changed"])
    assert line == "What changed is not shown to you."
    reader = Reader(his=False, name="Pa", language="en")
    heard = reader.says(line)
    assert heard == "What changed is not shown to Pa."


def test_his_own_key_hears_every_line_unchanged() -> None:
    line = words.fill(words.SUPPLEMENT_LINE["en"], name="the joint supplement")
    reader = Reader(his=True)
    assert reader.says(line) == line
