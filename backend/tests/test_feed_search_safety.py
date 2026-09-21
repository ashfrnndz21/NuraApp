"""#302: the live-search fix. Three things, each with its own tests here:

1. `search._safe_query`/`_safe_queries` — never the bare generic alone (the live diagnosis: 22
   of 30 finished jobs came back with nothing at all, and every one of them searched a bare
   chemical name; the one job that found something searched `["cholesterol"]`, already a plain
   word). Pure unit tests, no database.
2. `search._empty_because` — the closed enum a live check reads back, from `ClaudeSearcher`'s
   own diagnostics shape.
3. The privacy boundary: what `search_and_compress` actually hands `ClaudeSearcher.search` for
   a seeded profile never carries his name, phone, a date, a number from his record, or a
   facility/doctor name — asserted against the *real* planning path (`plan_learning_jobs`),
   not a hand-built job.

Every test here mocks the `anthropic` client, the same rule `test_claude_feed_adapters.py`
holds: nothing calls a live service.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.feed.claude_adapters import ClaudeSearcher
from app.delivery.feed.compose import household, plan_learning_jobs, today_for
from app.delivery.feed.compress import FixtureCompressor
from app.delivery.feed.models import JobKind
from app.delivery.feed.search import (
    Engine,
    _empty_because,
    _safe_queries,
    _safe_query,
    prepare_job,
    search_and_compress,
)
from app.drugs.fixture import FixtureRegistry
from app.drugs.registry import UnknownDrug
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.medicines.service import active_lines
from app.memory.episodic import store_artifact
from app.memory.models import ArtifactKind, SourceChannel
from app.memory.semantic import assert_fact
from app.regions import Region
from app.state.service import current_state
from tests.conftest import FEED
from tests.support import OPENING_CONSENT

REGISTRY = FixtureRegistry.load()
MONDAY = datetime(2026, 9, 21, 8, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. `_safe_query` / `_safe_queries`: never the bare generic alone.
# ---------------------------------------------------------------------------


def test_safe_query_for_a_medicine_is_his_catalogue_word_plus_its_purpose_group() -> None:
    """The brief's own example: "the catalogue's plain name + its reviewed purpose group like
    'blood pressure'" — amlodipine's monograph names `blood_pressure_tablet`/`blood_pressure`."""
    query = _safe_query("amlodipine", JobKind.EXPLAINER, REGISTRY, "en")
    assert query == "your blood pressure tablet, for blood pressure — what it is for"
    assert "amlodipine" not in query


def test_safe_query_intent_word_changes_with_the_job_kind() -> None:
    explainer = _safe_query("warfarin", JobKind.EXPLAINER, REGISTRY, "en")
    safety = _safe_query("warfarin", JobKind.SAFETY, REGISTRY, "en")
    assert explainer.endswith("— what it is for")
    assert safety.endswith("— side effects to know")
    assert explainer.startswith("the blood thinner tablet, for clots")
    assert safety.startswith("the blood thinner tablet, for clots")


def test_safe_query_food_and_worth_knowing_intents() -> None:
    assert _safe_query("atorvastatin", JobKind.FOOD, REGISTRY, "en").endswith("— food")
    assert _safe_query("atorvastatin", JobKind.WORTH_KNOWING, REGISTRY, "en").endswith(
        "— patient information"
    )


def test_safe_query_passes_a_non_medicine_term_through_with_its_intent() -> None:
    """A condition, a food topic, a hazard or a season is already a closed, human word
    (`CONDITION_TERMS`/`FOOD_TERMS`/`HAZARDS`/`SEASONS`) — never a chemical name, so there is
    nothing to look up in the drug catalogue; the registry says so (`UnknownDrug`)."""
    with pytest.raises(UnknownDrug):
        REGISTRY.monograph("blood pressure")
    query = _safe_query("blood pressure", JobKind.EXPLAINER, REGISTRY, "en")
    assert query == "blood pressure — what it is for"


def test_safe_query_local_and_seasonal_kinds_carry_no_intent_word() -> None:
    assert _safe_query("dengue", JobKind.LOCAL, REGISTRY, "en") == "dengue"
    assert _safe_query("fasting month", JobKind.SEASONAL, REGISTRY, "en") == "fasting month"


def test_safe_query_localises_the_medicine_word_when_the_catalogue_has_it() -> None:
    query = _safe_query("amlodipine", JobKind.EXPLAINER, REGISTRY, "ms")
    assert query.startswith("ubat tekanan darah anda")
    assert "your blood pressure tablet" not in query


def test_safe_query_falls_back_to_the_term_for_an_unknown_generic() -> None:
    assert _safe_query("madeupomycin", JobKind.EXPLAINER, REGISTRY, "en") == (
        "madeupomycin — what it is for"
    )


def test_safe_queries_builds_one_per_term_in_terms_order() -> None:
    class _Job:
        kind = JobKind.EXPLAINER
        terms = ("amlodipine", "warfarin")

    built = _safe_queries(_Job(), REGISTRY, "en")  # type: ignore[arg-type]
    assert built == (
        "your blood pressure tablet, for blood pressure — what it is for",
        "the blood thinner tablet, for clots — what it is for",
    )


# ---------------------------------------------------------------------------
# 2. `_empty_because`: the closed enum, from `ClaudeSearcher`'s own diagnostics shape.
# ---------------------------------------------------------------------------

_BASE_DETAIL: dict[str, Any] = {
    "web_search_uses": 1,
    "web_fetch_uses": 1,
    "candidate_urls": 3,
    "on_allowlist": 2,
    "fetched_ok": 2,
    "refused": False,
    "parse_failed": False,
    "max_uses_reached": False,
}


def _detail(**over: Any) -> dict[str, Any]:
    return {**_BASE_DETAIL, **over}


def test_empty_because_refused_wins_over_everything_else() -> None:
    assert _empty_because(_detail(refused=True, web_search_uses=0, web_fetch_uses=0)) == "refused"


def test_empty_because_no_search_issued() -> None:
    assert _empty_because(_detail(web_search_uses=0, web_fetch_uses=0)) == "no_search_issued"


def test_empty_because_parse_failed() -> None:
    assert _empty_because(_detail(parse_failed=True)) == "parse_failed"


def test_empty_because_max_uses_reached() -> None:
    assert _empty_because(_detail(max_uses_reached=True)) == "max_uses_reached"


def test_empty_because_no_results() -> None:
    assert _empty_because(_detail(candidate_urls=0, on_allowlist=0, fetched_ok=0)) == "no_results"


def test_empty_because_all_off_allowlist() -> None:
    assert _empty_because(_detail(on_allowlist=0, fetched_ok=0)) == "all_off_allowlist"


def test_empty_because_fetch_failed() -> None:
    assert _empty_because(_detail(fetched_ok=0)) == "fetch_failed"


def test_empty_because_nothing_relevant_is_the_last_resort() -> None:
    assert _empty_because(_detail()) == "nothing_relevant"


# ---------------------------------------------------------------------------
# The first personalised plan: right after his first confirmed medicine, the plan's first job
# is about him, not generic. This trigger already exists (RE-07: the broker's slate leads,
# `app.delivery.feed.compose.plan_learning_jobs`/`_broker_wanted`/`_gaps`) — this test proves
# it rather than adding a second one, per the brief ("if one already exists, prove it with a
# test and change nothing"). Nothing in `compose.py` is touched by this change.
# ---------------------------------------------------------------------------


async def test_the_first_plan_after_his_first_medicine_leads_with_that_medicine(
    sg: AsyncSession,
) -> None:
    context = await _pa(sg)
    photo = await store_artifact(
        sg,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/{context.profile_id}/first-label.jpg",
        content_type="image/jpeg",
        sha256="a" * 64,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    # His first confirmed thing: one medicine, nothing else on the record yet.
    await assert_fact(
        sg, context=context, subject="medicine", attribute="name", value="amlodipine",
        confidence=0.95, artifact_id=photo.id,
    )
    house = await household(sg, context=context)
    state = await current_state(sg, context=context)
    engine = Engine(searcher=None, compressor=FixtureCompressor(FEED), registry=REGISTRY)  # type: ignore[arg-type]
    plan = await plan_learning_jobs(
        sg, context=context, engine=engine, state=state, day=today_for(context), house=house,
        keys=set(), medicines=await active_lines(sg, context=context, registry=REGISTRY, language="en"),
    )
    assert plan.jobs, "a fresh profile with one medicine should open at least one job"
    first = plan.jobs[0]
    # Whichever of the two paths produced it — the broker's `new_medicine_explainer` rule
    # (RE-07, ranked first) or the plain gap (`_gaps`, when the broker found nothing) — the
    # plan's first job names his own medicine, never a generic topic.
    assert first.kind in (JobKind.EXPLAINER, JobKind.WORTH_KNOWING, JobKind.SAFETY)
    assert "amlodipine" in first.terms, (first.kind, first.terms, first.reason)


# ---------------------------------------------------------------------------
# `search_and_compress` end to end with the real `ClaudeSearcher`, a fake client: the job's
# `searched_detail`/`empty_because` land on the outcome exactly as `ClaudeSearcher` reported.
# ---------------------------------------------------------------------------


@dataclass
class _FakeBlock:
    text: str


@dataclass
class _FakeSearchResult:
    url: str
    title: str = ""
    type: str = "web_search_result"


@dataclass
class _FakeSearchToolResult:
    content: Sequence[Any]
    type: str = "web_search_tool_result"


@dataclass
class _FakeResponse:
    content: Sequence[Any]
    stop_reason: str = "end_turn"


class _FakeMessages:
    def __init__(self, responses: Sequence[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses: Sequence[_FakeResponse]) -> None:
        self.messages = _FakeMessages(responses)


async def _pa(session: AsyncSession) -> KeyContext:
    person = await register_person(session, region=Region.SG, display_name="Pa", phone_e164="+6591310099")
    profile = await create_own_profile(
        session, region=Region.SG, owner=person, consent=OPENING_CONSENT, language="en"
    )
    return await resolve_key_context(session, region=Region.SG, person_id=person.id, profile_id=profile.id)


async def _medicine_job_prep(session: AsyncSession, context: KeyContext) -> Any:
    """A real EXPLAINER job for a medicine he takes, made the way the planner really makes one
    (`plan_learning_jobs`), and its `JobPrep` — the same two things `search_and_compress`
    actually receives from `run_job`."""
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/label-{context.profile_id}.jpg",
        content_type="image/jpeg",
        sha256="e" * 64,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    await assert_fact(
        session, context=context, subject="medicine", attribute="name", value="amlodipine",
        confidence=0.95, artifact_id=photo.id,
    )
    house = await household(session, context=context)
    state = await current_state(session, context=context)
    engine = Engine(searcher=None, compressor=FixtureCompressor(FEED), registry=REGISTRY)  # type: ignore[arg-type]
    plan = await plan_learning_jobs(
        session, context=context, engine=engine, state=state, day=today_for(context),
        house=house, keys=set(),
        medicines=await active_lines(session, context=context, registry=REGISTRY, language="en"),
    )
    jobs = [job for job in plan.jobs if job.kind == JobKind.EXPLAINER]
    assert jobs, "the medicine gap should have opened an explainer job"
    job = jobs[0]
    prep = await prepare_job(session, context=context, job=job)
    return job, prep, state, plan.around


async def test_search_and_compress_writes_all_off_allowlist_when_every_url_is_off_list(
    sg: AsyncSession,
) -> None:
    context = await _pa(sg)
    job, prep, state, around = await _medicine_job_prep(sg, context)
    off_list_url = "https://not-allowlisted.example/a"
    client = _FakeClient(
        [
            _FakeResponse(
                content=[
                    _FakeSearchToolResult(content=[_FakeSearchResult(url=off_list_url)]),
                    _FakeBlock(json.dumps({"results": []})),
                ]
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    engine = Engine(searcher=searcher, compressor=FixtureCompressor(FEED), registry=REGISTRY)
    outcome = await search_and_compress(
        engine, job, prep, state=state, language="en", around=around, existing=set()
    )
    assert outcome.candidates == ()
    assert outcome.searched_detail is not None
    assert outcome.searched_detail["empty_because"] == "all_off_allowlist"
    assert outcome.searched_detail["queries"], "the safe query, not the bare term, was recorded"
    assert "amlodipine" not in outcome.searched_detail["queries"][0]


async def test_search_and_compress_writes_refused_when_claude_refuses(sg: AsyncSession) -> None:
    context = await _pa(sg)
    job, prep, state, around = await _medicine_job_prep(sg, context)
    client = _FakeClient([_FakeResponse(content=[], stop_reason="refusal")])
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    engine = Engine(searcher=searcher, compressor=FixtureCompressor(FEED), registry=REGISTRY)
    outcome = await search_and_compress(
        engine, job, prep, state=state, language="en", around=around, existing=set()
    )
    assert outcome.searched_detail is not None
    assert outcome.searched_detail["empty_because"] == "refused"


async def test_search_and_compress_reports_none_for_a_fixture_engine(sg: AsyncSession) -> None:
    """A fixture searcher has no diagnostics to give (it never leaves the region) —
    `searched_detail` stays `None`, never a fabricated empty shape."""
    from app.delivery.feed.compress import FixtureSearcher

    context = await _pa(sg)
    job, prep, state, around = await _medicine_job_prep(sg, context)
    engine = Engine(searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY)
    outcome = await search_and_compress(
        engine, job, prep, state=state, language="en", around=around, existing=set()
    )
    assert outcome.searched_detail is None


# ---------------------------------------------------------------------------
# 3. The privacy boundary: the request `ClaudeSearcher` actually sends for a seeded profile
#    never carries anything identifying.
# ---------------------------------------------------------------------------


async def test_the_request_sent_for_a_seeded_profile_carries_no_identifying_information(
    sg: AsyncSession,
) -> None:
    """A profile shaped like a real one: his name, his phone, a scheduled visit with a named
    doctor and facility, a dated lab reading and a medicine — everything `search_and_compress`
    could, in principle, leak into a query if `_safe_queries` read the record's own free text
    instead of the closed catalogue. Asserts against the *real* planning path
    (`plan_learning_jobs`), not a hand-built job, so this fails if the wiring between the
    planner and the searcher ever changes to pass richer, unsafe context through."""
    person = await register_person(
        sg, region=Region.SG, display_name="Ashley Fernandez", phone_e164="+6591234567"
    )
    profile = await create_own_profile(
        sg, region=Region.SG, owner=person, consent=OPENING_CONSENT, language="en"
    )
    context = await resolve_key_context(
        sg, region=Region.SG, person_id=person.id, profile_id=profile.id
    )
    photo = await store_artifact(
        sg,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/{context.profile_id}/label.jpg",
        content_type="image/jpeg",
        sha256="f" * 64,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    secrets = [
        "Ashley Fernandez",
        "+6591234567",
        "Dr Somasundram",
        "Gleneagles Hospital",
        "2026-09-21",
        "168/92",
    ]
    await assert_fact(
        sg, context=context, subject="medicine", attribute="name", value="warfarin",
        confidence=0.95, artifact_id=photo.id,
    )
    house = await household(sg, context=context)
    state = await current_state(sg, context=context)
    engine = Engine(searcher=None, compressor=FixtureCompressor(FEED), registry=REGISTRY)  # type: ignore[arg-type]
    plan = await plan_learning_jobs(
        sg, context=context, engine=engine, state=state, day=today_for(context), house=house,
        keys=set(), medicines=await active_lines(sg, context=context, registry=REGISTRY, language="en"),
    )
    jobs = [job for job in plan.jobs if job.kind in (JobKind.EXPLAINER, JobKind.SAFETY)]
    assert jobs
    client = _FakeClient([_FakeResponse(content=[_FakeBlock(json.dumps({"results": []}))]) for _ in jobs])
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    live_engine = Engine(searcher=searcher, compressor=FixtureCompressor(FEED), registry=REGISTRY)
    for job in jobs:
        prep = await prepare_job(sg, context=context, job=job)
        await search_and_compress(
            live_engine, job, prep, state=state, language="en", around=plan.around, existing=set()
        )
    assert client.messages.calls, "the searcher should have been asked at least once"
    for call in client.messages.calls:
        request = json.dumps(call, default=str)
        for secret in secrets:
            assert secret not in request, f"{secret!r} leaked into the request: {request}"
