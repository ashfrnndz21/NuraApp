"""The day's routine (E10-01): set once on a person's yes, rendered per persona.

    Acceptance: medicines, readings, walks, meals, sleep set once; renders to Dad and helper.

The day is five anchors — wake, breakfast, lunch, dinner, bed — each at a time on his wall
clock; the readings he is prompted for and the walks, each at an anchor; and the time his
Today page comes. Meals and sleep are the anchors themselves. The medicines are E04's dose
codes mapped onto the same anchors (`Dose.scheduled_anchors`): a twice-a-day tablet sits at
breakfast and dinner unless its label named other moments. A when-needed medicine has no
anchor and is listed apart; a weekly one sits at its anchor in the caregiver's table and is
left out of his daily lines.

Setting the day is a confirm-bound write (`RoutineDraft`): the person who sets it said yes to
exactly these times and prompts, naming the routine it replaces, and the old row stays,
marked with when it stopped. Who may set it: the owner, the steward, a chief or a caregiver;
a helper, a viewer, a clinic read it (`NotTheirsToSet`). Prompts for readings need the
readings scope to set and to see; a key without it sees the day with them withheld, by name.

Rendered per persona: the patient reads one line per moment in his words
(`app.delivery.routine_strings`), verified before it leaves; the caregiver reads a dense
table of times, codes and medicines. `due_now` answers what is due at a moment.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentPurpose
from app.consent.service import require_consent
from app.db import as_utc, utcnow
from app.delivery import routine_strings as words
from app.delivery.when_words import say_clock
from app.drafts import RoutineDraft
from app.drugs.registry import DrugRegistry
from app.errors import Refusal
from app.family.common import NotPlainWords
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext, OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.medicines.dose import Dose, Frequency
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.strings import PLAIN_NAME, language_of, say_amount
from app.regions import REGION_TZ
from app.routines.models import Routine
from app.safety.plain_words import verify

TARGET = Routine.__tablename__

ANCHORS: tuple[str, ...] = ("wake", "breakfast", "lunch", "dinner", "bed")
"""The moments of his day, in order. Meals and sleep are anchors; a dose hangs on one."""
DEFAULT_ANCHORS: Mapping[str, str] = {
    "wake": "06:30",
    "breakfast": "07:30",
    "lunch": "12:30",
    "dinner": "18:30",
    "bed": "22:00",
}
"""The day before anyone has set it. Shown as not set; a person sets his own."""
DEFAULT_MORNING_CARD = "07:00"
READINGS: tuple[str, ...] = ("blood_pressure", "blood_sugar", "weight")
"""What he can be prompted to take a reading of: the cuff, the glucometer, the scale."""
PER_LINE = 2
"""Medicines on one of his lines; a third starts a second line for the same moment."""
DUE_FOR = timedelta(minutes=60)
"""How long an anchor is due for, or until the next anchor if that comes sooner."""
SETTERS: frozenset[KeyRole] = frozenset({KeyRole.CHIEF, KeyRole.CAREGIVER})

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class Persona(StrEnum):
    PATIENT = "patient"
    CAREGIVER = "caregiver"


class NotARoutine(Refusal):
    """A day is five anchors at rising times on his clock, prompts and walks at anchors, and
    a morning card time. This was not one."""


class NotTheirsToSet(Refusal):
    """A key to read the day is not a key to set it."""


@dataclass(frozen=True, slots=True)
class Day:
    """The day, checked: times as times, prompts and walks in anchor order."""

    anchors: Mapping[str, time]
    reading_prompts: tuple[tuple[str, str], ...]
    walks: tuple[str, ...]
    morning_card_at: time

    def as_strings(self) -> dict[str, str]:
        return {anchor: self.anchors[anchor].strftime("%H:%M") for anchor in ANCHORS}


def _clock(text: Any, what: str) -> time:
    match = _HHMM.match(str(text))
    if match is None:
        raise NotARoutine(f"{what} is a time on the clock, HH:MM")
    return time(int(match.group(1)), int(match.group(2)))


def check_day(
    anchors: Mapping[str, str],
    reading_prompts: Sequence[Sequence[str]],
    walks: Sequence[str],
    morning_card_at: str,
) -> Day:
    """The day as given, or `NotARoutine`: all five anchors, each later than the one before,
    prompts for readings we know at anchors, walks at anchors, each once."""
    if set(anchors) != set(ANCHORS):
        raise NotARoutine(f"a day names exactly the anchors {', '.join(ANCHORS)}")
    times = {anchor: _clock(anchors[anchor], anchor) for anchor in ANCHORS}
    ordered = [times[anchor] for anchor in ANCHORS]
    if any(later <= earlier for earlier, later in pairwise(ordered)):
        raise NotARoutine("the anchors come in order: wake, breakfast, lunch, dinner, bed")
    prompts: list[tuple[str, str]] = []
    for prompt in reading_prompts:
        if len(prompt) != 2 or prompt[0] not in READINGS or prompt[1] not in ANCHORS:
            raise NotARoutine(f"a prompt is one of {', '.join(READINGS)} at an anchor")
        pair = (str(prompt[0]), str(prompt[1]))
        if pair in prompts:
            raise NotARoutine("a prompt is set once")
        prompts.append(pair)
    walked: list[str] = []
    for anchor in walks:
        if anchor not in ANCHORS or anchor in walked:
            raise NotARoutine("a walk is at an anchor, once")
        walked.append(anchor)
    return Day(
        anchors=times,
        reading_prompts=tuple(sorted(prompts, key=lambda p: (ANCHORS.index(p[1]), p[0]))),
        walks=tuple(sorted(walked, key=ANCHORS.index)),
        morning_card_at=_clock(morning_card_at, "the morning card"),
    )


def day_of(routine: Routine | None) -> Day:
    if routine is None:
        return check_day(DEFAULT_ANCHORS, (), (), DEFAULT_MORNING_CARD)
    return check_day(
        routine.anchors, routine.reading_prompts, routine.walks, routine.morning_card_at
    )


def may_set_routine(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role in SETTERS:
        return
    raise NotTheirsToSet(f"a {context.role} key reads the day; it does not set it")


@audited(Action.READ, Scope.MEDICINES, TARGET)
async def current_routine(session: AsyncSession, *, context: KeyContext) -> Routine | None:
    """The day as it is set now, or None before anyone has set it."""
    found = await audited_read(
        session, Routine, context, Scope.MEDICINES, where=(Routine.superseded_at.is_(None),)
    )
    return max(found, key=lambda row: as_utc(row.set_at), default=None)


@audited(Action.READ, Scope.MEDICINES, TARGET)
async def routine_draft_for(
    session: AsyncSession,
    *,
    context: KeyContext,
    anchors: Mapping[str, str],
    reading_prompts: Sequence[Sequence[str]],
    walks: Sequence[str],
    morning_card_at: str,
) -> RoutineDraft:
    """What the person is saying yes to: this day, replacing the one set now. The surface
    mints the yes over this; `set_routine` recomputes it."""
    may_set_routine(context)
    day = check_day(anchors, reading_prompts, walks, morning_card_at)
    if day.reading_prompts and not context.allows(Scope.READINGS):
        raise OutOfScope(scope=Scope.READINGS, context=context)
    current = await current_routine(session, context=context)
    return RoutineDraft(
        anchors=day.as_strings(),
        reading_prompts=day.reading_prompts,
        walks=day.walks,
        morning_card_at=day.morning_card_at.strftime("%H:%M"),
        supersedes_id=None if current is None else current.id,
    )


@audited(Action.WRITE, Scope.MEDICINES, TARGET)
async def set_routine(
    session: AsyncSession,
    *,
    context: KeyContext,
    anchors: Mapping[str, str],
    reading_prompts: Sequence[Sequence[str]],
    walks: Sequence[str],
    morning_card_at: str,
    confirmation_id: uuid.UUID,
) -> Routine:
    """Set the day on the person's yes for exactly it. The day it replaces stays, marked."""
    await require_consent(
        session, context=context, purpose=ConsentPurpose.HOLD_HEALTH_RECORD, scope=Scope.MEDICINES
    )
    draft = await routine_draft_for(
        session,
        context=context,
        anchors=anchors,
        reading_prompts=reading_prompts,
        walks=walks,
        morning_card_at=morning_card_at,
    )
    current = await current_routine(session, context=context)
    yes = await consume_confirmation(session, context, confirmation_id, draft)
    moment = utcnow()
    row = await audited_write(
        session,
        Routine,
        context,
        Scope.MEDICINES,
        anchors=dict(draft.anchors),
        reading_prompts=[list(prompt) for prompt in draft.reading_prompts],
        walks=list(draft.walks),
        morning_card_at=draft.morning_card_at,
        supersedes_id=draft.supersedes_id,
        set_by_person_id=yes.person_id,
        set_at=moment,
    )
    if current is not None:
        current.superseded_at = moment
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.MEDICINES,
            target=TARGET,
            target_id=current.id,
            rows=1,
        )
    return row


# --- the day, with the medicines on it ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class AtAnchor:
    """One medicine at one moment: which line, his name for it, how much, how often."""

    line_id: uuid.UUID
    generic: str
    strength: str
    name: str
    amount: float
    unit: str
    frequency: str


@dataclass(slots=True)
class Moment:
    anchor: str
    at: time
    medicines: list[AtAnchor] = field(default_factory=list)
    readings: list[str] = field(default_factory=list)
    walk: bool = False


@dataclass(frozen=True, slots=True)
class TheDay:
    routine: Routine | None
    day: Day
    moments: tuple[Moment, ...]
    when_needed: tuple[AtAnchor, ...]
    withheld: frozenset[Scope]


async def _active_lines(session: AsyncSession, context: KeyContext) -> Sequence[MedicationLine]:
    found = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(
            MedicationLine.superseded_at.is_(None),
            MedicationLine.status == LineStatus.ACTIVE,
        ),
    )
    return sorted(found, key=lambda line: (as_utc(line.started_at), line.generic))


@audited(Action.READ, Scope.MEDICINES, TARGET)
async def the_day(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry, language: str
) -> TheDay:
    """The day as set (or the default), with every active medicine at its anchors."""
    routine = await current_routine(session, context=context)
    day = day_of(routine)
    moments = {anchor: Moment(anchor=anchor, at=day.anchors[anchor]) for anchor in ANCHORS}
    withheld: set[Scope] = set()
    if context.allows(Scope.READINGS):
        for reading, anchor in day.reading_prompts:
            moments[anchor].readings.append(reading)
    elif day.reading_prompts:
        withheld.add(Scope.READINGS)
    for anchor in day.walks:
        moments[anchor].walk = True
    when_needed: list[AtAnchor] = []
    for line in await _active_lines(session, context):
        dose = Dose.from_json(line.dose)
        item = AtAnchor(
            line_id=line.id,
            generic=line.generic,
            strength=line.strength,
            name=PLAIN_NAME[language][registry.monograph(line.generic).plain_name_id],
            amount=dose.amount,
            unit=dose.unit,
            frequency=dose.frequency.value,
        )
        if dose.frequency is Frequency.PRN:
            when_needed.append(item)
            continue
        for anchor in dose.scheduled_anchors:
            moments[anchor.value].medicines.append(item)
    return TheDay(
        routine=routine,
        day=day,
        moments=tuple(moments[anchor] for anchor in ANCHORS),
        when_needed=tuple(when_needed),
        withheld=frozenset(withheld),
    )


# --- rendered per persona ------------------------------------------------------------------


def _join(items: Sequence[str], language: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return words.COMMA[language].join(items[:-1]) + words.AND[language] + items[-1]


def _capital(line: str) -> str:
    return line[:1].upper() + line[1:]


def patient_lines(the: TheDay, language: str) -> list[str]:
    """One line per moment of his day, in his words; the Today page's hour first."""
    lines = [words.MORNING_CARD[language].format(clock=say_clock(the.day.morning_card_at, language))]
    for moment in the.moments:
        tablets = [
            words.ITEM[language].format(
                amount=say_amount(item.amount, item.unit, language), name=item.name
            )
            for item in moment.medicines
            if item.frequency != Frequency.WEEKLY.value
        ]
        doing = [words.DOING[language][code] for code in moment.readings]
        if moment.walk:
            doing.append(words.DOING[language]["walk"])
        chunks = [tablets[i : i + PER_LINE] for i in range(0, len(tablets), PER_LINE)] or [[]]
        for index, chunk in enumerate(chunks):
            does = doing if index == 0 else []
            if not chunk and not does:
                continue
            key = "both" if chunk and does else ("take" if chunk else "do")
            lines.append(
                _capital(
                    words.LINE[language][key].format(
                        moment=words.MOMENTS[language][moment.anchor],
                        tablets=_join(chunk, language),
                        doing=_join(does, language),
                    )
                )
            )
    return lines


def caregiver_table(the: TheDay) -> list[dict[str, Any]]:
    """The dense table: every moment, its time, its medicines by code, its prompts."""

    def item(entry: AtAnchor) -> dict[str, Any]:
        return {
            "line_id": str(entry.line_id),
            "generic": entry.generic,
            "strength": entry.strength,
            "name": entry.name,
            "amount": entry.amount,
            "unit": entry.unit,
            "frequency": entry.frequency,
        }

    return [
        {
            "anchor": moment.anchor,
            "at": moment.at.strftime("%H:%M"),
            "medicines": [item(entry) for entry in moment.medicines],
            "readings": None if Scope.READINGS in the.withheld else list(moment.readings),
            "walk": moment.walk,
        }
        for moment in the.moments
    ]


def check_lines(lines: Sequence[str], language: str) -> None:
    failing = [
        f"{finding.problem} ({line})"
        for line in lines
        for finding in verify(line, language)
        if finding.severity == "fail"
    ]
    if failing:
        raise NotPlainWords(failing)


@dataclass(frozen=True, slots=True)
class RoutineView:
    the: TheDay
    persona: Persona
    language: str
    lines: tuple[str, ...]
    table: tuple[dict[str, Any], ...]
    when_needed: tuple[dict[str, Any], ...]


def default_persona(context: KeyContext) -> Persona:
    return Persona.PATIENT if context.is_owner or context.is_claimant else Persona.CAREGIVER


@audited(Action.READ, Scope.MEDICINES, TARGET)
async def render_routine(
    session: AsyncSession,
    *,
    context: KeyContext,
    registry: DrugRegistry,
    persona: Persona | None = None,
    language: str | None = None,
) -> RoutineView:
    """The day for one reader: his lines, or her table."""
    lang = language_of(
        language if language is not None else (await audited_profile_read(session, context)).language
    )
    the = await the_day(session, context=context, registry=registry, language=lang)
    who = persona or default_persona(context)
    lines: list[str] = []
    table: list[dict[str, Any]] = []
    if who is Persona.PATIENT:
        lines = patient_lines(the, lang)
        check_lines(lines, lang)
    else:
        table = caregiver_table(the)
    when_needed = [
        {"line_id": str(e.line_id), "generic": e.generic, "name": e.name, "unit": e.unit}
        for e in the.when_needed
    ]
    return RoutineView(
        the=the,
        persona=who,
        language=lang,
        lines=tuple(lines),
        table=tuple(table),
        when_needed=tuple(when_needed),
    )


# --- what is due now ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Due:
    """What is due at one moment of his day: the anchor, its time, its medicines, its prompts."""

    anchor: str
    at: time
    local: datetime
    medicine_line_ids: tuple[uuid.UUID, ...]
    readings: tuple[str, ...]
    walk: bool


def due_at(day: Day, local: datetime) -> str | None:
    """The anchor due at this local moment: from its time for `DUE_FOR`, or until the next
    anchor if that comes sooner. None between them."""
    for index, anchor in enumerate(ANCHORS):
        start = datetime.combine(local.date(), day.anchors[anchor], tzinfo=local.tzinfo)
        end = start + DUE_FOR
        if index + 1 < len(ANCHORS):
            end = min(
                end, datetime.combine(local.date(), day.anchors[ANCHORS[index + 1]], tzinfo=local.tzinfo)
            )
        if start <= local < end:
            return anchor
    return None


@audited(Action.READ, Scope.MEDICINES, TARGET)
async def due_now(session: AsyncSession, *, context: KeyContext, at: datetime) -> Due | None:
    """What is due at `at` on his wall clock: the anchor's daily medicines, its prompts and its
    walk, or None when no anchor is due or nothing hangs on it. A weekly or when-needed
    medicine is never due by the clock alone. `at` is read, never written: this is for the
    feed and the nudges to ask about a moment."""
    day = day_of(await current_routine(session, context=context))
    local = as_utc(at).astimezone(REGION_TZ[context.region])
    anchor = due_at(day, local)
    if anchor is None:
        return None
    lines = [
        line
        for line in await _active_lines(session, context)
        if Dose.from_json(line.dose).frequency not in {Frequency.PRN, Frequency.WEEKLY}
        and anchor in {a.value for a in Dose.from_json(line.dose).scheduled_anchors}
    ]
    readings: tuple[str, ...] = ()
    if context.allows(Scope.READINGS):
        readings = tuple(code for code, at_anchor in day.reading_prompts if at_anchor == anchor)
    walk = anchor in day.walks
    if not lines and not readings and not walk:
        return None
    return Due(
        anchor=anchor,
        at=day.anchors[anchor],
        local=local,
        medicine_line_ids=tuple(line.id for line in lines),
        readings=readings,
        walk=walk,
    )
