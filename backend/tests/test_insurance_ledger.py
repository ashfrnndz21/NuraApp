"""The insurance ledger (T2): what was claimed, what the insurer paid, what he paid himself,
with totals for the year and by policy — money's own door, the same as a policy and a claim
(`app.insurance.policy`, the owner's decision): the owner, a steward, or a chief his family
named. A caregiver or a viewer without `Scope.MONEY` reads none of it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.drafts import InsuranceClaimDraft, InsuranceClaimStatusDraft
from app.insurance.claim import ClaimStatus, change_claim_status, file_a_claim
from app.insurance.ledger import insurance_ledger
from app.insurance.strings import say_money
from app.keys.confirm import confirm
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.regions import Region
from tests.safety_support import clinic, let_in, pa
from tests.test_insurance_policy import _write as write_policy
from tests.timeline_support import book

SEPT_3 = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
JAN_5_LAST_YEAR = datetime(2025, 1, 5, 8, 0, tzinfo=UTC)


async def _file(session: AsyncSession, context, policy_id, appointment_id, *, amount=None):
    draft = InsuranceClaimDraft(
        policy_id=policy_id,
        appointment_id=appointment_id,
        claim_reference=None,
        claimed_amount_cents=amount,
    )
    yes = await confirm(session, context, draft)
    return await file_a_claim(
        session,
        context=context,
        policy_id=policy_id,
        appointment_id=appointment_id,
        claim_reference=None,
        confirmation_id=yes.id,
        claimed_amount_cents=amount,
    )


async def _move(
    session: AsyncSession,
    context,
    claim_id,
    status: ClaimStatus,
    *,
    paid_by_insurer=None,
    paid_by_patient=None,
):
    yes = await confirm(
        session,
        context,
        InsuranceClaimStatusDraft(
            claim_id=claim_id,
            status=status,
            paid_by_insurer_cents=paid_by_insurer,
            paid_by_patient_cents=paid_by_patient,
        ),
    )
    return await change_claim_status(
        session,
        context=context,
        claim_id=claim_id,
        status=status,
        confirmation_id=yes.id,
        paid_by_insurer_cents=paid_by_insurer,
        paid_by_patient_cents=paid_by_patient,
    )


async def test_the_ledger_sums_two_policies_three_claims_one_pending(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150001")
    tan = await clinic(sg, owner)

    ge = await write_policy(sg, owner, insurer_name="Great Eastern", policy_reference="GE-1")
    aia = await write_policy(sg, owner, insurer_name="AIA", policy_reference="AIA-1")

    cardio = await book(sg, owner, tan, SEPT_3, "cardiology")
    dental = await book(sg, owner, tan, SEPT_3, "dental")
    pending_visit = await book(sg, owner, tan, SEPT_3, "check-up")

    paid_claim = await _file(sg, owner, ge.id, cardio.id, amount=42_000)
    await _move(sg, owner, paid_claim.id, ClaimStatus.IN_REVIEW)
    await _move(
        sg,
        owner,
        paid_claim.id,
        ClaimStatus.APPROVED,
        paid_by_insurer=38_000,
        paid_by_patient=4_000,
    )
    await _move(sg, owner, paid_claim.id, ClaimStatus.PAID)

    aia_claim = await _file(sg, owner, aia.id, dental.id, amount=10_000)
    await _move(
        sg, owner, aia_claim.id, ClaimStatus.APPROVED, paid_by_insurer=10_000, paid_by_patient=0
    )
    await _move(sg, owner, aia_claim.id, ClaimStatus.PAID)

    pending = await _file(sg, owner, ge.id, pending_visit.id, amount=5_000)

    ledger = await insurance_ledger(sg, context=owner, language="en")

    assert len(ledger.lines) == 3
    assert ledger.currency == "S$"
    by_id = {line.claim_id: line for line in ledger.lines}
    assert by_id[paid_claim.id].status is ClaimStatus.PAID
    assert by_id[paid_claim.id].claimed_amount_cents == 42_000
    assert by_id[paid_claim.id].paid_by_insurer_cents == 38_000
    assert by_id[paid_claim.id].paid_by_patient_cents == 4_000
    assert by_id[paid_claim.id].claimed_amount_said == "S$420"
    assert by_id[paid_claim.id].paid_by_patient_said == "S$40"
    assert by_id[pending.id].status is ClaimStatus.SUBMITTED
    assert by_id[pending.id].paid_by_insurer_cents is None
    assert by_id[pending.id].paid_by_insurer_said is None

    assert ledger.total_claimed_cents == 42_000 + 10_000 + 5_000
    assert ledger.total_paid_by_insurer_cents == 38_000 + 10_000
    assert ledger.total_paid_by_patient_cents == 4_000
    assert ledger.total_claimed_said == say_money(57_000, Region.SG)

    by_policy = {row.policy_id: row for row in ledger.by_policy}
    assert by_policy[ge.id].claimed_cents == 42_000 + 5_000
    assert by_policy[ge.id].paid_by_insurer_cents == 38_000
    assert by_policy[aia.id].claimed_cents == 10_000
    assert by_policy[aia.id].policy_name == "AIA"


async def test_only_this_years_visits_count_toward_the_totals(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150002")
    tan = await clinic(sg, owner)
    ge = await write_policy(sg, owner)
    old_visit = await book(sg, owner, tan, JAN_5_LAST_YEAR, "check-up")
    this_visit = await book(sg, owner, tan, SEPT_3, "check-up")
    await _file(sg, owner, ge.id, old_visit.id, amount=1_000)
    await _file(sg, owner, ge.id, this_visit.id, amount=2_000)

    ledger = await insurance_ledger(sg, context=owner, language="en")

    assert len(ledger.lines) == 2  # every claim ever filed is still on the page
    assert ledger.total_claimed_cents == 2_000  # only this year counts toward the total


async def test_money_is_said_in_ringgit_for_a_malaysian_profile(my: AsyncSession) -> None:
    owner = await pa(my, region=Region.MY, phone="+60122200003")
    tan = await clinic(my, owner)
    policy = await write_policy(my, owner, insurer_name="Great Eastern")
    visit = await book(my, owner, tan, SEPT_3, "check-up")
    await _file(my, owner, policy.id, visit.id, amount=15_000)

    ledger = await insurance_ledger(my, context=owner, language="en")

    assert ledger.currency == "RM"
    assert ledger.lines[0].claimed_amount_said == "RM150"


async def test_a_caregiver_without_money_cannot_read_the_ledger(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150004")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, SEPT_3, "check-up")
    await _file(sg, owner, policy.id, visit.id, amount=1_000)

    caregiver = await let_in(sg, owner, phone="+6594440004", name="Lin", role=KeyRole.CAREGIVER)
    with pytest.raises(OutOfScope) as failed:
        await insurance_ledger(sg, context=caregiver, language="en")
    assert failed.value.scope is Scope.MONEY


async def test_a_custom_key_holding_money_but_no_visits_scope_still_reads_the_ledger(
    sg: AsyncSession,
) -> None:
    """The ledger's one gate is money (`app.insurance.ledger`): a key that holds it reads
    which visit each claim sits under too, without needing `Scope.VISITS` on top."""
    owner = await pa(sg, phone="+6591150005")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, SEPT_3, "cardiology")
    await _file(sg, owner, policy.id, visit.id, amount=1_000)

    widened = await let_in(
        sg,
        owner,
        phone="+6595550005",
        name="Wan",
        role=KeyRole.VIEWER,
        scopes={Scope.PROFILE, Scope.MONEY},
    )
    ledger = await insurance_ledger(sg, context=widened, language="en")
    assert len(ledger.lines) == 1
    assert ledger.lines[0].visit_purpose == "cardiology"
