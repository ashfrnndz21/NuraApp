"""The reorder card's two buttons (E04-05): "Ask the family to order." and "I have more at home."

    order_preview  what he reads before his yes: who will be asked — whoever is on duty now
                   (E12-03), else his chief — for which medicine. If the family was already
                   asked for this line today and the task is still open, the preview says so
                   instead, and names the one already asked.
    ask_to_order   on his yes for exactly that person and that line (`OrderDraft`, spent before
                   anything is written): one task on the family's list naming him, the medicine
                   and the line, and a notice to his chief. It changes no medicine and writes no
                   fact; it asks a person to buy some. One open order task a line a day: a second
                   yes that day answers with the task already on the list, not a new one.
    found_more     a count correction, on his yes for exactly that number: the tablets he
                   found at home become a supply on the line, resting on a fact that rests on
                   the moment he said so (an event on the medicines' part). A high-risk
                   medicine's count rests on a photo of the box or the label as well — the same
                   rule as its dose (`app.safety.high_risk`), since a typed count that is too
                   high would put off its reorder. Any other medicine's may rest on his word.

Both are behind the medicines' door. Asking reads the roster and writes the task and the
notice under the family's part, which only the owner and his chief arrange; anyone else's
tap is refused by the family module and is on the trail like any refusal.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.drafts import CountCorrectionDraft, FactDraft, OrderDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.common import a_chief
from app.family.models import Errand, Task
from app.family.roster import add_task, who_is_on_duty
from app.identity.models import Person
from app.keys.confirm import (
    NotAConfirmerHere,
    NotWhatWasConfirmed,
    confirm,
    consume_confirmation,
)
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
    ORDER_PREVIEW,
    ORDER_TASK,
    PLAIN_NAME,
    REORDER_NOTICE,
    language_of,
)
from app.memory.episodic import require_artifact
from app.memory.models import (
    ArtifactKind,
    ConfidenceState,
    Event,
    EventKind,
    Fact,
    SourceChannel,
)
from app.memory.semantic import assert_fact
from app.regions import REGION_TZ
from app.safety.high_risk import (
    MEDICATION,
    HighRiskNeedsLabelPhoto,
    class_of,
    high_risk_class,
)
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
class OrderPreview:
    """What he reads before his yes, and what the yes will bind to: the line, the one person
    the task will name, and — when the family was already asked for this line today and the
    task is still open — that task, which a yes answers with instead of a new one."""

    line: MedicationLine
    asked: Person
    open_task: Task | None
    language: str
    lines: Sequence[str]

    @property
    def draft(self) -> OrderDraft:
        return OrderDraft(line_id=self.line.id, person_id=self.asked.id)


@dataclass(frozen=True, slots=True)
class Asked:
    """What one yes did: the task, the person asked, who was told, and his lines. `already`
    when the task was on the family's list before this yes (one open task a line a day)."""

    line: MedicationLine
    task: Task
    asked: Person
    told: Sequence[Person]
    notices: Sequence[Notice]
    language: str
    lines: Sequence[str]
    already: bool = False


@dataclass(frozen=True, slots=True)
class FoundMore:
    """What one count correction wrote, and the count as it stands now."""

    line: MedicationLine
    event: Event
    fact: Fact
    supply: Supply
    count: Count | None


def high_risk_of(line: MedicationLine) -> str | None:
    """The high-risk class of a medicine line, by the same table the dose rule reads: the
    registry's class or flag on the line, or the generic name itself."""
    return class_of({"drug_class": line.drug_class, "high_risk": line.high_risk}) or (
        high_risk_class(line.generic)
    )


async def _count_rests_on(
    session: AsyncSession,
    context: KeyContext,
    line: MedicationLine,
    artifact_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """The artefact a count correction rests on, checked at the medicines' own door so he is
    told before a yes is spent. A high-risk line's count needs a PHOTO on this profile — a
    photo of the box or the label — and anything else is `HighRiskNeedsLabelPhoto`, naming
    the class. Any other line's count may rest on his word (None) or on a photo he adds."""
    danger = high_risk_of(line)
    if artifact_id is None:
        if danger is not None:
            raise HighRiskNeedsLabelPhoto(
                danger, f"a {danger} count is corrected from a photo of the box or the label"
            )
        return None
    artifact = await require_artifact(session, context=context, artifact_id=artifact_id)
    if danger is not None and artifact.kind is not ArtifactKind.PHOTO:
        raise HighRiskNeedsLabelPhoto(
            danger, f"a {danger} count is corrected from a photo, not a {artifact.kind}"
        )
    return artifact.id


def count_correction_draft(
    line_id: uuid.UUID, quantity: int, artifact_id: uuid.UUID | None = None
) -> CountCorrectionDraft:
    if quantity < 1 or quantity > MAX_FOUND:
        raise NotACount(f"{quantity} is not a count of tablets found at home")
    return CountCorrectionDraft(line_id=line_id, quantity=quantity, artifact_id=artifact_id)


@audited(Action.READ, Scope.MEDICINES, MedicationLine.__tablename__)
async def count_correction_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    line_id: uuid.UUID,
    quantity: int,
    artifact_id: uuid.UUID | None = None,
) -> CountCorrectionDraft:
    """The draft a person mints a yes for: an active line on this profile, a count, and the
    photo it rests on. A key that may not change the list is refused here, and so is a
    high-risk line's count with no photo of the box or the label, before any yes is written."""
    may_change_medicines(context)
    line = await _require_line(session, context=context, line_id=line_id)
    rests_on = await _count_rests_on(session, context, line, artifact_id)
    return count_correction_draft(line.id, quantity, rests_on)


async def _chief(session: AsyncSession, context: KeyContext) -> Person | None:
    """His chief: the first active chief key, read under the family's part."""
    moment = utcnow()
    keys = await list_keys(session, context=context)
    for key in sorted(keys, key=lambda one: (as_utc(one.granted_at), str(one.id))):
        if key.role is KeyRole.CHIEF and key.is_active(moment):
            return await key_holder(session, context, key.holder_person_id, scope=Scope.FAMILY)
    return None


def _his_day(context: KeyContext) -> tuple[datetime, datetime]:
    """Today on his wall clock (the profile's region), as the instants it starts and ends."""
    tz = REGION_TZ[context.region]
    local = utcnow().astimezone(tz)
    start = datetime.combine(local.date(), time(0), tz)
    return start, start + timedelta(days=1)


async def _open_order_today(
    session: AsyncSession, context: KeyContext, line_id: uuid.UUID
) -> Task | None:
    """The order task for this line opened today on his wall clock and not yet done, if
    any. Read by `opened_on`, not a range on `created_at`: `opened_on` is what the table's
    partial unique index keys on (`0030_order_task`), so this reads the same day the index
    enforces."""
    start, _ = _his_day(context)
    found = await audited_read(
        session,
        Task,
        context,
        Scope.FAMILY,
        where=(
            Task.medication_line_id == line_id,
            Task.errand == Errand.ORDER,
            Task.done_at.is_(None),
            Task.opened_on == start.date(),
        ),
    )
    return min(found, key=lambda task: as_utc(task.created_at)) if found else None


async def _who_to_ask(
    session: AsyncSession, context: KeyContext
) -> tuple[Person | None, Person | None]:
    """Whoever is on duty now (the roster, on his wall clock) and holds a key that opens his
    medicines, else his chief; and his chief. The task's words name the medicine by its
    chemical name and strength ("order more amlodipine 5 mg for Pa"), so the one asked to
    buy it is one whose key opens his medicines."""
    chief = await _chief(session, context)
    moment = utcnow()
    opens_medicines = {
        key.holder_person_id
        for key in await list_keys(session, context=context)
        if key.is_active(moment) and Scope.MEDICINES in key.scopes_held
    }
    on_duty = [
        duty
        for duty in await who_is_on_duty(session, context=context)
        if duty.person_id in opens_medicines
    ]
    asked: Person | None = chief
    if on_duty:
        asked = await key_holder(session, context, on_duty[0].person_id, scope=Scope.FAMILY)
    return asked, chief


async def _already_asked(
    session: AsyncSession,
    context: KeyContext,
    open_task: Task,
    lang: str,
    medicine: str,
) -> tuple[Person, str] | None:
    """Who an open order task already names, and the line he reads for it. The one answer
    for both callers: `_preview`, when the task is found before a yes is spent, and
    `ask_to_order`, when a yes loses the race to add one — the table's unique index
    (`0030_order_task`) is what actually enforces one open order task a line a day; this is
    just how either path reads the task that won (#166 review)."""
    already = await key_holder(session, context, open_task.assigned_person_id, scope=Scope.FAMILY)
    if already is None:
        return None
    return already, ASKED_TO_ORDER[lang].format(who=already.display_name, medicine=medicine)


async def _preview(
    session: AsyncSession,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    language: str | None,
) -> OrderPreview:
    line = await _require_line(session, context=context, line_id=line_id)
    a_chief(context)
    profile = await audited_profile_read(session, context)
    lang = language_of(language or profile.language)
    medicine = PLAIN_NAME[lang][registry.monograph(line.generic).plain_name_id]
    open_task = await _open_order_today(session, context, line.id)
    if open_task is not None:
        found = await _already_asked(session, context, open_task, lang, medicine)
        if found is not None:
            already, said = found
            return OrderPreview(line, already, open_task, lang, (said,))
    asked, _ = await _who_to_ask(session, context)
    if asked is None:
        raise NobodyToAsk(f"no one on duty and no chief on profile {context.profile_id}")
    lines = tuple(
        each.format(who=asked.display_name, medicine=medicine) for each in ORDER_PREVIEW[lang]
    )
    return OrderPreview(line, asked, None, lang, lines)


@audited(Action.READ, Scope.MEDICINES, TASK_TARGET)
async def order_preview(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    language: str | None = None,
) -> OrderPreview:
    """What he reads before his yes to "Ask the family to order.", in his words: "Nura will
    ask Mei to order more of your blood pressure tablet." / "Is that OK?". When the family was
    already asked for this line today and the task is still open, the one line says so and
    names who. Nobody on duty and no chief is `NobodyToAsk`; a key that does not arrange the
    family's list is `NotAChief`. Nothing is written."""
    return await _preview(session, context, registry, line_id, language)


@audited(Action.READ, Scope.MEDICINES, TASK_TARGET)
async def order_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    person_id: uuid.UUID,
) -> OrderDraft:
    """The draft he mints a yes for: this line, and the person the preview named. A person
    who is not the one the preview names now — the roster moved on — is refused
    (`NotWhatWasConfirmed`) before any yes is written."""
    preview = await _preview(session, context, registry, line_id, None)
    if preview.asked.id != person_id:
        raise NotWhatWasConfirmed("the one to ask is not the one the preview names now")
    return preview.draft


@audited(Action.WRITE, Scope.MEDICINES, TASK_TARGET)
async def ask_to_order(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    line_id: uuid.UUID,
    confirmation_id: uuid.UUID | None,
    language: str | None = None,
) -> Asked:
    """His yes to "Ask the family to order.", for exactly the person and the line the preview
    named. The preview is computed again here and the yes is spent on it before anything is
    written: no yes is `NotAConfirmerHere`, a yes for someone else or another line is refused
    by the confirm, and nothing is written for either.

    With the yes spent: if the family was already asked for this line today and the task is
    still open, that task is the answer and nothing more is written (one open order task a
    line a day). Otherwise one task for the person named — in their language, naming him and
    the medicine, never his "your" — and a notice to his chief unless she is the one tapping.
    """
    preview = await _preview(session, context, registry, line_id, language)
    if confirmation_id is None:
        raise NotAConfirmerHere("nothing is asked of the family without his yes")
    await consume_confirmation(session, context, confirmation_id, preview.draft)
    line, asked, lang = preview.line, preview.asked, preview.language
    if preview.open_task is not None:
        return Asked(
            line=line,
            task=preview.open_task,
            asked=asked,
            told=(),
            notices=(),
            language=lang,
            lines=preview.lines,
            already=True,
        )
    # The task names the medicine in the family's part: held under his agreement to Nura
    # keeping his record, like every other write that names his health.
    await require_consent(
        session,
        context=context,
        purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
        scope=Scope.FAMILY,
    )
    profile = await audited_profile_read(session, context)
    theirs = language_of(asked.language)
    name_id = registry.monograph(line.generic).plain_name_id
    medicine = PLAIN_NAME[lang][name_id]
    # The medicine as its box names it — the line's chemical name and strength — so the one
    # who buys it buys this one, and him by name (review #140, item 11).
    label = " ".join(part for part in (line.generic, line.strength) if part)
    # The check above and this insert are not one atomic step: two yeses at the same
    # moment (Pa's and Mei's, or a retried request) can each see no open task before
    # either writes. The table's unique index (`0030_order_task`) is what actually
    # enforces one open order task a line a day; a savepoint lets this attempt's own
    # `IntegrityError` be caught without poisoning the rest of the transaction, and this
    # yes then answers with the task the race committed — exactly as a second yes does
    # today — instead of failing outright (#166 review).
    today, _ = _his_day(context)
    savepoint = await session.begin_nested()
    try:
        task = await add_task(
            session,
            context=context,
            what=ORDER_TASK[theirs].format(patient=profile.display_name, medicine=label),
            assigned_person_id=asked.id,
            language=theirs,
            errand=Errand.ORDER,
            medication_line_id=line.id,
            opened_on=today.date(),
        )
    except IntegrityError:
        await savepoint.rollback()
        existing = await _open_order_today(session, context, line.id)
        if existing is None:
            raise
        found = await _already_asked(session, context, existing, lang, medicine)
        if found is None:
            raise
        already, said = found
        return Asked(
            line=line,
            task=existing,
            asked=already,
            told=(),
            notices=(),
            language=lang,
            lines=(said,),
            already=True,
        )
    else:
        await savepoint.commit()
    chief = await _chief(session, context)
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
    artifact_id: uuid.UUID | None = None,
    language: str | None = None,
) -> FoundMore:
    """"I have more at home.", on the person's yes for exactly this line, this number and
    this photo.

    The moment is written first (an event on the medicines' part, from the app, naming the
    photo when there is one), then the fact that rests on it — `medication` /
    `count:<generic>`, confirmed by the person, the way a typed reading is his own word — then
    the supply on the line that names the fact and the photo. The count on every screen moves
    by `quantity`. A key that may not change the list is refused (`NotTheirsToChange`), so is
    a yes for another number or another photo (`NotWhatWasConfirmed`), and so is a high-risk
    line's count with no photo of the box or the label (`HighRiskNeedsLabelPhoto`).
    """
    may_change_medicines(context)
    line = await _require_line(session, context=context, line_id=line_id)
    rests_on = await _count_rests_on(session, context, line, artifact_id)
    await consume_confirmation(
        session, context, confirmation_id, count_correction_draft(line.id, quantity, rests_on)
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
        artifact_id=rests_on,
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
            # The registry's class and flag, so the label-photo rule under the store sees a
            # high-risk count as the door above did (`high_risk.is_a_count`).
            "drug_class": line.drug_class,
            "high_risk": line.high_risk,
        },
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=rests_on,
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
        artifact_id=rests_on,
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
        artifact_id=rests_on,
        confirmed_by_person_id=context.person_id,
        recorded_at=moment,
    )
    views = await active_lines(session, context=context, registry=registry, language=language)
    count = next((view.count for view in views if view.line.id == line.id), None)
    return FoundMore(line=line, event=event, fact=fact, supply=supply, count=count)
