"""The pre-visit brief: purpose, what changed since last time, open questions, what to bring.

    T-3: what this visit is for, what to bring, GL status. T-0: the questions on one card.
    — docs/stage1-product-design.md (E05-01)

Everything on the brief is rendered from a template and checked by the plain-words verifier;
a brief with one line that fails is refused (`NotPlainEnough`) rather than shown with the
line missing. "What changed" is the State diff: the facts current now that were not in the
snapshot at the last visit, counted by what they are — numbers in his blood pressure book,
his medicines, his papers, how he is. The brief is a row that names the snapshot it was
rendered from and the one it was measured against, and it is never edited: a later brief
for the same visit is a newer row.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.memory.models import Appointment, AppointmentStatus, Fact
from app.reasoning.visits.gaps import find_gaps
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.models import Brief, MemoKind
from app.reasoning.visits.questions import (
    Visit,
    propose_questions,
    questions_for,
    render_proposed,
    require_visit,
)
from app.reasoning.visits.strings import (
    day_and_date,
    purpose_code,
    say,
    spoken,
    time_of_day,
    visit_subject_words,
)
from app.safety.high_risk import MEDICINE_SUBJECTS
from app.state.dimensions import VISIT_LENGTH
from app.state.models import Dimension, StateSnapshot
from app.state.service import StateView, current_state, render_from_state

BRIEF = Brief.__tablename__


@dataclass(frozen=True, slots=True)
class Line:
    """One line of the brief: its section, the template it came from, the text, and the
    ids it rests on."""

    section: str
    key: str
    text: str
    sources: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "key": self.key,
            "text": self.text,
            "spoken": spoken(self.text),
            "sources": list(self.sources),
        }


@dataclass(frozen=True, slots=True)
class Changed:
    """What is new since the snapshot measured against, by what it is."""

    readings: list[str] = field(default_factory=list)
    medicines: list[str] = field(default_factory=list)
    papers: list[str] = field(default_factory=list)
    how_you_are: list[str] = field(default_factory=list)

    def any(self) -> bool:
        return bool(self.readings or self.medicines or self.papers or self.how_you_are)


def _fact_ids(view: StateView | StateSnapshot) -> set[str]:
    ids: set[str] = set()
    dimensions = view.dimensions() if isinstance(view, StateSnapshot) else view.dimensions
    for held in dimensions.values():
        if held:
            ids.update(str(one) for one in held.get("fact_ids", []))
    return ids


async def _since_snapshot(
    session: AsyncSession, *, context: KeyContext, visit: Visit
) -> tuple[StateSnapshot | None, datetime]:
    """What to measure "what changed" from: the last snapshot computed by the end of the
    last visit before this one, and that visit's day. With no earlier visit the record is
    measured from nothing — everything on it is new to this doctor — and the day is the
    record's first."""
    moment = utcnow()
    earlier = await audited_read(
        session,
        Appointment,
        context,
        Scope.VISITS,
        where=(
            Appointment.scheduled_at < visit.appointment.scheduled_at,
            Appointment.scheduled_at <= moment,
            Appointment.status != AppointmentStatus.CANCELLED,
        ),
    )
    snapshots = await audited_read(
        session, StateSnapshot, context, Scope.RECORDS, order_by=(StateSnapshot.sequence.asc(),)
    )
    began = as_utc(snapshots[0].computed_at) if snapshots else moment
    if not earlier:
        return None, began
    last = max(earlier, key=lambda one: as_utc(one.scheduled_at))
    ended = as_utc(last.scheduled_at) + VISIT_LENGTH
    before = [one for one in snapshots if as_utc(one.computed_at) <= ended]
    return (before[-1] if before else None), as_utc(last.scheduled_at)


async def _changed(
    session: AsyncSession, *, context: KeyContext, state: StateView, since: StateSnapshot | None
) -> Changed:
    now_ids = _fact_ids(state)
    then_ids = _fact_ids(since) if since is not None else set()
    arrived = sorted(now_ids - then_ids)
    changed = Changed()
    if not arrived:
        return changed
    facts = await audited_read(
        session,
        Fact,
        context,
        Scope.RECORDS,
        where=(Fact.id.in_([uuid.UUID(one) for one in arrived]),),
    )
    for fact in sorted(facts, key=lambda one: (as_utc(one.asserted_at), str(one.id))):
        dimension = _dimension_of(state, str(fact.id))
        if dimension is Dimension.CLINICAL or dimension is None:
            if scope_for_subject(fact.subject) is Scope.READINGS:
                changed.readings.append(str(fact.id))
            elif fact.subject in MEDICINE_SUBJECTS:
                changed.medicines.append(str(fact.id))
            else:
                changed.papers.append(str(fact.id))
        else:
            changed.how_you_are.append(str(fact.id))
    return changed


def _dimension_of(state: StateView, fact_id: str) -> Dimension | None:
    for dimension, held in state.dimensions.items():
        if held and fact_id in held.get("fact_ids", []):
            return dimension
    return None


def compose(
    *,
    visit: Visit,
    since_day: str,
    changed: Changed,
    proposed_lines: Sequence[tuple[str, str, tuple[str, ...]]],
    bring_memos: Sequence[tuple[str, str]],
    has_medicines: bool,
    context: KeyContext,
) -> list[Line]:
    """The brief, section by section, every line through `say` — which refuses a line the
    verifier fails, and with it the whole brief."""
    lang = visit.language
    doctor = visit.doctor
    when = day_and_date(visit.appointment.scheduled_at, lang, context.region)
    at = time_of_day(visit.appointment.scheduled_at, lang, context.region)
    # The booking's purpose is a caregiver's label and never reaches him as written: it is
    # mapped to a fixed subject with his words for it, or the visit is "about your health".
    code = purpose_code(visit.appointment.purpose)
    about = (
        say("visit_about", lang, subject=visit_subject_words(code, lang))
        if code is not None
        else say("visit_about_health", lang)
    )
    lines = [
        Line("purpose", "visit_with", say("visit_with", lang, doctor=doctor, day=when, time=at)),
        Line(
            "purpose",
            "visit_about" if code is not None else "visit_about_health",
            about,
            (str(visit.appointment.id),),
        ),
    ]
    if not changed.any():
        lines.append(
            Line("changed", "nothing_changed", say("nothing_changed", lang, day=since_day))
        )
    counted: tuple[tuple[str, list[str]], ...] = (
        ("changed_readings", changed.readings),
        ("changed_medicines", changed.medicines),
        ("changed_papers", changed.papers),
        ("changed_how_you_are", changed.how_you_are),
    )
    for key, new_ids in counted:
        if new_ids:
            lines.append(
                Line(
                    "changed",
                    key,
                    say(key, lang, day=since_day, count=len(new_ids)),
                    tuple(new_ids),
                )
            )
    for key, text, source_ids in proposed_lines:
        lines.append(Line("questions", key, text, source_ids))
    lines.append(Line("bring", "bring_bp_book", say("bring_bp_book", lang, day=when)))
    if has_medicines:
        lines.append(Line("bring", "bring_medicines", say("bring_medicines", lang, day=when)))
    for key, text in bring_memos:
        lines.append(Line("bring", key, text))
    return lines


@audited(Action.WRITE, Scope.VISITS, BRIEF)
async def build_brief(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    registry: DrugRegistry,
) -> Brief:
    """Compose and file the brief for one visit, in the profile's language, from State.

    Refused whole if any line fails the verifier. The row names the snapshot it was rendered
    from and the one "what changed" was measured against, and every line carries the ids it
    rests on.
    """
    visit = await require_visit(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
    state = await current_state(session, context=context)
    since, since_moment = await _since_snapshot(session, context=context, visit=visit)
    changed = await _changed(session, context=context, state=state, since=since)
    since_day = day_and_date(since_moment, visit.language, context.region)
    proposed = await propose_questions(session, context=context, visit=visit)
    proposed_lines = [
        (one.key, render_proposed(one, visit.language), one.source_ids) for one in proposed
    ]
    memos = await current_memos(session, context=context)
    bring = [
        (m.key, m.text) for m in memos if m.kind is MemoKind.BRING and m.language == visit.language
    ]
    clinical = state.dimension(Dimension.CLINICAL) or {}
    has_medicines = any(subject in MEDICINE_SUBJECTS for subject in clinical.get("facts", {}))
    lines = compose(
        visit=visit,
        since_day=since_day,
        changed=changed,
        proposed_lines=proposed_lines,
        bring_memos=bring,
        has_medicines=has_medicines,
        context=context,
    )
    gaps = await find_gaps(
        session, context=context, registry=registry, appointment_id=appointment_id
    )
    # The questions list is refreshed here, the one write behind the brief; the questions
    # route itself only reads.
    await questions_for(session, context=context, appointment_id=appointment_id, registry=registry)
    return await render_from_state(
        session,
        Brief,
        context,
        Scope.VISITS,
        state=state,
        appointment_id=appointment_id,
        language=visit.language,
        since_state_id=None if since is None else since.id,
        lines=[line.as_json() for line in lines],
        sources={
            "gap_fact_ids": sorted({str(fid) for gap in gaps for fid in gap.fact_ids}),
            "memo_ids": sorted(str(m.id) for m in memos),
            "flag_ids": sorted(
                {sid for one in proposed if one.source.value == "flag" for sid in one.source_ids}
            ),
        },
        built_at=utcnow(),
    )


@audited(Action.READ, Scope.VISITS, BRIEF)
async def latest_brief(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID
) -> Brief | None:
    found = await audited_read(
        session, Brief, context, Scope.VISITS, where=(Brief.appointment_id == appointment_id,)
    )
    if not found:
        return None
    return max(found, key=lambda one: (as_utc(one.built_at), str(one.id)))


@audited(Action.READ, Scope.VISITS, BRIEF)
async def brief_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    appointment_id: uuid.UUID,
    registry: DrugRegistry,
) -> Brief:
    """The brief for this visit as it stands: the newest one, rebuilt when State has moved
    past it, so what he reads is always rendered from the record as it is now."""
    newest = await latest_brief(session, context=context, appointment_id=appointment_id)
    state = await current_state(session, context=context)
    if newest is not None and newest.state_id == state.id:
        return newest
    return await build_brief(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
