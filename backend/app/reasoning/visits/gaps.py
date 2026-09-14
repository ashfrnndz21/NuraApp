"""Gap detection: what the record is missing, as structured gaps.

    "No lipid panel in 14 months." "Dosage of amlodipine not confirmed since the discharge."
    Becomes a question for the next visit automatically. — docs/stage1-product-design.md

A gap is a `Gap(kind, subject, fact_ids, since)`: a fact past its validity window with nothing
current in its place, a reading with no recent value, a medicine line with no purpose, an
interaction the licensed data client flagged, an open dispute, an appointment with no stated
purpose. Nothing here judges a value — a number is never "high" here — it only notices what
is absent, and hands the gap to the questions (`questions.py`), which turn it into a line for
the doctor. The read is the record's: a gap is the record folded, like State.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import InteractionFlag, LineStatus, MedicationLine
from app.memory.episodic import fact_cites_only_what_is_held_here
from app.memory.models import Appointment, ConfidenceState, Fact

READING_WINDOW = timedelta(days=14)
"""A reading the record has had before, and none inside this window, is a gap."""

READING_SUBJECTS = frozenset({"blood_pressure", "blood_sugar", "weight"})


UNSTATED_PURPOSES = frozenset({"visit", "appointment", "check-up", "checkup", "unknown", "-"})
"""A purpose that says nothing: the visit was booked with no word for why."""

GAP_TARGET = "gap"


class GapKind(StrEnum):
    FACT_EXPIRED = "fact_expired"
    READING_STALE = "reading_stale"
    MEDICINE_NO_PURPOSE = "medicine_no_purpose"
    INTERACTION_FLAGGED = "interaction_flagged"
    OPEN_DISPUTE = "open_dispute"
    APPOINTMENT_NO_PURPOSE = "appointment_no_purpose"


class NoSuchAppointment(Refusal):
    """No appointment by that id on this profile."""


@dataclass(frozen=True, slots=True)
class Gap:
    """One thing the record is missing. `subject` is the fact subject, the medicine's name,
    or the appointment's id as text; `fact_ids` the facts it rests on; `since` when the gap
    opened. `medicine`, `other` and `flag_id` carry what a question needs to name."""

    kind: GapKind
    subject: str
    fact_ids: tuple[uuid.UUID, ...] = ()
    since: datetime | None = None
    medicine: str | None = None
    other: str | None = None
    flag_id: uuid.UUID | None = None
    line_id: uuid.UUID | None = None

    def source_ids(self) -> tuple[str, ...]:
        ids = [str(one) for one in self.fact_ids]
        if self.line_id is not None:
            ids.append(str(self.line_id))
        if self.flag_id is not None:
            ids.append(str(self.flag_id))
        return tuple(ids)


def _holds_at(fact: Fact, moment: datetime) -> bool:
    return as_utc(fact.valid_from) <= moment and (
        fact.valid_to is None or as_utc(fact.valid_to) > moment
    )


def purpose_known(registry: DrugRegistry, generic: str) -> bool:
    """Whether the licensed monograph says what this medicine is for. The purpose is the
    monograph's (`Monograph.purpose_id`, rendered by E04's story); a line the register has no
    monograph for, or one with no purpose, is a line with no purpose."""
    try:
        return bool(registry.monograph(generic).purpose_id)
    except UnknownDrug:
        return False


def gaps_in(
    facts: Sequence[Fact],
    lines: Sequence[MedicationLine],
    interactions: Sequence[InteractionFlag],
    appointment: Appointment | None,
    *,
    now: datetime,
    registry: DrugRegistry,
) -> list[Gap]:
    """The gaps among these rows at `now`. Pure: what `find_gaps` reads, worked out.

    `lines` are the active medication lines (E04's `MedicationLine`), `interactions` the
    `InteractionFlag` rows the licensed data wrote when a line arrived.
    """
    disputes = [f for f in facts if f.confidence_state is ConfidenceState.DISPUTED]
    settled = [f for f in facts if f.confidence_state is not ConfidenceState.DISPUTED]
    current = [f for f in settled if _holds_at(f, now)]
    current_keys = {(f.subject, f.attribute) for f in current}
    gaps: list[Gap] = []

    # 1. A fact whose window closed with nothing current in its place.
    expired: dict[tuple[str, str], tuple[datetime, Fact]] = {}
    for fact in settled:
        if fact.valid_to is None:
            continue
        closed_at = as_utc(fact.valid_to)
        key = (fact.subject, fact.attribute)
        newest_closed = key not in expired or closed_at > expired[key][0]
        if closed_at <= now and key not in current_keys and newest_closed:
            expired[key] = (closed_at, fact)
    for (subject, _attribute), (closed_at, fact) in sorted(expired.items()):
        gaps.append(Gap(GapKind.FACT_EXPIRED, subject, (fact.id,), closed_at))

    # 2. A reading the record has had, with none inside the window.
    for subject in sorted(READING_SUBJECTS):
        had = [f for f in settled if f.subject == subject]
        if not had:
            continue
        newest = max(had, key=lambda f: as_utc(f.valid_from))
        if as_utc(newest.valid_from) < now - READING_WINDOW:
            gaps.append(
                Gap(GapKind.READING_STALE, subject, (newest.id,), as_utc(newest.valid_from))
            )

    # 3. A medicine line with no purpose: the monograph has none, or the register has no
    # monograph for it. The line is E04's row, read under the medicines scope.
    active = {line.id: line for line in lines}
    for line in sorted(lines, key=lambda one: (as_utc(one.started_at), one.generic)):
        if purpose_known(registry, line.generic):
            continue
        gaps.append(
            Gap(
                GapKind.MEDICINE_NO_PURPOSE,
                line.generic,
                (line.fact_id,),
                as_utc(line.started_at),
                medicine=line.generic,
                line_id=line.id,
            )
        )

    # 4. An interaction the licensed data flagged between two lines still active.
    for flag in sorted(interactions, key=lambda one: (as_utc(one.flagged_at), str(one.id))):
        flagged, other = active.get(flag.line_id), active.get(flag.other_line_id)
        if flagged is None or other is None:
            continue
        gaps.append(
            Gap(
                GapKind.INTERACTION_FLAGGED,
                flagged.generic,
                (flagged.fact_id, other.fact_id),
                as_utc(flag.flagged_at),
                medicine=flagged.generic,
                other=other.generic,
                flag_id=flag.id,
            )
        )

    # 5. An open dispute: a person or a paper disagrees with a fact nobody has settled.
    for dispute in sorted(disputes, key=lambda f: as_utc(f.asserted_at)):
        ids = (dispute.id,) + ((dispute.supersedes_id,) if dispute.supersedes_id else ())
        gaps.append(Gap(GapKind.OPEN_DISPUTE, dispute.subject, ids, as_utc(dispute.asserted_at)))

    # 6. The visit itself, booked with no word for why.
    if appointment is not None and appointment.purpose.strip().lower() in UNSTATED_PURPOSES:
        gaps.append(
            Gap(
                GapKind.APPOINTMENT_NO_PURPOSE,
                str(appointment.id),
                (),
                as_utc(appointment.booked_at),
            )
        )
    return gaps


@audited(Action.READ, Scope.RECORDS, GAP_TARGET)
async def find_gaps(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    appointment_id: uuid.UUID | None = None,
) -> list[Gap]:
    """The gaps in this profile's record now, and in the visit named, if one is.

    Every fact not yet superseded is read — current, expired and disputed — because a gap
    is exactly what the current facts do not say. The read is the record's, under
    `Scope.RECORDS`, as State's is. The medicine lines and the interaction flags are E04's
    rows under `Scope.MEDICINES`: a key without it sees no medicine gaps, and that is a
    narrower brief, not a wrong one.
    """
    moment = utcnow()
    facts = await audited_read(
        session,
        Fact,
        context,
        Scope.RECORDS,
        where=(
            Fact.superseded_at.is_(None),
            fact_cites_only_what_is_held_here(context, Scope.RECORDS),
        ),
    )
    lines: Sequence[MedicationLine] = ()
    interactions: Sequence[InteractionFlag] = ()
    if context.allows(Scope.MEDICINES):
        lines = await audited_read(
            session,
            MedicationLine,
            context,
            Scope.MEDICINES,
            where=(
                MedicationLine.superseded_at.is_(None),
                MedicationLine.status == LineStatus.ACTIVE,
            ),
        )
        if lines:
            interactions = await audited_read(
                session,
                InteractionFlag,
                context,
                Scope.MEDICINES,
                where=(InteractionFlag.line_id.in_([line.id for line in lines]),),
            )
    appointment = None
    if appointment_id is not None:
        found = await audited_read(
            session, Appointment, context, Scope.VISITS, where=(Appointment.id == appointment_id,)
        )
        if not found:
            raise NoSuchAppointment(
                f"no appointment {appointment_id} on profile {context.profile_id}"
            )
        appointment = found[0]
    return gaps_in(facts, lines, interactions, appointment, now=moment, registry=registry)
