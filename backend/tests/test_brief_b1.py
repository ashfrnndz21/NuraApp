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

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import Delivery, DeliveryOutcome, TriggerType
from app.keys.scopes import KeyRole, Scope
from app.reasoning.visits.brief import (
    LINE_BUDGET,
    Changed,
    Line,
    NoBriefYet,
    _fold,
    brief_for,
    build_brief,
    compose,
    latest_brief,
    lines_for,
)
from app.reasoning.visits.guard import can_render_brief
from app.reasoning.visits.models import Brief
from app.reasoning.visits.questions import require_visit
from app.regions import Region
from app.safety.symptom_log import log_symptom, symptoms_since
from app.state.service import current_state
from tests.delivery_support import Home, home, via_for
from tests.safety_support import assert_plain, let_in, transcriber_for
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
        ("changed_readings_one", "Since Thursday 3 September, 1 new number is in your blood pressure book."),
        ("symptom", "You felt dizzy on Thursday 3 September."),
        # Since when, anchored to that day: he reads the brief days later.
        ("symptom_detail", "It was quite bad."),
        ("symptom_detail", "It started that morning."),
    ]
    # Never counted under his papers.
    assert "changed_papers" not in {line["key"] for line in brief.lines}
    log = await symptoms_since(sg, context=context, language="en")
    [entry] = log.entries
    assert changed[1]["sources"] == [str(entry.fact_id)] == changed[2]["sources"] == changed[3]["sources"]
    assert_plain([line["text"] for line in brief.lines])


async def test_a_symptom_in_malay_is_said_in_malay(sg: AsyncSession) -> None:
    context = await pa(sg, language="ms", phone="+6591110082")
    await _log(sg, context, "pening, agak banyak, sejak semalam")
    _provider, appointment = await visit(sg, context)
    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    said = [line["text"] for line in brief.lines if line["key"].startswith("symptom")]
    assert said == [
        "Anda rasa pening pada Khamis 3 September.",
        "Rasanya agak teruk.",
        "Ia bermula sehari sebelumnya.",
    ]
    assert_plain(said, "ms")


async def test_a_key_without_the_record_reads_the_brief_without_how_he_feels(
    sg: AsyncSession,
) -> None:
    """A symptom is the record's: a viewer who holds the visits and not the record reads the
    brief without the lines about how he feels, and is told the record was withheld. It keeps
    the words of the lines it does read and loses their provenance: a source is a row id, and
    this key may not read those rows (B1 review)."""
    context = await pa(sg, language="en", phone="+6591110084")
    await _log(sg, context, "dizzy, quite a lot, since this morning")
    _provider, appointment = await visit(sg, context)
    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    viewer = await let_in(
        sg, context, phone="+6593330084", name="Kit", role=KeyRole.VIEWER, scopes={Scope.VISITS}
    )
    shown, withheld = lines_for(brief, viewer)
    # This key holds the visits alone, so every scope a fact can sit under is named.
    assert withheld == [Scope.READINGS, Scope.MEDICINES, Scope.RECORDS]
    assert not any(line["key"].startswith("symptom") for line in shown)
    assert all(line["sources"] == [] for line in shown)
    mine, none = lines_for(brief, context)
    assert none == [] and any(line["key"] == "symptom" for line in mine)
    assert any(line["sources"] for line in mine), "the owner reads the brief's provenance"


async def test_a_red_flag_symptom_comes_first_and_a_long_entry_is_cut_never_dropped(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en", phone="+6591110085")
    await _log(sg, context, "tired")
    await _log(sg, context, "chest pain")
    await _log(sg, context, "dizzy")
    _provider, appointment = await visit(sg, context)
    brief = await build_brief(sg, context=context, appointment_id=appointment.id, registry=REGISTRY)
    felt = [line["text"] for line in brief.lines if line["key"] == "symptom"]
    assert felt[0] == "You felt chest pain on Thursday 3 September."
    group = [Line("changed", "symptom", f"You felt tired on day {n}.", ("s",)) for n in range(5)]
    more = Line("changed", "symptoms_more", "Nura has more notes about how you feel.")
    assert _fold([group], 4, more) == [*group[:3], more]


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
    assert bring[-1] == "Nura has 6 more things for you to bring on Thursday 10 September."
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
    doctor = "Dr Tan" if brief.appointment_id == first.id else "Dr Lim"
    hour = "10 in the morning" if brief.appointment_id == first.id else "3 in the afternoon"
    assert text == [
        "Your next visit is on Thursday 17 September.",
        f"You see {doctor} at {hour}.",
        "This visit is about your blood pressure.",
        "Bring your blood pressure book on Thursday 17 September.",
        "Nura prepared this from your papers.",
        "This is not a doctor's advice.",
        f"Ask {doctor}.",
    ]
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


# --- B1 review: a read-only visits key reads the brief, it does not render one ----------------


async def test_a_read_only_visits_key_reads_the_brief_as_it_stands_after_his_state_moves(
    sg: AsyncSession,
) -> None:
    """A viewer and a clinic key hold `Scope.VISITS` to read and are not among `CHANGERS`,
    so rendering is not theirs (`guard.may_render_brief`). `GET …/brief` rebuilds whenever
    State has moved past the newest brief — which would refuse them the read the moment the
    record moved. They get the brief as it stands instead (B1 review)."""
    context = await pa(sg, language="en")
    await reading(sg, context)
    _, appointment = await visit(sg, context)
    stood = await brief_for(
        sg, context=context, appointment_id=appointment.id, registry=REGISTRY
    )
    # His State moves past it: a symptom written down after the brief was rendered.
    await _log(sg, context, "dizzy, quite a lot, since this morning")
    moved = await current_state(sg, context=context)
    assert moved.id != stood.state_id, "the symptom did not move his State"

    for phone, name, role in (
        ("+6591110007", "Wei", KeyRole.VIEWER),
        ("+6591110008", "Clinic", KeyRole.CLINIC),
    ):
        key = await let_in(sg, context, phone=phone, name=name, role=role)
        assert Scope.VISITS in key.scopes and not can_render_brief(key)
        read = await brief_for(
            sg, context=key, appointment_id=appointment.id, registry=REGISTRY
        )
        # The one that stands, not a new one, and no refusal.
        assert read.id == stood.id and read.state_id == stood.state_id
        assert await latest_brief(sg, context=key, appointment_id=appointment.id) == read

    # And the key that may render it still gets the record as it is now.
    now = await current_state(sg, context=context)
    rebuilt = await brief_for(
        sg, context=context, appointment_id=appointment.id, registry=REGISTRY
    )
    assert rebuilt.id != stood.id and rebuilt.state_id == now.id


async def test_a_read_only_visits_key_is_told_when_no_brief_has_been_rendered_yet(
    sg: AsyncSession,
) -> None:
    """Nothing to read and nothing it may render: `NoBriefYet`, not a brief built under a key
    that is not allowed to render one."""
    context = await pa(sg, language="en")
    await reading(sg, context)
    _, appointment = await visit(sg, context)
    key = await let_in(sg, context, phone="+6591110009", name="Wei", role=KeyRole.VIEWER)
    with pytest.raises(NoBriefYet):
        await brief_for(sg, context=key, appointment_id=appointment.id, registry=REGISTRY)
    assert await latest_brief(sg, context=key, appointment_id=appointment.id) is None
