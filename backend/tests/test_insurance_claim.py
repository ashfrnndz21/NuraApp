"""E13-03: a claim against a policy, for a visit already on the spine — its status, and the
papers behind it (whatever is already attached to that visit; not a second upload path)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import now
from app.drafts import AttachDraft, InsuranceClaimDraft, InsuranceClaimStatusDraft
from app.insurance.claim import (
    ClaimStatus,
    NoSuchClaim,
    NotThatClaimStatusChange,
    NotTheirsToManageAClaim,
    change_claim_status,
    claims_for_appointment,
    file_a_claim,
    papers_for_claim,
    require_claim,
)
from app.keys.confirm import confirm
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.attach import attach_to_appointment
from tests.safety_support import clinic, let_in, pa
from tests.test_insurance_policy import _write as write_policy
from tests.timeline_support import artefact, book


async def _file(session: AsyncSession, context, policy_id, appointment_id, reference=None):
    draft = InsuranceClaimDraft(
        policy_id=policy_id, appointment_id=appointment_id, claim_reference=reference
    )
    yes = await confirm(session, context, draft)
    return await file_a_claim(
        session,
        context=context,
        policy_id=policy_id,
        appointment_id=appointment_id,
        claim_reference=reference,
        confirmation_id=yes.id,
    )


async def _move(session: AsyncSession, context, claim_id, status: ClaimStatus):
    yes = await confirm(session, context, InsuranceClaimStatusDraft(claim_id=claim_id, status=status))
    return await change_claim_status(
        session, context=context, claim_id=claim_id, status=status, confirmation_id=yes.id
    )


async def test_a_claim_is_filed_against_a_policy_for_a_visit(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591130001")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    claim = await _file(sg, owner, policy.id, visit.id, reference="CLM-1")
    assert claim.status is ClaimStatus.SUBMITTED
    found = await claims_for_appointment(sg, context=owner, appointment_id=visit.id)
    assert [row.id for row in found] == [claim.id]


async def test_a_claim_moves_one_step_at_a_time_on_a_yes(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591130002")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    claim = await _file(sg, owner, policy.id, visit.id)

    moved = await _move(sg, owner, claim.id, ClaimStatus.IN_REVIEW)
    assert moved.status is ClaimStatus.IN_REVIEW
    assert moved.status_changed_by_person_id == owner.person_id

    with pytest.raises(NotThatClaimStatusChange):
        await _move(sg, owner, claim.id, ClaimStatus.SUBMITTED)


async def test_the_papers_behind_a_claim_are_the_visits_own_attachments(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591130003")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    claim = await _file(sg, owner, policy.id, visit.id)
    assert list(await papers_for_claim(sg, context=owner, claim_id=claim.id)) == []

    letter = await artefact(sg, owner)
    hang_yes = await confirm(
        sg, owner, AttachDraft(artifact_id=letter.id, episode_id=None, appointment_id=visit.id)
    )
    await attach_to_appointment(
        sg,
        context=owner,
        artifact_id=letter.id,
        appointment_id=visit.id,
        confirmation_id=hang_yes.id,
    )
    papers = await papers_for_claim(sg, context=owner, claim_id=claim.id)
    assert [row.artifact_id for row in papers] == [letter.id]


async def test_a_helper_may_neither_file_nor_move_a_claim(sg: AsyncSession) -> None:
    """A helper is not preset to `Scope.MONEY`: the door itself refuses him, on the trail,
    before `may_manage_a_claim` is ever reached."""
    owner = await pa(sg, phone="+6591130004")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    helper = await let_in(sg, owner, phone="+6593330004", name="Kit", role=KeyRole.HELPER)
    with pytest.raises(OutOfScope) as failed:
        await _file(sg, helper, policy.id, visit.id)
    assert failed.value.scope is Scope.MONEY


async def test_a_custom_key_holding_money_but_not_the_chief_role_still_cannot_file_a_claim(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591130006")
    tan = await clinic(sg, owner)
    policy = await write_policy(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    widened = await let_in(
        sg,
        owner,
        phone="+6595550006",
        name="Wan",
        role=KeyRole.VIEWER,
        scopes={Scope.PROFILE, Scope.MONEY, Scope.VISITS},
    )
    with pytest.raises(NotTheirsToManageAClaim):
        await _file(sg, widened, policy.id, visit.id)


async def test_no_such_claim_is_refused(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591130005")
    with pytest.raises(NoSuchClaim):
        await require_claim(sg, context=owner, claim_id=uuid.uuid4())
