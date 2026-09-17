"""The first recommendation rules (RE-06, docs/recommendation-engine.md §2.4): what a
`RuleInputs` bundle can be turned into, by rule id.

Every `build` function here is a pure function of `RuleInputs` to `Sequence[Candidate]` — no
session, no key context reach, nothing awaited. `app.delivery.recommend.broker` does all the
reading (under the key, one scope at a time, the way `app.reasoning.patterns.series` does) and
hands each rule the same bundle; a rule only decides what it means, never how to read it. That
split is what makes a rule testable with no database at all, and what keeps a new rule from
inventing its own way to reach the record.

**Scope of this story's four rules**, against the design in §2.4:

- `new_medicine_explainer` and `feeling_after_new_medicine` are built as designed: the
  licensed monograph's watch-out ids (`app.reasoning.feelings.words.WATCH_OUT_WORDS`) already
  tie a feeling-cloud word to a medicine, so both rules read the same fourteen-day window
  (`NEW_MEDICINE_WINDOW`) the feeling cloud itself uses.
- `visit_topic_week` reads "a trend on that visit's provider kind" as a direction over the
  reading series that provider kind is usually seen for (`PROVIDER_KIND_READINGS`) — the
  design's own example ("what your kidney test measures") names a topic the catalogue does
  not carry yet (RE-04's catalogue is conditions and medicines only; tests are "a later
  story's topics", `topics.py` module doc). This rule fires only for the reading kinds that do
  have a condition topic today (`READING_TOPIC`): blood pressure and blood sugar.
- `test_coming` reads "a paper or a visit names a test" as an upcoming visit at a LAB
  provider, tagged by the existing `TopicTagger` (RE-04) against the appointment's own
  `purpose` text — never against Ask or search-bar text, which is exactly the gate
  `topics.py`'s module doc already draws. The design's second half — "REMINDER bring-line if
  the paper names fasting" — needs a fact that says a *specific upcoming test* requires
  fasting; the only fasting fact today (`subject="fasting", attribute="today"`) records
  whether he is fasting *right now*, not what a future test will need, and adding the former
  would be a new column this story does not add (brief: "no new columns, no migration"). This
  rule produces the CLIP only; the REMINDER half is a named gap for the story that adds that
  fact.

Every rule works only from evidence the caller already read under the key — no rule reaches
past what `RuleInputs` was built from — so `Candidate.because` is always something this same
key could re-read.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from app.delivery.recommend.models import Audience, Candidate, Evidence, OutputKind, SafetyClass
from app.delivery.recommend.rank import BEFORE_VISIT_TOPIC, RECENT_EVIDENCE
from app.delivery.recommend.topics import Catalogue, TopicTagger, catalogue
from app.keys.scopes import Scope
from app.memory.models import ProviderKind
from app.reasoning.feelings.words import NEW_MEDICINE_WINDOW, WATCH_OUT_WORDS
from app.reasoning.models import Direction
from app.reasoning.patterns.series import SeriesKind, SeriesSet
from app.reasoning.trends import direction_of
from app.safety.red_flags import Feeling
from app.state.dimensions import BEFORE_VISIT_WINDOW

RULE_NEW_MEDICINE_EXPLAINER = "new_medicine_explainer"
RULE_FEELING_AFTER_NEW_MEDICINE = "feeling_after_new_medicine"
RULE_VISIT_TOPIC_WEEK = "visit_topic_week"
RULE_TEST_COMING = "test_coming"
RULE_DID_YOU_KNOW = "did_you_know"

BASE_WEIGHT: Mapping[str, int] = {
    RULE_NEW_MEDICINE_EXPLAINER: 40,
    RULE_FEELING_AFTER_NEW_MEDICINE: 50,
    RULE_VISIT_TOPIC_WEEK: 30,
    RULE_TEST_COMING: 35,
    RULE_DID_YOU_KNOW: 20,
}
"""A rule's own weight before boosts (§2.4). `feeling_after_new_medicine` sits highest: it is
what fixes the §1.1 finding — a feeling read against a new medicine, with nowhere to raise it,
now reaches a visit question. `did_you_know` sits lowest of the five: it is a curiosity, never
more urgent than a real finding on his own record."""

DID_YOU_KNOW_ROTATION = timedelta(days=14)
"""How long a topic `did_you_know` has already used stays out of the pool (module doc below,
`did_you_know`): read back from the cards it made (`app.delivery.recommend.broker`), no new
column."""

FEELING_WINDOW = timedelta(days=7)
"""How recent a cloud tap must be for `feeling_after_new_medicine` (§2.4 rule table)."""

RECENT_WINDOW = timedelta(days=7)
""""The evidence is from the last 7 days" (§2.4: `RECENT_EVIDENCE`, **+20**)."""

PROVIDER_KIND_READINGS: Mapping[ProviderKind, tuple[SeriesKind, ...]] = {
    ProviderKind.LAB: (SeriesKind.SUGAR,),
    ProviderKind.CLINIC: (SeriesKind.BP_SYSTOLIC, SeriesKind.BP_DIASTOLIC),
    ProviderKind.DOCTOR: (SeriesKind.BP_SYSTOLIC, SeriesKind.BP_DIASTOLIC, SeriesKind.PULSE),
    ProviderKind.HOSPITAL: (
        SeriesKind.BP_SYSTOLIC,
        SeriesKind.BP_DIASTOLIC,
        SeriesKind.SUGAR,
        SeriesKind.PULSE,
    ),
}
"""Which reading series `visit_topic_week` checks for a moved trend, by the kind of provider
the upcoming visit is with (module doc: a stand-in for the design's own analyte-to-visit
mapping, which is not yet a table anywhere in the code this story can read)."""

READING_TOPIC: Mapping[SeriesKind, str] = {
    SeriesKind.SUGAR: "condition.diabetes",
    SeriesKind.BP_SYSTOLIC: "condition.high_blood_pressure",
    SeriesKind.BP_DIASTOLIC: "condition.high_blood_pressure",
}
"""The catalogue topic (RE-04) a moved reading series points to. `PULSE` has no condition
topic in the catalogue today, so a pulse trend never becomes a candidate (module doc)."""

MOVED: frozenset[Direction] = frozenset({Direction.UP, Direction.DOWN})
"""What "a trend... moved" means: arithmetic direction only (ADR 0016), never a threshold."""


@dataclass(frozen=True, slots=True)
class LineInfo:
    """An active medicine line, as a rule needs it: which, since when, and its licensed
    monograph's watch-out ids (`app.drugs.registry.Monograph.watch_out_ids`)."""

    line_id: uuid.UUID
    generic: str
    plain_name_id: str | None
    started_at: datetime
    watch_out_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TapInfo:
    """One feeling-cloud tap, as a rule needs it: the word and when."""

    tap_id: uuid.UUID
    word: Feeling
    at: datetime


@dataclass(frozen=True, slots=True)
class UpcomingVisit:
    """One visit still to come, as a rule needs it: no `Appointment` row, no `Provider` row —
    just the fields a rule reads, so a rule never depends on the memory schema directly."""

    appointment_id: uuid.UUID
    scheduled_at: datetime
    purpose: str
    provider_kind: ProviderKind | None


@dataclass(frozen=True, slots=True)
class ToldCondition:
    """One `condition.<code>` fact that holds (E01, `app.onboarding.settings`): the condition
    he told, and the fact it rests on — `did_you_know`'s own evidence for it."""

    code: str
    fact_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RuleInputs:
    """Everything a rule may read, already fetched under the key by the broker. A rule reads
    only this — never a session, never the key context, never another rule's output."""

    now: datetime
    series: SeriesSet
    lines: tuple[LineInfo, ...]
    taps: tuple[TapInfo, ...]
    upcoming_visits: tuple[UpcomingVisit, ...]
    before_visit: bool
    tagger: TopicTagger
    profile_id: uuid.UUID
    told_conditions: tuple[ToldCondition, ...] = ()
    recent_did_you_know_topics: frozenset[str] = frozenset()
    """Topics `did_you_know` has already used in the last `DID_YOU_KNOW_ROTATION` days (broker,
    read back from the cards it made — no new column)."""
    declined_topics: frozenset[str] = frozenset()
    """Topics he has said "not for me" to, still inside their thirty days
    (`app.delivery.feed.engagement._decline_topic_for_30_days`) — read directly by the broker
    under the same fact shape (subject `declined_topic`), the way `SIGNALS_SUBJECT` already
    is, so this module need not import `app.delivery.feed` (the cycle `compose.py`'s own
    module doc already documents for the reverse direction)."""


@lru_cache(maxsize=1)
def _catalogue() -> Catalogue:
    return catalogue()


def _known_topic(code: str) -> bool:
    return code in _catalogue()


def new_medicine_explainer(inputs: RuleInputs) -> Sequence[Candidate]:
    """A line started in the last 14 days: READ and CLIP on that medicine, boosted ahead of
    older topics when the start is inside the last 7 days (§2.4 rule table)."""
    out: list[Candidate] = []
    for line in inputs.lines:
        age = inputs.now - line.started_at
        if line.plain_name_id is None or age > NEW_MEDICINE_WINDOW:
            continue
        topic = f"medicine.{line.plain_name_id}"
        if not _known_topic(topic):
            continue
        because = (Evidence(kind="line", id=line.line_id, scope=Scope.MEDICINES),)
        boosts = (RECENT_EVIDENCE,) if age <= RECENT_WINDOW else ()
        for output in (OutputKind.READ, OutputKind.CLIP):
            out.append(
                Candidate(
                    rule_id=RULE_NEW_MEDICINE_EXPLAINER,
                    output=output,
                    topic=topic,
                    because=because,
                    safety=SafetyClass.EXTERNAL,
                    audience=frozenset({Audience.PATIENT}),
                    base=BASE_WEIGHT[RULE_NEW_MEDICINE_EXPLAINER],
                    boosts=boosts,
                )
            )
    return out


def feeling_after_new_medicine(inputs: RuleInputs) -> Sequence[Candidate]:
    """A cloud tap in the last 7 days whose word a medicine started in the last 14 days lists
    as a watch-out: READ on that feeling with that medicine, and the same finding as a
    VISIT_QUESTION (§1.1, §2.4)."""
    out: list[Candidate] = []
    for tap in inputs.taps:
        if inputs.now - tap.at > FEELING_WINDOW:
            continue
        for line in inputs.lines:
            age = inputs.now - line.started_at
            if line.plain_name_id is None or age > NEW_MEDICINE_WINDOW:
                continue
            matched = any(WATCH_OUT_WORDS.get(rule) is tap.word for rule in line.watch_out_ids)
            if not matched:
                continue
            topic = f"medicine.{line.plain_name_id}"
            if not _known_topic(topic):
                continue
            because = (
                Evidence(kind="line", id=line.line_id, scope=Scope.MEDICINES),
                Evidence(kind="tap", id=tap.tap_id, scope=Scope.RECORDS),
            )
            boosts = (RECENT_EVIDENCE,) if inputs.now - tap.at <= RECENT_WINDOW else ()
            out.append(
                Candidate(
                    rule_id=RULE_FEELING_AFTER_NEW_MEDICINE,
                    output=OutputKind.READ,
                    topic=topic,
                    because=because,
                    safety=SafetyClass.EXTERNAL,
                    audience=frozenset({Audience.PATIENT}),
                    base=BASE_WEIGHT[RULE_FEELING_AFTER_NEW_MEDICINE],
                    boosts=boosts,
                )
            )
            out.append(
                Candidate(
                    rule_id=RULE_FEELING_AFTER_NEW_MEDICINE,
                    output=OutputKind.VISIT_QUESTION,
                    topic=topic,
                    because=because,
                    safety=SafetyClass.RECORD_BACK,
                    audience=frozenset({Audience.PATIENT, Audience.MEMO}),
                    base=BASE_WEIGHT[RULE_FEELING_AFTER_NEW_MEDICINE],
                    boosts=boosts,
                )
            )
    return out


def _dedupe(evidence: Sequence[Evidence]) -> tuple[Evidence, ...]:
    seen: dict[tuple[str, uuid.UUID], Evidence] = {}
    for item in evidence:
        seen.setdefault((item.kind, item.id), item)
    return tuple(seen.values())


def visit_topic_week(inputs: RuleInputs) -> Sequence[Candidate]:
    """`Phase.BEFORE_VISIT`, and a trend on that visit's provider kind moved since the reading
    series began (module doc): READ and CLIP on that topic (§2.4)."""
    if not inputs.before_visit:
        return []
    out: list[Candidate] = []
    for visit in inputs.upcoming_visits:
        until = visit.scheduled_at - inputs.now
        if until < timedelta(0) or until > BEFORE_VISIT_WINDOW or visit.provider_kind is None:
            continue
        for kind in PROVIDER_KIND_READINGS.get(visit.provider_kind, ()):
            series = inputs.series.get(kind)
            topic = READING_TOPIC.get(kind)
            if series is None or topic is None or not _known_topic(topic):
                continue
            values = [point.value for point in series.points if isinstance(point.value, float)]
            if direction_of(values) not in MOVED:
                continue
            last_points = series.points[-3:]
            because = _dedupe(
                [Evidence(kind=e.kind, id=e.id, scope=e.scope) for p in last_points for e in p.ids]
            )
            if not because:
                continue
            recent = any(inputs.now - p.at <= RECENT_WINDOW for p in last_points)
            boosts = (BEFORE_VISIT_TOPIC, *((RECENT_EVIDENCE,) if recent else ()))
            for output in (OutputKind.READ, OutputKind.CLIP):
                out.append(
                    Candidate(
                        rule_id=RULE_VISIT_TOPIC_WEEK,
                        output=output,
                        topic=topic,
                        because=because,
                        safety=SafetyClass.EXTERNAL,
                        audience=frozenset({Audience.PATIENT}),
                        base=BASE_WEIGHT[RULE_VISIT_TOPIC_WEEK],
                        boosts=boosts,
                    )
                )
    return out


def test_coming(inputs: RuleInputs) -> Sequence[Candidate]:
    """A visit at a lab in the next 7 days: CLIP on what happens at that test (module doc:
    the REMINDER-if-fasting half is a named gap, no fact for it exists yet)."""
    out: list[Candidate] = []
    for visit in inputs.upcoming_visits:
        until = visit.scheduled_at - inputs.now
        if until < timedelta(0) or until > BEFORE_VISIT_WINDOW:
            continue
        if visit.provider_kind is not ProviderKind.LAB:
            continue
        topics = inputs.tagger.tag(visit.purpose)
        if not topics:
            continue
        topic = topics[0]
        because = (Evidence(kind="appointment", id=visit.appointment_id, scope=Scope.VISITS),)
        out.append(
            Candidate(
                rule_id=RULE_TEST_COMING,
                output=OutputKind.CLIP,
                topic=topic,
                because=because,
                safety=SafetyClass.EXTERNAL,
                audience=frozenset({Audience.PATIENT}),
                base=BASE_WEIGHT[RULE_TEST_COMING],
                boosts=(RECENT_EVIDENCE,),
            )
        )
    return out


def _did_you_know_pool(inputs: RuleInputs) -> dict[str, tuple[Evidence, ...]]:
    """Every topic today's own record makes eligible for `did_you_know`, by topic code: a
    condition he told, a medicine he takes, or this week's visit topic (module doc below).
    `dict.setdefault` only decides which evidence a topic already found from two sources keeps
    — never which topic wins the day, which `_pick_topic` alone decides, from the sorted keys,
    so build order here never changes the pick.

    No season topic is in this pool: `topics.py`'s catalogue carries conditions, medicines and
    the sensitive codes only (module doc, `app.delivery.recommend.topics`) — no season family
    — so a season "did you know" is a named gap here, the same shape `test_coming`'s own
    fasting-REMINDER gap is documented above."""
    pool: dict[str, tuple[Evidence, ...]] = {}
    for told in inputs.told_conditions:
        topic = f"condition.{told.code}"
        if _known_topic(topic):
            pool.setdefault(topic, (Evidence(kind="fact", id=told.fact_id, scope=Scope.RECORDS),))
    for line in inputs.lines:
        if line.plain_name_id is None:
            continue
        topic = f"medicine.{line.plain_name_id}"
        if _known_topic(topic):
            pool.setdefault(
                topic, (Evidence(kind="line", id=line.line_id, scope=Scope.MEDICINES),)
            )
    for visit in inputs.upcoming_visits:
        until = visit.scheduled_at - inputs.now
        if until < timedelta(0) or until > BEFORE_VISIT_WINDOW:
            continue
        for topic in inputs.tagger.tag(visit.purpose):
            if _known_topic(topic):
                pool.setdefault(
                    topic,
                    (Evidence(kind="appointment", id=visit.appointment_id, scope=Scope.VISITS),),
                )
    return pool


def _pick_topic(topics: Iterable[str], *, profile_id: uuid.UUID, day: str) -> str:
    """The one topic of the day: sorted so the pool's build order never matters, then a
    sha256 of `profile_id` and `day` alone decides the index — deterministic for the same
    profile on the same day (a refresh never changes it), and free to move the next day or for
    another profile, with no state of its own (the "hard-won rule" on tie-breaks, CLAUDE.md:
    never an insertion order, always an explicit, reproducible one)."""
    ordered = sorted(topics)
    digest = hashlib.sha256(f"{profile_id}:{day}".encode()).hexdigest()
    return ordered[int(digest, 16) % len(ordered)]


def did_you_know(inputs: RuleInputs) -> Sequence[Candidate]:
    """One small, true fact a day, on one topic that rests on his own record (module doc,
    `_did_you_know_pool`): a condition he told, a medicine he takes, or this week's visit
    topic — never a topic he has said "not for me" to in the last thirty days
    (`inputs.declined_topics`), and never one `did_you_know` itself has already used in the
    last `DID_YOU_KNOW_ROTATION` days (`inputs.recent_did_you_know_topics`). At most one
    candidate: the day's pick, or none at all when nothing on his record is eligible today —
    never a repeat manufactured to fill the slot."""
    pool = _did_you_know_pool(inputs)
    eligible = {
        topic: evidence
        for topic, evidence in pool.items()
        if topic not in inputs.recent_did_you_know_topics and topic not in inputs.declined_topics
    }
    if not eligible:
        return []
    topic = _pick_topic(eligible, profile_id=inputs.profile_id, day=inputs.now.date().isoformat())
    return [
        Candidate(
            rule_id=RULE_DID_YOU_KNOW,
            output=OutputKind.READ,
            topic=topic,
            because=eligible[topic],
            safety=SafetyClass.EXTERNAL,
            audience=frozenset({Audience.PATIENT}),
            base=BASE_WEIGHT[RULE_DID_YOU_KNOW],
        )
    ]


@dataclass(frozen=True, slots=True)
class RecommendationRule:
    """One entry in the catalogue: its id, the signal family it reads from (`None` when it
    reads nothing a switch covers), and the pure function that builds its candidates.

    `signal_family` is a plain string, not `app.reasoning.signals.SignalFamily` — that module
    is RE-05 (PR #243), not merged to `main` as this story starts. The broker reads the same
    `signals.<family>` fact shape that story defines (`subject="signals", attribute=<family>`)
    directly, so a rule can be marked as reading a switchable family without this module
    depending on a story that has not landed (docs/recommendation-engine.md §3.6, ADR 0016
    decision 3). None of this story's four rules reads a family RE-05 defines yet — food,
    sleep, steps, water and search-topic use are all lifestyle-log series RE-10 adds — but the
    mechanism is real and exercised by `tests/test_recommend_broker.py`, not a stub only a
    test can see.
    """

    rule_id: str
    signal_family: str | None
    build: Callable[[RuleInputs], Sequence[Candidate]]


CATALOGUE: tuple[RecommendationRule, ...] = (
    RecommendationRule(RULE_NEW_MEDICINE_EXPLAINER, None, new_medicine_explainer),
    RecommendationRule(RULE_FEELING_AFTER_NEW_MEDICINE, None, feeling_after_new_medicine),
    RecommendationRule(RULE_VISIT_TOPIC_WEEK, None, visit_topic_week),
    RecommendationRule(RULE_TEST_COMING, None, test_coming),
    # "What Nura uses" (module doc): off by the same `subject="signals", attribute="did_you_
    # know"` fact shape every other family switch reads, on by default like the rest.
    RecommendationRule(RULE_DID_YOU_KNOW, "did_you_know", did_you_know),
)
