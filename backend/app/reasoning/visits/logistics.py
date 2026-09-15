"""The logistics card for a visit: time, place, parking, who is driving, what to bring (E05-03).

    Logistics card: time, place, parking, who is driving, what to bring.
    Acceptance: driver pulled from roster; card sent T-1 and T-0.

Composed from the record only, the way the brief is (`app.reasoning.visits.brief`), and from
State: the time is the booking on the spine, said his way; the place is the provider's
address in his directory; the parking is the chief's own note about the place (E03-03), shown
as she wrote it under "Mei's note" — her words, like a message in the family thread, never
Nura's, and never read for facts; who drives is a family task naming this visit (E12-03,
`Errand.DRIVE`: "drive Pa to Dr Tan") and its assignee, or — when nobody has been asked — the
person the roster has on duty at the time of the visit, as a suggestion that needs the
chief's yes before it is anything (`drive_draft_for`, `assign_driver`); what to bring is the
brief's bring-lines: his blood pressure book, his medicines in their boxes when he has any,
his hospital letter when there is one, and the memos filed to bring.

Every line he reads is a template from `strings` through the verifier (`say`). The chief's
note is the one thing on the card that is not a template: it is carried beside the lines,
labelled with her name, and the line about it is a template. Each part is read under its own
scope; a part the key does not reach is not read and is named in `withheld`. The card names
the State it was rendered from. The feed's `visit_logistics` card (E21) is these lines, the
day before the visit and on the day.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, person_display_name
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.drafts import DriveDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.common import a_chief
from app.family.models import Errand, Task
from app.family.roster import add_task, tasks, who_is_on_duty
from app.ingestion.extract import DocumentKind
from app.ingestion.models import ReviewCard
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext, holds_the_profile
from app.keys.grants import list_keys
from app.keys.scopes import KeyRole, Scope
from app.memory.models import Appointment
from app.memory.providers import chief_notes, is_chief
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.models import MemoKind
from app.reasoning.visits.questions import Visit, require_visit
from app.reasoning.visits.strings import (
    DRIVE_TASK,
    FAMILY_NOTE_LABEL,
    NOTE_LABEL,
    NotASlotValue,
    NotPlainEnough,
    day_and_date,
    say,
    spoken,
    time_of_day,
)
from app.safety.high_risk import MEDICINE_SUBJECTS
from app.state.models import Dimension
from app.state.service import current_state

LOGISTICS = "visit_logistics"
"""The trail's name for a read of the logistics card."""

LETTER_KINDS = frozenset({DocumentKind.DISCHARGE_LETTER})
DRIVERS = frozenset({KeyRole.CHIEF, KeyRole.CAREGIVER, KeyRole.HELPER, KeyRole.VIEWER})
"""Who can be asked to drive him: the family and the helper — never a clinic's key, which is
the clinic's, or an emergency-only key, which is a neighbour's for the worst day."""
"""The papers "the last letter" means: his hospital letter, confirmed on its review card."""


class DriverStatus(StrEnum):
    ASSIGNED = "assigned"
    """A family task naming this visit, to drive him, not yet done."""
    SUGGESTED = "suggested"
    """Nobody is asked yet; the roster has this person on duty then. Needs the chief's yes."""
    NOBODY = "nobody"
    """Nobody is asked, and the roster has nobody on duty then."""
    WITHHELD = "withheld"
    """The key does not reach the family list, so who drives was not read."""


class NotOnThisVisit(Refusal):
    """A driver is someone who holds a key to the profile, for a visit still to come."""


@dataclass(frozen=True, slots=True)
class Line:
    """One line of the card: its part, its template, the words as printed and as spoken."""

    section: str
    key: str
    text: str
    spoken: str

    def as_json(self) -> dict[str, Any]:
        return {"section": self.section, "key": self.key, "text": self.text, "spoken": self.spoken}


@dataclass(frozen=True, slots=True)
class PlaceNote:
    """The chief's own note about the place, as she wrote it, under her name."""

    note_id: uuid.UUID
    text: str
    label: str
    by_person_id: uuid.UUID
    by_name: str
    written_at: datetime


@dataclass(frozen=True, slots=True)
class Driver:
    status: DriverStatus
    person_id: uuid.UUID | None = None
    name: str | None = None
    task_id: uuid.UUID | None = None
    can_say_yes: bool = False
    """Whether the key reading this may give the chief's yes to the suggestion."""

    @property
    def needs_yes(self) -> bool:
        return self.status is DriverStatus.SUGGESTED


@dataclass(frozen=True, slots=True)
class Logistics:
    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    doctor: str
    language: str
    scheduled_at: datetime
    state_id: uuid.UUID
    place: str | None
    note: PlaceNote | None
    driver: Driver
    lines: tuple[Line, ...]
    withheld: tuple[Scope, ...]

    @property
    def spoken(self) -> list[str]:
        return [line.spoken for line in self.lines]


def _line(section: str, key: str, language: str, **slots: Any) -> Line:
    text = say(key, language, **slots)
    return Line(section, key, text, spoken(text))


def _place_line(visit: Visit) -> Line:
    """Where the doctor is, from the directory; when there is no address, or it will not go
    into a line he can read, the line says Nura does not have it yet."""
    address = (visit.provider.address or "").strip()
    if address:
        try:
            return _line(
                "place", "logistics_place", visit.language, doctor=visit.doctor, place=address
            )
        except (NotPlainEnough, NotASlotValue):
            pass
    return _line("place", "logistics_no_place", visit.language, doctor=visit.doctor)


async def _name_of(session: AsyncSession, context: KeyContext, person_id: uuid.UUID) -> str | None:
    """A person's name as the profile knows it, or None when the account has none yet — a
    line then says "your family", never a line with an empty slot, and never no card."""
    name = (await person_display_name(session, context, person_id) or "").strip()
    return name or None


async def _chief_name(session: AsyncSession, context: KeyContext) -> str | None:
    """His chief's name, when the key reaching can read the family list."""
    if not context.allows(Scope.FAMILY):
        return None
    if context.role is KeyRole.CHIEF:
        return await _name_of(session, context, context.person_id)
    moment = utcnow()
    for key in await list_keys(session, context=context):
        if key.role is KeyRole.CHIEF and key.is_active(moment):
            return await _name_of(session, context, key.holder_person_id)
    return None


def drive_task_of(found: list[Task], appointment_id: uuid.UUID) -> Task | None:
    """The newest open drive task naming this visit."""
    drives = [
        task
        for task in found
        if task.errand is Errand.DRIVE
        and task.appointment_id == appointment_id
        and not task.is_done
    ]
    return max(drives, key=lambda task: (as_utc(task.created_at), str(task.id)), default=None)


async def _driver(session: AsyncSession, context: KeyContext, visit: Visit) -> Driver:
    if not context.allows(Scope.FAMILY):
        return Driver(DriverStatus.WITHHELD)
    chief = context.is_owner or context.role is KeyRole.CHIEF
    assigned = drive_task_of(
        await tasks(session, context=context, open_only=True), visit.appointment.id
    )
    if assigned is not None:
        return Driver(
            DriverStatus.ASSIGNED,
            person_id=assigned.assigned_person_id,
            name=await _name_of(session, context, assigned.assigned_person_id),
            task_id=assigned.id,
        )
    on_duty = await who_is_on_duty(session, context=context, at=visit.appointment.scheduled_at)
    if on_duty:
        first = on_duty[0]
        return Driver(
            DriverStatus.SUGGESTED,
            person_id=first.person_id,
            name=await _name_of(session, context, first.person_id),
            can_say_yes=chief,
        )
    return Driver(DriverStatus.NOBODY, can_say_yes=chief)


async def _has_letter(session: AsyncSession, context: KeyContext) -> bool:
    cards = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(
            ReviewCard.document_kind.in_([kind.value for kind in LETTER_KINDS]),
            ReviewCard.confirmed_at.is_not(None),
        ),
    )
    return bool(cards)


@audited(Action.READ, Scope.VISITS, LOGISTICS)
async def logistics_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    registry: DrugRegistry | None = None,
) -> Logistics:
    """The logistics card for one visit, in his language, from the record and State."""
    visit = await require_visit(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
    state = await current_state(session, context=context)
    lang = visit.language
    at = visit.appointment.scheduled_at
    day = day_and_date(at, lang, context.region)
    withheld: list[Scope] = []
    lines: list[Line] = [
        _line(
            "when",
            "visit_with",
            lang,
            doctor=visit.doctor,
            day=day,
            time=time_of_day(at, lang, context.region),
        ),
        _place_line(visit),
    ]

    note: PlaceNote | None = None
    if context.allows(Scope.FAMILY) and is_chief(context):
        notes = await chief_notes(session, context=context, provider_id=visit.provider.id)
        if notes:
            newest = notes[0]
            by = await _name_of(session, context, newest.written_by_person_id)
            note = PlaceNote(
                note_id=newest.id,
                text=newest.text,
                label=NOTE_LABEL[lang].format(who=by) if by else FAMILY_NOTE_LABEL[lang],
                by_person_id=newest.written_by_person_id,
                by_name=by or "",
                written_at=newest.written_at,
            )
            lines.append(
                _line("note", "logistics_note_by", lang, who=by, doctor=visit.doctor)
                if by
                else _line("note", "logistics_note_family", lang, doctor=visit.doctor)
            )
    else:
        withheld.append(Scope.FAMILY)

    driver = await _driver(session, context, visit)
    if driver.status is DriverStatus.ASSIGNED:
        lines.append(
            _line("driver", "logistics_driver", lang, who=driver.name, doctor=visit.doctor, day=day)
            if driver.name
            else _line("driver", "logistics_driver_family", lang, doctor=visit.doctor, day=day)
        )
    elif driver.status is not DriverStatus.WITHHELD:
        # Nobody is asked yet — a suggestion is not an answer until the chief says yes — so
        # he is told who will tell him, when there is a chief to name.
        chief = await _chief_name(session, context)
        if chief:
            lines.append(
                _line(
                    "driver", "logistics_driver_ask", lang, who=chief, doctor=visit.doctor, day=day
                )
            )

    clinical = state.dimension(Dimension.CLINICAL) or {}
    lines.append(_line("bring", "bring_bp_book", lang, day=day))
    if any(subject in MEDICINE_SUBJECTS for subject in clinical.get("facts", {})):
        lines.append(_line("bring", "bring_medicines", lang, day=day))
    if context.allows(Scope.RECORDS):
        if await _has_letter(session, context):
            lines.append(_line("bring", "bring_last_letter", lang, day=day))
    else:
        withheld.append(Scope.RECORDS)
    for memo in await current_memos(session, context=context):
        if memo.kind is MemoKind.BRING and memo.language == lang:
            lines.append(Line("memo", memo.key, memo.text, spoken(memo.text)))

    return Logistics(
        appointment_id=visit.appointment.id,
        provider_id=visit.provider.id,
        doctor=visit.doctor,
        language=lang,
        scheduled_at=at,
        state_id=state.id,
        place=(visit.provider.address or None),
        note=note,
        driver=driver,
        lines=tuple(lines),
        withheld=tuple(withheld),
    )


# --- the chief's yes to a driver ------------------------------------------------------------


async def _driving_visit(
    session: AsyncSession, context: KeyContext, appointment_id: uuid.UUID, person_id: uuid.UUID
) -> Appointment:
    a_chief(context)
    visit = await require_visit(session, context=context, appointment_id=appointment_id)
    if as_utc(visit.appointment.scheduled_at) < utcnow():
        raise NotOnThisVisit(f"visit {appointment_id} has already been")
    moment = utcnow()
    family = [
        key
        for key in await list_keys(session, context=context)
        if key.holder_person_id == person_id and key.role in DRIVERS and key.is_active(moment)
    ]
    if not family or not await holds_the_profile(
        session, profile_id=context.profile_id, person_id=person_id
    ):
        raise NotOnThisVisit(f"person {person_id} holds no family key on this profile")
    return visit.appointment


@audited(Action.READ, Scope.FAMILY, LOGISTICS)
async def drive_draft_for(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID, person_id: uuid.UUID
) -> DriveDraft:
    """What the chief says yes to: this person drives him to this visit. The owner's or his
    chief's to give (`a_chief`); a suggestion from the roster is nothing until then."""
    appointment = await _driving_visit(session, context, appointment_id, person_id)
    return DriveDraft(appointment_id=appointment.id, person_id=person_id)


@audited(Action.WRITE, Scope.FAMILY, LOGISTICS)
async def assign_driver(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    person_id: uuid.UUID,
    confirmation_id: uuid.UUID,
) -> Task:
    """On the chief's yes for exactly this, the family task "drive Pa to Dr Tan", given to
    that person, due at the visit, naming it. The yes is spent last, after every check."""
    appointment = await _driving_visit(session, context, appointment_id, person_id)
    visit = await require_visit(session, context=context, appointment_id=appointment.id)
    profile = await audited_profile_read(session, context)
    await consume_confirmation(
        session,
        context,
        confirmation_id,
        DriveDraft(appointment_id=appointment.id, person_id=person_id),
    )
    label = DRIVE_TASK[visit.language].format(name=profile.display_name, doctor=visit.doctor)
    return await add_task(
        session,
        context=context,
        what=label,
        assigned_person_id=person_id,
        due_at=appointment.scheduled_at,
        language=visit.language,
        appointment_id=appointment.id,
        errand=Errand.DRIVE,
    )


__all__ = [
    "Driver",
    "DriverStatus",
    "Line",
    "Logistics",
    "NotOnThisVisit",
    "PlaceNote",
    "assign_driver",
    "drive_draft_for",
    "drive_task_of",
    "logistics_for",
]
