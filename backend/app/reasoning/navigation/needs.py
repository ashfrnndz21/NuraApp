"""Reading the record for a real need to draft a message for (T3).

Four kinds, each read under its own scope, each a real row already on the graph — never a
guess and never a second store: a `FOLLOW_UP` need is a letter's own follow-up date
(`subject="follow_up", attribute="date"`, the field `#257` added to the extraction prompt); a
`NEW_MEDICINE` need is a medication line the pharmacy wrote for the first time
(`ChangeKind.NEW_LINE`), not a dose change; a `TEST_DUE` need is an upcoming visit at a lab
provider, the same window RE-06's `test_coming` rule reads; a `HOME_CARE` need is a
care-service provider already in the directory (PR #264's `Provider.category`) — Services'
own tile is the need, there is no second signal to wait for.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import ChangeKind, LineStatus, MedicationLine
from app.memory.models import Appointment, Fact, Provider, ProviderKind
from app.memory.spine import UPCOMING
from app.reasoning.navigation.models import Need, NeedKind
from app.state.dimensions import BEFORE_VISIT_WINDOW

NEW_MEDICINE_WINDOW = timedelta(days=30)
"""How long a newly-written line still counts as "new" for a navigation need — long enough
that a line the pharmacy just wrote is still worth asking about, short enough that it does
not sit in the list forever."""


def _as_date(value: object) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


async def _doctor_for_episode(
    session: AsyncSession, *, context: KeyContext, episode_id: uuid.UUID | None
) -> tuple[str | None, uuid.UUID | None]:
    """The provider a follow-up's own episode was seen at, if one visit names it — never a
    guess, and `(None, None)` when nothing on the record says who."""
    if episode_id is None:
        return None, None
    visits = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(Appointment.episode_id == episode_id,),
        order_by=(Appointment.scheduled_at.desc(),),
        limit=1,
    )
    if not visits:
        return None, None
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id == visits[0].provider_id,)
    )
    if not providers:
        return None, visits[0].provider_id
    return providers[0].name, providers[0].id


async def _follow_up_needs(session: AsyncSession, *, context: KeyContext) -> list[Need]:
    facts = await audited_read(
        session,
        Fact,
        context,
        Scope.RECORDS,
        where=(
            Fact.subject == "follow_up",
            Fact.attribute == "date",
            Fact.valid_to.is_(None),
        ),
    )
    out: list[Need] = []
    for fact in facts:
        when = _as_date(fact.value)
        doctor, provider_id = await _doctor_for_episode(
            session, context=context, episode_id=fact.episode_id
        )
        out.append(
            Need(
                id=f"{NeedKind.FOLLOW_UP}:{fact.id}",
                kind=NeedKind.FOLLOW_UP,
                evidence_kind="fact",
                evidence_id=fact.id,
                provider_id=provider_id,
                doctor=doctor,
                when=when,
            )
        )
    return out


async def _new_medicine_needs(session: AsyncSession, *, context: KeyContext) -> list[Need]:
    now = utcnow()
    lines = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(
            MedicationLine.change_kind == ChangeKind.NEW_LINE,
            MedicationLine.superseded_at.is_(None),
            # Independent review of #331, follow-up 1: a new-medicine question is never asked
            # about a line he has already stopped or paused.
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )
    out: list[Need] = []
    for line in lines:
        if now - as_utc(line.started_at) > NEW_MEDICINE_WINDOW:
            continue
        out.append(
            Need(
                id=f"{NeedKind.NEW_MEDICINE}:{line.id}",
                kind=NeedKind.NEW_MEDICINE,
                evidence_kind="medication_line",
                evidence_id=line.id,
                provider_id=None,
                doctor=line.prescriber,
                when=as_utc(line.started_at).date(),
            )
        )
    return out


async def _test_due_needs(session: AsyncSession, *, context: KeyContext) -> list[Need]:
    now = utcnow()
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.kind == ProviderKind.LAB,)
    )
    lab_ids = {p.id: p for p in providers}
    if not lab_ids:
        return []
    visits = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(
            Appointment.provider_id.in_(lab_ids.keys()),
            Appointment.status.in_(UPCOMING),
        ),
    )
    out: list[Need] = []
    for visit in visits:
        until = as_utc(visit.scheduled_at) - now
        if until < timedelta(0) or until > BEFORE_VISIT_WINDOW:
            continue
        provider = lab_ids[visit.provider_id]
        out.append(
            Need(
                id=f"{NeedKind.TEST_DUE}:{visit.id}",
                kind=NeedKind.TEST_DUE,
                evidence_kind="appointment",
                evidence_id=visit.id,
                provider_id=provider.id,
                doctor=provider.name,
                when=as_utc(visit.scheduled_at).date(),
            )
        )
    return out


async def _home_care_needs(session: AsyncSession, *, context: KeyContext) -> list[Need]:
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.category.is_not(None),)
    )
    return [
        Need(
            id=f"{NeedKind.HOME_CARE}:{provider.id}",
            kind=NeedKind.HOME_CARE,
            evidence_kind="provider",
            evidence_id=provider.id,
            provider_id=provider.id,
            doctor=None,
            when=None,
            category=None if provider.category is None else provider.category.value,
        )
        for provider in providers
    ]


async def list_needs(session: AsyncSession, *, context: KeyContext) -> Sequence[Need]:
    """Every real need on the record a message could be drafted for right now, across all
    four kinds — each read under the scope its own rows sit under, so a key missing that
    scope simply sees fewer needs, the same way any other read withholds by scope."""
    out: list[Need] = []
    out.extend(await _follow_up_needs(session, context=context))
    out.extend(await _new_medicine_needs(session, context=context))
    out.extend(await _test_due_needs(session, context=context))
    out.extend(await _home_care_needs(session, context=context))
    return out


async def need_by_id(
    session: AsyncSession, *, context: KeyContext, need_id: str
) -> Need | None:
    for need in await list_needs(session, context=context):
        if need.id == need_id:
            return need
    return None
