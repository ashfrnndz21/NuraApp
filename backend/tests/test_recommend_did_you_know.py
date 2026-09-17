"""The `did_you_know` rule (docs/recommendation-engine.md §RE-09's own "curiosity nudge" idea,
built here as a rule of its own, `app.delivery.recommend.rules`): one small, true fact a day,
on one topic that rests on his own record, never repeating inside its rotation, never a topic
he has said "not for me" to, and never guessed when nothing on his record is eligible.

Pure unit tests, against hand-built `RuleInputs` — no session, no key context reach, the same
shape every other rule in `rules.py` is tested to (module doc, `rules.py`). The broker's own
wiring (what it reads, the "What Nura uses" switch, the rotation read back from the cards the
rule made) is `test_recommend_broker.py`'s and `test_feed.py`'s to exercise end to end.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.delivery.recommend.models import Candidate, OutputKind
from app.delivery.recommend.rules import (
    RULE_DID_YOU_KNOW,
    LineInfo,
    RuleInputs,
    ToldCondition,
    UpcomingVisit,
    did_you_know,
)
from app.delivery.recommend.topics import KeywordTagger
from app.keys.scopes import Scope
from app.memory.models import ProviderKind
from app.reasoning.patterns.series import SeriesSet

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


class _Ctx:
    """A stand-in `KeyContext`: `Candidate.readable_by`/`Evidence.readable_by` need only
    `.allows(scope)`, never a real key or a session."""

    def __init__(self, scopes: frozenset[Scope]) -> None:
        self._scopes = scopes
        self.person_id = uuid.uuid4()

    def allows(self, scope: Scope) -> bool:
        return scope in self._scopes


def _amlodipine(*, started: timedelta = timedelta(days=30)) -> LineInfo:
    return LineInfo(
        line_id=uuid.uuid4(),
        generic="amlodipine",
        plain_name_id="blood_pressure_tablet",
        started_at=NOW - started,
        watch_out_ids=(),
    )


def _diabetes(fact_id: uuid.UUID | None = None) -> ToldCondition:
    return ToldCondition(code="diabetes", fact_id=fact_id or uuid.uuid4())


def _inputs(
    *,
    now: datetime = NOW,
    lines: tuple[LineInfo, ...] = (),
    told_conditions: tuple[ToldCondition, ...] = (),
    upcoming_visits: tuple[UpcomingVisit, ...] = (),
    recent: frozenset[str] = frozenset(),
    declined: frozenset[str] = frozenset(),
    profile_id: uuid.UUID | None = None,
) -> RuleInputs:
    return RuleInputs(
        now=now,
        series=SeriesSet(),
        lines=lines,
        taps=(),
        upcoming_visits=upcoming_visits,
        before_visit=False,
        tagger=KeywordTagger(),
        profile_id=profile_id or uuid.uuid4(),
        told_conditions=told_conditions,
        recent_did_you_know_topics=recent,
        declined_topics=declined,
    )


POOL_INPUTS = dict(lines=(_amlodipine(),), told_conditions=(_diabetes(),))
POOL_TOPICS = {"medicine.blood_pressure_tablet", "condition.diabetes"}


def test_no_eligible_topic_means_no_candidate_not_a_repeat() -> None:
    """Nothing on his record today: `did_you_know` says nothing, rather than manufacture a
    repeat to fill the slot (module doc)."""
    assert did_you_know(_inputs()) == []


def test_the_candidate_carries_its_own_evidence_and_is_readable_by_the_scope_it_rests_on() -> None:
    result = did_you_know(_inputs(**POOL_INPUTS))
    assert len(result) == 1
    candidate = result[0]
    assert isinstance(candidate, Candidate)
    assert candidate.rule_id == RULE_DID_YOU_KNOW
    assert candidate.output is OutputKind.READ
    assert candidate.because, "no evidence, no recommendation (RE-01)"
    scope = candidate.because[0].scope
    assert candidate.readable_by(_Ctx(frozenset({scope})))
    assert not candidate.readable_by(_Ctx(frozenset()))


def test_the_pick_is_deterministic_for_the_same_profile_on_the_same_day() -> None:
    profile_id = uuid.uuid4()
    first = did_you_know(_inputs(**POOL_INPUTS, profile_id=profile_id))
    again = did_you_know(_inputs(**POOL_INPUTS, profile_id=profile_id))
    assert first and again
    assert first[0].topic == again[0].topic

    # A refresh later the same day (a later moment, same date) never changes the pick.
    later = _inputs(
        **POOL_INPUTS, profile_id=profile_id, now=NOW + timedelta(hours=6, minutes=30)
    )
    assert did_you_know(later)[0].topic == first[0].topic

    # A different profile, same day, is free to land on a different topic — the pick is
    # never a plain function of the day alone.
    other_profile = did_you_know(_inputs(**POOL_INPUTS, profile_id=uuid.uuid4()))
    assert other_profile[0].topic in POOL_TOPICS


def test_the_pick_may_move_the_next_day() -> None:
    profile_id = uuid.uuid4()
    picks = {
        did_you_know(_inputs(**POOL_INPUTS, profile_id=profile_id, now=NOW + timedelta(days=day)))[
            0
        ].topic
        for day in range(10)
    }
    # Both eligible topics are still valid picks on any day, and across ten days a
    # deterministic-per-day hash lands on both at least once — it is not pinned to one.
    assert picks <= POOL_TOPICS
    assert len(picks) > 1


def test_a_topic_used_in_the_last_14_days_is_not_picked_again() -> None:
    result = did_you_know(_inputs(**POOL_INPUTS, recent=frozenset({"medicine.blood_pressure_tablet"})))
    assert result and result[0].topic == "condition.diabetes"


def test_when_every_eligible_topic_is_inside_its_14_day_rotation_no_candidate_is_made() -> None:
    result = did_you_know(_inputs(**POOL_INPUTS, recent=frozenset(POOL_TOPICS)))
    assert result == []


def test_a_topic_declined_in_the_last_30_days_is_not_picked() -> None:
    result = did_you_know(
        _inputs(**POOL_INPUTS, declined=frozenset({"medicine.blood_pressure_tablet"}))
    )
    assert result and result[0].topic == "condition.diabetes"


def test_when_every_eligible_topic_is_declined_no_candidate_is_made() -> None:
    result = did_you_know(_inputs(**POOL_INPUTS, declined=frozenset(POOL_TOPICS)))
    assert result == []


def test_a_medicine_with_no_licensed_plain_name_is_never_a_topic() -> None:
    """A line the licensed registry could not identify (`plain_name_id is None`) names no
    topic — the same guard `new_medicine_explainer` uses — never guessed from the generic."""
    unknown = replace(_amlodipine(), plain_name_id=None)
    result = did_you_know(_inputs(lines=(unknown,)))
    assert result == []


def test_this_weeks_visit_topic_is_eligible_when_it_tags_a_catalogue_topic() -> None:
    visit = UpcomingVisit(
        appointment_id=uuid.uuid4(),
        scheduled_at=NOW + timedelta(days=2),
        purpose="diabetes blood test",
        provider_kind=ProviderKind.LAB,
    )
    result = did_you_know(_inputs(upcoming_visits=(visit,)))
    assert result and result[0].topic == "condition.diabetes"
    assert result[0].because[0].kind == "appointment"
    assert result[0].because[0].id == visit.appointment_id
    assert result[0].because[0].scope is Scope.VISITS


def test_a_visit_outside_the_before_visit_window_is_not_a_topic_source() -> None:
    far = UpcomingVisit(
        appointment_id=uuid.uuid4(),
        scheduled_at=NOW + timedelta(days=90),
        purpose="diabetes blood test",
        provider_kind=ProviderKind.LAB,
    )
    assert did_you_know(_inputs(upcoming_visits=(far,))) == []
