"""How the six dimensions are worked out from what is known.

One rule runs through this whole module, and it is the boundary: **State arranges what is
known, it does not judge it.** No threshold on a reading lives here, nothing here decides
that a number is high or a condition is worsening, and nothing here produces a sentence for
anyone to read. A condition is "watch" because a clinician's letter said so and the fact
carries that word; it is never "watch" because this code compared 138 to something. Trends
belong to reasoning, red flags belong to safety, and the pharmacology belongs to the
licensed drug data. What State does is put what is known in six places, each with a posture
for how the day should be held and the ids it was worked out from, so everything downstream
ranks from one thing.

Every fact folded in keeps its own provenance — the fact id and the artefact or event it was
read from — so a card rendered from a snapshot can still cite the page it came from. Nothing
here is free text: an episode or a visit is named by its id, never by its label.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from app.db import as_utc
from app.keys.models import Key
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Episode,
    EpisodeKind,
    Event,
    EventKind,
    Fact,
)
from app.state.models import Dimension, Posture, worse_of

BEFORE_VISIT_WINDOW = timedelta(days=7)
"""T-7 to T-0: the week a visit is being prepared for."""

VISIT_LENGTH = timedelta(hours=2)
"""How long a visit is assumed to be under way, absent anything saying otherwise."""

AFTER_VISIT_WINDOW = timedelta(days=3)
"""T+0 to T+3: while what was said at the visit is still being written down."""

AFTER_DISCHARGE_WINDOW = timedelta(days=30)
"""T+0 to T+30: the month after a discharge, when most of what goes wrong goes wrong."""

CONTROL = "control"
"""The attribute a clinician's own word about a subject is recorded under.

`subject` is the condition (or the ability, or the arrangement), `value` is one of the
posture words, and the fact names the letter or the visit it was read from. This is the
only route from a fact to a posture, in every dimension: nothing in this module reads a
measurement and decides how anything is doing.
"""

ALLERGY = "allergy"
"""The attribute an allergy is recorded under; `subject` is what he reacts to."""

CONTROL_POSTURE: dict[str, Posture] = {posture.value: posture for posture in Posture}

SUBJECT_DIMENSION: dict[str, Dimension] = {
    "mobility": Dimension.FUNCTIONAL,
    "falls": Dimension.FUNCTIONAL,
    "vision": Dimension.FUNCTIONAL,
    "hearing": Dimension.FUNCTIONAL,
    "dexterity": Dimension.FUNCTIONAL,
    "language": Dimension.COGNITIVE,
    "dialect": Dimension.COGNITIVE,
    "literacy": Dimension.COGNITIVE,
    "memory_support": Dimension.COGNITIVE,
    "format": Dimension.COGNITIVE,
    "goal": Dimension.PREFERENCE,
    "agreed": Dimension.PREFERENCE,
    "declined": Dimension.PREFERENCE,
    "nudges": Dimension.PREFERENCE,
    "who_to_tell": Dimension.PREFERENCE,
    "travel": Dimension.SITUATIONAL,
    "fasting": Dimension.SITUATIONAL,
    "feeling": Dimension.SITUATIONAL,
}
"""Which dimension a subject belongs to. Everything not named here is about his health."""


def dimension_of(subject: str) -> Dimension:
    """Where a fact about this subject is folded in.

    Clinical is the default on purpose: a subject nobody has classified yet is still part of
    the record, and a fact that quietly went nowhere would be worse than one in the wrong box.
    """
    return SUBJECT_DIMENSION.get(subject, Dimension.CLINICAL)


class Phase(StrEnum):
    """Where the profile is in the rhythm of visits and discharges."""

    STEADY = "steady"
    BEFORE_VISIT = "before_visit"
    IN_VISIT = "in_visit"
    AFTER_VISIT = "after_visit"
    AFTER_DISCHARGE = "after_discharge"


PHASE_ORDER: tuple[Phase, ...] = (
    Phase.IN_VISIT,
    Phase.AFTER_DISCHARGE,
    Phase.BEFORE_VISIT,
    Phase.AFTER_VISIT,
)
"""When more than one window is open, the leading phase. Every open window is kept beside it."""

WATCHFUL_EPISODES = frozenset({EpisodeKind.ILLNESS, EpisodeKind.RECOVERY})


@dataclass(frozen=True, slots=True)
class Derived:
    """The six dimensions, each with its posture and its fact ids; the worst posture of the
    six; and when the whole thing stops describing today."""

    dimensions: dict[Dimension, dict[str, Any]]
    posture: Posture
    stale_after: datetime | None


def _moment(value: datetime | None) -> str | None:
    return None if value is None else as_utc(value).isoformat()


def _entry(fact: Fact) -> dict[str, Any]:
    """One fact as State keeps it: its value, how sure we are, and where it came from."""
    return {
        "value": fact.value,
        "unit": fact.unit,
        "confidence": fact.confidence,
        "confidence_state": fact.confidence_state.value,
        "fact_id": str(fact.id),
        "artifact_id": None if fact.artifact_id is None else str(fact.artifact_id),
        "event_id": None if fact.event_id is None else str(fact.event_id),
        "since": _moment(fact.valid_from),
        "until": _moment(fact.valid_to),
    }


class _Dimension:
    """One dimension being built: its facts by subject and attribute, its posture, and why."""

    def __init__(self) -> None:
        self.facts: dict[str, dict[str, dict[str, Any]]] = {}
        self.fact_ids: list[str] = []
        self.posture = Posture.STABLE
        self.because: list[dict[str, Any]] = []

    def raise_to(self, posture: Posture, **why: Any) -> None:
        self.posture = worse_of(self.posture, posture)
        if posture is not Posture.STABLE:
            self.because.append({"posture": posture.value, **why})

    def finished(self, **more: Any) -> dict[str, Any]:
        return {
            "posture": self.posture.value,
            "because": self.because,
            "fact_ids": sorted(self.fact_ids),
            "facts": self.facts,
            **more,
        }


def _fold(facts: Sequence[Fact]) -> dict[Dimension, _Dimension]:
    """Every current fact under its dimension, its subject and its attribute.

    Supersession should leave one current fact per subject and attribute. Where it has not,
    the most recently asserted one is the one folded in — a stated rule rather than whichever
    row the database happened to return first. The safety-critical readings of the same facts
    (conditions and allergies, below) keep every one of them instead of choosing.
    """
    folded = {dimension: _Dimension() for dimension in Dimension}
    newest_last = sorted(
        facts, key=lambda one: (one.subject, one.attribute, as_utc(one.asserted_at))
    )
    for fact in newest_last:
        into = folded[dimension_of(fact.subject)]
        into.facts.setdefault(fact.subject, {})[fact.attribute] = _entry(fact)
        into.fact_ids.append(str(fact.id))
    return folded


def _spine(
    appointments: Sequence[Appointment], now: datetime
) -> tuple[list[Phase], Appointment | None, list[datetime]]:
    """The visit windows open now, the next visit, and the moments those windows change."""
    windows: list[Phase] = []
    boundaries: list[datetime] = []
    upcoming: list[Appointment] = []
    for visit in appointments:
        at = as_utc(visit.scheduled_at)
        if at >= now and visit.status in {AppointmentStatus.PLANNED, AppointmentStatus.CONFIRMED}:
            upcoming.append(visit)
        if now < at - BEFORE_VISIT_WINDOW:
            boundaries.append(at - BEFORE_VISIT_WINDOW)
        elif now < at:
            windows.append(Phase.BEFORE_VISIT)
            boundaries.append(at)
        elif now < at + VISIT_LENGTH:
            windows.append(Phase.IN_VISIT)
            boundaries.append(at + VISIT_LENGTH)
        elif now < at + AFTER_VISIT_WINDOW:
            windows.append(Phase.AFTER_VISIT)
            boundaries.append(at + AFTER_VISIT_WINDOW)
    next_visit = min(upcoming, key=lambda visit: as_utc(visit.scheduled_at), default=None)
    return windows, next_visit, boundaries


def _discharged_at(events: Sequence[Event]) -> datetime | None:
    """The most recent discharge on the record, if there is one."""
    discharges = [
        as_utc(event.occurred_at) for event in events if event.kind is EventKind.DISCHARGE
    ]
    return max(discharges, default=None)


def derive(
    *,
    facts: Sequence[Fact],
    events: Sequence[Event],
    episodes: Sequence[Episode],
    appointments: Sequence[Appointment],
    keys: Sequence[Key],
    now: datetime,
) -> Derived:
    """Work out the six dimensions from what is known at `now`.

    `facts` are the ones holding now, `episodes` the ones open now, `events` the recent ones
    and `appointments` those near enough to matter. `keys` are every key ever cut, so the
    family dimension can say who holds what and who used to.
    """
    folded = _fold(facts)
    boundaries: list[datetime] = [
        as_utc(fact.valid_to) for fact in facts if fact.valid_to is not None
    ]

    # Conditions and allergies are kept as lists of facts, never as a value that the next
    # fact overwrites: two current facts that disagree about one substance is exactly the
    # thing a person needs to see, and the one that happened to be read last is not an answer.
    conditions: dict[str, list[dict[str, Any]]] = {}
    allergies: dict[str, list[dict[str, Any]]] = {}
    not_read: list[dict[str, Any]] = []
    for fact in facts:
        if fact.attribute == CONTROL:
            into = folded[dimension_of(fact.subject)]
            if into is folded[Dimension.CLINICAL]:
                conditions.setdefault(fact.subject, []).append(_entry(fact))
            word = fact.value if isinstance(fact.value, str) else None
            if word in CONTROL_POSTURE:
                raised = CONTROL_POSTURE[str(word)]
            else:
                # The record says something about control that State cannot read. It is
                # kept, it is named, and it is not shown as a settled day: the word came
                # from a clinician and reading it is for a person, not for this code.
                not_read.append({"subject": fact.subject, "fact_id": str(fact.id)})
                raised = Posture.WATCH
            into.raise_to(raised, subject=fact.subject, fact_id=str(fact.id))
        elif fact.attribute == ALLERGY:
            allergies.setdefault(fact.subject, []).append(_entry(fact))

    clinical = folded[Dimension.CLINICAL]
    for episode in episodes:
        raised = (
            Posture.ACT
            if episode.kind is EpisodeKind.ADMISSION
            else Posture.WATCH
            if episode.kind in WATCHFUL_EPISODES
            else Posture.STABLE
        )
        clinical.raise_to(raised, episode_id=str(episode.id), episode_kind=episode.kind.value)

    open_kinds = {episode.kind for episode in episodes}
    windows, next_visit, spine_boundaries = _spine(appointments, now)
    boundaries.extend(spine_boundaries)

    situational = folded[Dimension.SITUATIONAL]
    discharged_at = _discharged_at(events)
    if discharged_at is not None and now < discharged_at + AFTER_DISCHARGE_WINDOW:
        windows.append(Phase.AFTER_DISCHARGE)
        boundaries.append(discharged_at + AFTER_DISCHARGE_WINDOW)
        situational.raise_to(
            Posture.WATCH, phase=Phase.AFTER_DISCHARGE.value, since=_moment(discharged_at)
        )
    phase = next((one for one in PHASE_ORDER if one in windows), Phase.STEADY)

    holders: list[dict[str, Any]] = []
    for key in sorted(keys, key=lambda one: as_utc(one.granted_at)):
        holders.append(
            {
                "person_id": str(key.holder_person_id),
                "role": key.role.value,
                "scopes": sorted(scope.value for scope in key.scopes_held),
                "granted_at": _moment(key.granted_at),
                "expires_at": _moment(key.expires_at),
                "holding_now": key.is_active(now),
            }
        )
        if key.expires_at is not None and now < as_utc(key.expires_at):
            boundaries.append(as_utc(key.expires_at))

    languages = folded[Dimension.COGNITIVE].facts.get("language", {})

    dimensions: dict[Dimension, dict[str, Any]] = {
        Dimension.CLINICAL: clinical.finished(
            conditions=conditions,
            allergies=allergies,
            # Control words the record carries that this code has no mapping for. Named
            # here so a person can read what a clinician wrote; never quietly dropped.
            control_not_read=not_read,
            open_episodes=[
                {"id": str(episode.id), "kind": episode.kind.value, "since": _moment(episode.opened_at)}
                for episode in sorted(episodes, key=lambda one: as_utc(one.opened_at))
            ],
            discharged_at=_moment(discharged_at),
        ),
        Dimension.FUNCTIONAL: folded[Dimension.FUNCTIONAL].finished(),
        Dimension.COGNITIVE: folded[Dimension.COGNITIVE].finished(
            reading_language=languages.get("reading", {}).get("value"),
            spoken_language=languages.get("spoken", {}).get("value"),
        ),
        Dimension.SITUATIONAL: situational.finished(
            phase=phase.value,
            windows=sorted(window.value for window in set(windows)),
            next_visit=None
            if next_visit is None
            else {
                "id": str(next_visit.id),
                "provider_id": str(next_visit.provider_id),
                "at": _moment(next_visit.scheduled_at),
            },
            travelling=EpisodeKind.TRAVEL in open_kinds,
            fasting=EpisodeKind.FASTING in open_kinds,
        ),
        Dimension.PREFERENCE: folded[Dimension.PREFERENCE].finished(),
        Dimension.FAMILY: folded[Dimension.FAMILY].finished(
            holders=holders,
            holding_now=sum(1 for holder in holders if holder["holding_now"]),
        ),
    }

    posture = Posture.STABLE
    for built in folded.values():
        posture = worse_of(posture, built.posture)
    ahead = [moment for moment in boundaries if moment > now]
    return Derived(dimensions=dimensions, posture=posture, stale_after=min(ahead, default=None))
