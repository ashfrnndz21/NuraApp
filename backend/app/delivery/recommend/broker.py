"""The broker (RE-06, docs/recommendation-engine.md §2.4): the one place State, series and
the record turn into `Candidate`s, and the one `Ranker` call that puts them in order.

`slate()` writes no words and no rows (§2.1 rule 1, the same promise `search/retrieve.py`
keeps): it reads under the caller's key, one scope at a time, builds candidates through the
rule catalogue (`app.delivery.recommend.rules`), drops every one this key may not see
(`Candidate.readable_by`), and returns them ranked and grouped by `OutputKind`. Nothing here
decides what a card says; that is the output that consumes the slate later (RE-07 onward).

**What a scope this key does not hold does to a slate.** Every reader below is gated the same
way `app.reasoning.patterns.series` gates its own: `context.allows(scope)` first, and the
scope named in `Slate.withheld` when it does not, never a silent empty read standing in for
"nothing happened". A candidate built from a scope this key does hold is still checked again
by `Candidate.readable_by` before it is returned — belt and braces, the same shape
`readable_by` documents for `Pattern` and `FeelingNote` (ADR 0004 decision 10) — so a rule bug
that built a candidate from the wrong scope can never reach a key that should not see it.

**What "What Nura uses" (RE-05, PR #243, not merged) does to a slate.** A rule that names a
`signal_family` (`app.delivery.recommend.rules.RecommendationRule.signal_family`) is skipped
before it is ever called when that family's switch (`subject="signals", attribute=<family>`,
the exact fact shape RE-05 defines) is off. Reading that fact does not need RE-05's module —
it is one more fact under RECORDS, read with `current_facts` the way every other fact reader
in this codebase already does.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import as_utc, utcnow
from app.delivery.feed.models import FeedItem
from app.delivery.recommend.models import Candidate, OutputKind
from app.delivery.recommend.rank import Ranker, RuleRanker, TopicEngagement
from app.delivery.recommend.rules import (
    CATALOGUE,
    DID_YOU_KNOW_ROTATION,
    RULE_DID_YOU_KNOW,
    LineInfo,
    RecommendationRule,
    RuleInputs,
    TapInfo,
    ToldCondition,
    UpcomingVisit,
)
from app.delivery.recommend.topics import KeywordTagger, TopicTagger
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.models import LineStatus, MedicationLine
from app.memory.models import Provider
from app.memory.semantic import current_facts
from app.memory.spine import upcoming_appointments
from app.reasoning.feelings.models import FeelingTap
from app.reasoning.patterns.series import read_series
from app.state.dimensions import Phase
from app.state.models import Dimension
from app.state.service import StateView

SIGNALS_SUBJECT = "signals"
"""`subject` every "What Nura uses" switch is a Fact under (RE-05 §3.6, ADR 0016 decision 3).
Read here by the fact shape alone; `app.reasoning.signals` is not on `main` (module doc)."""

FEELING_WINDOW_DAYS = 7
"""How far back `feeling_after_new_medicine` reads the feeling cloud (§2.4 rule table)."""

CONDITION_SUBJECT = "condition"
"""`subject` a told condition (E01, `app.onboarding.settings`) is a Fact under; its `attribute`
is the condition's own code."""

DECLINED_TOPIC_SUBJECT = "declined_topic"
"""The exact fact shape `app.delivery.feed.engagement._decline_topic_for_30_days` writes
(`subject="declined_topic"`, `attribute=<topic>`), read here directly by the fact shape alone,
the way `SIGNALS_SUBJECT` already is above — `app.delivery.feed` reaches back into this module
(`compose._broker_wanted`), so this module does not import it in the other direction."""


class Slate:
    """One key's ordered candidates for one day, grouped by `OutputKind`. Nothing here is
    written; a caller that wants a row still writes it itself (§2.1 rule 1)."""

    __slots__ = ("candidates", "withheld")

    def __init__(self, candidates: Sequence[Candidate], withheld: Sequence[Scope]) -> None:
        self.candidates = tuple(candidates)
        self.withheld = tuple(withheld)

    def of(self, kind: OutputKind) -> tuple[Candidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.output is kind)


async def _active_lines(
    session: AsyncSession, *, context: KeyContext, registry: DrugRegistry
) -> tuple[LineInfo, ...]:
    if not context.allows(Scope.MEDICINES):
        return ()
    found = await audited_read(
        session,
        MedicationLine,
        context,
        Scope.MEDICINES,
        where=(MedicationLine.superseded_at.is_(None), MedicationLine.status == LineStatus.ACTIVE),
    )
    lines: list[LineInfo] = []
    for line in found:
        watch: tuple[str, ...]
        plain: str | None
        try:
            monograph = registry.monograph(line.generic)
        except UnknownDrug:
            watch, plain = (), None
        else:
            watch, plain = monograph.watch_out_ids, monograph.plain_name_id
        lines.append(
            LineInfo(
                line_id=line.id,
                generic=line.generic,
                plain_name_id=plain,
                started_at=as_utc(line.started_at),
                watch_out_ids=tuple(watch),
            )
        )
    return tuple(lines)


async def _recent_taps(
    session: AsyncSession, *, context: KeyContext, now: datetime
) -> tuple[TapInfo, ...]:
    if not context.allows(Scope.RECORDS):
        return ()
    since = now - timedelta(days=FEELING_WINDOW_DAYS)
    found = await audited_read(
        session,
        FeelingTap,
        context,
        Scope.RECORDS,
        where=(FeelingTap.tapped_at >= since, FeelingTap.tapped_at <= now),
    )
    return tuple(
        TapInfo(tap_id=tap.id, word=tap.word, at=as_utc(tap.tapped_at)) for tap in found
    )


async def _upcoming_visits(
    session: AsyncSession, *, context: KeyContext, now: datetime
) -> tuple[UpcomingVisit, ...]:
    if not context.allows(Scope.VISITS):
        return ()
    visits = await upcoming_appointments(session, context=context, at=now)
    if not visits:
        return ()
    provider_ids = {visit.provider_id for visit in visits}
    providers = await audited_read(
        session, Provider, context, Scope.VISITS, where=(Provider.id.in_(provider_ids),)
    )
    by_id: dict[uuid.UUID, Provider] = {provider.id: provider for provider in providers}
    return tuple(
        UpcomingVisit(
            appointment_id=visit.id,
            scheduled_at=as_utc(visit.scheduled_at),
            purpose=visit.purpose,
            provider_kind=by_id[visit.provider_id].kind if visit.provider_id in by_id else None,
        )
        for visit in visits
    )


async def _told_conditions(
    session: AsyncSession, *, context: KeyContext
) -> tuple[ToldCondition, ...]:
    """`did_you_know`'s own read of the conditions he told (E01): `condition.<code>` facts
    that hold, under RECORDS, the same subject `app.delivery.feed.compose._conditions_of`
    already reads for State's clinical facts, here read directly rather than through State so
    `did_you_know` works even where `state` is `None` (a key too narrow to compute one, the
    same shape `_active_lines`/`_recent_taps` already read under their own scope alone)."""
    if not context.allows(Scope.RECORDS):
        return ()
    facts = await current_facts(session, context=context, subject=CONDITION_SUBJECT)
    return tuple(
        ToldCondition(code=fact.attribute, fact_id=fact.id) for fact in facts if fact.value is True
    )


async def _recent_did_you_know_topics(
    session: AsyncSession, *, context: KeyContext, now: datetime
) -> frozenset[str]:
    """The topics `did_you_know` has already used in the last `DID_YOU_KNOW_ROTATION` days,
    read back from the cards it made (`FeedItem.why`, RE-08: `Why.rule`/`Why.topic`) — no new
    column, the same "existing engagement rows" every other rotation in this codebase reads.
    Read under `Scope.PROFILE`, as `rank.require_item` already does for a `FeedItem` whose own
    scope varies row by row, and filtered back to what this key actually holds before any
    topic is trusted (belt and braces, the shape `Candidate.readable_by`'s own docstring
    documents) — a card `did_you_know` made under a scope this key has since lost is not read
    back as "already shown" for it."""
    since = now - DID_YOU_KNOW_ROTATION
    found = await audited_read(
        session,
        FeedItem,
        context,
        Scope.PROFILE,
        where=(FeedItem.created_at >= since, FeedItem.created_at <= now),
    )
    topics: set[str] = set()
    for item in found:
        if not context.allows(item.scope):
            continue
        why = item.why if isinstance(item.why, dict) else {}
        if why.get("rule") != RULE_DID_YOU_KNOW:
            continue
        topic = why.get("topic")
        if isinstance(topic, str) and topic:
            topics.add(topic)
    return frozenset(topics)


async def _declined_topics(
    session: AsyncSession, *, context: KeyContext, now: datetime
) -> frozenset[str]:
    """The topic codes he has said "not for me" to, still inside their thirty days at `now` —
    the exact fact shape `app.delivery.feed.engagement._decline_topic_for_30_days` writes
    (module doc: `DECLINED_TOPIC_SUBJECT`), read here so `did_you_know` rotates past a topic he
    declined rather than silently producing nothing for the day it would have picked it."""
    if not context.allows(Scope.RECORDS):
        return frozenset()
    facts = await current_facts(session, context=context, subject=DECLINED_TOPIC_SUBJECT, at=now)
    return frozenset(fact.attribute for fact in facts)


def _before_visit(state: StateView | None) -> bool:
    if state is None:
        return False
    situational = state.dimension(Dimension.SITUATIONAL)
    if situational is None:
        return False
    return situational.get("phase") == Phase.BEFORE_VISIT.value


async def _signal_is_on(session: AsyncSession, *, context: KeyContext, family: str) -> bool:
    """Whether `family`'s switch is on: RE-05's own default (on, unless he has said off) when
    the fact exists; on when it does not, or when this key cannot read RECORDS at all — a key
    too narrow to see the switch is also, in every case in this codebase today, too narrow to
    see the series that family would have fed, so the family is withheld by that scope check
    already, not by this default."""
    if not context.allows(Scope.RECORDS):
        return True
    facts = await current_facts(session, context=context, subject=SIGNALS_SUBJECT, attribute=family)
    if not facts:
        return True
    return bool(facts[-1].value)


async def slate(
    session: AsyncSession,
    *,
    context: KeyContext,
    state: StateView | None,
    registry: DrugRegistry,
    now: datetime | None = None,
    tagger: TopicTagger | None = None,
    ranker: Ranker | None = None,
    rules: Sequence[RecommendationRule] | None = None,
    engagement: Mapping[str, TopicEngagement] | None = None,
) -> Slate:
    """One key's ranked slate for right now. Reads the series, the medicine lines, the recent
    feeling taps and the visits on the spine, each under its own scope; runs the rule
    catalogue; drops what this key may not see; ranks what is left.

    `state` is read by the caller, not here (§2.4: `slate(session, *, context, state, day)`
    in the design; this adapter takes a moment, `now`, in place of `day`, in the shape every
    other reader in `app.reasoning.patterns.series` already takes it).
    """
    moment = as_utc(now) if now is not None else utcnow()
    catalogue = tuple(rules) if rules is not None else CATALOGUE
    tag = tagger if tagger is not None else KeywordTagger()
    order = ranker if ranker is not None else RuleRanker()
    seen_engagement = engagement if engagement is not None else {}

    series_set = await read_series(session, context=context, now=moment)
    lines = await _active_lines(session, context=context, registry=registry)
    taps = await _recent_taps(session, context=context, now=moment)
    visits = await _upcoming_visits(session, context=context, now=moment)
    told_conditions = await _told_conditions(session, context=context)
    recent_did_you_know = await _recent_did_you_know_topics(session, context=context, now=moment)
    declined = await _declined_topics(session, context=context, now=moment)

    families = {rule.signal_family for rule in catalogue if rule.signal_family is not None}
    off_families = {
        family
        for family in families
        if not await _signal_is_on(session, context=context, family=family)
    }

    inputs = RuleInputs(
        now=moment,
        series=series_set,
        lines=lines,
        taps=taps,
        upcoming_visits=visits,
        before_visit=_before_visit(state),
        tagger=tag,
        profile_id=context.profile_id,
        told_conditions=told_conditions,
        recent_did_you_know_topics=recent_did_you_know,
        declined_topics=declined,
    )

    built: list[Candidate] = []
    for rule in catalogue:
        if rule.signal_family is not None and rule.signal_family in off_families:
            continue
        built.extend(rule.build(inputs))

    readable = [candidate for candidate in built if candidate.readable_by(context)]

    withheld: list[Scope] = list(series_set.withheld)
    for scope in (Scope.MEDICINES, Scope.RECORDS, Scope.VISITS):
        if not context.allows(scope) and scope not in withheld:
            withheld.append(scope)

    ranked = order.rank(readable, state=state, engagement=seen_engagement)
    return Slate(candidates=ranked, withheld=tuple(withheld))
