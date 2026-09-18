"""The Health Analyst's default adapter (`app.reasoning.analyst.rule.RuleAnalyst`): five real
reads, each a candidate list through `app.reasoning.analyst.pipeline.finalize` before it is
shown. Mocked throughout — no live model call, no API key (`RuleAnalyst` calls none)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.insurance.claim import ClaimStatus
from app.insurance.policy import PolicyStatus
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.onboarding.settings import SettingsValues, save_settings
from app.reasoning.analyst.pipeline import Candidate, drop_reroute, finalize
from app.reasoning.analyst.port import (
    AskWho,
    Confidence,
    Evidence,
    Insight,
    InsightKind,
    Report,
    Step,
)
from app.reasoning.analyst.rule import RuleAnalyst
from app.reasoning.visits.models import MemoKind, MemoSource
from tests.medicines_support import REGISTRY, label
from tests.medicines_support import add as add_medicine
from tests.safety_support import clinic, let_in, pa
from tests.test_insurance_ledger import _file, _move
from tests.test_insurance_policy import _write as write_policy
from tests.timeline_support import book


async def _report(
    session: AsyncSession, context, *, language: str = "en", now: datetime | None = None
) -> Report:
    analyst = RuleAnalyst(registry=REGISTRY)
    report: Report | None = None
    async for event in analyst.report_stream(session, context=context, language=language, now=now):
        if isinstance(event, Report):
            report = event
    assert report is not None
    return report


async def _lab_fact(
    session: AsyncSession, context, *, subject: str, attribute: str, value: object, on: datetime
) -> None:
    """A lab-report fact (#257's own shape: subject the panel, attribute the analyte),
    EXTRACTED — no confirmation needed — `valid_from` the day the result is from."""
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=on,
        label="a lab result",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        session,
        context=context,
        subject=subject,
        attribute=attribute,
        value=value,
        confidence=1.0,
        confidence_state=ConfidenceState.EXTRACTED,
        event_id=event.id,
        valid_from=on,
    )


def _section(report: Report, key: str):
    return next((s for s in report.sections if s.key == key), None)


async def test_a_supplement_with_no_condition_on_file_is_flagged(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150011")
    await save_settings(
        sg, context=owner, values=SettingsValues(language="en", conditions=("high_blood_pressure",))
    )
    await add_medicine(sg, owner, label("glucosamine", "1500 mg", "1 tab OD"))

    report = await _report(sg, owner)
    section = _section(report, "medicines_and_supplements")
    assert section is not None
    supplements = [i for i in section.insights if i.kind is InsightKind.SUPPLEMENT]
    assert len(supplements) == 1
    assert supplements[0].ask_who is AskWho.PHARMACIST
    assert supplements[0].evidence


async def test_a_supplement_with_a_matching_condition_is_not_flagged(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150012")
    await save_settings(
        sg, context=owner, values=SettingsValues(language="en", conditions=("joints",))
    )
    await add_medicine(sg, owner, label("glucosamine", "1500 mg", "1 tab OD"))

    report = await _report(sg, owner)
    section = _section(report, "medicines_and_supplements")
    assert section is not None
    assert not [i for i in section.insights if i.kind is InsightKind.SUPPLEMENT]


async def test_two_medicines_in_the_same_class_are_flagged_as_duplicate_therapy(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591150013")
    await add_medicine(sg, owner, label("bisoprolol", "2.5 mg", "1 tab OD"))
    await add_medicine(sg, owner, label("atenolol", "50 mg", "1 tab OD"))

    report = await _report(sg, owner)
    section = _section(report, "medicines_and_supplements")
    assert section is not None
    duplicates = [i for i in section.insights if i.kind is InsightKind.MEDICINE]
    assert len(duplicates) == 1
    assert duplicates[0].ask_who is AskWho.PHARMACIST
    assert len(duplicates[0].evidence) == 2


async def test_a_screening_is_due_by_age_and_by_condition(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150014")
    await save_settings(
        sg,
        context=owner,
        values=SettingsValues(language="en", conditions=("diabetes",), birth_decade=2000),
    )
    report = await _report(sg, owner)
    section = _section(report, "screenings_due")
    assert section is not None
    keys = {i.insight_id for i in section.insights}
    # diabetes (a condition, whatever his age) and the eye check and kidney check it also
    # opens; not the cholesterol test, which this table only opens from 40.
    assert "screening:diabetes_screening" in keys
    assert "screening:eye_check" in keys
    assert "screening:cholesterol_test" not in keys
    assert all(i.ask_who is AskWho.DOCTOR for i in section.insights)


NOW = datetime(2026, 9, 18, 8, 0, tzinfo=UTC)


async def test_a_screening_done_inside_its_interval_is_not_due(sg: AsyncSession) -> None:
    """The sugar test's own interval is 36 months (`app.reasoning.analyst.screenings`, sourced
    from the ADA's own repeat guidance): a matching fact from 6 months ago means it is not due
    even though the condition alone would otherwise open it every time."""
    owner = await pa(sg, phone="+6591150141")
    await save_settings(
        sg,
        context=owner,
        values=SettingsValues(language="en", conditions=("diabetes",), birth_decade=2000),
    )
    await _lab_fact(
        sg, owner, subject="hba1c", attribute="hba1c", value=6.1, on=NOW - timedelta(days=180)
    )
    report = await _report(sg, owner, now=NOW)
    section = _section(report, "screenings_due")
    assert section is not None
    keys = {i.insight_id for i in section.insights}
    assert "screening:diabetes_screening" not in keys
    # A screening this table names no fact subject for (`eye_check`) is unaffected: it is
    # still read as due, the same reading held before this fix.
    assert "screening:eye_check" in keys


async def test_a_screening_done_outside_its_interval_is_due_again(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150142")
    await save_settings(
        sg,
        context=owner,
        values=SettingsValues(language="en", conditions=("diabetes",), birth_decade=2000),
    )
    await _lab_fact(
        sg, owner, subject="hba1c", attribute="hba1c", value=6.4, on=NOW - timedelta(days=365 * 4)
    )
    report = await _report(sg, owner, now=NOW)
    section = _section(report, "screenings_due")
    assert section is not None
    keys = {i.insight_id for i in section.insights}
    assert "screening:diabetes_screening" in keys


async def test_the_newest_matching_fact_is_the_one_compared_against_the_interval(
    sg: AsyncSession,
) -> None:
    """Two matching facts, one inside the interval and one outside it: the newest is what
    decides, so a screening someone kept re-doing is not wrongly flagged due by its oldest
    result alone (the tie-breaker rule, `.claude/rules` — a "latest" reading needs one)."""
    owner = await pa(sg, phone="+6591150143")
    await save_settings(
        sg,
        context=owner,
        values=SettingsValues(language="en", conditions=("diabetes",), birth_decade=2000),
    )
    await _lab_fact(
        sg, owner, subject="hba1c", attribute="hba1c", value=6.4, on=NOW - timedelta(days=365 * 4)
    )
    await _lab_fact(
        sg, owner, subject="hba1c", attribute="hba1c", value=6.0, on=NOW - timedelta(days=30)
    )
    report = await _report(sg, owner, now=NOW)
    section = _section(report, "screenings_due")
    assert section is not None
    keys = {i.insight_id for i in section.insights}
    assert "screening:diabetes_screening" not in keys


async def test_cost_concentration_flags_the_policy_carrying_most_of_the_spend(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591150015")
    provider = await clinic(sg, owner)
    ge = await write_policy(sg, owner, insurer_name="Great Eastern", policy_reference="GE-1")
    aia = await write_policy(sg, owner, insurer_name="AIA", policy_reference="AIA-1")

    visit_a = await book(sg, owner, provider, datetime(2026, 2, 1, 9, tzinfo=UTC), "cardiology")
    visit_b = await book(sg, owner, provider, datetime(2026, 2, 2, 9, tzinfo=UTC), "dental")
    claim_a = await _file(sg, owner, ge.id, visit_a.id, amount=100_000)
    await _move(
        sg, owner, claim_a.id, ClaimStatus.APPROVED, paid_by_insurer=20_000, paid_by_patient=80_000
    )
    claim_b = await _file(sg, owner, aia.id, visit_b.id, amount=10_000)
    await _move(
        sg, owner, claim_b.id, ClaimStatus.APPROVED, paid_by_insurer=8_000, paid_by_patient=2_000
    )

    report = await _report(sg, owner)
    section = _section(report, "what_you_pay")
    assert section is not None
    assert len(section.insights) == 1
    assert section.insights[0].kind is InsightKind.COST
    assert "Great Eastern" in section.insights[0].text


async def test_a_lapsed_policy_is_worth_a_look(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150017")
    await write_policy(
        sg, owner, insurer_name="Great Eastern", policy_reference="GE-2", status=PolicyStatus.LAPSED
    )
    report = await _report(sg, owner)
    section = _section(report, "worth_a_look")
    assert section is not None
    assert len(section.insights) == 1
    assert section.insights[0].kind is InsightKind.COVERAGE
    assert section.insights[0].ask_who is AskWho.NOBODY


async def test_a_key_without_money_or_records_gets_those_sections_withheld(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591150018")
    viewer = await let_in(
        sg,
        owner,
        phone="+6591150019",
        name="Mei",
        role=KeyRole.VIEWER,
        scopes={Scope.PROFILE, Scope.MEDICINES, Scope.READINGS},
    )
    report = await _report(sg, viewer)
    keys = {s.key for s in report.sections}
    assert "what_you_pay" not in keys
    assert "worth_a_look" not in keys
    assert "screenings_due" not in keys
    # what_changed (READINGS) and medicines_and_supplements (MEDICINES) are still attempted.
    assert "what_changed" in keys
    assert "medicines_and_supplements" in keys


async def test_the_stream_yields_steps_in_order_then_the_report(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150020")
    analyst = RuleAnalyst()
    events = [event async for event in analyst.report_stream(sg, context=owner, language="en")]
    steps = [e for e in events if isinstance(e, Step)]
    assert [s.key.value for s in steps] == ["records", "series", "medicines", "ledger", "coverage"]
    assert isinstance(events[-1], Report)
    assert all(isinstance(e, Step) for e in events[:-1])


async def test_a_blocked_candidate_with_no_evidence_is_dropped() -> None:
    candidate = Candidate(
        insight_id="x",
        kind=InsightKind.COST,
        text="This looks high.",  # trips the conclusion blocklist ("looks", "high")
        ask_who=AskWho.NOBODY,
        evidence=(Evidence(kind="policy", id="1", label="GE"),),
        why_plain="why",
        confidence=Confidence.LIKELY,
    )
    assert await finalize(candidate, language="en", reroute=drop_reroute) is None


async def test_a_candidate_with_no_evidence_at_all_is_dropped() -> None:
    candidate = Candidate(
        insight_id="x",
        kind=InsightKind.CHECK,
        text="A screening has not been written down.",
        ask_who=AskWho.DOCTOR,
        evidence=(),
        why_plain="why",
        confidence=Confidence.SURE,
    )
    assert await finalize(candidate, language="en", reroute=drop_reroute) is None


async def test_a_blocked_medicine_candidate_is_rerouted_never_printed() -> None:
    seen: list[Candidate] = []

    async def reroute(candidate: Candidate) -> Insight:
        seen.append(candidate)
        return Insight(
            insight_id=f"reroute:{candidate.insight_id}",
            kind=candidate.kind,
            text="Something about one of your medicines is worth asking about.",
            ask_who=AskWho.DOCTOR,
            evidence=candidate.evidence,
            why_plain="This was set aside instead of being shown as written.",
            confidence=Confidence.WORTH_A_LOOK,
        )

    candidate = Candidate(
        insight_id="med:1",
        kind=InsightKind.MEDICINE,
        text="You should stop this tablet.",  # blocked: "should", "stop"
        ask_who=AskWho.PHARMACIST,
        evidence=(Evidence(kind="medication_line", id="1", label="x"),),
        why_plain="why",
        confidence=Confidence.LIKELY,
    )
    result = await finalize(candidate, language="en", reroute=reroute)
    assert seen == [candidate]
    assert result is not None
    assert "stop" not in result.text.lower()
    assert result.ask_who is AskWho.DOCTOR


async def test_the_real_reroute_files_a_doctor_question(sg: AsyncSession) -> None:
    """`RuleAnalyst.ask_the_doctor` (via `finalize`) files a real memo when a medicine or
    supplement candidate's own words are blocked — exercised by forcing one of `RuleAnalyst`'s
    own duplicate-therapy candidates to carry blocked words, the way a future template change
    could accidentally do."""
    from app.audit.access import audited_read
    from app.reasoning.visits.models import Memo

    owner = await pa(sg, phone="+6591150021")
    from app.reasoning.analyst import rule as rule_module

    async def _blocked(session, context, language, candidate):
        return await rule_module.ask_the_doctor(session, context, language, candidate)

    candidate = Candidate(
        insight_id="med:blocked",
        kind=InsightKind.MEDICINE,
        text="You must stop this tablet.",
        ask_who=AskWho.PHARMACIST,
        evidence=(Evidence(kind="medication_line", id="1", label="x"),),
        why_plain="why",
        confidence=Confidence.LIKELY,
    )
    insight = await finalize(
        candidate, language="en", reroute=lambda c: rule_module.ask_the_doctor(sg, owner, "en", c)
    )
    assert insight is not None
    assert insight.text == "Something about one of your medicines is worth asking the doctor about."
    memos = await audited_read(sg, Memo, owner, Scope.VISITS, where=(Memo.source == MemoSource.ANALYST,))
    assert len(memos) == 1
    assert memos[0].kind is MemoKind.ASK
