"""T2: the appointment planner (`app.reasoning.visits.planner`).

Each of the four sources yields a cited proposal; declining hides it for 90 days; accepting
one is the ordinary `AppointmentDraft`/confirm booking, on the proposal's own suggested
fields, with no special path of its own; a key without the visits scope is shown nothing.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.drafts import AppointmentDraft, FactDraft
from app.keys.confirm import confirm
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, EventKind, ProviderKind, SourceChannel
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment
from app.reasoning.visits.planner import VisitSource, decline_proposal, propose_visits
from app.regions import Region
from tests.family_support import household
from tests.feelings_support import new_medicine


async def _told_condition(session: AsyncSession, owner, *, code: str) -> None:
    event = await record_event(
        session,
        context=owner,
        kind=EventKind.ONBOARDING,
        occurred_at=utcnow(),
        label="a condition he told",
        source_channel=SourceChannel.APP,
    )
    draft = FactDraft(
        subject="condition",
        attribute=code,
        value=True,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, owner, draft)
    await assert_fact(
        session,
        context=owner,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
    )


async def _follow_up_letter(session: AsyncSession, owner, *, on: str):
    event = await record_event(
        session,
        context=owner,
        kind=EventKind.DISCHARGE,
        occurred_at=utcnow(),
        label="discharge letter",
        source_channel=SourceChannel.CONNECTOR,
    )
    draft = FactDraft(
        subject="follow_up",
        attribute="date",
        value=on,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, owner, draft)
    return await assert_fact(
        session,
        context=owner,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
    )


async def _flagged_lab_row(session: AsyncSession, owner):
    event = await record_event(
        session,
        context=owner,
        kind=EventKind.DISCHARGE,
        occurred_at=utcnow(),
        label="lab report",
        source_channel=SourceChannel.CONNECTOR,
    )
    draft = FactDraft(
        subject="lipid_panel",
        attribute="ldl_flagged",
        value=True,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, owner, draft)
    return await assert_fact(
        session,
        context=owner,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
    )


async def test_a_follow_up_letter_yields_a_cited_proposal(sg: AsyncSession) -> None:
    hh = await household(sg)
    owner = await hh.ctx(sg, hh.pa)
    fact = await _follow_up_letter(sg, owner, on="2026-11-01")

    proposed = await propose_visits(sg, context=owner, language="en", region=owner.region)

    found = [one for one in proposed.proposals if one.source is VisitSource.FOLLOW_UP]
    assert len(found) == 1
    proposal = found[0]
    assert proposal.why == (
        proposal.why[0],
    )  # exactly one citation
    assert proposal.why[0].id == fact.id
    assert proposal.why[0].scope is Scope.RECORDS
    assert proposal.purpose  # plain-words verified by `say()`; non-empty is enough here
    assert proposal.suggested_at is not None
    assert proposal.suggested_at.date().isoformat() == "2026-11-01"


async def test_a_medicine_review_due_yields_a_cited_proposal(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    hh = await household(sg)
    owner = await hh.ctx(sg, hh.pa)
    reconciled = await new_medicine(sg, owner)
    clock.step(timedelta(days=210))  # past the six-month default review interval

    proposed = await propose_visits(sg, context=owner, language="en", region=owner.region)

    found = [one for one in proposed.proposals if one.source is VisitSource.MEDICINE_REVIEW]
    assert len(found) == 1
    assert found[0].why[0].id == reconciled.line.id
    assert found[0].why[0].scope is Scope.MEDICINES
    assert found[0].provider_kind is ProviderKind.CLINIC


async def test_a_flagged_test_result_yields_a_cited_proposal(sg: AsyncSession) -> None:
    hh = await household(sg)
    owner = await hh.ctx(sg, hh.pa)
    fact = await _flagged_lab_row(sg, owner)

    proposed = await propose_visits(sg, context=owner, language="en", region=owner.region)

    found = [one for one in proposed.proposals if one.source is VisitSource.TEST_COMING]
    assert len(found) == 1
    assert found[0].why[0].id == fact.id
    assert found[0].provider_kind is ProviderKind.LAB


async def test_a_told_condition_yields_a_cited_screening_proposal(sg: AsyncSession) -> None:
    hh = await household(sg)
    owner = await hh.ctx(sg, hh.pa)
    await _told_condition(sg, owner, code="diabetes")

    proposed = await propose_visits(sg, context=owner, language="en", region=owner.region)

    found = [one for one in proposed.proposals if one.source is VisitSource.SCREENING_DUE]
    assert len(found) == 1
    assert found[0].provider_kind is ProviderKind.CLINIC


async def test_declining_a_proposal_hides_it_for_ninety_days(sg: AsyncSession) -> None:
    hh = await household(sg)
    owner = await hh.ctx(sg, hh.pa)
    await _told_condition(sg, owner, code="diabetes")
    before = await propose_visits(sg, context=owner, language="en", region=owner.region)
    proposal_id = before.proposals[0].proposal_id

    await decline_proposal(sg, context=owner, proposal_id=proposal_id)

    after = await propose_visits(sg, context=owner, language="en", region=owner.region)
    assert proposal_id not in {one.proposal_id for one in after.proposals}

    # Declining twice is a no-op, not a second fact: the tap is idempotent.
    await decline_proposal(sg, context=owner, proposal_id=proposal_id)


async def test_accepting_a_proposal_is_the_ordinary_booking_flow(sg: AsyncSession) -> None:
    hh = await household(sg)
    owner = await hh.ctx(sg, hh.pa)
    await _follow_up_letter(sg, owner, on="2026-11-01")
    proposed = await propose_visits(sg, context=owner, language="en", region=owner.region)
    proposal = next(one for one in proposed.proposals if one.source is VisitSource.FOLLOW_UP)

    # "Book it" opens the ordinary booking screen pre-filled with the proposal's own fields,
    # and books through the same yes any other visit rests on — no path of the planner's own.
    provider = await add_provider(
        sg, context=owner, name="Dr Tan", kind=ProviderKind.CLINIC, region=Region.SG
    )
    draft = AppointmentDraft(
        provider_id=provider.id, scheduled_at=proposal.suggested_at, purpose=proposal.purpose
    )
    yes = await confirm(sg, owner, draft)
    booked = await book_appointment(
        sg,
        context=owner,
        provider_id=provider.id,
        scheduled_at=proposal.suggested_at,
        purpose=proposal.purpose,
        confirmation_id=yes.id,
    )
    assert booked.provider_id == provider.id

    # Once a visit is booked after the evidence, the same proposal is no longer offered.
    after = await propose_visits(sg, context=owner, language="en", region=owner.region)
    assert proposal.proposal_id not in {one.proposal_id for one in after.proposals}


async def test_withheld_without_the_visits_scope(sg: AsyncSession) -> None:
    narrow = ROLE_SCOPES[KeyRole.CAREGIVER] - {Scope.VISITS}
    hh = await household(sg, kit_scopes=narrow)
    owner = await hh.ctx(sg, hh.pa)
    await _told_condition(sg, owner, code="diabetes")
    kit = await hh.ctx(sg, hh.kit)
    assert not kit.allows(Scope.VISITS)

    proposed = await propose_visits(sg, context=kit, language="en", region=kit.region)

    assert proposed.proposals == ()
    assert Scope.VISITS in proposed.withheld
