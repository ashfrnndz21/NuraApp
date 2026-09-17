"""The pre-visit brief: purpose, what changed since last time, open questions, what to bring.

    T-3: what this visit is for, what to bring, GL status. T-0: the questions on one card.
    — docs/stage1-product-design.md (E05-01)

Everything on the brief is rendered from a template and checked by the plain-words verifier;
a brief with one line that fails is refused (`NotPlainEnough`) rather than shown with the
line missing. "What changed" is the State diff: the facts current now that were not in the
snapshot at the last visit, counted by what they are — numbers in his blood pressure book,
his medicines, his papers, how he is — and, each on a line of its own, every symptom written
down since the last visit (E14-01), in the symptom log's own words (`app.safety.symptom_log`),
with how much and since when. A symptom is never counted under his papers.

Generated at T-3 (E05-01): E11's engine renders the brief three days before a visit and hands
its card to delivery (`app.delivery.triggers.engine`, rule `brief_three_days_before`), and the
feed builds it again inside the week whenever State has moved.

One page: at most `LINE_BUDGET` lines. A section that would run over is folded — what fits,
then one line saying how many more (`_fold`) — so the brief never needs a second page.

The brief is a row that names the snapshot it was rendered from and the one it was measured
against, and it is never edited: a later brief for the same visit is a newer row. Its lines
come from the record, not from a person's typing; what he and his chief want to add goes on
the questions card (E05-02), which is theirs to edit — the operator's decision of 15
September 2026.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import FACT_SCOPES, Scope, scope_for_subject
from app.memory.models import Appointment, AppointmentStatus, Fact
from app.reasoning.visits.gaps import find_gaps
from app.reasoning.visits.guard import can_render_brief, may_render_brief
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.models import Brief, MemoKind, QuestionSource
from app.reasoning.visits.questions import (
    Visit,
    feeling_notes_for,
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
from app.regions import REGION_TZ
from app.safety.boundary import Surface, boundary_line
from app.safety.high_risk import MEDICINE_SUBJECTS
from app.state.dimensions import VISIT_LENGTH
from app.state.models import Dimension, StateSnapshot
from app.state.service import StateView, current_state, render_from_state

BRIEF = Brief.__tablename__

LINE_BUDGET = 21
"""One page (E05-01): the most lines a brief has — two for the purpose, four for what changed,
four for the symptoms, four for the questions, four for what to bring, three for the
boundary — each line held to plain words' length, so the whole fits one printed page at 20 px."""

SYMPTOM_LINES = 4
QUESTION_LINES = 4
MEMO_LINES = 2
"""The most lines a section takes before it is folded (`_fold`): the symptoms, the questions,
the memos to bring beside the two fixed bring lines."""


class NotOnePage(Refusal):
    """A brief would run over its one page. `compose` folds every section, so this is a bug."""


class NoBriefYet(Refusal):
    """A key that only reads the visits asked for a brief nobody has rendered yet. It reads
    the one that stands; it never renders one (`guard.may_render_brief`), and there is none
    to read. Nura renders it at T-3, or whoever may change the visits opens it first."""


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
        if fact.subject == SYMPTOM_SUBJECT:
            # A symptom has a line of its own (`symptom_lines`), never a count in his papers.
            continue
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


SYMPTOM_SUBJECT = "symptom"
"""The subject a symptom is written under (`app.safety.not_feeling_well.SYMPTOM`, which this
module does not import: the safety flow reaches the delivery engine, which reaches the brief)."""


def symptom_lines(entries: Sequence[Any], language: str, zone: tzinfo) -> list[list[Line]]:
    """One group of lines per symptom entry — a red flag's first, then newest first: a line per
    thing he felt, the symptom log's own sentence said to him ("You felt dizzy on Monday 14
    September."), and one line with how much and since when when he said either ("It was quite
    bad and it started that morning." — since when anchored to that day, not to the day he
    reads it). Every line is rendered by the log's catalogue, so verified; the sources are the
    fact."""
    from app.channels.safety_strings import (
        SINCE_THEN_WORDS,
        SYMPTOM_LINES_YOU,
        phrase,
        render,
        severity_said,
    )

    def order(entry: Any) -> tuple[bool, float, str]:
        return (not entry.red_flags, -entry.at.timestamp(), str(entry.fact_id))

    groups: list[list[Line]] = []
    for entry in sorted(entries, key=order):
        source = (str(entry.fact_id),)
        codes = [
            *(flag.value for flag in entry.red_flags),
            *(one.value for one in entry.symptoms if one.value != "not_well"),
        ] or ["not_well"]
        group = [
            Line(
                "changed",
                "symptom",
                render(
                    f"you.{code}" if code in SYMPTOM_LINES_YOU else "you.not_well",
                    language,
                    date=entry.at.astimezone(zone).date(),
                ),
                source,
            )
            for code in codes
        ]
        severity = None if entry.severity is None else severity_said(entry.severity, language)
        since = (
            None
            if entry.duration is None
            else phrase(SINCE_THEN_WORDS, language, entry.duration.value)
        )
        # How much and since when, one idea a line (plain words, rules 1 and 2): "It was quite
        # bad." then "It started that morning." — never joined into one.
        if severity is not None:
            detail = render("sym.severity", language, severity=severity)
            group.append(Line("changed", "symptom_detail", detail, source))
        if since is not None:
            detail = render("sym.since", language, since=since)
            group.append(Line("changed", "symptom_detail", detail, source))
        groups.append(group)
    return groups


def _fold(groups: Sequence[Sequence[Line]], cap: int, more: Line) -> list[Line]:
    """The groups that fit in `cap` lines, whole, then `more` — or all of them when they fit.
    The section is never empty when it has something to say: a first group too long for the
    page is cut to fit, never dropped (B1 review)."""
    every = [line for group in groups for line in group]
    if len(every) <= cap:
        return every
    shown: list[Line] = []
    for group in groups:
        room = cap - 1 - len(shown)
        if len(group) <= room:
            shown.extend(group)
            continue
        if not shown:
            shown.extend(group[:room])
        break
    return [*shown, more]


SYMPTOM_KEYS = frozenset({"symptom", "symptom_detail", "symptoms_more", "feeling_note"})
"""The brief's lines about how he feels: the record's (`Scope.RECORDS`, the scope the symptom
log and the feeling notes (RE-02) are read under), not the visits'."""


def feeling_note_lines(notes: Sequence[Any]) -> list[list[Line]]:
    """One group of lines per feeling note kept for this visit (RE-02), newest first, beside
    the symptom log: the note's own words, already rendered and verified when the tap was
    answered (`app.reasoning.feelings.inference.compose_note`) — never re-templated here, so
    what he read on the cloud's reply is exactly what reaches the doctor. The source is the
    note itself, so a reader without the part of the record it rests on loses it, not just its
    provenance (`lines_for`, `SYMPTOM_KEYS`)."""

    def order(note: Any) -> tuple[float, str]:
        return (-note.created_at.timestamp(), str(note.id))

    return [
        [Line("changed", "feeling_note", text, (str(note.id),)) for text in note.lines]
        for note in sorted(notes, key=order)
    ]


def lines_for(brief: Brief, context: KeyContext) -> tuple[list[dict[str, Any]], list[Scope]]:
    """The brief's lines as this key may read them, and what was withheld.

    A brief is rendered once, by a key that opens the whole record, and read by every key that
    holds the visits — so what it carries is narrowed here, to the reader, not at render time.

    A symptom is the record's: a key that holds the visits and not the record — a viewer's —
    reads the brief without the lines about how he feels, and is told the record was withheld
    (B1 review). A line also names the rows it rests on, and a row id is a row: a key missing
    any scope a fact can sit under (`FACT_SCOPES`) keeps the words and loses the provenance,
    rather than being handed the id of a fact it may not read. Nothing is narrowed for a key
    that holds all three, which is every key that may render a brief.
    """
    missing = [one for one in FACT_SCOPES if not context.allows(one)]
    if not missing:
        return list(brief.lines), []
    kept = list(brief.lines)
    if Scope.RECORDS in missing:
        kept = [line for line in kept if line["key"] not in SYMPTOM_KEYS]
    return [{**line, "sources": []} for line in kept], missing


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
    symptoms: Sequence[Sequence[Line]] = (),
) -> list[Line]:
    """The brief, section by section, every line through `say` — which refuses a line the
    verifier fails, and with it the whole brief — on one page (`LINE_BUDGET`): the symptoms,
    the questions and the memos to bring are each folded to what fits, and one line says how
    many more."""
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
    if not changed.any() and not symptoms:
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
            # "1 new number is", never "1 new numbers are".
            said = f"{key}_one" if len(new_ids) == 1 else key
            lines.append(
                Line(
                    "changed",
                    said,
                    say(said, lang, day=since_day, count=len(new_ids)),
                    tuple(new_ids),
                )
            )
    lines.extend(
        _fold(
            symptoms,
            SYMPTOM_LINES,
            Line("changed", "symptoms_more", say("symptoms_more", lang)),
        )
    )
    questions = [[Line("questions", key, text, ids)] for key, text, ids in proposed_lines]
    extra = len(questions) - (QUESTION_LINES - 1)
    lines.extend(
        _fold(
            questions,
            QUESTION_LINES,
            Line(
                "questions",
                "questions_more",
                say("questions_more", lang, count=max(extra, 2), doctor=doctor),
            ),
        )
    )
    lines.append(Line("bring", "bring_bp_book", say("bring_bp_book", lang, day=when)))
    if has_medicines:
        lines.append(Line("bring", "bring_medicines", say("bring_medicines", lang, day=when)))
    memos = [[Line("bring", key, text)] for key, text in bring_memos]
    extra = len(memos) - (MEMO_LINES - 1)
    lines.extend(
        _fold(
            memos,
            MEMO_LINES,
            Line("bring", "bring_more", say("bring_more", lang, count=max(extra, 2), day=when)),
        )
    )
    # Three boundary lines follow (`build_brief`); the whole must fit its one page.
    if len(lines) + 3 > LINE_BUDGET:
        raise NotOnePage(f"{len(lines) + 3} lines is more than one page")
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
    rests on. Only whoever may render it — whoever may change the visits, and Nura itself at T-3
    — gets past the first line; nothing is read for anyone else (B1 review).
    """
    may_render_brief(context)
    visit = await require_visit(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
    state = await current_state(session, context=context)
    since, since_moment = await _since_snapshot(session, context=context, visit=visit)
    changed = await _changed(session, context=context, state=state, since=since)
    since_day = day_and_date(since_moment, visit.language, context.region)
    proposed = await propose_questions(session, context=context, visit=visit)
    proposed_lines = [
        (
            one.key,
            one.text if one.text is not None else render_proposed(one, visit.language),
            one.source_ids,
        )
        for one in proposed
        # A feeling note is listed beside the symptom log (RE-02, below), in its own words,
        # not a second time in the questions section: it is already his own account of how he
        # feels, not a gap or a flag the record raised.
        if one.source is not QuestionSource.FEELING
    ]
    symptoms: list[list[Line]] = []
    feeling_notes: Sequence[Any] = ()
    if context.allows(Scope.RECORDS):
        # Every symptom written down since the last visit (E14-01), each its own line.
        from app.safety.symptom_log import symptoms_since

        log = await symptoms_since(
            session, context=context, since=since_moment, language=visit.language
        )
        symptoms = symptom_lines(log.entries, visit.language, REGION_TZ[context.region])
        # A cloud tap read against the record, kept for this visit (RE-02): beside the
        # symptom log, in his own already-verified words, never re-read from a Fact — the
        # promise the feeling cloud makes is kept here, not just recorded.
        feeling_notes = await feeling_notes_for(
            session, context=context, appointment_id=appointment_id
        )
        symptoms = [*symptoms, *feeling_note_lines(feeling_notes)]
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
        symptoms=symptoms,
    )
    # The brief infers — what changed, what to ask — so it ends on its boundary line
    # (E16-01), in his language, naming his doctor; the row carries the same words.
    boundary = boundary_line(Surface.BRIEF, visit.language, doctor=visit.doctor)
    lines = [*lines, *(Line("boundary", "boundary", text) for text in boundary.splitlines())]
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
        surface=Surface.BRIEF,
        boundary=boundary,
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
            "feeling_note_ids": sorted(str(note.id) for note in feeling_notes),
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
    past it, so what he reads is always rendered from the record as it is now.

    Rebuilt only for a key that may render it — whoever may change the visits, and Nura at
    T-3 (`guard.can_render_brief`). A viewer, a helper or a clinic key holds the visits scope
    to read: it gets the brief as it stands, State moved or not, because reading the brief is
    never rendering one and a read must not turn into a refusal the moment the record moves
    (B1 review). `NoBriefYet` when there is none for it to read.
    """
    newest = await latest_brief(session, context=context, appointment_id=appointment_id)
    if not can_render_brief(context):
        if newest is None:
            raise NoBriefYet(f"no brief for visit {appointment_id} yet")
        return newest
    state = await current_state(session, context=context)
    if newest is not None and newest.state_id == state.id:
        return newest
    return await build_brief(
        session, context=context, appointment_id=appointment_id, registry=registry
    )
