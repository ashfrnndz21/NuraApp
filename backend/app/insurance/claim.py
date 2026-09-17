"""A claim against a policy, for one visit: its status, and the papers behind it.

A claim names the policy it is against and the visit it is for (`app.memory.models.
Appointment`, already on the spine) — nothing else identifies it, because nothing else is
needed: the insurer's own claim number, where there is one already, is the one identifier
this module keeps for it, on the same terms as a policy reference (never logged, never on a
card, never in a message; refused if it looks like an identity card,
`app.insurance.insurer.looks_like_an_identity_card`).

**The papers behind it are not a second upload path.** A claim does not carry its own
attachments: the papers are whatever is already hung off the visit it is for
(`app.memory.attach.attachments`, `appointment_id=`), the one path a paper joins a visit on
this record. `papers_for_claim` reads that, under the record's own scope, not a new one —
seeing which letters are behind a claim is seeing what is attached to the visit, and a key
that cannot see the visit's papers cannot see them because it is a claim.

**The scope decision.** A claim is money, the same door as the policy it is against
(`Scope.MONEY`, § the decision written down in `app.insurance.policy`): nobody but the
owner, a steward or a chief files one or moves one.

**Status moves one way** (`CLAIM_STATUS_GOES_TO`), the same shape as a visit's own
`app.memory.spine.STATUS_GOES_TO`: submitted, then in review, then approved, partly
approved or rejected; an approved or partly approved claim is then paid. Paid and rejected
are the end of it — a claim resubmitted after a rejection is a new claim, with its own yes.
Every step is a person's own word that the insurer said so, confirmed like any other change
here; Nura does not learn a claim's status from anywhere but a person typing it in.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import Base, ProfileScoped, as_utc, enum_column, frozen, utcnow
from app.drafts import InsuranceClaimDraft, InsuranceClaimStatusDraft
from app.errors import Refusal
from app.insurance.insurer import looks_like_an_identity_card
from app.insurance.policy import POLICY_SCOPE, NoSuchPolicy, Policy
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole
from app.memory.attach import attachments, require_appointment
from app.memory.models import Attachment, _row_of_profile, _tied_to_profile

CLAIM_SCOPE = POLICY_SCOPE
"""A claim is money like the policy it is against (§ the scope decision in
`app.insurance.policy`): the same door, the same hands."""

TARGET = "insurance_claim"
REFERENCE_LENGTH = 40


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    REJECTED = "rejected"
    PAID = "paid"


CLAIM_STATUS_GOES_TO: dict[ClaimStatus, frozenset[ClaimStatus]] = {
    ClaimStatus.SUBMITTED: frozenset(
        {
            ClaimStatus.IN_REVIEW,
            ClaimStatus.APPROVED,
            ClaimStatus.PARTIALLY_APPROVED,
            ClaimStatus.REJECTED,
        }
    ),
    ClaimStatus.IN_REVIEW: frozenset(
        {ClaimStatus.APPROVED, ClaimStatus.PARTIALLY_APPROVED, ClaimStatus.REJECTED}
    ),
    ClaimStatus.APPROVED: frozenset({ClaimStatus.PAID}),
    ClaimStatus.PARTIALLY_APPROVED: frozenset({ClaimStatus.PAID}),
    ClaimStatus.REJECTED: frozenset(),
    ClaimStatus.PAID: frozenset(),
}
"""The one path a claim's status takes. Paid and rejected are the end of it: a claim
resubmitted after a rejection is a new claim, with its own yes, not a re-opened one."""

STATUS_CHANGE_IN_PROGRESS = "insurance_claim_status_change"
"""`session.info` key: the id of the one claim `change_claim_status` is moving right now —
the only time a claim's status may change (mirrors `app.memory.models.
STATUS_CHANGE_IN_PROGRESS` for a visit)."""


def _status_change_is_in_progress(session: Any, row: Any) -> bool:
    return session is not None and session.info.get(STATUS_CHANGE_IN_PROGRESS) == row.id


class InsuranceClaim(ProfileScoped, Base):
    """One claim, against one policy, for one visit. The one change it takes after it is
    written is its status, and only while `change_claim_status` is making it."""

    __tablename__ = TARGET
    __table_args__ = (
        _row_of_profile(TARGET),
        _tied_to_profile(TARGET, "policy_id", "policy"),
        _tied_to_profile(TARGET, "appointment_id", "appointment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("policy.id"), index=True)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointment.id"), index=True)
    claim_reference: Mapped[str | None] = mapped_column(String(REFERENCE_LENGTH), default=None)
    status: Mapped[ClaimStatus] = mapped_column(enum_column(ClaimStatus, "insurance_claim_status"))
    filed_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    confirmation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("confirmation.id"))
    filed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    status_changed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    status_changed_confirmation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("confirmation.id"), default=None
    )
    status_changed_at: Mapped[datetime | None] = mapped_column(default=None)


# Moving is the one change a filed claim takes, and only through `change_claim_status`.
frozen(
    InsuranceClaim,
    except_for=frozenset(
        {
            "status",
            "status_changed_by_person_id",
            "status_changed_confirmation_id",
            "status_changed_at",
        }
    ),
    only_when=_status_change_is_in_progress,
)


class NotTheirsToManageAClaim(Refusal):
    """A claim is filed and moved by him, the steward holding his graph, or the chief he
    named — the same hands a policy already trusts (`app.insurance.policy`)."""


class NotAClaim(Refusal):
    """A claim names a policy on this profile and a visit on this profile; a claim reference
    is at most 40 characters, and an identity-card number is not one."""


class NoSuchClaim(Refusal):
    """No claim by that id on this profile."""


class NotThatClaimStatusChange(Refusal):
    """A claim's status goes one way (`CLAIM_STATUS_GOES_TO`). This was a step it does not
    take."""


def may_manage_a_claim(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role is KeyRole.CHIEF:
        return
    raise NotTheirsToManageAClaim(
        f"a {context.role} key reads claims; it does not file or move them"
    )


def _clean_reference(text: str | None) -> str | None:
    if text is None:
        return None
    one_line = " ".join(text.split())
    if not one_line:
        return None
    if len(one_line) > REFERENCE_LENGTH:
        raise NotAClaim(f"a claim reference is at most {REFERENCE_LENGTH} characters")
    if looks_like_an_identity_card(one_line):
        raise NotAClaim("that holds an identity-card number")
    return one_line


@audited(Action.WRITE, CLAIM_SCOPE, TARGET)
async def file_a_claim(
    session: AsyncSession,
    *,
    context: KeyContext,
    policy_id: uuid.UUID,
    appointment_id: uuid.UUID,
    claim_reference: str | None,
    confirmation_id: uuid.UUID,
) -> InsuranceClaim:
    """File a claim against a policy, for a visit, on the typer's own yes for exactly these
    words. The policy and the visit must both already be on this profile."""
    may_manage_a_claim(context)
    reference = _clean_reference(claim_reference)
    found_policy = await audited_read(
        session, Policy, context, CLAIM_SCOPE, where=(Policy.id == policy_id,)
    )
    if not found_policy:
        raise NoSuchPolicy(f"no policy {policy_id} on profile {context.profile_id}")
    await require_appointment(session, context=context, appointment_id=appointment_id)
    draft = InsuranceClaimDraft(
        policy_id=policy_id, appointment_id=appointment_id, claim_reference=reference
    )
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    return await audited_write(
        session,
        InsuranceClaim,
        context,
        CLAIM_SCOPE,
        policy_id=policy_id,
        appointment_id=appointment_id,
        claim_reference=reference,
        status=ClaimStatus.SUBMITTED,
        filed_by_person_id=yes.person_id,
        confirmation_id=yes.id,
        filed_at=utcnow(),
    )


async def require_claim(
    session: AsyncSession, *, context: KeyContext, claim_id: uuid.UUID
) -> InsuranceClaim:
    found = await audited_read(
        session, InsuranceClaim, context, CLAIM_SCOPE, where=(InsuranceClaim.id == claim_id,)
    )
    if not found:
        raise NoSuchClaim(f"no claim {claim_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.WRITE, CLAIM_SCOPE, TARGET)
async def change_claim_status(
    session: AsyncSession,
    *,
    context: KeyContext,
    claim_id: uuid.UUID,
    status: ClaimStatus,
    confirmation_id: uuid.UUID,
) -> InsuranceClaim:
    """Move a claim one step along `CLAIM_STATUS_GOES_TO`, on a person's own word that the
    insurer said so, confirmed like any other change here."""
    may_manage_a_claim(context)
    claim = await require_claim(session, context=context, claim_id=claim_id)
    if status not in CLAIM_STATUS_GOES_TO[claim.status]:
        raise NotThatClaimStatusChange(f"a {claim.status} claim does not become {status}")
    yes = await consume_confirmation(
        session, context, confirmation_id, InsuranceClaimStatusDraft(claim_id=claim.id, status=status)
    )
    session.info[STATUS_CHANGE_IN_PROGRESS] = claim.id
    try:
        claim.status = status
        claim.status_changed_by_person_id = yes.person_id
        claim.status_changed_confirmation_id = yes.id
        claim.status_changed_at = utcnow()
        await session.flush()
    finally:
        session.info.pop(STATUS_CHANGE_IN_PROGRESS, None)
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=CLAIM_SCOPE,
        target=TARGET,
        target_id=claim.id,
        rows=1,
    )
    return claim


@audited(Action.READ, CLAIM_SCOPE, TARGET)
async def claims_for_appointment(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> Sequence[InsuranceClaim]:
    """Every claim filed for this visit, newest first, tied on `(filed_at, id)`."""
    found = await audited_read(
        session,
        InsuranceClaim,
        context,
        CLAIM_SCOPE,
        where=(InsuranceClaim.appointment_id == appointment_id,),
    )
    return sorted(found, key=lambda row: (as_utc(row.filed_at), str(row.id)), reverse=True)


@audited(Action.READ, CLAIM_SCOPE, TARGET)
async def papers_for_claim(
    session: AsyncSession, *, context: KeyContext, claim_id: uuid.UUID
) -> Sequence[Attachment]:
    """The papers behind a claim: whatever is hung off the visit it is for, read the one way
    a paper ever joins a visit here (`app.memory.attach.attachments`). Not a claim-specific
    read: a key that cannot see the visit's papers sees none of these either.

    Wrapped so a `NoSuchClaim` lands on the trail like any other refusal here — `require_claim`
    on its own raises outside any door (clinical-safety review)."""
    claim = await require_claim(session, context=context, claim_id=claim_id)
    return await attachments(session, context=context, appointment_id=claim.appointment_id)


__all__ = [
    "CLAIM_SCOPE",
    "CLAIM_STATUS_GOES_TO",
    "REFERENCE_LENGTH",
    "ClaimStatus",
    "InsuranceClaim",
    "NoSuchClaim",
    "NotAClaim",
    "NotThatClaimStatusChange",
    "NotTheirsToManageAClaim",
    "change_claim_status",
    "claims_for_appointment",
    "file_a_claim",
    "may_manage_a_claim",
    "papers_for_claim",
    "require_claim",
]
