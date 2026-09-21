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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.audit.trail import read_audit
from app.delivery.feed.compose import around_for, today_for
from app.delivery.feed.compress import (
    Compressed,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    PortUnavailable,
)
from app.delivery.feed.models import JobKind, JobStatus, Source
from app.delivery.feed.search import (
    FAILED_JOB_RETRY_LIMIT,
    Engine,
    create_job,
    due,
    prepare_job,
    run_job,
    search_and_compress,
    write_job_results,
)
from app.drugs.fixture import FixtureRegistry
from app.identity.service import create_own_profile, register_person
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import Scope
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

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
        raise PortUnavailable("the API refused every call")

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        raise PortUnavailable("the API refused every call")


class _NothingCompressor:
    def compress(self, text: str, language: str, facts: object) -> Compressed | None:
        return None


async def _run_once(sg: AsyncSession, *, context: KeyContext, engine: Engine, job: object) -> list[object]:
    """A job, run once, synchronously, on this session — what `app.delivery.feed.background.
    run_job` does across three, off it, for the same result. These tests are about `due`'s
    and `write_job_results`'s own bookkeeping, not the background module's scheduling
    (`tests/test_feed_background.py`, `tests/test_feed_background_locking.py` cover that)."""
    day = today_for(context)
    state = await current_state(sg, context=context)
    around = await around_for(sg, context=context, engine=engine, state=state, day=day)
    return await run_job(
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


async def test_write_time_re_checks_the_source_allowlist(sg: AsyncSession) -> None:
    """#291 review, REQUIRED 2: the allowlist is re-checked at write time
    (`write_job_results`'s own `require_usable_source` call), not only when the job searched
    — a source de-listed in the gap between the network phase and the write must still
    refuse the card, never cite a source that is no longer allowlisted."""
    context = await _pa(sg)
    engine = Engine(
        searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
    )
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    day = today_for(context)
    state = await current_state(sg, context=context)
    around = await around_for(sg, context=context, engine=engine, state=state, day=day)
    prep = await prepare_job(sg, context=context, job=job)
    outcome = await search_and_compress(
        engine, job, prep, state=state, language="en", around=around, existing=set()
    )
    assert outcome.candidates, "the fixture must find something to compress, or this proves nothing"

    # De-listed between the network phase and the write.
    sources = (await sg.scalars(select(Source))).all()
    assert sources
    for source in sources:
        source.allowlisted = False
    await sg.flush()

    made = await write_job_results(
        sg,
        context=context,
        job=job,
        engine=engine,
        state=state,
        language="en",
        around=around,
        doctor=None,
        existing=set(),
        outcome=outcome,
    )
    assert not made, "a source de-listed since the network phase must never be cited"
    await sg.refresh(job)
    assert job.results["rejected"], "the candidate is rejected, not silently dropped"
    assert all(r["because"] == "not_allowlisted" for r in job.results["rejected"])


class _LabelledSearcher:
    """Wraps the fixture searcher so it behaves exactly like it, but declares
    `external_processor` the way a real Claude-backed adapter does — for testing the audit
    line without a live API call."""

    external_processor: str | None = "anthropic"

    def __init__(self, delegate: FixtureSearcher) -> None:
        self._delegate = delegate

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
        return self._delegate.search(kind, terms, domains)

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        return self._delegate.find(words, domains, media=media)


class _LabelledCompressor:
    external_processor: str | None = "anthropic"

    def __init__(self, delegate: FixtureCompressor) -> None:
        self._delegate = delegate

    def compress(self, text: str, language: str, facts: object) -> Compressed | None:
        return self._delegate.compress(text, language, facts)  # type: ignore[arg-type]


async def test_an_external_call_writes_the_external_model_processor_audit_line(
    sg: AsyncSession,
) -> None:
    """#291 review, REQUIRED 3: the feed's searcher and compressor never wrote the
    `EXTERNAL_MODEL_PROCESSOR` share entry the brief said not to drop — every other
    Claude-backed path does. One line, once per job that actually reached out, whether it
    made a card or not."""
    context = await _pa(sg)
    engine = Engine(
        searcher=_LabelledSearcher(FixtureSearcher(FEED)),
        compressor=_LabelledCompressor(FixtureCompressor(FEED)),
        registry=REGISTRY,
    )
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    made = await _run_once(sg, context=context, engine=engine, job=job)

    trail = await read_audit(sg, context=context, action=Action.SHARE, scope=Scope.RECORDS)
    shared = [e for e in trail if e.target == EXTERNAL_MODEL_PROCESSOR and e.target_id == job.id]
    assert len(shared) == 1, "one line, once per job, not once per page it compressed"
    assert shared[0].shared_with_label == "anthropic"
    assert made, "the fixture-backed call still made its card, sanity check on the setup"


async def test_a_failed_external_call_still_writes_the_audit_line(sg: AsyncSession) -> None:
    """The bytes already left before the call failed — REQUIRED 3 is explicit that a `FAILED`
    job still earns the line."""
    context = await _pa(sg)

    class _FailsButLabelled:
        external_processor: str | None = "anthropic"

        def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
            raise PortUnavailable("the API refused every call")

        def find(
            self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
        ) -> Sequence[Found]:
            raise PortUnavailable("the API refused every call")

    engine = Engine(
        searcher=_FailsButLabelled(), compressor=_NothingCompressor(), registry=REGISTRY
    )
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    await _run_once(sg, context=context, engine=engine, job=job)
    await sg.refresh(job)
    assert job.status is JobStatus.FAILED

    trail = await read_audit(sg, context=context, action=Action.SHARE, scope=Scope.RECORDS)
    shared = [e for e in trail if e.target == EXTERNAL_MODEL_PROCESSOR and e.target_id == job.id]
    assert len(shared) == 1, "a failed call still left the job's terms with the processor"
    assert shared[0].shared_with_label == "anthropic"


async def test_a_fixture_job_never_writes_the_external_model_processor_line(
    sg: AsyncSession,
) -> None:
    context = await _pa(sg)
    engine = Engine(
        searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
    )
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["metformin"], reason={}, cadence="daily"
    )
    await _run_once(sg, context=context, engine=engine, job=job)

    trail = await read_audit(sg, context=context, action=Action.SHARE, scope=Scope.RECORDS)
    shared = [e for e in trail if e.target == EXTERNAL_MODEL_PROCESSOR]
    assert not shared, "a fixture engine never leaves the region; nothing is shared"
