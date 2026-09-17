"""Pre-visit relevance: given an upcoming visit, what his own records show about cover, and
what to bring.

**Nura does not decide coverage.** Nothing here ever says a visit *is* covered — only that
insurance is on his own record that may apply, or that none is, and always to confirm with
the insurer or the clinic. That is the boundary line (CLAUDE.md, `docs/00-MASTER-BUILD-
SPEC.md` §1): Nura organises and surfaces what to discuss; it does not decide.

**Two tiers, by the owner's own decision.** A key that holds `Scope.MONEY` — the owner, a
steward before a claim, a chief the family named — sees the full picture: which policies are
active, a line saying cover may apply or that none is on file, and what to bring, the
guarantee letter named only when a policy on file says the insurer uses one. Every other key
that can see the visit at all — a caregiver, a viewer, a clinic key — sees exactly one line:
"Bring his insurance card to the visit." Nothing about which insurer, whether a policy is
even on file, or what it costs: that line is fixed, never built from a policy row, so a
narrower key learns nothing about his cover or his finances by asking this question, however
the record it cannot open reads. A key that cannot see the visit at all (it holds no
`Scope.VISITS`) is refused before either tier is reached, the same as any other read of a
visit — this module does not widen that door.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_profile_read
from app.audit.models import Action
from app.insurance.policy import POLICY_SCOPE, Policy, PolicyStatus, PolicyType, current_policies
from app.insurance.strings import render
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.attach import require_appointment
from app.memory.models import Appointment

__all__ = ["Line", "PolicySummary", "PreVisitInsurance", "pre_visit_relevance"]


@dataclass(frozen=True, slots=True)
class Line:
    """One rendered, verified line, with the id of the template it came from."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class PolicySummary:
    """One active policy, as much as the full tier ever shows for this purpose — not what it
    covers in full (`app.insurance.policy.Policy.covers`), just enough to say cover may
    apply and what to bring for it."""

    policy_id: uuid.UUID
    insurer_name: str
    policy_type: PolicyType
    guarantee_letter: bool


@dataclass(frozen=True, slots=True)
class PreVisitInsurance:
    """What this key is shown before this visit. `full` says which tier: false means
    `policies` is always empty and `note` always empty — `bring` is the one line there is."""

    appointment_id: uuid.UUID
    full: bool
    policies: tuple[PolicySummary, ...]
    note: tuple[Line, ...]
    bring: tuple[Line, ...]


def _policy_summary(row: Policy) -> PolicySummary:
    return PolicySummary(
        policy_id=row.id,
        insurer_name=row.insurer_name,
        policy_type=row.policy_type,
        guarantee_letter=row.guarantee_letter,
    )


async def pre_visit_relevance(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    language: str | None = None,
) -> PreVisitInsurance:
    """What to prepare, for this visit, on the insurance record — narrowed to what this key
    may see (§ the module docstring). Refused (`OutOfScope`) for a key that cannot read the
    visit at all, the same door `app.memory.attach.require_appointment` already keeps.

    `require_appointment` raises `NoSuchAppointment` outside any door of its own; wrapped in
    `audited_guard` here so that refusal lands on the trail too (clinical-safety review) —
    `Refusal.written_down` keeps the `OutOfScope` case, already logged inside
    `require_appointment`'s own read, from being written twice.
    """
    async with audited_guard(
        session, context, Action.READ, Scope.VISITS, Appointment.__tablename__
    ):
        await require_appointment(session, context=context, appointment_id=appointment_id)
    profile = await audited_profile_read(session, context)
    lang = language or profile.language
    name = profile.display_name

    if not context.allows(POLICY_SCOPE):
        bring = (Line("insurance.bring_card", render("insurance.bring_card", lang, name=name)),)
        return PreVisitInsurance(
            appointment_id=appointment_id, full=False, policies=(), note=(), bring=bring
        )

    policies = await current_policies(session, context=context)
    active = [row for row in policies if row.status is PolicyStatus.ACTIVE]

    if not active:
        no_cover_note: tuple[Line, ...] = (
            Line(
                "insurance.no_cover_on_file",
                render("insurance.no_cover_on_file", lang, name=name),
            ),
            Line("insurance.confirm_if_any", render("insurance.confirm_if_any", lang)),
        )
        return PreVisitInsurance(
            appointment_id=appointment_id, full=True, policies=(), note=no_cover_note, bring=()
        )

    note: tuple[Line, ...] = (
        Line("insurance.has_cover", render("insurance.has_cover", lang, name=name)),
        Line("insurance.may_apply", render("insurance.may_apply", lang)),
        Line("insurance.confirm_with_insurer", render("insurance.confirm_with_insurer", lang)),
    )
    bring_items = [
        Line("insurance.bring_policy_card", render("insurance.bring_policy_card", lang))
    ]
    if any(row.guarantee_letter for row in active):
        bring_items.append(
            Line(
                "insurance.bring_guarantee_letter",
                render("insurance.bring_guarantee_letter", lang),
            )
        )
    return PreVisitInsurance(
        appointment_id=appointment_id,
        full=True,
        policies=tuple(_policy_summary(row) for row in active),
        note=note,
        bring=tuple(bring_items),
    )
