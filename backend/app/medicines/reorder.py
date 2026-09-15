"""The reorder card's two buttons (E04-05): "Ask the family to order." and "I have more at home."

    ask_to_order   his tap: a task on the family's list (E12-03) for whoever is on duty now,
                   else his chief, and a notice to his chief. The tap is the yes, as Taken
                   is: it changes no medicine and writes no fact; it asks a person to buy some.
    found_more     a count correction, on his yes for exactly that number: the tablets he
                   found at home become a supply on the line, resting on a fact that rests on
                   the moment he said so (an event on the medicines' part). No line, dose or
                   instruction changes, so the high-risk label rule, which guards a dose, is
                   not what applies here (`count:` is not one of its attributes).

Both are behind the medicines' door. Asking reads the roster and writes the task and the
notice under the family's part, which only the owner and his chief arrange; anyone else's
tap is refused by the family module and is on the trail like any refusal.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_write
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import CountCorrectionDraft, FactDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.models import Task
from app.family.roster import add_task, who_is_on_duty
from app.identity.models import Person
from app.keys.confirm import confirm, consume_confirmation
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import MedicationLine, Supply
from app.medicines.service import (
    Count,
    _require_line,
    active_lines,
    may_change_medicines,
)
from app.medicines.strings import (
    ASKED_TO_ORDER,
    KNOWS_NOW,
    ORDER_TASK,
    PLAIN_NAME,
    REORDER_NOTICE,
    language_of,
)
from app.memory.models import ConfidenceState, Event, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact
from app.safety.high_risk import MEDICATION
from app.safety.models import Notice, NoticeKind
from app.safety.people import key_holder

TASK_TARGET = Task.__tablename__
SUPPLY_TARGET = Supply.__tablename__
NOTICE_TEMPLATE = "reorder.ask_to_order"
MAX_FOUND = 1000
"""More than this many at home is not a count anyone typed on purpose."""


class NobodyToAsk(Refusal):
    """Nobody is on duty and the profile has no chief: there is no one to give the task to.
    Nothing was written; the family list is where the next step is set up."""


class NotACount(Refusal):
    """A count correction is a whole number of tablets, more than none."""


@dataclass(frozen=True, slots=True)
class Asked:
    """What one tap did: the task, the person asked, who was told, and his lines."""

    line: MedicationLine
    task: Task
    asked: Person
    told: Sequence[Person]
    notices: Sequence[Notice]
    language: str
    lines: Sequence[str]


@dataclass(frozen=True, slots=True)
class FoundMore:
    """What one count correction wrote, and the count as it stands now."""

    line: MedicationLine
    event: Event
    fact: Fact
    supply: Supply
    count: Count | None


def count_correction_draft(line_id: uuid.UUID, quantity: int) -> CountCorrectionDraft:
    if quantity < 1 or quantity > MAX_FOUND:
        raise NotACount(f"{quantity} is not a count of tablets found at home")
    return CountCorrectionDraft(line_id=line_id, quantity=quantity)


@audited(Action.READ, Scope.MEDICINES, MedicationLine.__tablename__)
async def count_correction_draft_for(
    session: AsyncSession, *, context: KeyContext, line_id: uuid.UUID, quantity: int
) -> CountCorrectionDraft:
    """The draft a person mints a yes for: an active line on this profile, and a count. A
    key that may not change the list is refused here, before any yes is written."""
    may_change_medicines(context)
    line = await _require_line(session, context=context, line_id=line_id)
    return count_correction_draft(line.id, quantity)


async def _chief(session: AsyncSession, context: KeyContext) -> Person | None:
    """His chief: the first active chief key, read under the family's part."""
    moment = utcnow()
    keys = await list_keys(session, context=context)
    for key in sorted(keys, key=lambda one: (as_utc(one.granted_at), str(one.id))):
        if key.role is KeyRole.CHIEF and key.is_active(moment):
            return await key_holder(session, context, key.holder_person_id, scope=Scope.FAMILY)
    return None


@audited(Action.WRITE, Scope.MEDICINES, TASK_TARGET)
async def ask_to_order(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    language: str | None = None,
) -> Asked:
    """His tap on "Ask the family to order.": one task for whoever is on duty now (the
    roster, on his wall clock), else for his chief, and a notice to his chief unless she is
    the one tapping. Nobody on duty and no chief is `NobodyToAsk`, and nothing is written."""
    line = await _require_line(session, context=context, line_id=line_id)
    profile = await audited_profile_read(session, context)
    lang = language_of(language or profile.language)
    medicine = PLAIN_NAME[lang][registry.monograph(line.generic).plain_name_id]
    chief = await _chief(session, context)
    on_duty = await who_is_on_duty(session, context=context)
    asked: Person | None = chief
    if on_duty:
        asked = await key_holder(session, context, on_duty[0].person_id, scope=Scope.FAMILY)
    if asked is None:
        raise NobodyToAsk(f"no one on duty and no chief on profile {context.profile_id}")
    task = await add_task(
        session,
        context=context,
        what=ORDER_TASK[lang].format(medicine=medicine),
        assigned_person_id=asked.id,
        language=lang,
    )
    told: list[Person] = []
    notices: list[Notice] = []
    if chief is not None and chief.id != context.person_id:
        moment = utcnow()
        notices.append(
            await audited_write(
                session,
                Notice,
                context,
                Scope.FAMILY,
                kind=NoticeKind.REORDER,
                to_person_id=chief.id,
                template=NOTICE_TEMPLATE,
                slots={"task_id": str(task.id), "line_id": str(line.id)},
                language=language_of(chief.language),
                flag_id=None,
                event_id=None,
                created_at=moment,
                deliver_after=moment,
            )
        )
        told.append(chief)
    lines = [ASKED_TO_ORDER[lang].format(who=asked.display_name, medicine=medicine)]
    if chief is not None and told and chief.id != asked.id:
        lines.append(KNOWS_NOW[lang].format(who=chief.display_name))
    return Asked(
        line=line,
        task=task,
        asked=asked,
        told=told,
        notices=notices,
        language=lang,
        lines=lines,
    )


def reorder_notice_lines(notice: Notice, *, patient: str, language: str | None = None) -> list[str]:
    """The notice to his chief, in her language: he asked, and it is on the family's list."""
    lang = language_of(language or notice.language)
    return [line.format(patient=patient) for line in REORDER_NOTICE[lang]]


@audited(Action.WRITE, Scope.MEDICINES, SUPPLY_TARGET)
async def found_more(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    quantity: int,
    confirmation_id: uuid.UUID,
    language: str | None = None,
) -> FoundMore:
    """"I have more at home.", on the person's yes for exactly this line and this number.

    The moment is written first (an event on the medicines' part, from the app), then the
    fact that rests on it — `medication` / `count:<generic>`, confirmed by the person, the
    way a typed reading is his own word — then the supply on the line that names the fact.
    The count on every screen moves by `quantity`. A key that may not change the list is
    refused (`NotTheirsToChange`), and so is a yes for another number (`NotWhatWasConfirmed`).
    """
    may_change_medicines(context)
    line = await _require_line(session, context=context, line_id=line_id)
    await consume_confirmation(
        session, context, confirmation_id, count_correction_draft(line.id, quantity)
    )
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.MEDICINES,
    )
    moment = utcnow()
    event = await audited_write(
        session,
        Event,
        context,
        Scope.MEDICINES,
        kind=EventKind.SUPPLY,
        occurred_at=moment,
        source_channel=SourceChannel.APP,
        label=f"more at home: {line.generic}",
        artifact_id=None,
        episode_id=None,
        recorded_at=moment,
    )
    draft = FactDraft(
        subject=MEDICATION,
        attribute=f"count:{line.generic}",
        value={
            "generic": line.generic,
            "line_id": str(line.id),
            "quantity": quantity,
            "change": "found_at_home",
        },
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    said = await confirm(session, context, draft)
    fact = await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        confidence=draft.confidence,
        confidence_state=draft.confidence_state,
        confirmation_id=said.id,
        event_id=event.id,
        valid_from=moment,
    )
    supply = await audited_write(
        session,
        Supply,
        context,
        Scope.MEDICINES,
        line_id=line.id,
        fact_id=fact.id,
        quantity=quantity,
        dispensed_at=moment,
        artifact_id=None,
        confirmed_by_person_id=context.person_id,
        recorded_at=moment,
    )
    views = await active_lines(session, context=context, registry=registry, language=language)
    count = next((view.count for view in views if view.line.id == line.id), None)
    return FoundMore(line=line, event=event, fact=fact, supply=supply, count=count)
