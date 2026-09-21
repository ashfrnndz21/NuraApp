"""#297 defect 2: a search that FAILED must be recorded as `FAILED`, not `DONE`, and stay due
for a retry the same day, up to a limit — never hammered forever, never silently skipped for
the rest of the day either.

Live evidence: on 2026-09-18 the Anthropic API refused every call. `ClaudeSearcher`/
`ClaudeCompressor` logged and returned a clean empty answer (`[]`/`None`), indistinguishable
from a job that genuinely searched and found nothing, so every job that day ended
`status=done`, `results=[]`, and `due` said none of them were due again once the API came
back. The fix: a port's own call failing raises `app.delivery.feed.compress.PortUnavailable`,
which `write_job_results` tells apart from a clean empty answer.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.feed.compose import around_for, today_for
from app.delivery.feed.compress import (
    Compressed,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    PortUnavailable,
)
from app.delivery.feed.models import JobKind, JobStatus
from app.delivery.feed.search import FAILED_JOB_RETRY_LIMIT, Engine, create_job, due, run_job
from app.drugs.fixture import FixtureRegistry
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.regions import Region
from app.state.service import current_state
from tests.conftest import FEED
from tests.support import OPENING_CONSENT

PHONE = "+6591310099"
REGISTRY = FixtureRegistry.load()


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=PHONE)
    profile = await create_own_profile(
        session, region=Region.SG, owner=pa, consent=OPENING_CONSENT, language="en"
    )
    return await resolve_key_context(session, region=Region.SG, person_id=pa.id, profile_id=profile.id)


class _AlwaysFails:
    """A `Searcher` whose call always fails — the 2026-09-18 incident: every call to the API
    itself refused, never a clean "nothing found"."""

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        raise PortUnavailable("the API refused every call")

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        raise PortUnavailable("the API refused every call")


class _NothingCompressor:
    def compress(self, text: str, language: str, facts: object) -> Compressed | None:
        return None


async def _run_once(sg: AsyncSession, *, context: KeyContext, engine: Engine, job: object) -> None:
    """A job, run once, synchronously, on this session — what `app.delivery.feed.background.
    run_job` does across three, off it, for the same result. These tests are about `due`'s
    and `write_job_results`'s own bookkeeping, not the background module's scheduling
    (`tests/test_feed_background.py`, `tests/test_feed_background_locking.py` cover that)."""
    day = today_for(context)
    state = await current_state(sg, context=context)
    around = await around_for(sg, context=context, engine=engine, state=state, day=day)
    await run_job(
        sg,
        context=context,
        job=job,
        engine=engine,
        state=state,
        language="en",
        around=around,
        doctor=None,
        existing=set(),
    )


async def test_a_port_failure_leaves_the_job_failed_and_still_due_today(sg: AsyncSession) -> None:
    context = await _pa(sg)
    engine = Engine(searcher=_AlwaysFails(), compressor=_NothingCompressor(), registry=REGISTRY)
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    day = today_for(context)

    await _run_once(sg, context=context, engine=engine, job=job)

    await sg.refresh(job)
    assert job.status is JobStatus.FAILED
    assert job.results["failed_attempts"] == 1
    assert job.results["failed_day"] == day.key
    assert due(job, day), "a job whose own call failed is still due today, whatever its cadence"


async def test_a_genuinely_empty_search_is_done_and_not_due_again_today(sg: AsyncSession) -> None:
    """The other half of the same distinction: a job that ran cleanly and simply found
    nothing (the fixture searcher, no matching page) is `DONE`, and — daily cadence, same day
    — not due again until tomorrow. Never confused with the failure case above."""
    context = await _pa(sg)
    engine = Engine(
        searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
    )
    job = await create_job(
        sg,
        context=context,
        kind=JobKind.EXPLAINER,
        terms=["a term with no fixture page at all"],
        reason={},
        cadence="daily",
    )
    day = today_for(context)

    await _run_once(sg, context=context, engine=engine, job=job)

    await sg.refresh(job)
    assert job.status is JobStatus.DONE
    assert "failed_attempts" not in job.results
    assert not due(job, day), "a clean empty search is done, not retried the same day"


async def test_the_retry_limit_is_honoured(sg: AsyncSession) -> None:
    """`FAILED_JOB_RETRY_LIMIT` attempts, no more, before `due` falls back to the job's
    ordinary cadence — a dead API is retried, not hammered for the rest of the day."""
    context = await _pa(sg)
    engine = Engine(searcher=_AlwaysFails(), compressor=_NothingCompressor(), registry=REGISTRY)
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    day = today_for(context)

    for attempt in range(1, FAILED_JOB_RETRY_LIMIT + 1):
        assert due(job, day), f"attempt {attempt}: still under the retry limit"
        await _run_once(sg, context=context, engine=engine, job=job)
        await sg.refresh(job)
        assert job.status is JobStatus.FAILED
        assert job.results["failed_attempts"] == attempt

    assert not due(job, day), "the retry budget for today is spent; due falls back to cadence"


async def test_a_job_that_recovers_resets_its_retry_count(sg: AsyncSession) -> None:
    """A job need not exhaust its retry budget to recover: once it runs cleanly, `results`
    carries no `failed_attempts` any more, so a later day's failure starts back at zero."""
    context = await _pa(sg)
    failing = Engine(searcher=_AlwaysFails(), compressor=_NothingCompressor(), registry=REGISTRY)
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    await _run_once(sg, context=context, engine=failing, job=job)
    await sg.refresh(job)
    assert job.status is JobStatus.FAILED

    recovered = Engine(
        searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
    )
    await _run_once(sg, context=context, engine=recovered, job=job)
    await sg.refresh(job)
    assert job.status is JobStatus.DONE
    assert "failed_attempts" not in job.results
