"""E05-01, E14-01: the pre-visit brief at T-3, on one page, with his symptoms on it.

    E05-01 — Generated at T-3 days; editable; one page.
    E14-01 — Logged in his words; appears in the pre-visit brief.

The brief is rendered three days before a visit by E11's engine and its card handed to him
under the cap on briefs a day; it fits one page (`LINE_BUDGET`), each over-long section folded
into a line that says how many more; a symptom written down since the last visit is a line of
its own, in the symptom log's own words, with how much and since when — never a count under
his papers. The brief's lines come from the record and are not edited; what he and his chief
add goes on the questions card (E05-02).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import Delivery, DeliveryOutcome, TriggerType
from app.reasoning.visits.brief import (
    LINE_BUDGET,
    Changed,
    Line,
    build_brief,
    compose,
)
from app.reasoning.visits.models import Brief
from app.reasoning.visits.questions import require_visit
from app.regions import Region
from app.safety.symptom_log import log_symptom, symptoms_since
from tests.delivery_support import Home, home, via_for
from tests.safety_support import assert_plain, transcriber_for
from tests.visits import REGISTRY, pa, reading, visit

SGT = ZoneInfo("Asia/Singapore")


class _Store:
    region = Region.SG

    def __init__(self) -> None:
        self.kept: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.kept[key] = data

    async def get(self, key: str) -> bytes:
        return self.kept[key]


async def _log(session: AsyncSession, context, words: str):
    return await log_symptom(
        session,
        context=context,
        store=_Store(),
        transcriber=transcriber_for(context.region),
        registry=REGISTRY,
        via=via_for(context.region),
        words=words,
    )


# --- E14-01: symptoms on the brief ----------------------------------------------------------


async def test_a_symptom_since_the_last_visit_is_its_own_line_in_his_words_and_not_a_paper(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en")
    await reading(sg, context)
    await _log(sg, context, "dizzy, quite a lot, since this morning")
    _provider, appointment = await visit(sg, context)
    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    changed = [line for line in brief.lines if line["section"] == "changed"]
    assert [(line["key"], line["text"]) for line in changed] == [
        ("changed_readings", "Since Thursday 3 September, 1 new numbers are in your blood pressure book."),
        ("symptom", "Pa felt dizzy on Thursday 3 September."),
        ("symptom_detail", "It was quite bad and it started this morning."),
    ]
    # Never counted under his papers.
    assert "changed_papers" not in {line["key"] for line in brief.lines}
    # The same words the symptom log says back: one vocabulary.
    log = await symptoms_since(sg, context=context, language="en")
    [entry] = log.entries
    assert changed[1]["text"] == entry.lines[0].text
    assert changed[1]["sources"] == [str(entry.fact_id)] == changed[2]["sources"]
    assert_plain([line["text"] for line in brief.lines])


async def test_a_symptom_in_malay_is_said_in_malay(sg: AsyncSession) -> None:
    context = await pa(sg, language="ms", phone="+6591110082")
    await _log(sg, context, "pening, agak banyak, sejak semalam")
    _provider, appointment = await visit(sg, context)
    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    said = [line["text"] for line in brief.lines if line["key"].startswith("symptom")]
    assert said == [
        "Pa rasa pening pada Khamis 3 September.",
        "Rasanya agak teruk dan ia bermula semalam.",
    ]
    assert_plain(said, "ms")


# --- E05-01: one page -----------------------------------------------------------------------


async def test_the_brief_fits_one_page_whatever_the_record_holds(sg: AsyncSession) -> None:
    context = await pa(sg, language="en", phone="+6591110083")
    _provider, appointment = await visit(sg, context)
    seen = await require_visit(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    symptoms = [
        [
            Line("changed", "symptom", "Pa felt dizzy on Thursday 3 September.", (f"s{n}",)),
            Line("changed", "symptom_detail", "It was quite bad.", (f"s{n}",)),
        ]
        for n in range(6)
    ]
    lines = compose(
        visit=seen,
        since_day="Monday 1 September",
        changed=Changed(readings=["r"], medicines=["m"], papers=["p"], how_you_are=["h"]),
        proposed_lines=[
            (f"q{n}", "Ask Dr Tan how often to take your blood pressure.", ()) for n in range(9)
        ],
        bring_memos=[(f"m{n}", "Bring your blood pressure book.") for n in range(7)],
        has_medicines=True,
        context=context,
        symptoms=symptoms,
    )
    assert len(lines) + 3 <= LINE_BUDGET  # the three boundary lines follow
    keys = [line.key for line in lines]
    assert keys.count("symptom") <= 2 and "symptoms_more" in keys
    questions = [line.text for line in lines if line.section == "questions"]
    assert len(questions) == 4 and questions[-1] == "Nura has 6 more questions for Dr Tan."
    bring = [line.text for line in lines if line.section == "bring"]
    assert bring[-1] == "Nura has 6 more things for you to bring on the day."
    # The two fixed lines, the first memo, and one line for the rest.
    assert len(bring) == 4
    assert_plain([line.text for line in lines])
    # What fits is not folded: four questions are four lines, and no "more".
    fits = compose(
        visit=seen,
        since_day="Monday 1 September",
        changed=Changed(),
        proposed_lines=[(f"q{n}", "Ask Dr Tan how often to take your blood pressure.", ()) for n in range(4)],
        bring_memos=[],
        has_medicines=False,
        context=context,
    )
    assert [line.key for line in fits if line.section == "questions"] == ["q0", "q1", "q2", "q3"]


# --- E05-01: generated at T-3 ---------------------------------------------------------------


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _briefs(report: Report) -> list[Delivery]:
    return [s.delivery for s in report.sent if s.delivery.trigger_type is TriggerType.BRIEF]


async def test_the_brief_is_rendered_three_days_before_and_its_card_goes_once_under_the_cap(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    # Two visits on Thursday 17 September: three days on from Monday the 14th.
    _tan, first = await visit(sg, h.owner, when=at(10, day=17), doctor="Dr Tan")
    _lim, second = await visit(sg, h.owner, when=at(15, day=17), doctor="Dr Lim")
    # Before his breakfast (07:30): nothing yet.
    assert _briefs(await _run(sg, h, clock, at(7, 20))) == []
    report = await _run(sg, h, clock, at(7, 31))
    rows = _briefs(report)
    assert [row.outcome for row in rows] == [DeliveryOutcome.SENT, DeliveryOutcome.CAPPED], [
        (row.outcome, row.reason) for row in rows
    ]
    sent, held = rows
    assert sent.rule == "brief_three_days_before" and sent.template_name == "visit_brief"
    assert sent.why["days_before"] == 3 and held.reason == "1 a day"
    # The brief was rendered then — T-3 — and the row the delivery names is it.
    brief = await sg.get(Brief, __import__("uuid").UUID(sent.why["brief_id"]))
    assert brief is not None and brief.built_at == at(7, 31)
    assert brief.appointment_id in (first.id, second.id)
    text = h.sent_to(h.pa)[-1].splitlines()
    assert text[0] == "Your visit is in a few days."
    assert text[1].startswith("You see Dr ") and text[1].endswith("on Thursday 17 September at 10 in the morning.") or "Thursday 17 September" in text[1]
    assert text[-2:] == ["This is not a doctor's advice.", "Ask Dr Tan."] or text[-1].startswith("Ask ")
    assert_plain(text)
    # Once: later that day nothing more for the first; the next day the second goes.
    assert [r.outcome for r in _briefs(await _run(sg, h, clock, at(9)))] == []
    tuesday = _briefs(await _run(sg, h, clock, at(7, 31, day=15)))
    assert [(r.outcome, r.why["days_before"]) for r in tuesday] == [(DeliveryOutcome.SENT, 2)]
    # The day before is the visit reminder's, not the brief's.
    assert _briefs(await _run(sg, h, clock, at(7, 31, day=16))) == []
    every = (await sg.scalars(select(Delivery).where(Delivery.trigger_type == TriggerType.BRIEF))).all()
    assert sorted(str(r.why["appointment_id"]) for r in every if r.outcome is DeliveryOutcome.SENT) == sorted(
        [str(first.id), str(second.id)]
    )
