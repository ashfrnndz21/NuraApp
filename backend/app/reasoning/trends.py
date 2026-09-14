"""The lab trend (E09-01): his results for one analyte, against the range that fits him.

    Acceptance: a trend per analyte with its range band and its direction in words.

`trend` reads the confirmed facts for one analyte — each with its provenance, the paper it was
read from — and for each result finds the range that fits him on that day through the
`ReferenceRanges` port: his age band from the decade he was born in, his sex when a
`person.sex` fact exists, and the lab when the same paper names one (a `lab_report.lab` fact on
the same artefact), whose printed range then wins. The decade is read, in this order, from the
`setting.birth_decade` fact onboarding writes (E01), then a lab header's year of birth
(`person.birth_year`), then a lab header's age (`person.age`) on that paper's date; only the
decade ever enters the band. Each result is
placed in, above or below its range by arithmetic, and the direction over the last three
results is arithmetic too (`direction_of`). No model is called.

The lines he reads are templates (`app.delivery.trend_strings`) in his language: the latest
number and its day, the range, where the number sits only when the range is the lab's own,
the direction, and the boundary line for `Surface.TREND` last, naming the doctor to ask.
Every line is verified against docs/plain-words.md before it leaves (`NotPlainWords`). A
trend is a pattern to discuss, never a finding: no line names a cause or a treatment.

It is rendered from State. A key that can recompute State (the owner, a chief) renders from
the current State — every result shown must be one it was computed from — through
`render_from_state`, which stamps the State and refuses the row without its boundary line. A
key that cannot (a caregiver with the analyte's scope) renders from the last snapshot through
`render_from_last_snapshot`, the emergency card's pattern: refused as stale (`StaleState`,
409) unless that snapshot's `computed_from` already covers every result the trend shows, so a
result written since, that nobody who can recompute has caught State up with, is never shown
on a State that did not fold it in.
The door's scope is the analyte's subject's (`scope_for_subject`), so a key that does not
reach that part of the record is refused and the refusal is on the trail.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read
from app.audit.models import Action
from app.db import as_utc, utcnow
from app.delivery import trend_strings as words
from app.delivery.when_words import say_day
from app.errors import Refusal
from app.family.common import NotPlainWords
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.medicines.models import LineStatus, MedicationLine
from app.memory.models import ConfidenceState, Fact, ProviderKind
from app.memory.semantic import current_facts
from app.memory.spine import list_providers, upcoming_appointments
from app.reasoning.models import Direction, TrendCard
from app.reasoning.ranges import (
    Analyte,
    Band,
    NoRangeBecause,
    Range,
    RangeSource,
    ReferenceRanges,
    Sex,
    age_from_decade,
)
from app.regions import REGION_TZ
from app.safety.boundary import (
    Surface,
    boundary_line,
    boundary_lines,
    is_boundary_line,
    language_of,
)
from app.safety.plain_words import verify
from app.state.service import (
    RECOMPUTE_SCOPES,
    NoBoundaryLine,
    SnapshotBehindTheCard,
    StaleState,
    StateView,
    current_state,
    render_from_last_snapshot,
    render_from_state,
)

LAST = 3
"""The direction is read over the last three results."""
STEADY_WITHIN = 0.05
"""The last within five per cent of the first of the three reads as about the same."""

PERSON = "person"
SETTING = ("setting", "birth_decade")
"""Where onboarding (E01) keeps the decade he was born in, as a Fact: the first place to look."""
LAB_REPORT = ("lab_report", "lab")


class NoSuchAnalyte(Refusal):
    """The trend is for an analyte the range table knows. This one it does not."""


@dataclass(frozen=True, slots=True)
class Point:
    """One confirmed result: the fact, the paper, the number, its day, and where it sits."""

    fact_id: uuid.UUID
    artifact_id: uuid.UUID | None
    event_id: uuid.UUID | None
    confirmed_by_person_id: uuid.UUID | None
    value: float
    unit: str | None
    on: date
    lab: str | None
    age: int | None
    range: Range | None
    no_range_because: NoRangeBecause | None
    in_analyte_unit: float | None
    band: Band


@dataclass(frozen=True, slots=True)
class Trend:
    analyte: Analyte
    language: str
    points: tuple[Point, ...]
    direction: Direction
    direction_since: date | None
    lines: tuple[str, ...]
    boundary: str
    doctor: str | None
    birth_decade: int | None
    sex: Sex | None
    card: TrendCard


def direction_of(values: Sequence[float]) -> Direction:
    """Up, down, about the same, or up and down, over the last three values. Arithmetic only:
    about the same when the last is within `STEADY_WITHIN` of the first; up or down when every
    step goes that way; otherwise up and down."""
    last = list(values)[-LAST:]
    if not last:
        return Direction.NONE
    if len(last) == 1:
        return Direction.ONE
    first, final = last[0], last[-1]
    if abs(final - first) <= STEADY_WITHIN * abs(first):
        return Direction.STEADY
    steps = [after - before for before, after in pairwise(last)]
    if all(step >= 0 for step in steps):
        return Direction.UP
    if all(step <= 0 for step in steps):
        return Direction.DOWN
    return Direction.MIXED


def say_number(value: float) -> str:
    """230, 5.2, 10.78: digits, no trailing zeros."""
    rounded = round(value, 2)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _capital(line: str) -> str:
    return line[:1].upper() + line[1:]


def _bounds_in(range_: Range, analyte: Analyte, unit: str | None) -> tuple[str, str] | None:
    """The range's ends in the unit his paper used, so the number and the range agree."""
    factor = analyte.factor_for(unit)
    if factor is None or factor == 0:
        return None

    def end(bound: float | None) -> str:
        if bound is None:
            return ""
        return say_number(bound if factor == 1.0 else round(bound / factor, 1))

    return end(range_.lower), end(range_.upper)


def trend_lines(
    analyte: Analyte,
    points: Sequence[Point],
    direction: Direction,
    since: date | None,
    language: str,
    doctor: str | None,
) -> list[str]:
    """The lines he reads, in order, ending on the boundary line. Pure: no database."""
    name = words.NAMES[language][analyte.id]
    lines: list[str] = []
    if not points:
        lines.append(words.NOTHING_YET[language].format(name=name))
    else:
        latest = points[-1]
        day = say_day(latest.on, language, with_year=True)
        lines.extend(
            line.format(name=name, value=say_number(latest.value), day=day)
            for line in words.VALUE[language]
        )
        ends = None if latest.range is None else _bounds_in(latest.range, analyte, latest.unit)
        if latest.range is not None and ends is not None and latest.band is not Band.NOT_COMPARED:
            lower, upper = ends
            shape = "between" if lower and upper else ("under" if upper else "or_more")
            table = words.LAB_RANGE if latest.range.source is RangeSource.LAB else words.USUAL_RANGE
            lines.append(table[language][shape].format(lower=lower, upper=upper))
            if latest.range.source is RangeSource.LAB:
                lines.append(words.WHERE_IT_SITS[language][latest.band.value])
        if since is not None and direction in {
            Direction.UP,
            Direction.DOWN,
            Direction.STEADY,
            Direction.MIXED,
        }:
            lines.append(
                words.DIRECTION[language][direction.value].format(
                    day=say_day(since, language, with_year=True)
                )
            )
    lines = [_capital(line) for line in lines]
    lines.extend(boundary_lines(Surface.TREND, language, doctor=doctor))
    return lines


def check_lines(lines: Sequence[str], language: str) -> None:
    """Every line against docs/plain-words.md, as filled. A failing line refuses the trend."""
    failing = [
        f"{finding.problem} ({line})"
        for line in lines
        for finding in verify(line, language)
        if finding.severity == "fail"
    ]
    if failing:
        raise NotPlainWords(failing)


def _door(call: dict[str, Any]) -> Scope:
    """The analyte's subject's scope; the record's when the analyte is not one we know."""
    ranges: ReferenceRanges = call["ranges"]
    analyte = ranges.analyte(str(call["analyte"]))
    return scope_for_subject(None if analyte is None else analyte.subject)


def _newest(facts: Sequence[Fact]) -> Fact | None:
    confirmed = [f for f in facts if f.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON]
    pool = confirmed or list(facts)
    return max(pool, key=lambda f: as_utc(f.asserted_at), default=None)


def _decade(value: Any, *, this_year: int) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer() or not 1900 <= number <= this_year:
        return None
    return int(number) // 10 * 10


async def birth_decade(session: AsyncSession, context: KeyContext) -> int | None:
    """The decade he was born in, in this order: the `setting.birth_decade` fact onboarding
    writes (E01), a lab header's year of birth (`person.birth_year`), a lab header's age
    (`person.age`) on the date of that paper. Only the decade is kept; None when the record
    holds none of the three."""
    this_year = utcnow().year
    said = _newest(
        await current_facts(session, context=context, subject=SETTING[0], attribute=SETTING[1])
    )
    if said is not None and (decade := _decade(said.value, this_year=this_year)) is not None:
        return decade
    born = _newest(
        await current_facts(session, context=context, subject=PERSON, attribute="birth_year")
    )
    if born is not None and (decade := _decade(born.value, this_year=this_year)) is not None:
        return decade
    aged = _newest(await current_facts(session, context=context, subject=PERSON, attribute="age"))
    years = None if aged is None else _number(aged.value)
    if aged is not None and years is not None and years.is_integer() and 0 < years < 130:
        return _decade(as_utc(aged.valid_from).year - int(years), this_year=this_year)
    return None


async def _about_him(
    session: AsyncSession, context: KeyContext
) -> tuple[int | None, Sex | None, dict[uuid.UUID, str]]:
    """The decade he was born in and his sex, when the record holds them, and the lab each
    paper names."""
    decade = await birth_decade(session, context)
    said = _newest(await current_facts(session, context=context, subject=PERSON, attribute="sex"))
    sex = None
    if said is not None and isinstance(said.value, str) and said.value.lower() in {"male", "female"}:
        sex = Sex(said.value.lower())
    labs: dict[uuid.UUID, str] = {}
    for fact in await current_facts(
        session, context=context, subject=LAB_REPORT[0], attribute=LAB_REPORT[1]
    ):
        if fact.artifact_id is not None and isinstance(fact.value, str):
            labs[fact.artifact_id] = fact.value
    return decade, sex, labs


async def doctor_to_ask(session: AsyncSession, context: KeyContext) -> str | None:
    """The doctor the record names: the doctor of his next visit, else the prescriber on his
    newest medicine label, else nobody (the line then says "your doctor")."""
    if context.allows(Scope.VISITS):
        visits = await upcoming_appointments(session, context=context, limit=10)
        if visits:
            providers = {p.id: p for p in await list_providers(session, context=context)}
            for visit in visits:
                provider = providers.get(visit.provider_id)
                if provider is not None and provider.kind is ProviderKind.DOCTOR:
                    return provider.name
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
        named = sorted((line for line in lines if line.prescriber), key=lambda line: as_utc(line.asserted_at))
        if named:
            return named[-1].prescriber
    return None


@audited(Action.READ, _door, TrendCard.__tablename__)
async def trend(
    session: AsyncSession,
    *,
    context: KeyContext,
    ranges: ReferenceRanges,
    analyte: str,
    language: str | None = None,
) -> Trend:
    """The trend for one analyte, rendered from the current State, in `language` or his own."""
    found = ranges.analyte(analyte)
    if found is None:
        raise NoSuchAnalyte(f"no analyte {analyte!r} in the range table")
    # A key that can recompute renders from the current State; one that cannot renders from
    # the last snapshot, provided it covers every result shown (below).
    state: StateView | None = None
    if RECOMPUTE_SCOPES <= context.scopes:
        state = await current_state(session, context=context)
        if state.stale is not False:
            raise StaleState("a trend is rendered from a State checked against the record")
    lang = language_of(
        language if language is not None else (await audited_profile_read(session, context)).language
    )
    zone = REGION_TZ[context.region]
    decade, sex, labs = await _about_him(session, context)
    facts = await current_facts(
        session, context=context, subject=found.subject, attribute=found.attribute
    )
    points: list[Point] = []
    for fact in facts:
        if fact.confidence_state is not ConfidenceState.CONFIRMED_BY_PERSON:
            continue
        value = _number(fact.value)
        if value is None:
            continue
        on = as_utc(fact.valid_from).astimezone(zone).date()
        lab = None if fact.artifact_id is None else labs.get(fact.artifact_id)
        age = None if decade is None else age_from_decade(decade, on)
        answer = ranges.range_for(found.id, age=age, sex=sex, lab=lab)
        factor = found.factor_for(fact.unit)
        canonical = None if factor is None else value * factor
        band = (
            Band.NOT_COMPARED
            if answer.range is None or canonical is None
            else answer.range.band_of(canonical)
        )
        points.append(
            Point(
                fact_id=fact.id,
                artifact_id=fact.artifact_id,
                event_id=fact.event_id,
                confirmed_by_person_id=fact.confirmed_by_person_id,
                value=value,
                unit=fact.unit,
                on=on,
                lab=lab,
                age=age,
                range=answer.range,
                no_range_because=answer.because,
                in_analyte_unit=canonical,
                band=band,
            )
        )
    points.sort(key=lambda point: (point.on, str(point.fact_id)))

    # Rendered from State: every result shown is one the snapshot was computed from.
    if state is not None:
        held = {
            fact_id
            for dimension in state.dimensions.values()
            if dimension is not None
            for fact_id in dimension.get("fact_ids", [])
        }
        if any(str(point.fact_id) not in held for point in points):
            raise StaleState("a result on the trend is not in the State it is rendered from")

    comparable = [p for p in points if p.in_analyte_unit is not None]
    values = [p.in_analyte_unit for p in comparable if p.in_analyte_unit is not None]
    direction = direction_of(values) if points else Direction.NONE
    recent = comparable[-LAST:]
    since = recent[0].on if len(recent) >= 2 else None
    doctor = await doctor_to_ask(session, context)
    lines = trend_lines(found, points, direction, since, lang, doctor)
    check_lines(lines, lang)
    line = boundary_line(Surface.TREND, lang, doctor=doctor)
    columns: dict[str, Any] = {
        "analyte": found.id,
        "language": lang,
        "fact_ids": [str(point.fact_id) for point in points],
        "direction": direction,
        "lines": lines,
        "rendered_for_person_id": context.person_id,
        "rendered_at": utcnow(),
    }
    scope = scope_for_subject(found.subject)
    if state is not None:
        card = await render_from_state(
            session,
            TrendCard,
            context,
            scope,
            state=state,
            surface=Surface.TREND,
            boundary=line,
            **columns,
        )
    else:
        if not is_boundary_line(Surface.TREND, line):
            raise NoBoundaryLine("a trend carries the boundary line for it")
        try:
            card = await render_from_last_snapshot(
                session,
                TrendCard,
                context,
                scope,
                covering=[point.fact_id for point in points],
                boundary=line,
                **columns,
            )
        except SnapshotBehindTheCard as behind:
            raise StaleState("the last State has not folded in every result shown") from behind
    return Trend(
        analyte=found,
        language=lang,
        points=tuple(points),
        direction=direction,
        direction_since=since,
        lines=tuple(lines),
        boundary=line,
        doctor=doctor,
        birth_decade=decade,
        sex=sex,
        card=card,
    )
