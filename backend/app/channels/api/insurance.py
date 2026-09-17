"""The fuller insurance record's routes (E13-03). Every one takes the key context.

    POST /profiles/{id}/insurance/policies                          write a policy, on a yes
    GET  /profiles/{id}/insurance/policies                          every policy in force
    POST /profiles/{id}/insurance/claims                            file a claim, on a yes
    GET  /profiles/{id}/insurance/appointments/{appointment_id}/claims  claims for one visit
    POST /profiles/{id}/insurance/claims/{claim_id}/status          move a claim, on a yes
    GET  /profiles/{id}/insurance/claims/{claim_id}/papers          the papers behind it
    GET  /profiles/{id}/insurance/pre-visit/{appointment_id}        what to prepare, narrowed
                                                                     to what this key may see

A policy and a claim open only under `Scope.MONEY`: a helper, a viewer, an emergency-only key
and a clinic key are refused (`OutOfScope`, 403) reaching any route above but the last.
`pre-visit` is open to any key that can read the visit at all (`Scope.VISITS`); what it
returns then narrows by the same door (`app.insurance.relevance`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.channels.api.deps import Context, Db
from app.channels.api.insurance_schemas import (
    ClaimIn,
    ClaimOut,
    ClaimPaperOut,
    ClaimStatusIn,
    PolicyIn,
    PolicyOut,
    PolicySummaryOut,
    PreVisitInsuranceOut,
)
from app.insurance.claim import (
    change_claim_status,
    claims_for_appointment,
    file_a_claim,
    papers_for_claim,
)
from app.insurance.policy import current_policies, set_a_policy
from app.insurance.relevance import pre_visit_relevance

router = APIRouter(prefix="/profiles", tags=["insurance"])

Language = Query(default=None, min_length=2, max_length=16)


def _policy_out(row) -> PolicyOut:  # type: ignore[no-untyped-def]
    return PolicyOut(
        policy_id=row.id,
        insurer_name=row.insurer_name,
        policy_reference=row.policy_reference,
        policy_type=row.policy_type,
        covered=row.covered,
        covers=row.covers,
        start_date=row.start_date,
        renewal_date=row.renewal_date,
        premium_due_date=row.premium_due_date,
        status=row.status,
        guarantee_letter=row.guarantee_letter,
        supersedes_id=row.supersedes_id,
        set_by_person_id=row.set_by_person_id,
        set_at=row.set_at,
    )


def _claim_out(row) -> ClaimOut:  # type: ignore[no-untyped-def]
    return ClaimOut(
        claim_id=row.id,
        policy_id=row.policy_id,
        appointment_id=row.appointment_id,
        claim_reference=row.claim_reference,
        status=row.status,
        filed_by_person_id=row.filed_by_person_id,
        filed_at=row.filed_at,
        status_changed_by_person_id=row.status_changed_by_person_id,
        status_changed_at=row.status_changed_at,
    )


@router.post("/{profile_id}/insurance/policies", status_code=status.HTTP_201_CREATED)
async def write_policy(body: PolicyIn, context: Context, session: Db) -> PolicyOut:
    """A policy, new or a correction of one already held, on the typer's own yes for exactly
    these fields; his, the steward's or his chief's (`NotTheirsToSetAPolicy`, 403)."""
    row = await set_a_policy(
        session,
        context=context,
        insurer_name=body.insurer_name,
        policy_reference=body.policy_reference,
        policy_type=body.policy_type,
        covered=body.covered,
        covers=body.covers,
        start_date=body.start_date,
        renewal_date=body.renewal_date,
        premium_due_date=body.premium_due_date,
        status=body.status,
        guarantee_letter=body.guarantee_letter,
        supersedes_id=body.supersedes_id,
        confirmation_id=body.confirmation_id,
    )
    return _policy_out(row)


@router.get("/{profile_id}/insurance/policies")
async def policies(context: Context, session: Db) -> list[PolicyOut]:
    """Every policy in force: money, so only the owner, a steward or a chief reach this."""
    found = await current_policies(session, context=context)
    return [_policy_out(row) for row in found]


@router.post("/{profile_id}/insurance/claims", status_code=status.HTTP_201_CREATED)
async def write_claim(body: ClaimIn, context: Context, session: Db) -> ClaimOut:
    """A claim against a policy, for a visit, on the typer's own yes."""
    row = await file_a_claim(
        session,
        context=context,
        policy_id=body.policy_id,
        appointment_id=body.appointment_id,
        claim_reference=body.claim_reference,
        confirmation_id=body.confirmation_id,
    )
    return _claim_out(row)


@router.get("/{profile_id}/insurance/appointments/{appointment_id}/claims")
async def claims(appointment_id: uuid.UUID, context: Context, session: Db) -> list[ClaimOut]:
    """Every claim filed for one visit, newest first."""
    found = await claims_for_appointment(session, context=context, appointment_id=appointment_id)
    return [_claim_out(row) for row in found]


@router.post("/{profile_id}/insurance/claims/{claim_id}/status")
async def write_claim_status(
    claim_id: uuid.UUID, body: ClaimStatusIn, context: Context, session: Db
) -> ClaimOut:
    """Move a claim one step, on the typer's own word that the insurer said so
    (`NotThatClaimStatusChange`, 409, for a step it does not take)."""
    row = await change_claim_status(
        session,
        context=context,
        claim_id=claim_id,
        status=body.status,
        confirmation_id=body.confirmation_id,
    )
    return _claim_out(row)


@router.get("/{profile_id}/insurance/claims/{claim_id}/papers")
async def claim_papers(claim_id: uuid.UUID, context: Context, session: Db) -> list[ClaimPaperOut]:
    """The papers behind a claim: whatever is already attached to the visit it is for
    (`app.memory.attach.attachments`), read the one way a paper joins a visit here. Not a
    second upload path."""
    found = await papers_for_claim(session, context=context, claim_id=claim_id)
    return [
        ClaimPaperOut(attachment_id=row.id, artifact_id=row.artifact_id, attached_at=row.attached_at)
        for row in found
    ]


@router.get("/{profile_id}/insurance/pre-visit/{appointment_id}")
async def pre_visit(
    appointment_id: uuid.UUID,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> PreVisitInsuranceOut:
    """What to prepare on the insurance record for this visit, narrowed to what this key may
    see (`app.insurance.relevance`): the full picture under money, or the one line — "bring
    his insurance card" — for every other key that can see the visit at all. Refused
    (`OutOfScope`, 403) for a key that cannot see the visit."""
    shown = await pre_visit_relevance(
        session, context=context, appointment_id=appointment_id, language=language
    )
    return PreVisitInsuranceOut(
        appointment_id=shown.appointment_id,
        full=shown.full,
        policies=[
            PolicySummaryOut(
                policy_id=one.policy_id,
                insurer_name=one.insurer_name,
                policy_type=one.policy_type,
                guarantee_letter=one.guarantee_letter,
            )
            for one in shown.policies
        ],
        note=[line.text for line in shown.note],
        bring=[line.text for line in shown.bring],
    )
