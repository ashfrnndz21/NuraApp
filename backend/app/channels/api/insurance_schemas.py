"""The wire shapes for the fuller insurance record (E13-03): policies, claims, and what a
key is shown before a visit. Nothing here carries a policy or claim reference to a caller
that did not already have it: `PolicySummaryOut` (the pre-visit tier) never includes one."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.insurance.claim import ClaimStatus
from app.insurance.policy import PolicyPeriodState, PolicyStatus, PolicyType


class PolicyIn(BaseModel):
    """A policy as typed, on a yes minted for exactly these fields
    (`POST /profiles/{id}/confirmations`, subject `policy`)."""

    insurer_name: str
    policy_reference: str | None = None
    policy_type: PolicyType
    covered: str | None = None
    covers: str | None = None
    start_date: date | None = None
    renewal_date: date | None = None
    premium_due_date: date | None = None
    status: PolicyStatus
    guarantee_letter: bool = False
    supersedes_id: uuid.UUID | None = None
    confirmation_id: uuid.UUID


class PolicyOut(BaseModel):
    policy_id: uuid.UUID
    insurer_name: str
    policy_reference: str | None
    policy_type: PolicyType
    covered: str | None
    covers: str | None
    start_date: date | None
    renewal_date: date | None
    premium_due_date: date | None
    status: PolicyStatus
    guarantee_letter: bool
    supersedes_id: uuid.UUID | None
    set_by_person_id: uuid.UUID
    set_at: datetime
    period_state: PolicyPeriodState
    """The passport's own quiet state chip (E13-04), computed here on the profile's own
    wall-clock day (`app.insurance.policy.policy_period_state`) — never left for the client to
    infer from a free-text field or the device's own clock."""
    period_state_said: str
    """`period_state`, already in his language — 'In force', 'Ends on {date}', 'Ended'."""


class ClaimIn(BaseModel):
    """A claim as filed, on a yes minted for exactly this policy, this visit and this
    reference (`POST /profiles/{id}/confirmations`, subject `insurance_claim`)."""

    policy_id: uuid.UUID
    appointment_id: uuid.UUID
    claim_reference: str | None = None
    claimed_amount_cents: int | None = None
    confirmation_id: uuid.UUID


class ClaimStatusIn(BaseModel):
    """A yes to moving one claim one step (subject `insurance_claim_status`), with the
    amounts that step learns (T2, the insurance ledger)."""

    status: ClaimStatus
    paid_by_insurer_cents: int | None = None
    paid_by_patient_cents: int | None = None
    confirmation_id: uuid.UUID


class ClaimOut(BaseModel):
    claim_id: uuid.UUID
    policy_id: uuid.UUID
    appointment_id: uuid.UUID
    claim_reference: str | None
    status: ClaimStatus
    claimed_amount_cents: int | None
    paid_by_insurer_cents: int | None
    paid_by_patient_cents: int | None
    filed_by_person_id: uuid.UUID
    filed_at: datetime
    status_changed_by_person_id: uuid.UUID | None
    status_changed_at: datetime | None


class ClaimPaperOut(BaseModel):
    """One paper behind a claim: what is already attached to the visit it is for
    (`app.memory.attach.attachments`) — not a claim-specific store."""

    attachment_id: uuid.UUID
    artifact_id: uuid.UUID
    attached_at: datetime


class PolicySummaryOut(BaseModel):
    policy_id: uuid.UUID
    insurer_name: str
    policy_type: PolicyType
    guarantee_letter: bool


class PreVisitInsuranceOut(BaseModel):
    """What this key is shown before this visit — `full=false` means `policies` and `note`
    are always empty and `bring` is the one line (§ `app.insurance.relevance`, the owner's
    decision on who sees what)."""

    appointment_id: uuid.UUID
    full: bool
    policies: list[PolicySummaryOut]
    note: list[str]
    bring: list[str]


class LedgerLineOut(BaseModel):
    """One claim on the ledger (T2): raw fields the screen lays out itself
    (`visit_purpose`, `policy_name` — what a clinic or a person typed, not Nura's words) and
    the words and numbers already said in his language and his region's currency."""

    claim_id: uuid.UUID
    policy_id: uuid.UUID
    policy_name: str
    policy_type: PolicyType
    appointment_id: uuid.UUID
    visit_purpose: str
    visit_date: date
    visit_date_said: str
    status: ClaimStatus
    status_word: str
    claimed_amount_cents: int | None
    claimed_amount_said: str | None
    paid_by_insurer_cents: int | None
    paid_by_insurer_said: str | None
    paid_by_patient_cents: int | None
    paid_by_patient_said: str | None


class PolicyTotalOut(BaseModel):
    policy_id: uuid.UUID
    policy_name: str
    claimed_cents: int
    claimed_said: str
    paid_by_insurer_cents: int
    paid_by_insurer_said: str
    paid_by_patient_cents: int
    paid_by_patient_said: str


class LedgerOut(BaseModel):
    """His whole ledger (T2, `app.insurance.ledger`): every claim ever filed, newest visit
    first, and the year's totals — overall and by policy. Money's one door: refused
    (`OutOfScope`, 403) for a key that does not hold `Scope.MONEY`."""

    year: int
    currency: str
    lines: list[LedgerLineOut]
    total_claimed_cents: int
    total_claimed_said: str
    total_paid_by_insurer_cents: int
    total_paid_by_insurer_said: str
    total_paid_by_patient_cents: int
    total_paid_by_patient_said: str
    by_policy: list[PolicyTotalOut]
