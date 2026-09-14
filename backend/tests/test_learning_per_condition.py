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

from app.db import utcnow
from app.delivery.feed.compose import refresh
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.models import CardType, FeedItem, Source
from app.delivery.feed.rank import item_json
from app.delivery.feed.search import Engine, list_jobs
from app.keys.context import KeyContext
from app.memory.episodic import record_event
from app.memory.models import EventKind, SourceChannel
from app.memory.semantic import assert_fact
from app.safety.boundary import Surface, boundary_line
from tests.conftest import FEED
from tests.medicines_support import REGISTRY
from tests.visits import pa

ENGINE = Engine(searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY)
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

    jobs = await list_jobs(sg, context=context)
    [job] = [j for j in jobs if list(j.terms) == ["diabetes"]]
    assert job.kind.value == "explainer" and job.reason["scope"] == "records"
    assert job.reason["fact_ids"]
    [card] = [c for c in await _learning(sg, context) if c.why.get("gap") == "diabetes"]
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
    terms = [list(j.terms) for j in await list_jobs(sg, context=context)]
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
            return [replace(page, url="https://supplement-shop.example/diabetes") for page in super().search(kind, terms, domains)]

    context = await pa(sg, language="en")
    await _told(sg, context, "diabetes", holds=True)
    await refresh(sg, context=context, engine=Engine(searcher=Elsewhere(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY))
    assert not [c for c in await _learning(sg, context) if c.why.get("gap") == "diabetes"]
    [job] = [j for j in await list_jobs(sg, context=context) if list(j.terms) == ["diabetes"]]
    assert {r["because"] for r in job.results["rejected"]} == {"not_on_its_source"}
