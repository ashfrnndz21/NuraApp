"""E21-06 acceptance: evergreen learning from allowlisted sources, per condition and medicine.

    No card from outside the allowlist; every card cites its page.

A medicine on his list already starts an explainer (tests/test_feed.py). A condition he told
when his profile was set up (E01, a `condition.<code>` fact) starts one too, searched only on
the allowlist, and its card carries the page it cites — the publisher, the link and the
passage — in the payload the web shows as "From {publisher}".
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.db import utcnow
from app.delivery.feed.compose import (
    Day,
    household,
    plan_learning_jobs,
    refresh,
    say_ahead,
    today_for,
)
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.models import CardType, FeedItem, Source
from app.delivery.feed.rank import item_json
from app.delivery.feed.search import Engine, list_jobs
from app.delivery.feed.search import run_job as search_run_job
from app.delivery.recommend.rules import RULE_DID_YOU_KNOW
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.service import LineView, active_lines
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.safety.boundary import Surface, boundary_line
from app.state.service import current_state
from tests.conftest import FEED
from tests.medicines_support import REGISTRY
from tests.visits import pa


async def _run_learning(
    session: AsyncSession, *, context: KeyContext, engine: Engine, day: Day
) -> list[FeedItem]:
    """Today's self-searches, run synchronously on this same session — what
    `app.delivery.feed.background._run` does on its own session, off the request entirely, for
    tests that check which cards a job makes, not the background module's own scheduling
    (`tests/test_feed_background.py` covers that)."""
    house = await household(session, context=context)
    state = await current_state(session, context=context)
    medicines: list[LineView] = (
        await active_lines(session, context=context, registry=engine.registry, language=house.language)
        if context.allows(Scope.MEDICINES)
        else []
    )
    every = await audited_read(session, FeedItem, context, Scope.PROFILE)
    keys = {item.dedupe_key for item in every}
    plan = await plan_learning_jobs(
        session,
        context=context,
        engine=engine,
        state=state,
        day=day,
        house=house,
        keys=keys,
        medicines=medicines,
    )
    made: list[FeedItem] = []
    for job in plan.jobs:
        items = await search_run_job(
            session,
            context=context,
            job=job,
            engine=engine,
            state=await current_state(session, context=context),
            language=house.language,
            around=plan.around,
            doctor=house.doctor,
            existing=set(keys),
        )
        if items:
            await say_ahead(session, engine, context, items)
            made.extend(items)
            keys.update(item.dedupe_key for item in items)
    return made

ENGINE = Engine(
    searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
)
PAGE = "https://www.healthhub.sg/a-z/diseases-and-conditions/diabetes"


async def _told(session: AsyncSession, context: KeyContext, code: str, *, holds: bool) -> None:
    moment = await record_event(
        session,
        context=context,
        kind=EventKind.ONBOARDING,
        occurred_at=utcnow(),
        label="the conditions he told",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        session,
        context=context,
        subject="condition",
        attribute=code,
        value=holds,
        confidence=1.0,
        event_id=moment.id,
    )


async def _learning(session: AsyncSession, context: KeyContext) -> list[FeedItem]:
    return list(
        await session.scalars(
            select(FeedItem).where(
                FeedItem.profile_id == context.profile_id, FeedItem.type == CardType.LEARNING
            )
        )
    )


async def test_a_condition_he_told_starts_a_search_and_its_card_cites_its_page(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en")
    await _told(sg, context, "diabetes", holds=True)
    await refresh(sg, context=context, engine=ENGINE)
    await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))

    jobs = await list_jobs(sg, context=context)
    # The explainer (a condition also starts his weekly food watch: test_feed_formats).
    [job] = [j for j in jobs if list(j.terms) == ["diabetes"] and j.kind.value == "explainer"]
    assert job.kind.value == "explainer" and job.reason["scope"] == "records"
    assert job.reason["fact_ids"]
    # "Did you know" (RE-07) is one extra learning job a day, not a second explainer: on a
    # bare profile with only this one condition told, it is the day's only eligible topic, so
    # it names the same term through its own `worth_knowing` job rather than crowding the
    # explainer's. It must never change the explainer's own behaviour, so the explainer's
    # card is picked out by its rule-less `why` (a broker-proposed card always names its
    # rule, `app.delivery.feed.items.Why.rule`; a State-found gap's card never does).
    [extra] = [j for j in jobs if list(j.terms) == ["diabetes"] and j.kind.value == "worth_knowing"]
    assert extra.reason["rule"] == RULE_DID_YOU_KNOW
    [card] = [
        c
        for c in await _learning(sg, context)
        if c.why.get("gap") == "diabetes" and c.why.get("rule") is None
    ]
    assert card.headline == "About your blood sugar"
    assert "This comes from HealthHub." in card.body
    line = boundary_line(Surface.LEARNING_CARD, "en")
    assert list(card.body[-len(line.splitlines()) :]) == line.splitlines()
    source = await sg.get(Source, card.source_id)
    assert source is not None and source.allowlisted and source.domain == "healthhub.sg"

    # The page it cites rides on the card, for the web to show and link.
    cite = item_json(card, "generated")["cite"]
    assert cite["publisher"] == "HealthHub" and cite["domain"] == "healthhub.sg"
    assert cite["url"] == PAGE
    assert cite["passage"].startswith("Diabetes is a condition where there is too much sugar")


async def test_a_condition_he_said_he_does_not_have_starts_no_search(sg: AsyncSession) -> None:
    context = await pa(sg, language="en")
    await _told(sg, context, "diabetes", holds=False)
    await refresh(sg, context=context, engine=ENGINE)
    assert not [j for j in await list_jobs(sg, context=context) if list(j.terms) == ["diabetes"]]
    assert not [c for c in await _learning(sg, context) if c.why.get("gap") == "diabetes"]


async def test_high_blood_pressure_is_the_blood_pressure_search_not_a_second_one(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en")
    await _told(sg, context, "high_blood_pressure", holds=True)
    await refresh(sg, context=context, engine=ENGINE)
    await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
    terms = [
        list(j.terms) for j in await list_jobs(sg, context=context) if j.kind.value == "explainer"
    ]
    assert terms.count(["blood pressure"]) == 1 and ["high blood pressure"] not in terms


def test_a_cited_page_is_on_its_sources_own_site_over_https() -> None:
    from app.delivery.feed.search import on_its_source

    assert on_its_source("https://www.healthhub.sg/a-z/diabetes", "healthhub.sg")
    assert on_its_source("https://healthhub.sg/x", "healthhub.sg")
    assert not on_its_source("http://www.healthhub.sg/x", "healthhub.sg")
    assert not on_its_source("https://healthhub.sg.example.com/x", "healthhub.sg")
    assert not on_its_source("https://evilhealthhub.sg/x", "healthhub.sg")


async def test_a_page_the_searcher_says_is_allowlisted_but_links_elsewhere_makes_no_card(
    sg: AsyncSession,
) -> None:
    from dataclasses import replace

    class Elsewhere(FixtureSearcher):
        def search(self, kind, terms, domains):  # type: ignore[no-untyped-def]
            return [
                replace(page, url="https://supplement-shop.example/diabetes")
                for page in super().search(kind, terms, domains)
            ]

    context = await pa(sg, language="en")
    await _told(sg, context, "diabetes", holds=True)
    engine = Engine(searcher=Elsewhere(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY)
    await refresh(sg, context=context, engine=engine)
    await _run_learning(sg, context=context, engine=engine, day=today_for(context))
    assert not [c for c in await _learning(sg, context) if c.why.get("gap") == "diabetes"]
    [job] = [
        j
        for j in await list_jobs(sg, context=context)
        if list(j.terms) == ["diabetes"] and j.kind.value == "explainer"
    ]
    assert {r["because"] for r in job.results["rejected"]} == {"not_on_its_source"}
