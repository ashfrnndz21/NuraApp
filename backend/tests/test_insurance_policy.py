"""E13-03: the fuller insurance record. A policy is typed on a yes, kept as a history tied to
its own lineage, and read only by the owner, a steward or a chief — money, not the emergency
card's door (`Scope.MONEY`, the owner's decision)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.insurance.policy import (
    NoSuchPolicy,
    NotAPolicy,
    NotAPolicyReference,
    NotTheirsToSetAPolicy,
    Policy,
    PolicyStatus,
    PolicyType,
    current_policies,
    policy_draft,
    set_a_policy,
)
from app.keys.confirm import confirm
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from tests.safety_support import let_in, pa


async def _write(
    session: AsyncSession,
    context,
    *,
    insurer_name: str = "Great Eastern",
    policy_reference: str | None = "GE-4471-0932",
    policy_type: PolicyType = PolicyType.HOSPITAL,
    covered: str | None = "Pa",
    covers: str | None = "Hospital stays, up to $500 a day.",
    start_date: date | None = date(2026, 1, 1),
    renewal_date: date | None = date(2027, 1, 1),
    premium_due_date: date | None = date(2026, 12, 1),
    status: PolicyStatus = PolicyStatus.ACTIVE,
    guarantee_letter: bool = False,
    supersedes_id=None,
) -> Policy:
    draft = policy_draft(
        insurer_name=insurer_name,
        policy_reference=policy_reference,
        policy_type=policy_type,
        covered=covered,
        covers=covers,
        start_date=start_date,
        renewal_date=renewal_date,
        premium_due_date=premium_due_date,
        status=status,
        guarantee_letter=guarantee_letter,
        supersedes_id=supersedes_id,
    )
    yes = await confirm(session, context, draft)
    return await set_a_policy(
        session,
        context=context,
        insurer_name=insurer_name,
        policy_reference=policy_reference,
        policy_type=policy_type,
        covered=covered,
        covers=covers,
        start_date=start_date,
        renewal_date=renewal_date,
        premium_due_date=premium_due_date,
        status=status,
        guarantee_letter=guarantee_letter,
        supersedes_id=supersedes_id,
        confirmation_id=yes.id,
    )


async def test_a_policy_is_typed_on_a_yes_and_read_back(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591120001")
    written = await _write(sg, owner)
    held = await current_policies(sg, context=owner)
    assert [row.id for row in held] == [written.id]
    assert held[0].insurer_name == "Great Eastern"
    assert held[0].covers == "Hospital stays, up to $500 a day."


async def test_a_correction_supersedes_and_the_newest_of_each_lineage_wins(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591120002")
    first = await _write(sg, owner, status=PolicyStatus.ACTIVE)
    corrected = await _write(
        sg, owner, status=PolicyStatus.LAPSED, supersedes_id=first.id, policy_reference="GE-9"
    )
    held = await current_policies(sg, context=owner)
    assert [row.id for row in held] == [corrected.id]
    assert held[0].status is PolicyStatus.LAPSED and held[0].policy_reference == "GE-9"


async def test_a_profile_holds_more_than_one_policy_at_once(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591120003")
    hospital = await _write(sg, owner, insurer_name="Great Eastern", policy_type=PolicyType.HOSPITAL)
    scheme = await _write(
        sg,
        owner,
        insurer_name="MediShield Life",
        policy_type=PolicyType.GOVERNMENT_SCHEME,
        policy_reference=None,
    )
    held = {row.id for row in await current_policies(sg, context=owner)}
    assert held == {hospital.id, scheme.id}


async def test_two_policies_written_in_the_same_instant_still_resolve_to_one_winner(
    sg: AsyncSession,
) -> None:
    """A tie on `set_at` (the frozen clock did not move between the two writes) is broken on
    id, never left arbitrary — the same rule `current_insurer` already keeps."""
    owner = await pa(sg, phone="+6591120004")
    first = await _write(sg, owner, insurer_name="AIA")
    second = await _write(sg, owner, insurer_name="AIA", supersedes_id=first.id)
    assert first.set_at == second.set_at  # the clock did not move
    held = await current_policies(sg, context=owner)
    assert [row.id for row in held] == [second.id]
    # The winner is deterministic across repeated reads, not just "some" row.
    again = await current_policies(sg, context=owner)
    assert [row.id for row in again] == [row.id for row in held]


async def test_his_chief_may_set_a_policy(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591120005")
    mei = await let_in(sg, owner, phone="+6592220005", name="Mei", role=KeyRole.CHIEF)
    written = await _write(sg, mei, insurer_name="Prudential")
    held = await current_policies(sg, context=owner)
    assert held[0].set_by_person_id == mei.person_id and held[0].id == written.id


async def test_a_helper_cannot_read_or_set_a_policy_and_a_caregiver_cannot_either(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591120006")
    await _write(sg, owner)
    helper = await let_in(sg, owner, phone="+6593330006", name="Kit", role=KeyRole.HELPER)
    caregiver = await let_in(sg, owner, phone="+6594440006", name="Lin", role=KeyRole.CAREGIVER)
    for narrower in (helper, caregiver):
        with pytest.raises(OutOfScope) as failed:
            await current_policies(sg, context=narrower)
        assert failed.value.scope is Scope.MONEY
        with pytest.raises(NotTheirsToSetAPolicy):
            await _write(sg, narrower)


async def test_an_identity_card_number_is_refused_in_any_field(sg: AsyncSession) -> None:
    with pytest.raises(NotAPolicyReference):
        policy_draft(
            insurer_name="AIA",
            policy_reference="S1234567D",
            policy_type=PolicyType.HOSPITAL,
            covered=None,
            covers=None,
            start_date=None,
            renewal_date=None,
            premium_due_date=None,
            status=PolicyStatus.ACTIVE,
            guarantee_letter=False,
            supersedes_id=None,
        )


async def test_a_renewal_before_the_start_date_is_not_a_policy() -> None:
    with pytest.raises(NotAPolicy):
        policy_draft(
            insurer_name="AIA",
            policy_reference=None,
            policy_type=PolicyType.HOSPITAL,
            covered=None,
            covers=None,
            start_date=date(2026, 6, 1),
            renewal_date=date(2026, 1, 1),
            premium_due_date=None,
            status=PolicyStatus.ACTIVE,
            guarantee_letter=False,
            supersedes_id=None,
        )


async def test_a_yes_is_for_exactly_the_fields_shown(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591120007")
    draft = policy_draft(
        insurer_name="AIA",
        policy_reference="AIA-1",
        policy_type=PolicyType.HOSPITAL,
        covered=None,
        covers=None,
        start_date=None,
        renewal_date=None,
        premium_due_date=None,
        status=PolicyStatus.ACTIVE,
        guarantee_letter=False,
        supersedes_id=None,
    )
    yes = await confirm(sg, owner, draft)
    from app.keys.confirm import NotWhatWasConfirmed

    with pytest.raises(NotWhatWasConfirmed):
        await set_a_policy(
            sg,
            context=owner,
            insurer_name="AIA",
            policy_reference="AIA-2",  # not what was shown
            policy_type=PolicyType.HOSPITAL,
            covered=None,
            covers=None,
            start_date=None,
            renewal_date=None,
            premium_due_date=None,
            status=PolicyStatus.ACTIVE,
            guarantee_letter=False,
            supersedes_id=None,
            confirmation_id=yes.id,
        )


async def test_correcting_a_policy_that_does_not_exist_is_refused(sg: AsyncSession) -> None:
    import uuid

    owner = await pa(sg, phone="+6591120008")
    with pytest.raises(NoSuchPolicy):
        await _write(sg, owner, supersedes_id=uuid.uuid4())
