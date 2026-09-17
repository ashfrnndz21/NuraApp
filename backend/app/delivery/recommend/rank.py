"""The `Ranker` port (RE-06, docs/recommendation-engine.md §2.4): one ordered list of
`Candidate` per key per day, from a fixed table of weights. Rule-based now (ADR 0016
decision 6); a model never chooses which candidate outranks another.

`RuleRanker` is the default adapter: `base` (the rule's own weight, set when the rule built
the candidate) plus a boost per code the rule attached to `Candidate.boosts` — never derived
by the ranker itself from anything the candidate does not already carry, so a candidate
built by a fixture rule in a test ranks exactly as one the real catalogue would build with
the same `base` and `boosts`.

**Deterministic ordering, explicit tie-break** (the "hard-won rule": sixteen queries were
once found picking "the newest" by timestamp alone). Two candidates that score the same are
ordered by `rule_id`, then `topic`, then the sorted string form of their evidence ids — never
by insertion order, which a `dict` or a set comprehension upstream is not bound to keep.

`engagement` is part of the port's signature because the design names it
(`rank(candidates, *, state, engagement)`), but no story before RE-07 gives per-topic
engagement counts a place to live (`FeedItem` does not yet carry a topic to count against).
`RuleRanker` reads it defensively — an empty mapping today answers "no history yet" — so it
drops in unchanged the day RE-07 starts passing real counts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.delivery.recommend.models import Candidate
from app.fixtures import fixture
from app.state.service import StateView

RECENT_EVIDENCE = "recent_evidence"
"""A rule attaches this when the evidence it found is from the last 7 days (§2.4: **+20**)."""

BEFORE_VISIT_TOPIC = "before_visit_topic"
"""A rule attaches this when, in `Phase.BEFORE_VISIT`, the candidate's topic belongs to the
visit being prepared for (§2.4: **+15**)."""

OPENED_RECENTLY = "opened_recently"
"""The topic was opened or played in the last 30 days (§2.4: **+10**, once)."""

DECLINED_RECENTLY = "declined_recently"
""""Not for me" on this topic in the last 30 days (§2.4: **−15**, once per occurrence this
adapter is told about — `TopicEngagement.declines_30d`)."""

RECENT_EVIDENCE_BOOST = 20
BEFORE_VISIT_TOPIC_BOOST = 15
OPENED_RECENTLY_BOOST = 10
DECLINED_PENALTY = -15


@dataclass(frozen=True, slots=True)
class TopicEngagement:
    """What is known about how this key's household has treated one topic, in the last 30
    days. `RuleRanker` never counts an engagement itself — RE-07 is the story that ties an
    `Engagement` row to the topic it was on; this is the shape that answer will take."""

    opened_or_played_30d: int = 0
    declines_30d: int = 0


def _tie_break(candidate: Candidate) -> tuple[str, str, str, tuple[str, ...]]:
    """`rule_id`, then `topic`, then `output` — two candidates the same rule builds for the
    same topic (a READ and a CLIP of the same finding) still need a total order between them —
    then the sorted string form of the evidence ids, so two candidates equal on every field
    above (which nothing in this story's rules ever builds, but nothing here assumes that)
    still land in the same order every time, never the incidental order `list.build()`
    happened to append them in."""
    ids = tuple(sorted(f"{item.kind}:{item.id}" for item in candidate.because))
    return (candidate.rule_id, candidate.topic, candidate.output.value, ids)


class Ranker(Protocol):
    """Any adapter that orders a slate's candidates must answer this. `RuleRanker` is the
    default; `FixtureRanker` is what tests use, in the pattern of `FixtureTagger`
    (`app.delivery.recommend.topics`) and `FixtureRegistry` (`app.drugs.fixture`)."""

    def rank(
        self,
        candidates: Sequence[Candidate],
        *,
        state: StateView | None,
        engagement: Mapping[str, TopicEngagement],
    ) -> list[Candidate]:
        """`candidates`, ordered best first. Never widens, never drops one silently — a
        candidate a caller should not see is the broker's job to have already dropped
        (`Candidate.readable_by`), not this port's."""
        ...


def _score(candidate: Candidate, engagement: Mapping[str, TopicEngagement]) -> int:
    score = candidate.base
    if RECENT_EVIDENCE in candidate.boosts:
        score += RECENT_EVIDENCE_BOOST
    if BEFORE_VISIT_TOPIC in candidate.boosts:
        score += BEFORE_VISIT_TOPIC_BOOST
    topic_engagement = engagement.get(candidate.topic)
    if topic_engagement is not None:
        if topic_engagement.opened_or_played_30d > 0:
            score += OPENED_RECENTLY_BOOST
        score += DECLINED_PENALTY * topic_engagement.declines_30d
    return score


class RuleRanker:
    """The default `Ranker`: the fixed table (§2.4), arithmetic only, recomputed on every
    read — "learning from dismissals is counting his own taps at read time", never a model
    trained on engagement (CLAUDE.md: nothing trains on user data)."""

    def rank(
        self,
        candidates: Sequence[Candidate],
        *,
        state: StateView | None = None,
        engagement: Mapping[str, TopicEngagement] = {},
    ) -> list[Candidate]:
        return sorted(
            candidates,
            key=lambda candidate: (-_score(candidate, engagement), *_tie_break(candidate)),
        )


@fixture
class FixtureRanker:
    """A `Ranker` whose scores come from a fixed table keyed by `rule_id`, for tests that
    want a slate's order to hold whatever the real `RuleRanker`'s weights do later — the same
    reason `FixtureTagger` and `FixtureRegistry` answer from a table instead of a formula."""

    def __init__(self, scores: Mapping[str, int]) -> None:
        self._scores = dict(scores)

    def rank(
        self,
        candidates: Sequence[Candidate],
        *,
        state: StateView | None = None,
        engagement: Mapping[str, TopicEngagement] = {},
    ) -> list[Candidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                -self._scores.get(candidate.rule_id, 0),
                *_tie_break(candidate),
            ),
        )
