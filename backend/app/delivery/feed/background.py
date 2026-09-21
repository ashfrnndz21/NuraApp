"""The day's self-searches, run in the background, never inline in a request (#269/#276,
#280).

Live evidence: `GET /profiles/{id}/feed` on the first open of a day ran every one of the
day's due self-searches right there, inline (`app.delivery.feed.compose._learning`, now
`plan_learning_jobs`) — real web search, fetch and compression, sometimes a dozen jobs deep —
and held the request open past 400s until the client gave up. Worse, the searcher's and the
compressor's real adapters make their model call synchronously (`ClaudeSearcher._ask`,
`app.delivery.feed.compress`), which blocks this process's one event loop for as long as the
call takes — not just this request, every request the process was serving.

`GET /feed` (`app.channels.api.feed.feed`) still calls `compose.refresh`, which still makes
every other card inline — the flag, now, today, the gate, the story, all fast, all reads and
plain writes. It no longer runs a self-search. Instead, once the page is built, the route
calls `ensure_learning_scheduled` here, which returns at once: if nothing is due, or a run
already started or finished today, it does nothing; otherwise it starts this module's own
`asyncio.create_task`, on its own session (never the request's, which closes the moment the
response is sent), and returns immediately, before the response goes out. A card the run
makes lands in storage the moment its job finishes and shows on the next page load, the same
as any other card.

One run per profile per day: `_runs` is this process's record of it (`RunRecord`), keyed on
`(profile_id, day.key)`, checked and set without an `await` between the two, so two requests
racing to schedule the same day's run cannot both start one — whichever coroutine runs first
(cooperative scheduling has no other contender until the next `await`) claims it. In-process
and in-memory: a second worker process, or a restart mid-run, would not see this profile's
run as already claimed. Acceptable for this deployment (one process; see `app.demo`'s own
night watch and `app.channels.api.sse_pump`, the two existing background-task patterns this
follows) and worth a line in the PR, not a migration, before this task's clock ran out.

At most `MAX_CONCURRENT_JOBS` jobs run at once, each on its own session (an `AsyncSession` is
never shared across concurrent coroutines — the same reason `app.channels.api.deps.db` opens
one per request), each bounded by `JOB_DEADLINE_SECONDS`; the whole run is bounded by
`RUN_DEADLINE_SECONDS`. A job that raises or times out is logged and counted as failed; it
never stops the others.

**#297 defect 1 (2026-09-18): the write lock held across the network wait.** On SQLite every
transaction begins IMMEDIATE (`app.db.make_engine`) and holds the database's one write lock
for its whole life, not just its first write. `_run_one` used to open one session for a whole
job — search, compress, and the cards it wrote — so that lock sat open for as long as the
search and the compression took (20-40s each, real adapters), one job after another
(`MAX_CONCURRENT_JOBS = 1`): every other request that writes, `resolve_session` on every
authenticated call included, answered `sqlite3.OperationalError: database is locked` for
minutes at a time. `run_job` (`app.delivery.feed.search`) is now three phases — a short read,
the network with no session at all, a short write — and this module's own `run_job` below
calls them directly, each on its own short-lived session, so no transaction is ever open
while a job waits on the network. `speak_ahead`/`record_say_ahead_failures`
(`app.delivery.feed.compose`) get the same treatment for the voice pre-render `_run_one` does
after a job's cards land.

**#297 defect 2 (2026-09-18): a failed search recorded as "done, found nothing".** The
Anthropic API refused every call that day; `ClaudeSearcher`/`ClaudeCompressor` logged and
returned an empty answer, indistinguishable from a job that searched and genuinely found
nothing, so every job that day ended `status=done`, `results=[]`, and `due` (`app.delivery.
feed.search`) said none of them were due again once the API came back. A port's own call
failing now raises `app.delivery.feed.compress.PortUnavailable`, which `write_job_results`
tells apart from a clean empty answer: the job is left `FAILED`, and `due` keeps it due for a
retry the same day, up to `FAILED_JOB_RETRY_LIMIT` attempts. `_runs`, this process's
once-a-day cache of what already ran, would otherwise never look again after a run finished —
`RunRecord.worth_rechecking` and `ensure_learning_scheduled` below let a later `GET /feed` the
same day start a fresh (short) replan when a failed job is still due, without ever running
two at once for one profile.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.access import audited_read
from app.db import unit_of_work, utcnow
from app.delivery.feed.compose import (
    Household,
    LearningPlan,
    household,
    plan_learning_jobs,
    record_say_ahead_failures,
    speak_ahead,
)
from app.delivery.feed.days import Day
from app.delivery.feed.models import FeedItem, SearchJob
from app.delivery.feed.search import (
    Around,
    Engine,
    failed_jobs_due,
    prepare_job,
    search_and_compress,
    write_job_results,
)
from app.errors import Refusal
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import Scope
from app.llm import call_counter
from app.medicines.service import LineView, active_lines
from app.state.service import current_state

log = logging.getLogger("nura.delivery.feed")

MAX_CONCURRENT_JOBS = 1
"""How many self-searches are in flight at once for one run: one. The plan's order is the
broker's order (`plan_learning_jobs` — the week's new medicine leads its learning supply), and
a card lands in storage the moment its job finishes, so two jobs in flight put their cards in
whichever order they happened to complete, not the broker's: the general clip ahead of the
tablet's (#286's first CI round, and the same suite locally). One at a time keeps the order the
plan decided, and the run is in the background anyway — nothing is waiting on it."""

JOB_DEADLINE_SECONDS = 60
"""One job — one search, its pages, their compression — gets at most this long."""

RUN_DEADLINE_SECONDS = 900
"""The whole day's catch-up, however many jobs it holds, gets at most this long: one at a
time, a dozen live jobs at their own pace fit well inside it, and nothing waits on the run."""

MAX_JOBS_PER_RUN = 6
"""The default cap on how many of the plan's jobs one run actually executes, when a caller
does not pass `max_jobs_per_run=` (`ensure_learning_scheduled`'s own default; a real
deployment's cap comes from `Settings.max_jobs_per_run`/`NURA_MAX_JOBS_PER_RUN`, read by
`app.channels.api.feed.feed`). A run takes the plan's *first* N jobs, in the plan's own order
(the broker's — see `MAX_CONCURRENT_JOBS` above on why that order matters) and leaves the
rest untouched, due for a later run — ordinarily the next day's. One live run fanned out into
about 48 Opus calls behind one card; this is the run-level cap that keeps any one run bounded,
whatever a deployment's plan turns up."""

State = Literal["looking", "done", "none"]


@dataclass
class RunRecord:
    """Today's run for one profile, as the feed response's own `jobs` line reads it back
    (`app.channels.api.feed_schemas.FeedJobsOut`): "looking" while jobs are still to run or
    running, "done" once they have (however many succeeded), "none" when nothing was ever
    due — never a guess, always this record."""

    state: State
    started_at: datetime | None = None
    done_at: datetime | None = None
    worth_rechecking: bool = False
    """True when something is still due right now — most often a job this run's last attempt
    left `FAILED` and still inside its retry budget (#297 defect 2:
    `search.FAILED_JOB_RETRY_LIMIT`), read back with `search.failed_jobs_due`.
    `ensure_learning_scheduled` checks this to decide whether a later `GET /feed` the same
    day is worth a fresh (short) replan — false once nothing is due any more, so a spent
    retry budget stops asking again for the rest of the day."""
    made: int = 0
    """Cards the run's jobs made, once it reaches `"done"` (#291 review, REQUIRED 4)."""
    failed: int = 0
    """Jobs the run counted as failed, once it reaches `"done"`: raised, timed out, or left
    `FAILED` by `write_job_results` — every way a job can end badly, not only the ones that
    raise (#291 review, REQUIRED 4: live, all 14 jobs ended `FAILED` while the old count,
    which only ever incremented on a raise or a timeout, read 0)."""
    deferred: int = 0
    """How many of the plan's jobs this run left untouched past `max_jobs_per_run`
    (`MAX_JOBS_PER_RUN`/`NURA_MAX_JOBS_PER_RUN`): the plan found more work than the cap, so
    only its first N, in the plan's own order, actually ran — the rest stay due, for a later
    run. 0 the ordinary day the plan never reaches the cap. The feed response's `jobs` block
    (`app.channels.api.feed_schemas.FeedJobsOut.deferred`) reads this back, so a live check
    can say exactly how many were held back, not just how many ran."""


_runs: dict[tuple[uuid.UUID, str], RunRecord] = {}
"""This process's memory of today's run, per profile. Never persisted; see the module
docstring on what that trades away."""

_tasks: set[asyncio.Task[None]] = set()
"""Every run this module has started that may still be in flight — tests only. Nothing in
the running app reads this: a request never waits on the task it starts (that is the whole
point of `ensure_learning_scheduled`), so there is no caller in production that would ever
need to. A test that calls `GET /feed` twice and expects the second call to see the first
run's cards needs the run to have actually finished first; `drain` is that wait."""


def run_state(profile_id: uuid.UUID, day_key: str) -> RunRecord | None:
    """A read only: never starts anything, never blocks. `None` means no run has ever been
    scheduled for this profile on this day — the caller reads that as "none"."""
    return _runs.get((profile_id, day_key))


def ensure_learning_scheduled(
    *,
    context: KeyContext,
    engine: Engine,
    day: Day,
    sessions: async_sessionmaker[AsyncSession],
    max_jobs_per_run: int = MAX_JOBS_PER_RUN,
) -> RunRecord | None:
    """Called from `GET /feed` after the page is built. Starts today's catch-up at most once
    while it is actually running: a "looking" record already here means a run for today is in
    flight (by this call or an earlier one) and this never starts a second one alongside it.
    A "done" or "none" record with nothing left `worth_rechecking` (#297 defect 2 — the common
    case) does nothing more either, the same as before. Only a finished run that left
    something due again — most often a job still inside its retry budget after its own search
    or compression failed — gets a fresh (short) replan here. Never awaited on the slow part:
    the task this starts runs on its own, after this function has returned."""
    key = (context.profile_id, day.key)
    existing = _runs.get(key)
    if existing is not None and (existing.state == "looking" or not existing.worth_rechecking):
        return existing
    _runs[key] = RunRecord(
        state="looking", started_at=existing.started_at if existing is not None else utcnow()
    )
    task = asyncio.create_task(
        _run(
            key,
            context=context,
            engine=engine,
            day=day,
            sessions=sessions,
            resuming=existing is not None,
            max_jobs_per_run=max_jobs_per_run,
        )
    )
    _tasks.add(task)
    task.add_done_callback(_log_if_failed)
    task.add_done_callback(_tasks.discard)
    return _runs[key]


async def drain() -> None:
    """Wait for every run this module has started that has not finished yet. Tests only: a
    real caller never awaits the task `ensure_learning_scheduled` starts. Safe to call with
    nothing in flight (returns at once) and safe to call again after a run it waited on
    starts another (loops until the set is actually empty)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def _log_if_failed(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    failed = task.exception()
    if failed is not None:
        log.error("feed: the background learning run crashed: %s", failed, exc_info=failed)


@asynccontextmanager
async def _own_session(sessions: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """The same boundary `app.channels.api.deps.session_scope` gives a request, for a task
    that has no request: one session, one unit of work, committed on success or on a refusal
    (whose own audit lines still land), rolled back on anything else."""
    async with sessions() as session:
        try:
            async with unit_of_work(session):
                yield session
        except Refusal:
            await session.commit()
            raise
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()


async def _plan(
    sessions: async_sessionmaker[AsyncSession], *, context: KeyContext, engine: Engine, day: Day
) -> tuple[LearningPlan, Household, set[str]] | None:
    """What to run, read fresh on its own session: the household, State, his medicines, the
    dedupe keys already on the profile, and the plan itself (`plan_learning_jobs` — DB reads
    and plain writes only, no search, no compression). `None` if the key no longer resolves
    (the profile or the key was removed between the request and this task starting)."""
    try:
        async with _own_session(sessions) as session:
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
            return plan, house, keys
    except Refusal:
        log.warning("feed: the background learning run's own key no longer resolves; nothing planned")
        return None


@dataclass(frozen=True, slots=True)
class JobRunResult:
    """What one job's phased run left: the cards it made (if any), and whether the run's own
    summary line (`_run`) should count it as failed."""

    items: list[FeedItem]
    failed: bool = False
    """True when the job ended `FAILED` (#291 review, REQUIRED 4: the run's own "N made, M
    failed" line used to count only a job that raised or timed out here — a job whose search
    or compression itself failed returned normally, with an empty `items`, and was silently
    left out of "failed" entirely; live, all 14 jobs ended `FAILED` while the log read "0
    cards made, 0 failed"), or when its write phase was skipped outright (its deadline hit
    before phase 3 could even start; see `run_job`)."""


async def run_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    context: KeyContext,
    job: SearchJob,
    engine: Engine,
    language: str,
    around: Around,
    doctor: str | None,
    existing: set[str],
) -> JobRunResult:
    """One job, phased so the database's write lock is never held while it waits on the
    network (#297 defect 1): a short read (`prepare_job`, plus the state a job's compression
    grounds on), the search and the compression with no session open at all
    (`search_and_compress`, bounded by `JOB_DEADLINE_SECONDS` on its own — #291 review
    suggestion: the deadline fires here, before phase 3 ever opens a session, so a timeout
    can never cancel a task mid-write), then a short write for the cards and the job's own
    `status`/`last_run_at`/`results` (`write_job_results`) — three units of work, each on its
    own short-lived session, never one held open across the network wait in between.
    `_run_one`'s own `asyncio.wait_for` around this whole call is the backstop for anything
    that predates or bypasses this (a monkeypatched fake in a test, or phase 1/3 somehow
    hanging), not the primary deadline any more.

    Phase 3 never reuses the `job` (or its `context`) carried across the wait: with
    `expire_on_commit=False`, that Python object still holds its load-time column values, and
    `session.merge()` would copy every one of them onto the fresh row — overwriting a pause
    (`SearchJob.enabled`) `pause_job` set while phase 2 was waiting, with no error and no
    trail (#291 review, REQUIRED 1: reproduced live on a file-backed database — pause during
    the wait, and the merge silently wrote `enabled` back to `True`). Instead this re-fetches
    the job fresh by id (`session.get`, never `.merge`), and re-resolves `context` fresh too
    (`resolve_key_context` — REQUIRED 2: a key revoked, a scope narrowed, or the account
    closed while phase 2 waited must refuse the write here, at write time, not slip through
    on a stale, already-cleared context). A job found paused, deleted, or whose key no longer
    resolves is skipped outright: no cards, and the skip itself is logged (never silently
    dropped) — `write_job_results` itself still re-checks the one thing left, that each
    candidate's source is still a usable, allowlisted one right now.

    This is the seam `_run_one` calls once per job, and the one
    `tests/test_feed_background.py` monkeypatches to make a job raise or hang.
    `app.delivery.feed.search.run_job` stays the single-session version, for every caller
    that already holds one session across a whole job (the inline `POST .../jobs/{id}/run`
    path, and every test that calls it directly) — this function is `background`'s own
    phased variant of it, composed from the same three phases search.py exports.
    """
    async with _own_session(sessions) as session:
        state = await current_state(session, context=context)
        prep = await prepare_job(session, context=context, job=job)
    try:
        outcome = await asyncio.wait_for(
            search_and_compress(
                engine, job, prep, state=state, language=language, around=around, existing=existing
            ),
            timeout=JOB_DEADLINE_SECONDS,
        )
    except TimeoutError:
        log.warning("feed: a background learning job hit its %ss deadline", JOB_DEADLINE_SECONDS)
        return JobRunResult(items=[], failed=True)
    async with _own_session(sessions) as session:
        try:
            fresh_context = await resolve_key_context(
                session, region=context.region, person_id=context.person_id, profile_id=context.profile_id
            )
        except Refusal:
            log.warning(
                "feed: job %s's own key no longer resolves at write time; skipped, no cards written",
                job.id,
            )
            return JobRunResult(items=[], failed=True)
        fresh_job = await session.get(SearchJob, job.id)
        if fresh_job is None or not fresh_job.enabled:
            log.warning(
                "feed: job %s was paused or removed mid-run; skipped, no cards written", job.id
            )
            return JobRunResult(items=[])
        items = await write_job_results(
            session,
            context=fresh_context,
            job=fresh_job,
            engine=engine,
            state=state,
            language=language,
            around=around,
            doctor=doctor,
            existing=existing,
            outcome=outcome,
        )
        return JobRunResult(items=items, failed=outcome.failed_because is not None)


async def _run_one(
    sessions: async_sessionmaker[AsyncSession],
    semaphore: asyncio.Semaphore,
    *,
    context: KeyContext,
    engine: Engine,
    house: Household,
    plan: LearningPlan,
    keys: set[str],
    job: SearchJob,
) -> JobRunResult | None:
    """`None` means this job raised or ran past its deadline before `run_job` itself could
    tell the difference — told apart from a `JobRunResult` (whether or not `.failed`), so the
    run's own "N cards made, M failed" line counts every way a job can end (#291 review,
    REQUIRED 4): raised, timed out here, or left `FAILED` by `write_job_results` (its own
    search or compression call failed, not a clean "nothing for him")."""
    async with semaphore:
        try:
            result = await asyncio.wait_for(
                run_job(
                    sessions,
                    context=context,
                    job=job,
                    engine=engine,
                    language=house.language,
                    around=plan.around,
                    doctor=house.doctor,
                    existing=set(keys),
                ),
                timeout=JOB_DEADLINE_SECONDS,
            )
        except TimeoutError:
            log.warning("feed: a background learning job hit its %ss deadline", JOB_DEADLINE_SECONDS)
            return None
        except Exception:
            log.exception("feed: a background learning job failed")
            return None
        if result.items:
            # Every card's spoken twin, pre-rendered (`app.delivery.feed.compose._say_ahead`'s
            # own docstring) — the network call (`speak_ahead`) with no session open, then a
            # short write only when one actually failed (#297 defect 1: this is the same
            # pattern as `run_job` above, and for the same reason).
            results = await speak_ahead(engine, context, result.items)
            if any(outcome.failed is not None for outcome in results):
                async with _own_session(sessions) as session:
                    await record_say_ahead_failures(session, context=context, results=results)
        return result


async def _run(
    key: tuple[uuid.UUID, str],
    *,
    context: KeyContext,
    engine: Engine,
    day: Day,
    sessions: async_sessionmaker[AsyncSession],
    resuming: bool = False,
    max_jobs_per_run: int = MAX_JOBS_PER_RUN,
) -> None:
    record = _runs[key]
    try:
        planned = await _plan(sessions, context=context, engine=engine, day=day)
        if planned is None or not planned[0].jobs:
            # Nothing due right now. `resuming` tells apart the day's first check (truly
            # nothing was ever due: "none") from a later replan that found nothing left to
            # retry (a run already happened today: stay "done", never regress it to "none").
            record.state = "done" if resuming else "none"
            record.worth_rechecking = False
            record.done_at = utcnow()
            return
        plan, house, keys = planned
        # The plan's *first* N jobs, in the plan's own order (the broker's — see
        # `MAX_CONCURRENT_JOBS`'s docstring on why that order matters): the rest are left
        # exactly as `plan_learning_jobs` found them, never run, never marked done, so they
        # stay due for a later run by their own ordinary cadence (`app.delivery.feed.search.
        # due`) — ordinarily the next day's, unless something else about them is due sooner.
        run_jobs = plan.jobs[:max_jobs_per_run]
        deferred = len(plan.jobs) - len(run_jobs)
        record.deferred = deferred
        if deferred:
            log.info(
                "feed: plan held %d learning jobs, capped at %d; deferring %d to a later run",
                len(plan.jobs),
                max_jobs_per_run,
                deferred,
            )
        log.info("feed: running %d learning jobs in the background", len(run_jobs))
        calls_before = call_counter.counts()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        made = 0
        failed = 0

        async def _one(job: SearchJob) -> None:
            nonlocal made, failed
            result = await _run_one(
                sessions, semaphore, context=context, engine=engine, house=house, plan=plan, keys=keys, job=job
            )
            if result is None or result.failed:
                failed += 1
            else:
                made += len(result.items)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(_one(job) for job in run_jobs)), timeout=RUN_DEADLINE_SECONDS
            )
        except TimeoutError:
            log.warning("feed: the background learning run hit its %ss deadline", RUN_DEADLINE_SECONDS)
        log.info("feed: %d cards made, %d failed", made, failed)
        calls_after = call_counter.counts()
        run_calls = {
            key: calls_after[key] - calls_before.get(key, 0)
            for key in calls_after
            if calls_after[key] > calls_before.get(key, 0)
        }
        log.info(
            "feed: %d external model calls this run (%s)",
            sum(run_calls.values()),
            ", ".join(f"{task.value}/{model}={count}" for (task, model), count in sorted(run_calls.items()))
            or "none",
        )
        record.state = "done"
        record.made = made
        record.failed = failed
        record.done_at = utcnow()
        # #297 defect 2: a job left `FAILED` by `write_job_results` (its own search or
        # compression call failed, not a clean "nothing for him") is still due, up to its
        # retry limit — `failed_jobs_due` checks exactly that, never a job that merely raised
        # or is due by its ordinary cadence (see its own docstring for why the distinction
        # matters: those were already, quietly, "due again" before this fix, and reopening a
        # finished run for them is not what #297 asked for). `ensure_learning_scheduled`
        # checks this flag to decide whether a later `GET /feed` today is worth another look.
        async with _own_session(sessions) as session:
            record.worth_rechecking = await failed_jobs_due(session, context=context, day=day)
    except Exception:
        log.exception("feed: the background learning run failed")
        record.state = "done"
        record.worth_rechecking = True
        record.done_at = utcnow()
        raise


__all__ = ["RunRecord", "drain", "ensure_learning_scheduled", "run_state"]
