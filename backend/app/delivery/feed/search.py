"""Self-search: a job the engine runs for him, against the allowlist, through the two ports.

A job is made from a gap State shows — a medicine with no explainer, a condition with none —
or by the owner or his chief by hand. It names the sources it may read, every one of them
usable at the time, and `run_job` reads no others. What comes back goes through the
compressor; what the compressor returns is checked — cited, in his language — and only then
becomes a learning card through `items.create_item`, which checks the source and the words
again, and refuses outright anything that would change treatment (#236,
`items.TreatmentChangingCard`). A finding like that is not lost: it is held for his chief as
a card that says a finding needs her doctor's look, never the finding's own words, and — a
real drug name known or not — becomes a real question for the doctor
(`reasoning.visits.memos.write_memo`), never a `FeedItem` nothing reads.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.db import nested_unit_of_work, utcnow
from app.delivery.feed.clips import ClipRenderer, clip_length_ok, may_excerpt
from app.delivery.feed.compress import (
    Compressed,
    Compressor,
    Found,
    PortUnavailable,
    Searcher,
    changes_treatment,
)
from app.delivery.feed.days import Day, plain_day
from app.delivery.feed.items import NotPlainWords, Why, create_item
from app.delivery.feed.local import (
    area_matches,
    check_hazard,
    check_season_term,
    open_season,
    relevant_to,
)
from app.delivery.feed.models import (
    CardFormat,
    CardType,
    DeliverTo,
    FeedItem,
    JobKind,
    JobStatus,
    SearchJob,
)
from app.delivery.feed.sources import (
    SourceNotAllowlisted,
    require_manager,
    require_usable_source,
    usable_sources,
)
from app.delivery.strings import (
    YOUR_DOCTOR,
    Lines,
    language_for,
    learning_lines,
    needs_doctor_look_lines,
    recall_action_lines,
    season_name,
)
from app.delivery.voice import MAX_SECONDS, Voice, seconds_to_say
from app.drugs.registry import DrugRegistry, LabelFields, UnknownDrug
from app.errors import Refusal
from app.ingestion.objects import ObjectStore
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.language.voice_script import script_for
from app.medicines.strings import PLAIN_NAME
from app.reasoning.ranges import ReferenceRanges
from app.reasoning.visits.memos import MEMO, write_memo
from app.reasoning.visits.models import MemoKind, MemoSource
from app.reasoning.visits.strings import NotASlotValue, medicine_words
from app.state.models import Dimension
from app.state.service import StateView

log = logging.getLogger("nura.delivery.search")

JOB_TARGET = SearchJob.__tablename__
LEARNING_LIFETIME = timedelta(days=90)
"""Evergreen: a learning card stays in the supply for a season, then is made again if the
gap is still there."""


class NoSuchSearchJob(Refusal):
    """No search job by that id on this profile."""


class NoTerms(Refusal):
    """A search job searches for something."""


class NotACadence(Refusal):
    """How often a search runs: on a change, daily, weekly, or before visits."""


class FastingIsHisToSay(Refusal):
    """Whether he fasts in Ramadan is his to say — it speaks of his faith — so a watch for the
    fasting month is added on his own key, or the steward's who holds his papers for him;
    never by a chief or anyone else, and never guessed."""


HIS_OWN_WORD: frozenset[str] = frozenset({"fasting month"})
"""The watches only he (or his steward) may add: those that say something about his faith."""

FAITH_WORDS: tuple[str, ...] = ("fasting month", "ramadan", "ramadhan", "puasa", "斋戒")
"""The words that say something about his faith wherever they stand in a watch's terms, and
whatever kind of watch it is: "ramadan" asked for as an explainer is the same guess about him
as the fasting month asked for as a season. ("Fasting" alone is his word for no food before a
blood test, and says nothing about his faith.)"""


def speaks_of_his_faith(terms: Sequence[str]) -> bool:
    """Whether a watch's terms say something about his faith (`FAITH_WORDS`)."""
    return any(word in term.strip().lower() for term in terms for word in FAITH_WORDS)


CADENCES = frozenset({"on_change", "daily", "weekly", "before_visits", "once"})
DEFAULT_CADENCE: Mapping[JobKind, str] = {
    JobKind.EXPLAINER: "on_change",
    JobKind.SAFETY: "daily",
    JobKind.LOCAL: "daily",
    JobKind.SEASONAL: "weekly",
    JobKind.FOOD: "weekly",
    JobKind.PROVIDER: "before_visits",
    JobKind.WORTH_KNOWING: "weekly",
}
"""How often each kind runs when nobody says: an explainer when the record changes, a safety
or local bulletin every day, a season or a food card every week."""

FOOD_HELD_FOR: frozenset[str] = frozenset({"kidneys", "kidney_watched"})
"""The conditions whose food a dietitian sets: no general food card, and no season's card
(festive food, breaking the fast with dates), is made for them."""


@dataclass(frozen=True, slots=True)
class Around:
    """What a run knows about him besides the State: the day on his wall clock, his area (on
    this server only), the conditions he told and the medicines on his list (to decide whether
    a local bulletin is for him), and the formats his feed has settled on."""

    day: Day
    area: str | None = None
    conditions: tuple[str, ...] = ()
    medicines: tuple[str, ...] = ()
    format: CardFormat = CardFormat.TEXT
    clips_as_cards: bool = False
    """Two clips went unplayed (E11-08): a video comes as a voice note instead of a clip."""
    fact_ids: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    """The fact each condition and medicine rests on, by its code or generic name."""


@dataclass(frozen=True, slots=True)
class Engine:
    """The ports the feed composes from, as one deployment has them: the searcher and the
    compressor (fixtures here; real adapters later), the licensed drug registry
    (`app.drugs`) the medicines module reads a line's plain name and count through, and the
    reference ranges a lab result is placed against for a story card (E09-01, E21-05) — None
    where a deployment has not named them, and then no lab story is told."""

    searcher: Searcher
    compressor: Compressor
    registry: DrugRegistry
    ranges: ReferenceRanges | None = None
    voice: Voice | None = None
    store: ObjectStore | None = None
    """Where a card's spoken twin is said and kept the moment the card is made (E22-03): the
    one voice port, and the region's object store. None, and the twin is said on its first
    play instead (`app.delivery.feed.twin`)."""
    clips: ClipRenderer | None = None
    """What makes a clip's still and, where the licence allows, its excerpt (E09-06,
    `app.delivery.feed.clips`). None, and a clip is its narration and captions alone."""


@audited(Action.WRITE, Scope.RECORDS, JOB_TARGET)
async def create_job(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: JobKind,
    terms: Sequence[str],
    reason: Mapping[str, Any],
    source_ids: Sequence[uuid.UUID] | None = None,
    cadence: str | None = None,
) -> SearchJob:
    """Queue a self-search for this profile, scoped to usable sources only.

    The owner's and his chief's to make (`NotTheirsToManage`). Named sources are each
    checked against the allowlist (`SourceNotAllowlisted`); none named means every usable
    source in the profile's region. A local watch is for dengue, haze or heat
    (`NotAHazard`); a seasonal one for a season Nura knows (`NotASeason`). How often it runs is
    the kind's own unless one is named (`NotACadence`).
    """
    await require_manager(session, context=context, target=JOB_TARGET)
    cleaned = [term.strip().lower() for term in terms if term.strip()]
    if not cleaned:
        raise NoTerms("a search job needs at least one term")
    if kind is JobKind.LOCAL:
        cleaned = [check_hazard(term) for term in cleaned]
    elif kind is JobKind.SEASONAL:
        cleaned = [check_season_term(term) for term in cleaned]
    if speaks_of_his_faith(cleaned) and not (context.is_owner or context.is_steward):
        refusal = FastingIsHisToSay(f"a {context.role} key does not say whether he fasts")
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=JOB_TARGET,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
        )
        refusal.written_down = True
        raise refusal
    cadence = cadence or DEFAULT_CADENCE[kind]
    if cadence not in CADENCES:
        raise NotACadence(f"{cadence!r} is not a cadence a search runs on")
    sources = await usable_sources(session, region=context.region, source_ids=source_ids)
    return await audited_write(
        session,
        SearchJob,
        context,
        Scope.RECORDS,
        kind=kind,
        terms=cleaned,
        source_ids=[str(source.id) for source in sources],
        cadence=cadence,
        reason=dict(reason),
        status=JobStatus.QUEUED,
        results={},
        enabled=True,
        created_by_person_id=context.person_id,
        created_at=utcnow(),
    )


@audited(Action.READ, Scope.RECORDS, JOB_TARGET)
async def list_jobs(session: AsyncSession, *, context: KeyContext) -> Sequence[SearchJob]:
    await require_manager(session, context=context, target=JOB_TARGET)
    # `.id` breaks a tie in `created_at` (#192/#218): a management listing, every job shown
    # regardless of order, so a stable-but-arbitrary tiebreaker is enough.
    return await audited_read(
        session,
        SearchJob,
        context,
        Scope.RECORDS,
        order_by=(SearchJob.created_at.desc(), SearchJob.id.asc()),
    )


@audited(Action.READ, Scope.RECORDS, JOB_TARGET)
async def get_job(session: AsyncSession, *, context: KeyContext, job_id: uuid.UUID) -> SearchJob:
    await require_manager(session, context=context, target=JOB_TARGET)
    found = await audited_read(
        session, SearchJob, context, Scope.RECORDS, where=(SearchJob.id == job_id,)
    )
    if not found:
        raise NoSuchSearchJob(f"no search job {job_id} on profile {context.profile_id}")
    return found[0]


async def jobs_looking_today(session: AsyncSession, *, context: KeyContext, day: Day) -> bool:
    """Whether any of his self-searches is due to run today and has not run yet — for the
    feed's own "Nura is looking for today's reads" line (docs/design-direction.md,
    'Conversation, waiting and thinking'), never the watches list itself (`list_jobs`,
    owner/chief only, #185): a plain read of the same rows `_learning` already runs inline,
    synchronously, within `GET /feed` (`app.delivery.feed.compose._learning`'s own module
    docstring: "a daily or weekly one that has not run today or this week runs again") — so
    this is never a guess at what the request that follows will actually do, only a read of
    whether it has work left before it runs. `due` is the exact rule `_learning` itself
    calls; this changes nothing and writes nothing."""
    jobs = await audited_read(session, SearchJob, context, Scope.RECORDS)
    return any(due(job, day) for job in jobs)


async def failed_jobs_due(session: AsyncSession, *, context: KeyContext, day: Day) -> bool:
    """Whether any of his jobs was left `FAILED` by its last attempt and is still due for a
    retry today (#297 defect 2) — never a job that has simply never run, or one due again by
    its ordinary cadence: those already surface through `jobs_looking_today`, and reopening a
    day's finished run for them is out of this fix's scope (`app.delivery.feed.background.
    _run`'s own `resuming` check would otherwise put a crashed-but-never-written-down job
    straight back in the plan, which is not what #297 asked for — a job that raised is
    already naturally due again next time, the same as it always was; only a job this module
    itself marked `FAILED` gets the extra "worth reopening a finished run for" treatment)."""
    jobs = await audited_read(session, SearchJob, context, Scope.RECORDS)
    return any(job.status is JobStatus.FAILED and due(job, day) for job in jobs)


async def pause_job(
    session: AsyncSession, *, context: KeyContext, job_id: uuid.UUID, enabled: bool
) -> SearchJob:
    """Pause a watch, or resume it ("Watching for Pa"). A paused job is not run again; the
    cards it made stay what they were. The owner's and his chief's to do, and on the trail —
    except a watch about his faith (the fasting month), which only he or his steward pauses or
    resumes (`FastingIsHisToSay`)."""
    job = await get_job(session, context=context, job_id=job_id)
    if speaks_of_his_faith(job.terms) and not (context.is_owner or context.is_steward):
        # His yes or his no about Ramadan is his: his chief neither resumes a watch he
        # stopped nor stops one he asked for.
        refusal = FastingIsHisToSay(f"a {context.role} key does not say whether he fasts")
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.RECORDS,
            target=JOB_TARGET,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
        )
        refusal.written_down = True
        raise refusal
    job.enabled = enabled
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.RECORDS,
        target=JOB_TARGET,
        rows=1,
        target_id=job.id,
    )
    return job


FAILED_JOB_RETRY_LIMIT = 3
"""A job whose own search or compression call failed (`app.delivery.feed.compress.
PortUnavailable` — an API error, a timeout, a dead connection, never a clean "nothing for
him") is retried the same day, whatever its cadence, up to this many attempts (#297 defect
2) — enough to ride out a short outage without hammering a dead API for the rest of the day.
Past the limit `due` falls back to the job's normal cadence, same as any other job."""


def _failed_attempts_today(job: SearchJob, day: Day) -> int:
    """How many times `write_job_results` has already marked this job `FAILED` today. Reads
    `job.results`, the same row `write_job_results` writes it to — no new column: a run
    that finally succeeds overwrites `results` with its own clean shape (no `failed_attempts`
    key), so the count starts back at zero the next time the job fails, on any day."""
    if job.status is not JobStatus.FAILED:
        return 0
    if job.results.get("failed_day") != day.key:
        return 0
    return int(job.results.get("failed_attempts") or 0)


def due(job: SearchJob, day: Day) -> bool:
    """Whether a job that has run should run again today: a daily one not yet today, a
    weekly one not yet this week. One that runs on a change, or before visits, runs when that
    happens; a paused one does not run.

    A job left `FAILED` by its last attempt is due again regardless of cadence, up to
    `FAILED_JOB_RETRY_LIMIT` attempts the same day (#297 defect 2) — a search that could not
    even run is not "looked at and found nothing"."""
    if not job.enabled:
        return False
    if job.status is JobStatus.FAILED and _failed_attempts_today(job, day) < FAILED_JOB_RETRY_LIMIT:
        return True
    if job.last_run_at is None:
        return True
    last = job.last_run_at if job.last_run_at.tzinfo else job.last_run_at.replace(tzinfo=day.now.tzinfo)
    if job.cadence == "daily":
        return last < day.starts_at
    if job.cadence == "weekly":
        return last < day.week_starts_at
    return False


def _hash(found: Found) -> str:
    return hashlib.sha256(found.url.encode()).hexdigest()[:24]


def _dedupe_key(job_id: uuid.UUID, found: Found, language: str) -> str:
    return f"learning:{job_id}:{_hash(found)}:{language}"


def _narrates_in_time(lines: Sequence[str], language: str, boundary: str | None) -> bool:
    """Whether a clip's narration — its lines, the boundary last — is said in thirty seconds."""
    spoken = script_for(lines, language, boundary=boundary).spoken()
    return seconds_to_say(spoken, language) <= MAX_SECONDS


def _food_pick(found: Sequence[Found], day: Day) -> list[Found]:
    """One food card a week (spec §2): the pages in a fixed order, one of them each week, in
    turn."""
    if not found:
        return []
    ordered = sorted(found, key=lambda one: one.url)
    week = day.local.isocalendar()[1]
    return [ordered[week % len(ordered)]]


def _facts_for(state: StateView) -> Mapping[str, Any]:
    """What the compressor may ground on: the clinical facts the snapshot holds, by id."""
    clinical = state.dimension(Dimension.CLINICAL)
    return {} if clinical is None else dict(clinical.get("facts", {}))


@dataclass(frozen=True, slots=True)
class JobPrep:
    """What a job needs read from the record before it may search or compress: the domains
    of its own usable sources, named when it was made (`create_job`, `SearchJob.source_ids`)
    — nothing else. Safe to carry into the network phase, when no session is open (#297
    defect 1)."""

    domains: list[str]


async def prepare_job(session: AsyncSession, *, context: KeyContext, job: SearchJob) -> JobPrep:
    """Phase 1 of `run_job`: the one database read a job needs before it may search, so its
    caller can commit and close this session before the network phase starts."""
    sources = await usable_sources(
        session, region=context.region, source_ids=[uuid.UUID(one) for one in job.source_ids]
    )
    return JobPrep(domains=[source.domain for source in sources])


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One found page that passed every check `search_and_compress` can make without a
    database session, compressed and ready for `write_job_results` to turn into a card — or
    reject for want of an allowlisted source, the one check left that still needs a row."""

    found: Found
    compressed: Compressed
    season: Any
    key: str


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """Everything `search_and_compress` made of a job's network calls, for `write_job_results`
    to turn into cards with no network call of its own left to make."""

    candidates: tuple[_Candidate, ...]
    rejected: list[dict[str, str]]
    domains: list[str]
    reasons: list[str]
    failed_because: str | None = None
    """Set when the searcher's or the compressor's own call failed (`PortUnavailable` — an
    API error, a timeout, a dead connection), never when the job simply searched and found
    nothing to keep: `write_job_results` marks the job `FAILED`, not `DONE`, and leaves it due
    for a retry (#297 defect 2). Whatever candidates were already compressed before the
    failure are still written as real cards; only the job's own status reflects the failure,
    so a retry never remakes them (`existing` already carries their dedupe keys by then)."""


async def search_and_compress(
    engine: Engine,
    job: SearchJob,
    prep: JobPrep,
    *,
    state: StateView,
    language: str,
    around: Around,
    existing: set[str],
) -> SearchOutcome:
    """Phase 2 of `run_job`: every network call a job makes — the search, then each kept
    page's compression — and nothing else. No session parameter, deliberately: this must
    never run with a database transaction open (#297 defect 1). On SQLite every transaction
    begins IMMEDIATE and holds the write lock for its whole life, not just its first write
    (`app.db.make_engine`'s own docstring) — so a session open here would block every other
    request on the process for as long as the search and the compression take, the bug that
    held `resolve_session` (every authenticated request) behind `sqlite3.OperationalError:
    database is locked` for minutes on 2026-09-18.

    Every check that does not need a database row runs here, in the same order `run_job`
    always ran it, so a page already on the profile (`existing`) is never compressed for
    nothing: relevance, the kidney-diet hold, the food pick, whether the page is really on
    the domain it claims (`on_its_source` — DB-free: a `require_usable_source` row's own
    `.domain` is always `found.domain` by construction of that query, so this needs no row),
    his area, its season, its dedupe key. The one check that does need a row — whether that
    domain is still a *usable*, allowlisted source right now — waits for `write_job_results`,
    after compression: the job's own `source_ids` already bounded what was searched
    (`prepare_job`'s `prep.domains`), so this only ever re-confirms it, the rare exception a
    searcher returning a page off its own list.
    """
    code = language_for(language)
    day = around.day
    domains = prep.domains
    rejected: list[dict[str, str]] = []
    try:
        # `Searcher.search` is a synchronous port (the real adapter's own `messages.create`
        # call, `ClaudeSearcher._ask`), so awaiting it directly would block this event loop —
        # every other request on the process, not just this job — for as long as the search
        # and fetch take. `asyncio.to_thread` runs it off-thread; the fixture searcher in
        # tests pays a thread hop for nothing, which is cheap next to never blocking the real
        # one.
        found_pages = list(
            await asyncio.to_thread(engine.searcher.search, job.kind.value, job.terms, domains)
        )
    except PortUnavailable as failed:
        return SearchOutcome(
            candidates=(),
            rejected=[],
            domains=domains,
            reasons=[],
            failed_because=f"search_failed:{failed}",
        )
    reasons: list[str] = []
    if job.kind is JobKind.LOCAL:
        reasons = relevant_to(job.terms[0], around.conditions, around.medicines)
        if not reasons:
            # Not for him: no condition or medicine on his record makes this hazard relevant
            # (E09-07). Nothing is compressed and nothing is made.
            for found in found_pages:
                rejected.append({"url": found.url, "because": "not_relevant_to_his_record"})
            found_pages = []
    if job.kind in (JobKind.FOOD, JobKind.SEASONAL) and FOOD_HELD_FOR & set(around.conditions):
        # His kidneys are on his record: a kidney diet (less potassium and phosphate) is a
        # dietitian's to set, and a general food choice could go against it — a season's card
        # too (mooncakes; dates to break the fast, which are high in potassium). No card.
        for found in found_pages:
            rejected.append({"url": found.url, "because": "held_for_his_dietitian"})
        found_pages = []
    if job.kind is JobKind.FOOD:
        found_pages = _food_pick(
            [one for one in found_pages if one.domain in domains], day
        ) + [one for one in found_pages if one.domain not in domains]
    candidates: list[_Candidate] = []
    seen: set[str] = set()
    for found in found_pages:
        if not on_its_source(found.url, found.domain):
            # The page a card links to is on the allowlisted site itself, over https, or the
            # card is not made: a searcher cannot put another site's link on his card.
            rejected.append({"url": found.url, "because": "not_on_its_source"})
            continue
        if job.kind is JobKind.LOCAL and not area_matches(around.area, found.areas):
            rejected.append({"url": found.url, "because": "not_his_area"})
            continue
        season = open_season(found.season, day.local.date()) if found.season else None
        if job.kind is JobKind.SEASONAL and season is None:
            rejected.append({"url": found.url, "because": "not_in_season"})
            continue
        if (
            job.kind is JobKind.SEASONAL
            and season is not None
            and season.season.conditions
            and not season.season.conditions & set(around.conditions)
        ):
            # The season's page is written for a condition he has not told ("fasting safely
            # with diabetes"): not for him, however the watch was added.
            rejected.append({"url": found.url, "because": "not_relevant_to_his_record"})
            continue
        key = _key_for(job, found, code, day, season.starts.year if season else None)
        if key in existing or key in seen:
            # Already a card on the profile (or already claimed by an earlier page this same
            # job found): never worth a compress call. Moved ahead of compression itself
            # (`run_job`'s own history checked this only after compressing — see #297's PR
            # for why that reordering is safe: the key never depended on the compressed
            # text, only on the job, the page and its season, all already known here).
            continue
        try:
            # Same reason as the search call above: `Compressor.compress` is synchronous too
            # (the real adapter's own model call), so it also runs off-thread.
            compressed = await asyncio.to_thread(
                engine.compressor.compress, found.text, code, _facts_for(state)
            )
        except PortUnavailable as failed:
            return SearchOutcome(
                candidates=tuple(candidates),
                rejected=rejected,
                domains=domains,
                reasons=reasons,
                failed_because=f"compress_failed:{failed}",
            )
        if compressed is None:
            rejected.append({"url": found.url, "because": "nothing_for_him_in_" + code})
            continue
        if not compressed.passage.strip():
            rejected.append({"url": found.url, "because": "uncited"})
            continue
        seen.add(key)
        candidates.append(_Candidate(found=found, compressed=compressed, season=season, key=key))
    return SearchOutcome(
        candidates=tuple(candidates), rejected=rejected, domains=domains, reasons=reasons
    )


async def write_job_results(
    session: AsyncSession,
    *,
    context: KeyContext,
    job: SearchJob,
    engine: Engine,
    state: StateView,
    language: str,
    around: Around,
    doctor: str | None,
    existing: set[str],
    outcome: SearchOutcome,
) -> list[FeedItem]:
    """Phase 3 of `run_job`: every database read and write a job's results need, and no
    network call of its own — safe inside any short unit of work, opened fresh after
    `search_and_compress` has already finished waiting on the network (#297 defect 1). Turns
    `outcome`'s compressed candidates into cards exactly the way `run_job` always has —
    notices, recalls, a treatment-changing finding rerouted as a doctor's question, the
    plain-words check — re-checking here the one thing `search_and_compress` could not
    without a session: that each candidate's domain is still a usable, allowlisted source.

    Writes the job's own `status`/`last_run_at`/`results` at the end: `FAILED`, not `DONE`,
    when `outcome.failed_because` is set, so `due` (#297 defect 2) leaves it due for a retry
    instead of writing it down as looked at and done.
    """
    code = language_for(language)
    day = around.day
    moment = utcnow()
    reasons = outcome.reasons
    made: list[FeedItem] = []
    questions: list[FeedItem] = []
    rejected: list[dict[str, str]] = list(outcome.rejected)
    for candidate in outcome.candidates:
        found = candidate.found
        compressed = candidate.compressed
        season = candidate.season
        key = candidate.key
        if key in existing:
            continue
        try:
            source = await require_usable_source(
                session, region=context.region, domain=found.domain
            )
        except SourceNotAllowlisted:
            rejected.append({"url": found.url, "because": "not_allowlisted"})
            continue
        cite: dict[str, Any] = {
            # The page the card cites, for the card to show and link (E21-06): who published
            # it, where, and the passage the lines came from.
            "publisher": source.name,
            "domain": source.domain,
            "url": found.url,
            "title": found.title,
            "published_at": found.published_at,
            "passage": compressed.passage,
            "start_sec": compressed.start_sec,
            "end_sec": compressed.end_sec,
        }
        if found.media == "video":
            # A video on an allowlisted site: the card links to the whole of it there, and the
            # server keeps an excerpt only where the licence allows reuse (spec §7).
            cite |= {
                "media": "video",
                "full_url": found.url,
                "licence": found.licence,
                "excerpt": may_excerpt(found.licence)
                and engine.clips is not None
                and engine.clips.excerpts,
            }
        if job.kind is JobKind.SAFETY:
            # A notice is never his card, batch match or not (spec §0, §9; #181): it is held
            # for the chief, capped like any other of hers — ALWAYS, because she must hear
            # about a recall on his own box whatever else is true of it (#224 review finding:
            # a `continue` here used to skip the caregiver notice entirely whenever the words
            # also read as a treatment change, so the most urgent notice reached nobody).
            # When its words would start, stop or change a medicine, the card is never those
            # words (#236, `items.TreatmentChangingCard`): a safety job always names the
            # medicine it watches (`job.terms[0]`), so the caregiver's card is rerouted to
            # `needs_doctor_look_lines` and a real question is filed for the doctor
            # (`reasoning.visits.memos.write_memo`) — the caregiver still gets a card, never
            # nothing, and never a `FeedItem` nobody reads (`DeliverTo.MEMO` is not a supply
            # any route or ranking serves). The notice's own words — whichever of the two —
            # never reach `create_item` with `DeliverTo.PATIENT` (`NoticeNotForPatient`); where
            # the batch on his own pack matches (#183), he still gets his own `RECALL_ACTION`
            # card below, in fixed catalogue words that never repeat the notice's own text.
            matches = found.batch is not None and found.batch.strip().lower() in _batches_on_record(
                state
            )
            notice_lines = learning_lines(
                code,
                headline=compressed.headline,
                body=compressed.body,
                topic=compressed.why_topic,
                source_name=source.name,
                doctor=doctor or YOUR_DOCTOR[code],
            )
            fact_ids = tuple(_fact_ids_about(state, job.terms))
            suppressed = None if matches else "batch_does_not_match_the_pack"
            if changes_treatment([notice_lines.headline, *notice_lines.body]):
                memo_id = await _ask_the_doctor(
                    session,
                    context=context,
                    state=state,
                    code=code,
                    doctor=doctor,
                    generic=job.terms[0],
                    registry=engine.registry,
                    source_id=source.id,
                )
                rejected.append(
                    {
                        "url": found.url,
                        "because": "treatment_change_rerouted_as_question",
                        "memo_id": memo_id or "not_filed",
                    }
                )
                lines = needs_doctor_look_lines(code, doctor=doctor or YOUR_DOCTOR[code])
                why = Why(
                    kind="needs_doctor_look",
                    plain=lines.why,
                    source_id=str(source.id),
                    gap=job.terms[0],
                    fact_ids=fact_ids,
                    suppressed=suppressed,
                    memo_id=memo_id,
                )
            else:
                lines = notice_lines
                why = Why(
                    kind="notice",
                    plain=notice_lines.why,
                    source_id=str(source.id),
                    gap=job.terms[0],
                    fact_ids=fact_ids,
                    suppressed=suppressed,
                )
            notice = await create_item(
                session,
                context=context,
                state=state,
                type=CardType.NOTICE,
                lines=lines,
                why=why,
                scope=Scope.MEDICINES,
                deliver_to=DeliverTo.CAREGIVER,
                day=day.key,
                dedupe_key=key,
                expires_at=moment + LEARNING_LIFETIME,
                format=around.format,
                source=source,
                cite={**cite, "batch": found.batch},
                search_job_id=job.id,
            )
            existing.add(key)
            made.append(notice)
            if matches:
                # His own pack is one of the recalled batches (#183): he gets his own card,
                # in his own words, saying what he can do about the box in his hand today —
                # never the notice's own words above, whether they stayed `notice_lines` or
                # were rerouted to `needs_doctor_look_lines`; both stay his chief's to read.
                action_key = f"{key}:recall_action"
                action_lines = recall_action_lines(
                    code,
                    medicine=_plain_medicine_name(engine, job.terms[0], code),
                    doctor=doctor or YOUR_DOCTOR[code],
                )
                try:
                    action = await create_item(
                        session,
                        context=context,
                        state=state,
                        type=CardType.RECALL_ACTION,
                        lines=action_lines,
                        why=Why(
                            kind="recall_action",
                            plain=action_lines.why,
                            source_id=str(source.id),
                            gap=job.terms[0],
                            fact_ids=fact_ids,
                        ),
                        scope=Scope.MEDICINES,
                        deliver_to=DeliverTo.PATIENT,
                        day=day.key,
                        dedupe_key=action_key,
                        expires_at=moment + LEARNING_LIFETIME,
                        format=around.format,
                        source=source,
                        cite={**cite, "batch": found.batch},
                        search_job_id=job.id,
                    )
                except NotPlainWords as failed:
                    rejected.append(
                        {"url": found.url, "because": "not_plain_words", "detail": str(failed)}
                    )
                    continue
                existing.add(action_key)
                made.append(action)
            continue
        # #236: a page whose words would start, stop or change a medicine is never simply
        # dropped, whichever job found it, and it is never addressed to anyone in its own
        # words (`items.TreatmentChangingCard`) — the caregiver gets a card that says a
        # finding needs her doctor's look and points at the question filed for him
        # (`needs_doctor_look_lines`), the same card she would have had, rerouted. A doctor
        # question is filed whenever the finding is treatment-changing, whether or not a real
        # drug name is known: where the job's own terms name a medicine he takes, the question
        # asks about it by name (`_ask_the_doctor`, the same door #224 built for a safety
        # notice); a local hazard, a season or a food page names no medicine, so the question
        # asks about "your medicines" generally instead — a name-free memo key, never nothing.
        # This replaces a `CardType.QUESTION`/`DeliverTo.MEMO` `FeedItem` that used to stand
        # here — nothing reads `DeliverTo.MEMO` (`rank.py`'s two supplies exclude it, no route
        # queries it), so that card reached nobody at all.
        #
        # Whether a real drug name is known cannot be read off `job.reason["scope"]` — a watch
        # added by hand (`add_search_job`) builds `reason={"asked": ..., "by": ...}` with no
        # `"scope"` at all, so a chief who names a medicine he takes got no doctor question
        # when its finding changed treatment. Decided instead from whether the job's own first
        # term actually is a medicine on his list (`_medicine_he_takes`), which is true for
        # every planner-made job too (`compose._gaps` only ever names his own medicines with a
        # `"medicines"` reason), so this changes nothing for those.
        treatment_changing = changes_treatment([compressed.headline, *compressed.body])
        is_medicine_job = bool(job.terms) and _medicine_he_takes(
            job.terms[0], around, engine.registry
        )
        shape = _shape(
            job.kind,
            found,
            compressed,
            code=code,
            source_name=source.name,
            doctor=doctor or YOUR_DOCTOR[code],
            around=around,
            season=season,
            about_a_medicine=is_medicine_job,
        )
        if shape.cite:
            cite |= shape.cite
        fact_ids = tuple(
            sorted(
                {*_fact_ids_about(state, job.terms)}
                | {one for reason in reasons for one in around.fact_ids.get(reason, ())}
            )
        )
        scope = _scope_of(job, reasons, around, engine.registry)
        # RE-07: a job the broker's slate proposed (`compose._broker_wanted`) carries its
        # rule id, boosts and topic in its own `reason` — never guessed back from the words,
        # which the broker never writes (module doc). A job the state's own gaps proposed
        # carries none of these, and `Why.rule`/`Why.topic` are `None` for it, as before.
        rule = job.reason.get("rule")
        boosts = tuple(job.reason.get("boosts") or ())
        topic = job.reason.get("topic")
        # Independent safety review, item 2: a candidate resting on his own private search
        # history names `Candidate.private_to` (§3.5), and `_broker_wanted` now carries it
        # here, JSON-stringified. Read back to a `uuid.UUID` (or `None` for a plain `_gaps`
        # job, which never sets it) and passed to `create_item` below so the card it becomes
        # holds the same `private_to` its candidate did — `rank.require_item`/`_visible`
        # refuse it to every key but his own, whatever her scopes (RE-01).
        private_to_raw = job.reason.get("private_to")
        private_to = uuid.UUID(private_to_raw) if private_to_raw else None
        if treatment_changing:
            # `private_to` is deliberately left off the card below: #224 already overrides
            # privacy here on purpose — a treatment-changing finding always reaches the
            # caregiver as a question for the doctor, private search topic or not.
            memo_id = await _ask_the_doctor(
                session,
                context=context,
                state=state,
                code=code,
                doctor=doctor,
                generic=job.terms[0] if is_medicine_job else None,
                registry=engine.registry,
                source_id=source.id,
            )
            rejected.append(
                {
                    "url": found.url,
                    "because": "treatment_change_rerouted_as_question",
                    "memo_id": memo_id or "not_filed",
                }
            )
            lines = needs_doctor_look_lines(code, doctor=doctor or YOUR_DOCTOR[code])
            item = await create_item(
                session,
                context=context,
                state=state,
                type=shape.type,
                lines=lines,
                why=Why(
                    kind="needs_doctor_look",
                    plain=lines.why,
                    source_id=str(source.id),
                    gap=job.terms[0],
                    fact_ids=fact_ids,
                    memo_id=memo_id,
                    rule=rule,
                    topic=topic,
                ),
                scope=scope,
                deliver_to=DeliverTo.CAREGIVER,
                day=day.key,
                dedupe_key=key,
                expires_at=_expiry(job.kind, day, moment, season),
                format=shape.format,
                source=source,
                cite=cite,
                search_job_id=job.id,
            )
        else:
            try:
                item = await create_item(
                    session,
                    context=context,
                    state=state,
                    type=shape.type,
                    lines=shape.lines,
                    why=Why(
                        kind=shape.type.value,
                        plain=shape.lines.why,
                        source_id=str(source.id),
                        gap=job.terms[0],
                        fact_ids=fact_ids,
                        boosts=boosts,
                        rule=rule,
                        topic=topic,
                    ),
                    scope=scope,
                    deliver_to=DeliverTo.PATIENT,
                    day=day.key,
                    dedupe_key=key,
                    expires_at=_expiry(job.kind, day, moment, season),
                    format=shape.format,
                    source=source,
                    cite=cite,
                    search_job_id=job.id,
                    private_to=private_to,
                )
            except NotPlainWords as failed:
                rejected.append(
                    {"url": found.url, "because": "not_plain_words", "detail": str(failed)}
                )
                continue
        existing.add(key)
        made.append(item)
    if outcome.failed_because is not None:
        attempts = _failed_attempts_today(job, day) + 1
        job.status = JobStatus.FAILED
        job.last_run_at = moment
        job.results = {
            "items": [str(item.id) for item in made],
            "questions": [str(item.id) for item in questions],
            "rejected": rejected,
            "searched": outcome.domains,
            "failed_attempts": attempts,
            "failed_day": day.key,
            "because": outcome.failed_because,
        }
    else:
        job.status = JobStatus.DONE
        job.last_run_at = moment
        job.results = {
            "items": [str(item.id) for item in made],
            "questions": [str(item.id) for item in questions],
            "rejected": rejected,
            "searched": outcome.domains,
        }
    await session.flush()
    return [*made, *questions]


async def run_job(
    session: AsyncSession,
    *,
    context: KeyContext,
    job: SearchJob,
    engine: Engine,
    state: StateView,
    language: str,
    around: Around,
    doctor: str | None,
    existing: set[str],
) -> list[FeedItem]:
    """Run one job now: search, keep what is for him, compress, check, and write the cards.

    `existing` is the dedupe keys already on the profile; a page already turned into a card
    (for this day, this week or this season, by kind) is not made twice. The job's `results`
    record every page by outcome — never his area, which stays out of the record of a search.
    What is kept, by kind:

    - a local bulletin (dengue, haze, heat) about his area — or the whole region — and only
      when a condition or medicine on his record makes it relevant; a card for today;
    - a seasonal page while its season is near or on; a card until the season ends;
    - a food page, one a week in turn;
    - a video, as a clip (narrated, captioned, 20–30 s) — or as a voice note when his clips
      have gone unplayed — and any other page as a learning card.

    Unchanged for every caller but `app.delivery.feed.background`'s own background run (the
    inline `POST .../jobs/{id}/run` path, and every test that calls this directly): the three
    phases below (`prepare_job`, `search_and_compress`, `write_job_results`), composed back
    to back on the one session already open here — fine for a single job on a caller's own
    request. `app.delivery.feed.background.run_job` is the phased variant #297 defect 1
    needed: the same three phases, called directly, each on its own short-lived session, so
    the database's write lock is never held while a background run's dozen jobs wait on the
    network one after another.
    """
    prep = await prepare_job(session, context=context, job=job)
    outcome = await search_and_compress(
        engine, job, prep, state=state, language=language, around=around, existing=existing
    )
    return await write_job_results(
        session,
        context=context,
        job=job,
        engine=engine,
        state=state,
        language=language,
        around=around,
        doctor=doctor,
        existing=existing,
        outcome=outcome,
    )


def _key_for(job: SearchJob, found: Found, code: str, day: Day, season_year: int | None) -> str:
    """A card is made once per page, per job — and, for what comes round, once per issue of a
    local bulletin, once per week (a food card) or once per season (a seasonal page).

    #236: keyed on `job.id`, not just the page and the kind. `existing` is one dedupe set
    shared across every job a run touches (`compose.refresh`), and two different jobs can find
    the same page — an EXPLAINER on "metformin" and one on "diabetes" both turning up the same
    explainer, say. Without the job in the key, whichever ran first silently claimed the page
    for both: its own `treatment_changing`/`is_medicine_job` decided whether a question got
    filed, and the second job's `if key in existing: continue` (above) skipped its page
    entirely — table row order, not anything about the finding, decided whether a question
    existed. Keying on the job makes every job's dedupe independent of every other job's, so
    running order can no longer change what gets filed; a job is still idempotent against
    itself (`job.id` is stable across `refresh()` calls for the same `(kind, terms)`,
    `compose._learning`'s `have` set reuses the row rather than making a new one)."""
    if job.kind is JobKind.LOCAL:
        # Once a bulletin: an unchanged bulletin does not take one of his two new cards a
        # day, every day. A new issue of it (its date) is a new card.
        return f"local:{job.id}:{_hash(found)}:{code}:{found.published_at or day.key}"
    if job.kind is JobKind.FOOD:
        return f"food:{job.id}:{_hash(found)}:{code}:{day.week}"
    if job.kind is JobKind.SEASONAL:
        return f"seasonal:{job.id}:{_hash(found)}:{code}:{season_year}"
    if found.media == "video":
        return f"clip:{job.id}:{_hash(found)}:{code}"
    return _dedupe_key(job.id, found, code)


def _expiry(kind: JobKind, day: Day, moment: datetime, season: Any) -> datetime:
    """A local alert is today's; a food card this week's; a seasonal card lasts until its
    season ends; everything else is evergreen for a season of its own."""
    if kind is JobKind.LOCAL:
        return day.ends_at
    if kind is JobKind.FOOD:
        return day.week_ends_at
    if kind is JobKind.SEASONAL and season is not None:
        after = datetime.combine(season.ends + timedelta(days=1), time(0), day.tz)
        return after.astimezone(day.now.tzinfo)
    return moment + LEARNING_LIFETIME


def _medicine_he_takes(term: str, around: Around, registry: DrugRegistry) -> bool:
    """Whether a job's first term names a medicine he actually takes: his own list first
    (`around.medicines`, already the licensed register's generic — `compose.around_for`), then
    the register's brand lookup for whatever name the term was written as, for a term that
    names the same medicine by a different name (a brand, a salt) the register still resolves.

    #236: this is the one source of truth for "is this a medicine job" — `job.reason["scope"]`
    is not, because a watch added by hand (`add_search_job`) never sets it. Every job the
    planner itself makes with a `"medicines"` reason already names one of his own medicines as
    its first term (`compose._gaps`), so this agrees with the old check for all of those.

    The register is asked by `brand`, not `generic`: `identify` narrows its candidates to
    products whose own generic name equals whatever `LabelFields.generic` is given
    (`app.drugs.fixture.FixtureRegistry.identify`), so asking it "is `written` a generic?"
    with `generic=written` only ever hands back a product whose generic already *is*
    `written` — the same fact the line above already checked, and already returned on. A term
    written as a brand ("Coumadin" for warfarin) needs the brand field to resolve at all; a
    term already written as the generic is answered by the first check and never reaches the
    register a second time."""
    written = term.strip().lower()
    if written in around.medicines:
        return True
    matches = registry.identify(LabelFields(brand=written))
    return bool(matches) and matches[0].generic.strip().lower() in around.medicines


def _scope_of(
    job: SearchJob, reasons: Sequence[str], around: Around, registry: DrugRegistry
) -> Scope:
    """The part of the record a card was built from: a local alert made relevant by a medicine
    alone is the medicines'; one made relevant by a condition, and every other card, the
    record's — unless the gap it fills was a medicine's."""
    if job.kind is JobKind.LOCAL:
        by_condition = any(reason in around.conditions for reason in reasons)
        return Scope.RECORDS if by_condition else Scope.MEDICINES
    if job.terms and _medicine_he_takes(job.terms[0], around, registry):
        return Scope.MEDICINES
    return Scope.RECORDS


@dataclass(frozen=True, slots=True)
class _Shape:
    type: CardType
    lines: Lines
    format: CardFormat
    cite: dict[str, Any] | None = None


def _shape(
    kind: JobKind,
    found: Found,
    compressed: Compressed,
    *,
    code: str,
    source_name: str,
    doctor: str,
    around: Around,
    season: Any,
    about_a_medicine: bool = False,
) -> _Shape:
    """Which card a page becomes, and its words: the compressed lines, where they came from,
    the boundary line, and why it is here."""
    common: dict[str, Any] = {
        "headline": compressed.headline,
        "body": compressed.body,
        "topic": compressed.why_topic,
        "source_name": source_name,
        "doctor": doctor,
    }
    if kind is JobKind.LOCAL:
        if found.areas and around.area:
            lines = learning_lines(code, why="local", area=around.area, **common)
        else:
            lines = learning_lines(code, why="local_region", **common)
        return _Shape(CardType.LOCAL, lines, around.format)
    if kind is JobKind.SEASONAL and season is not None:
        when = plain_day(datetime.combine(season.starts, time(12), around.day.tz), code)
        lines = learning_lines(
            code,
            why="seasonal" if season.season.exact else "seasonal_about",
            season=season_name(season.season.code, code),
            day=when,
            **common,
        )
        return _Shape(CardType.SEASONAL, lines, around.format)
    if kind is JobKind.FOOD:
        return _Shape(CardType.FOOD, learning_lines(code, **common), around.format)
    lines = learning_lines(code, keep_taking=about_a_medicine, **common)
    if found.media == "video":
        fits = clip_length_ok(compressed.start_sec, compressed.end_sec) and _narrates_in_time(
            lines.voice, code, lines.boundary
        )
        if fits and around.clips_as_cards:
            # His clips have gone unplayed (E11-08): this one comes as a voice note instead.
            return _Shape(
                CardType.LEARNING, lines, CardFormat.VOICE_FIRST, {"instead_of_clip": True}
            )
        if fits:
            return _Shape(CardType.CLIP, lines, CardFormat.CLIP)
    return _Shape(CardType.LEARNING, lines, around.format)


def on_its_source(url: str, domain: str) -> bool:
    """Whether a page is on its source's site: https, and the host the domain or under it."""
    page = urlparse(url)
    host = (page.hostname or "").lower()
    site = domain.strip().lower()
    return page.scheme == "https" and bool(site) and (host == site or host.endswith("." + site))


def _batches_on_record(state: StateView) -> set[str]:
    """The batch numbers read off his packs (a `medicine.batch` fact from a label photo)."""
    clinical = state.dimension(Dimension.CLINICAL) or {}
    facts = clinical.get("facts", {})
    found: set[str] = set()
    for subject in ("medicine", "medication"):
        batch = facts.get(subject, {}).get("batch", {}).get("value")
        if isinstance(batch, str):
            found.add(batch.strip().lower())
    return found


def _plain_medicine_name(engine: Engine, generic: str, language: str) -> str:
    """His word for the generic a safety job watches (#183) — "the water pill", never
    "furosemide": the same catalogue `app.medicines.service` reads a reconciled line's name
    from. A generic the licensed registry has no monograph for (reachable only if a batch
    fact somehow outlived the line it was read from) falls back to the generic itself rather
    than failing the whole day's safety run over one card."""
    try:
        plain_name_id = engine.registry.monograph(generic).plain_name_id
    except UnknownDrug:
        return generic
    return PLAIN_NAME[language].get(plain_name_id, generic)


def _fact_ids_about(state: StateView, terms: Sequence[str]) -> list[str]:
    """The clinical fact ids whose subject or value names one of the terms."""
    clinical = state.dimension(Dimension.CLINICAL)
    if clinical is None:
        return []
    ids: list[str] = []
    for subject, attributes in clinical.get("facts", {}).items():
        for entry in attributes.values():
            haystack = f"{subject} {entry.get('value')}".lower()
            if any(term in haystack for term in terms):
                ids.append(entry["fact_id"])
    return sorted(ids)


async def _ask_the_doctor(
    session: AsyncSession,
    *,
    context: KeyContext,
    state: StateView,
    code: str,
    doctor: str | None,
    generic: str | None,
    registry: DrugRegistry,
    source_id: uuid.UUID,
) -> str | None:
    """File a treatment-changing finding as a real question for the doctor (#181, #224, #236),
    through the same memo the post-visit summary files one against — never a `FeedItem`, which
    nothing reads for `DeliverTo.MEMO` (rank.py's two supplies exclude it, and no route queries
    it). `appointment_id` is left unset: this is not about one visit, so it is a standing
    question `current_memos`/`propose_questions` picks up for whichever comes next, the same
    way an unfiled memo already works there.

    `generic` names the medicine when one is known — a safety job's own term, or a job whose
    first term `_medicine_he_takes`. A question that names it asks about it by name
    (`"ask_safety_notice"`); one that cannot is filed anyway, never dropped for want of a name
    (#236's own finding, one branch over from the bug it fixed) — a name-free question asks
    about "your medicines" generally (`"ask_medicines_change"`, `reasoning.visits.strings`,
    the same name-free key `visits.summary.compose_items` already uses for a post-visit change
    whose drug the register does not know). The same fallback covers a `generic` the
    register does not carry a plain name for (`medicine_words` raising `NotASlotValue`): asking
    about his medicines in general is still a real question, where asking about a name he'd
    never recognise would not be.

    In a savepoint of its own, the way a review sample sits beside a card
    (`items._sample`): whatever goes wrong here — a line that fails the verifier, the database
    — is logged, written to the audit trail as a refusal, and rolled back. It must never cost
    him the caregiver notice this always runs alongside; that is written by the caller
    regardless of what happens here. The audit write itself is guarded too (#236): a caller
    that already lost the question filing to an exception must never also lose the caregiver
    notice to a second, unrelated failure writing that down.
    """
    key = "ask_medicines_change"
    slots: dict[str, Any] = {"doctor": doctor or YOUR_DOCTOR[code]}
    if generic:
        try:
            slots["medicine"] = medicine_words(generic, code, registry)
            key = "ask_safety_notice"
        except NotASlotValue:
            pass  # no plain name known either: ask about his medicines, not nothing.
    try:
        async with nested_unit_of_work(session):
            memo = await write_memo(
                session,
                context=context,
                kind=MemoKind.ASK,
                key=key,
                slots=slots,
                source=MemoSource.SEARCH,
                source_id=source_id,
                state=state,
                language=code,
            )
            return str(memo.id)
    except Exception as skipped:  # noqa: BLE001 — nothing here may cost him the notice
        log.warning("doctor-question filing skipped: %s", type(skipped).__name__)
        # A filing failure is silent to him by design (the caregiver notice still lands
        # regardless), but it must never be silent on the trail: the same discipline
        # `create_job`'s own refusals already keep (#236).
        try:
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.VISITS,
                target=MEMO,
                outcome=Outcome.REFUSED,
                refused_because=type(skipped).__name__,
            )
        except Exception as unaudited:  # noqa: BLE001 — see the docstring: never his notice
            log.error(
                "the filing failure itself could not be written to the trail: %s",
                type(unaudited).__name__,
            )
        return None
