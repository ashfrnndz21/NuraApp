"""The insurance ledger (T2): one line per claim, in his own numbers — what was claimed, what
the insurer paid, what he paid himself — with totals for the year and for each policy.

Nothing here is a new store. A claim already carries its status and the visit and policy it
sits under (`app.insurance.claim`); `0047_insurance_claim_amounts` gave it the three amounts
this module sums. The ledger reads them, in minor units, and turns them into his language's
line (`app.insurance.strings.say_money`) and his region's currency — never a symbol decided
here, always the one on his profile (`app.regions.Region`).

**One gate, money's own.** `Scope.MONEY` is the door a policy and a claim already stand behind
(`app.insurance.policy`, the owner's decision): the owner, a steward, or the chief his family
named. `insurance_ledger` opens nothing more and nothing less — a caregiver or a viewer without
`Scope.MONEY` is refused (`OutOfScope`, 403, written to the trail the same as any other read
here) before a single row is read, the same door `current_policies` and `claims_for_appointment`
already stand behind. There is no second, narrower tier the way a visit's pre-visit line has
one (`app.insurance.relevance`): money is money, on or off, never partly shown.

**The visit each claim sits under is read here too**, under this same door: a key that can see
the ledger at all can see which visit a claim was for, the same as it can already see which
policy — one gate, not two, for one page about money.

**Raw words stay raw.** A visit's purpose (`Appointment.purpose`) and a policy's name
(`Policy.insurer_name`) are what a clinic or a person typed, not Nura's own words: they are
returned as plain fields here, never folded into a checked template (`app.safety.plain_words`
would refuse "cardiology" as too long a word to decode, which it is not — it is a specialty's
name, the same standing as a doctor's own name elsewhere in the record). The web screen lays
them out beside the words that are Nura's to check.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.insurance.claim import CLAIM_SCOPE, ClaimStatus, InsuranceClaim
from app.insurance.policy import Policy, PolicyType
from app.insurance.strings import CURRENCY_BY_REGION, claim_status_word, say_money
from app.keys.context import KeyContext
from app.medicines.strings import say_date, say_monthly_cost
from app.memory.models import Appointment
from app.memory.semantic import current_facts
from app.regions import REGION_TZ, Region

__all__ = [
    "Ledger",
    "LedgerLine",
    "MedicineMonthlyCost",
    "PolicyTotal",
    "insurance_ledger",
    "medicine_monthly_costs",
]

MEDICINE_COST_SUBJECT = "medicine_cost"
"""What `app.ingestion.review._write_receipt` writes a matched pharmacy receipt line's cost
under: subject `medicine_cost`, attribute the generic, value carrying `total_cents`."""


@dataclass(frozen=True, slots=True)
class LedgerLine:
    """One claim, as the ledger shows it: raw fields the web screen lays out itself
    (`visit_purpose`, `policy_name`), and the words and numbers already said in his region's
    currency and his own language (`*_said`, `visit_date_said`, `status_word`)."""

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


@dataclass(frozen=True, slots=True)
class PolicyTotal:
    """One policy's totals for the year: the same three sums as the ledger's own, narrowed to
    the claims filed against this one policy."""

    policy_id: uuid.UUID
    policy_name: str
    claimed_cents: int
    claimed_said: str
    paid_by_insurer_cents: int
    paid_by_insurer_said: str
    paid_by_patient_cents: int
    paid_by_patient_said: str


@dataclass(frozen=True, slots=True)
class Ledger:
    """His whole ledger: every claim ever filed, newest visit first, and the year's totals —
    overall and by policy. `currency` is his region's symbol, said once for the whole page."""

    year: int
    currency: str
    lines: Sequence[LedgerLine]
    total_claimed_cents: int
    total_claimed_said: str
    total_paid_by_insurer_cents: int
    total_paid_by_insurer_said: str
    total_paid_by_patient_cents: int
    total_paid_by_patient_said: str
    by_policy: Sequence[PolicyTotal]


def _this_year(context: KeyContext) -> int:
    """The calendar year on his own wall clock, from the frozen clock in a dev run or the
    real one otherwise (`app.clock`) — never a bare UTC year, which can already be tomorrow
    or still be yesterday for him."""
    return utcnow().astimezone(REGION_TZ[context.region]).year


async def insurance_ledger(
    session: AsyncSession, *, context: KeyContext, language: str
) -> Ledger:
    """Every claim on this profile, in his language and his region's currency, with the
    year's totals overall and by policy. Refused (`OutOfScope`, 403) for a key that does not
    hold `Scope.MONEY` — the one gate the whole page stands behind."""
    claims = await audited_read(session, InsuranceClaim, context, CLAIM_SCOPE)
    ordered = sorted(claims, key=lambda row: (as_utc(row.filed_at), str(row.id)), reverse=True)

    policy_ids = {row.policy_id for row in ordered}
    appointment_ids = {row.appointment_id for row in ordered}
    policies_by_id: dict[uuid.UUID, Policy] = {}
    if policy_ids:
        found_policies = await audited_read(
            session, Policy, context, CLAIM_SCOPE, where=(Policy.id.in_(policy_ids),)
        )
        policies_by_id = {row.id: row for row in found_policies}
    appointments_by_id: dict[uuid.UUID, Appointment] = {}
    if appointment_ids:
        found_appointments = await audited_read(
            session,
            Appointment,
            context,
            CLAIM_SCOPE,
            where=(Appointment.id.in_(appointment_ids),),
        )
        appointments_by_id = {row.id: row for row in found_appointments}

    zone = REGION_TZ[context.region]
    year = _this_year(context)

    lines: list[LedgerLine] = []
    for claim in ordered:
        policy = policies_by_id[claim.policy_id]
        visit = appointments_by_id[claim.appointment_id]
        visit_date = as_utc(visit.scheduled_at).astimezone(zone).date()
        lines.append(
            LedgerLine(
                claim_id=claim.id,
                policy_id=policy.id,
                policy_name=policy.insurer_name,
                policy_type=policy.policy_type,
                appointment_id=visit.id,
                visit_purpose=visit.purpose,
                visit_date=visit_date,
                visit_date_said=say_date(visit_date, language),
                status=claim.status,
                status_word=claim_status_word(claim.status.value, language),
                claimed_amount_cents=claim.claimed_amount_cents,
                claimed_amount_said=_said(claim.claimed_amount_cents, context.region),
                paid_by_insurer_cents=claim.paid_by_insurer_cents,
                paid_by_insurer_said=_said(claim.paid_by_insurer_cents, context.region),
                paid_by_patient_cents=claim.paid_by_patient_cents,
                paid_by_patient_said=_said(claim.paid_by_patient_cents, context.region),
            )
        )

    this_year = [line for line in lines if line.visit_date.year == year]
    total_claimed = sum(line.claimed_amount_cents or 0 for line in this_year)
    total_insurer = sum(line.paid_by_insurer_cents or 0 for line in this_year)
    total_patient = sum(line.paid_by_patient_cents or 0 for line in this_year)

    by_policy: list[PolicyTotal] = []
    for policy_id in sorted(
        {line.policy_id for line in this_year}, key=lambda one: str(one)
    ):
        rows = [line for line in this_year if line.policy_id == policy_id]
        claimed = sum(row.claimed_amount_cents or 0 for row in rows)
        insurer = sum(row.paid_by_insurer_cents or 0 for row in rows)
        patient = sum(row.paid_by_patient_cents or 0 for row in rows)
        by_policy.append(
            PolicyTotal(
                policy_id=policy_id,
                policy_name=rows[0].policy_name,
                claimed_cents=claimed,
                claimed_said=say_money(claimed, context.region),
                paid_by_insurer_cents=insurer,
                paid_by_insurer_said=say_money(insurer, context.region),
                paid_by_patient_cents=patient,
                paid_by_patient_said=say_money(patient, context.region),
            )
        )
    # A deterministic order for a tie is the ledger's own rule (`docs/00-MASTER-BUILD-
    # SPEC.md`, "any latest query needs a tie-breaker"): by policy name, then by id.
    by_policy.sort(key=lambda one: (one.policy_name, str(one.policy_id)))

    return Ledger(
        year=year,
        currency=CURRENCY_BY_REGION[context.region],
        lines=lines,
        total_claimed_cents=total_claimed,
        total_claimed_said=say_money(total_claimed, context.region),
        total_paid_by_insurer_cents=total_insurer,
        total_paid_by_insurer_said=say_money(total_insurer, context.region),
        total_paid_by_patient_cents=total_patient,
        total_paid_by_patient_said=say_money(total_patient, context.region),
        by_policy=by_policy,
    )


def _said(cents: int | None, region: Region) -> str | None:
    return None if cents is None else say_money(cents, region)


@dataclass(frozen=True, slots=True)
class MedicineMonthlyCost:
    """What one medicine or supplement on his list costs a month, from every pharmacy
    receipt line matched to it (`app.ingestion.review._write_receipt`), summed and spread
    over the calendar months a receipt actually fell in — one receipt alone stands for what
    a month costs; more receipts refine it, never inflate it."""

    generic: str
    monthly_cents: int
    monthly_said: str


async def medicine_monthly_costs(
    session: AsyncSession, *, context: KeyContext, language: str
) -> Sequence[MedicineMonthlyCost]:
    """Every medicine or supplement with at least one matched pharmacy receipt line, and what
    it costs a month. Read under `Scope.MEDICINES` — the same door the medicines list already
    stands behind, not this module's own `Scope.MONEY`: a key that can see what he takes can
    see what it costs to keep taking it; the claims ledger above is untouched by this."""
    facts = await current_facts(session, context=context, subject=MEDICINE_COST_SUBJECT)
    by_generic: dict[str, list[Any]] = {}
    for fact in facts:
        by_generic.setdefault(fact.attribute, []).append(fact)
    zone = REGION_TZ[context.region]
    out: list[MedicineMonthlyCost] = []
    for generic in sorted(by_generic):
        rows = by_generic[generic]
        months = {as_utc(row.valid_from).astimezone(zone).strftime("%Y-%m") for row in rows}
        total_cents = sum(int((row.value or {}).get("total_cents", 0)) for row in rows)
        monthly_cents = round(total_cents / max(1, len(months)))
        out.append(
            MedicineMonthlyCost(
                generic=generic,
                monthly_cents=monthly_cents,
                monthly_said=say_monthly_cost(say_money(monthly_cents, context.region), language),
            )
        )
    # A deterministic order, the ledger's own rule for any sum: by generic name.
    return out
