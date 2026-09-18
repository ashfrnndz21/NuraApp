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
    say_ahead,
)
from app.delivery.feed.days import Day
from app.delivery.feed.models import FeedItem, SearchJob
from app.delivery.feed.search import Engine, run_job
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.medicines.service import LineView, active_lines
from app.state.service import current_state

log = logging.getLogger("nura.delivery.feed")

MAX_CONCURRENT_JOBS = 2
"""At most this many self-searches in flight at once for one run."""

JOB_DEADLINE_SECONDS = 60
"""One job — one search, its pages, their compression — gets at most this long."""

RUN_DEADLINE_SECONDS = 300
"""The whole day's catch-up, however many jobs it holds, gets at most this long."""

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
) -> RunRecord | None:
    """Called from `GET /feed` after the page is built. Starts today's catch-up at most once:
    a record already here — "looking", "done", or "none" — means a run for today has already
    been claimed (by this call or an earlier one) and this does nothing more. Never awaited on
    the slow part: the task this starts runs on its own, after this function has returned."""
    key = (context.profile_id, day.key)
    if key in _runs:
        return _runs[key]
    _runs[key] = RunRecord(state="looking", started_at=utcnow())
    task = asyncio.create_task(_run(key, context=context, engine=engine, day=day, sessions=sessions))
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
) -> list[FeedItem] | None:
    """`None` means this job failed (raised, or ran past its deadline) — told apart from a
    job that ran cleanly and simply found nothing (`[]`), so the run's own "N cards made, M
    failed" line counts what actually went wrong, not every job that came back empty."""
    async with semaphore:
        try:
            async with _own_session(sessions) as session:
                # `job` was loaded (or just created) on `_plan`'s own session, already closed
                # by the time this one opens — detached, so a plain attribute write on it
                # (`run_job` sets `status`, `last_run_at`, `results`) is never part of this
                # session's unit of work and is silently lost at commit, however cleanly the
                # job itself ran: `session.merge` first, so every write `run_job` makes lands
                # on an instance this session actually tracks.
                job = await session.merge(job)
                items = await asyncio.wait_for(
                    run_job(
                        session,
                        context=context,
                        job=job,
                        engine=engine,
                        state=await current_state(session, context=context),
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
        if items:
            async with _own_session(sessions) as session:
                await say_ahead(session, engine, context, items)
        return items


async def _run(
    key: tuple[uuid.UUID, str],
    *,
    context: KeyContext,
    engine: Engine,
    day: Day,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    record = _runs[key]
    try:
        planned = await _plan(sessions, context=context, engine=engine, day=day)
        if planned is None or not planned[0].jobs:
            record.state = "none"
            record.done_at = utcnow()
            return
        plan, house, keys = planned
        log.info("feed: running %d learning jobs in the background", len(plan.jobs))
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
        made = 0
        failed = 0

        async def _one(job: SearchJob) -> None:
            nonlocal made, failed
            items = await _run_one(
                sessions, semaphore, context=context, engine=engine, house=house, plan=plan, keys=keys, job=job
            )
            if items is None:
                failed += 1
            else:
                made += len(items)

        try:
            await asyncio.wait_for(
                asyncio.gather(*(_one(job) for job in plan.jobs)), timeout=RUN_DEADLINE_SECONDS
            )
        except TimeoutError:
            log.warning("feed: the background learning run hit its %ss deadline", RUN_DEADLINE_SECONDS)
        log.info("feed: %d cards made, %d failed", made, failed)
        record.state = "done"
        record.done_at = utcnow()
    except Exception:
        log.exception("feed: the background learning run failed")
        record.state = "done"
        record.done_at = utcnow()
        raise


__all__ = ["RunRecord", "drain", "ensure_learning_scheduled", "run_state"]
