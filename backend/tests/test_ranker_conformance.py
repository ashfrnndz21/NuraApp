"""The `Ranker` port's conformance suite (RE-06): what ANY adapter must answer, in the pattern
of `test_topic_tagger_conformance.py` (RE-04) and `test_drug_registry_conformance.py`.

`app.delivery.recommend.rank.Ranker` is a port; `RuleRanker` is the default adapter and
`FixtureRanker` is the one a test that wants a slate's order to hold whatever the real
weights do later uses. `assert_ranker_conforms` is the suite either must pass: it names the
shape and the invariants a caller is entitled to rely on — total order, determinism, an
explicit tie-break, nothing lost or duplicated — so a later adapter drops in with no change
to a caller.

The suite takes its sample from the caller, exactly as the tagger suite does: `higher` must
outrank `lower` by whatever means this adapter uses, and `tied` is a pair the adapter is
known to score identically, so the suite can check the tie-break without knowing the scoring
formula underneath it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.delivery.recommend.models import Audience, Candidate, Evidence, OutputKind, SafetyClass
from app.delivery.recommend.rank import FixtureRanker, Ranker, RuleRanker, TopicEngagement
from app.keys.scopes import Scope


def _evidence(scope: Scope = Scope.RECORDS, kind: str = "fact") -> Evidence:
    return Evidence(kind=kind, id=uuid.uuid4(), scope=scope)


def _candidate(
    rule_id: str,
    *,
    topic: str = "condition.diabetes",
    output: OutputKind = OutputKind.READ,
    base: int = 0,
    boosts: tuple[str, ...] = (),
    evidence: Evidence | None = None,
) -> Candidate:
    return Candidate(
        rule_id=rule_id,
        output=output,
        topic=topic,
        because=(evidence or _evidence(),),
        safety=SafetyClass.RECORD_BACK,
        audience=frozenset({Audience.PATIENT}),
        base=base,
        boosts=boosts,
    )


def assert_ranker_conforms(
    ranker: Ranker,
    *,
    higher: Candidate,
    lower: Candidate,
    tied: tuple[Candidate, Candidate],
) -> None:
    """The contract every `Ranker` adapter must meet.

    `higher` is known to outrank `lower` under this adapter's own scoring. `tied` is a pair
    this adapter scores identically, so the suite can assert its tie-break is a real, fixed
    order — not "whatever order the input happened to be in".
    """
    # Nothing to rank ranks to nothing.
    assert ranker.rank([], state=None, engagement={}) == []

    # A higher-scoring candidate always sorts first, whichever order it is given in.
    assert ranker.rank([lower, higher], state=None, engagement={}) == [higher, lower]
    assert ranker.rank([higher, lower], state=None, engagement={}) == [higher, lower]

    # Nothing is dropped, nothing is duplicated: the same set comes back, ranked.
    ranked = ranker.rank([lower, higher], state=None, engagement={})
    assert {id(c) for c in ranked} == {id(lower), id(higher)}
    assert len(ranked) == 2

    # Two candidates this adapter scores the same still land in one order, not "either" —
    # and it is the same order whichever order they are given in (the tie-break, not luck).
    first, second = tied
    forward = ranker.rank([first, second], state=None, engagement={})
    backward = ranker.rank([second, first], state=None, engagement={})
    assert forward == backward
    assert set(forward) == {first, second}

    # Calling twice on the same input answers the same way: nothing here reads a clock, a
    # random source, or anything else that could make "the same slate" rank differently on a
    # second read of it.
    assert ranker.rank([lower, higher], state=None, engagement={}) == ranked


def test_the_rule_ranker_conforms() -> None:
    higher = _candidate("rule_a", base=50)
    lower = _candidate("rule_b", base=10)
    # A tie the rule ranker's own formula produces: same rule, same topic, same output, same
    # boosts — score is identical, so only the tie-break (evidence ids) can separate them.
    tied_evidence_low = _evidence()
    tied_evidence_high = _evidence()
    tied = (
        _candidate("rule_c", base=30, evidence=tied_evidence_low),
        _candidate("rule_c", base=30, evidence=tied_evidence_high),
    )
    assert_ranker_conforms(RuleRanker(), higher=higher, lower=lower, tied=tied)


def test_the_rule_ranker_applies_its_boost_table() -> None:
    base_only = _candidate("rule_a", base=40)
    recent = _candidate("rule_b", base=30, boosts=("recent_evidence",))  # +20 = 50
    ranked = RuleRanker().rank([base_only, recent], state=None, engagement={})
    assert ranked == [recent, base_only]


def test_the_fixture_ranker_conforms() -> None:
    scores = {"rule_a": 5, "rule_b": 1, "rule_c": 3}
    higher = _candidate("rule_a")
    lower = _candidate("rule_b")
    tied = (_candidate("rule_c", evidence=_evidence()), _candidate("rule_c", evidence=_evidence()))
    assert_ranker_conforms(FixtureRanker(scores), higher=higher, lower=lower, tied=tied)


def test_an_unscored_rule_in_the_fixture_ranker_sorts_last() -> None:
    known = _candidate("rule_a")
    unknown = _candidate("rule_z")
    ranked = FixtureRanker({"rule_a": 1}).rank([unknown, known], state=None, engagement={})
    assert ranked == [known, unknown]


def test_engagement_moves_a_candidate_without_changing_the_boost_table() -> None:
    plain = _candidate("rule_a", base=20, topic="condition.diabetes")
    opened = _candidate("rule_b", base=20, topic="condition.high_blood_pressure")
    declined = _candidate("rule_c", base=20, topic="condition.checkup")
    engagement = {
        "condition.high_blood_pressure": TopicEngagement(opened_or_played_30d=2),
        "condition.checkup": TopicEngagement(declines_30d=1),
    }
    ranked = RuleRanker().rank([plain, declined, opened], state=None, engagement=engagement)
    assert ranked == [opened, plain, declined]


def _candidates_from(rankers: Sequence[Ranker]) -> None:
    """Both adapters are, at minimum, the same kind of thing: neither raises on an empty
    slate, and both return a `list`, not any other sequence a caller might not expect."""
    for ranker in rankers:
        result = ranker.rank([], state=None, engagement={})
        assert isinstance(result, list)


def test_every_adapter_answers_the_same_shape_on_nothing() -> None:
    _candidates_from([RuleRanker(), FixtureRanker({})])
