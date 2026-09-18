"""The demo's own Pa and Mei (`app.demo_seed`): a fresh sign-in opens onto a living record.

Idempotent (seeding twice changes nothing), every seeded row is on Pa's own trail, Mei's
chief key reads what her scopes allow, and the seed refuses to run outside a declared demo
or dev run — the same gate every other fixture provider is held to.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.audit.models import AuditEntry
from app.channels.api import Providers
from app.channels.whatsapp.provider import FixtureProvider
from app.clock import now
from app.db import as_utc
from app.delivery.feed.compose import (
    Day,
    household,
    plan_learning_jobs,
    refresh,
    say_ahead,
    today_for,
)
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.models import CardType, FeedItem
from app.delivery.feed.search import Engine
from app.delivery.feed.search import run_job as search_run_job
from app.delivery.recommend.rules import NEW_MEDICINE_WINDOW, RULE_NEW_MEDICINE_EXPLAINER
from app.demo_numbers import DEMO_NUMBERS, mei_number, pa_number
from app.demo_seed import (
    NEW_MEDICINE,
    NEW_MEDICINE_AGO,
    DemoSeedOutsideDevOrDemo,
    require_seedable,
    seed_demo,
)
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.identity.service import find_person_by_phone
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.speakers import FixtureSeparator
from app.ingestion.transcribe import FixtureTranscriber
from app.keys.context import KeyContext, owned_profile, resolve_key_context
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.service import LineView, active_lines
from app.reasoning.ranges import FixtureRanges
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings
from app.state.service import current_state
from tests.conftest import FEED, SPEAKERS, VISITS, WHATSAPP_FIXTURES, WHATSAPP_SECRET
from tests.paper import PAPER
from tests.voice_notes import VOICE

REGISTRY = FixtureRegistry.load()


def _settings(*, demo_mode: bool = False, dev_code_sender: bool = False) -> Settings:
    return Settings(
        region=Region.SG,
        database_url="sqlite+aiosqlite://",
        demo_mode=demo_mode,
        demo_login_code="123456" if demo_mode else None,
        dev_code_sender=dev_code_sender,
        demo_seed=True,
    )


def _providers() -> Providers:
    root = Path(tempfile.mkdtemp(prefix="nura-demo-seed-test-"))
    return Providers(
        code_sender=LoggingCodeSender(reveal=True),
        object_store=LocalObjectStore(root, Region.SG),
        extractor=FixtureExtractor(PAPER),
        summariser=FixtureSummariser(VISITS),
        transcriber=FixtureTranscriber(VOICE, Region.SG),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=REGISTRY,
        whatsapp=FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES),
        reference_ranges=FixtureRanges.load(),
        speaker_separator=FixtureSeparator(SPEAKERS, Region.SG),
        clips=None,
    )


def test_seed_refuses_outside_demo_or_dev() -> None:
    with pytest.raises(DemoSeedOutsideDevOrDemo):
        require_seedable(_settings(demo_mode=False, dev_code_sender=False))
    require_seedable(_settings(demo_mode=True))
    require_seedable(_settings(dev_code_sender=True))


async def _seed_twice(sg: AsyncSession) -> None:
    settings = _settings(dev_code_sender=True)
    providers = _providers()
    await seed_demo(sg, settings, providers)
    await seed_demo(sg, settings, providers)


async def test_seed_refuses_outside_demo_or_dev_at_the_call_too(sg: AsyncSession) -> None:
    settings = _settings(demo_mode=False, dev_code_sender=False)
    with pytest.raises(DemoSeedOutsideDevOrDemo):
        await seed_demo(sg, settings, _providers())


async def test_seed_twice_writes_the_same_rows(sg: AsyncSession) -> None:
    await _seed_twice(sg)
    pa_phone, mei_phone = DEMO_NUMBERS[Region.SG]
    assert pa_phone == pa_number(Region.SG)
    assert mei_phone == mei_number(Region.SG)
    pa = await find_person_by_phone(sg, pa_phone)
    assert pa is not None
    lines = (
        await sg.scalar(
            select(func.count())
            .select_from(MedicationLine)
            .where(MedicationLine.status == LineStatus.ACTIVE)
        )
    ) or 0
    assert lines == 4, "one seed's worth of medicines, not two"

    mei = await find_person_by_phone(sg, mei_phone)
    assert mei is not None


async def test_every_seeded_row_is_on_pas_trail(sg: AsyncSession) -> None:
    await seed_demo(sg, _settings(dev_code_sender=True), _providers())
    pa = await find_person_by_phone(sg, pa_number(Region.SG))
    assert pa is not None
    profile = await owned_profile(sg, region=Region.SG, owner_person_id=pa.id)
    assert profile is not None
    lines = list(
        await sg.scalars(select(AuditEntry).where(AuditEntry.profile_id == profile.id))
    )
    assert len(lines) > 10, "the profile's opening, the medicines, the readings, the visits…"
    assert all(line.profile_id == profile.id for line in lines)
    scopes_seen = {line.scope for line in lines}
    for expected in (Scope.MEDICINES, Scope.READINGS, Scope.VISITS, Scope.FAMILY, Scope.RECORDS):
        assert expected in scopes_seen, f"nothing on the trail under {expected}"


async def test_meis_key_reads_what_her_scopes_allow(sg: AsyncSession) -> None:
    """Reuses `test_row_scope.py`'s pattern lightly: a chief's key resolves to the full set
    of scopes her consent named, and a service read under it returns exactly what Pa's own
    context reads — nothing withheld that her key holds, nothing extra that it does not."""
    await seed_demo(sg, _settings(dev_code_sender=True), _providers())
    pa = await find_person_by_phone(sg, pa_number(Region.SG))
    mei = await find_person_by_phone(sg, mei_number(Region.SG))
    assert pa is not None and mei is not None
    profile = await owned_profile(sg, region=Region.SG, owner_person_id=pa.id)
    assert profile is not None
    owner_ctx = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    mei_ctx = await resolve_key_context(sg, region=Region.SG, person_id=mei.id, profile_id=profile.id)
    assert mei_ctx.role is KeyRole.CHIEF
    assert mei_ctx.scopes == ALL_SCOPES, "the chief's key holds every scope her consent named"

    owner_lines = await active_lines(sg, context=owner_ctx, registry=REGISTRY)
    mei_lines = await active_lines(sg, context=mei_ctx, registry=REGISTRY)
    assert {view.line.id for view in mei_lines} == {view.line.id for view in owner_lines}
    assert len(mei_lines) == 4


async def test_the_seeded_blood_pressure_tablet_is_started_this_week(sg: AsyncSession) -> None:
    """Live-run defect: "no learning cards appear" — `new_medicine_explainer` only proposes a
    READ/CLIP for a line started within `NEW_MEDICINE_WINDOW` (14 days). A medicine reconciled
    at seed time is dated from that moment (`reconcile`), so this held on a freshly seeded
    database — but the demo seeds Pa once, idempotently, and a dev run's own database is never
    nightly-wiped, so on a laptop that has had Pa seeded for a while every medicine's own
    `started_at` just kept receding into the past. `NEW_MEDICINE` (amlodipine, his blood
    pressure tablet) is explicitly backdated by a fixed, small amount instead, so it stays
    inside the window regardless of how long ago the row was actually written."""
    await seed_demo(sg, _settings(dev_code_sender=True), _providers())
    pa = await find_person_by_phone(sg, pa_number(Region.SG))
    assert pa is not None
    profile = await owned_profile(sg, region=Region.SG, owner_person_id=pa.id)
    assert profile is not None
    owner_ctx = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    lines = await active_lines(sg, context=owner_ctx, registry=REGISTRY)
    [tablet] = [view for view in lines if view.line.generic == NEW_MEDICINE]
    age = now() - as_utc(tablet.line.started_at)
    assert age < NEW_MEDICINE_WINDOW, "inside the explainer's own 14-day window"
    assert age >= NEW_MEDICINE_AGO - timedelta(seconds=5), "backdated, not started at seed time"

    others = [view for view in lines if view.line.generic != NEW_MEDICINE]
    assert others, "the other medicines are seeded, unaffected by the one backdate"
    for view in others:
        assert now() - as_utc(view.line.started_at) < timedelta(minutes=1), "started at seed time, as before"


async def _run_learning(
    session: AsyncSession, *, context: KeyContext, engine: Engine, day: Day
) -> list[FeedItem]:
    """Today's self-searches, run synchronously on this same session — what
    `app.delivery.feed.background._run` does on its own session, off the request entirely, for
    a test that means to check what a first feed load makes, not the background module's own
    scheduling (`tests/test_feed_background.py` covers that)."""
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


async def test_a_freshly_seeded_profiles_first_feed_load_shows_a_learning_card(
    sg: AsyncSession,
) -> None:
    """The acceptance this story is for: a seeded profile's first feed load (`refresh`, what
    `GET /feed` calls on a first, cursor-less page) creates the day's search jobs and, with a
    mocked searcher and compressor (`FixtureSearcher`/`FixtureCompressor`, never a live call),
    yields a learning card that names its rule under `Why` — not just now/visit/reading/gate/
    recap, the live run's own report of what was missing."""
    providers = _providers()
    await seed_demo(sg, _settings(dev_code_sender=True), providers)
    pa = await find_person_by_phone(sg, pa_number(Region.SG))
    assert pa is not None
    profile = await owned_profile(sg, region=Region.SG, owner_person_id=pa.id)
    assert profile is not None
    owner_ctx = await resolve_key_context(sg, region=Region.SG, person_id=pa.id, profile_id=profile.id)
    engine = Engine(
        searcher=providers.searcher, compressor=providers.compressor, registry=REGISTRY
    )

    _, made = await refresh(sg, context=owner_ctx, engine=engine)
    made = list(made) + await _run_learning(sg, context=owner_ctx, engine=engine, day=today_for(owner_ctx))

    learning = [item for item in made if item.type in (CardType.LEARNING, CardType.CLIP)]
    assert learning, "the first feed load made no READ or CLIP card at all"
    assert any(item.why.get("rule") == RULE_NEW_MEDICINE_EXPLAINER for item in learning), (
        "the backdated blood pressure tablet should have led the learning supply"
    )
    for item in learning:
        assert item.why, "every learning card names why (Why sheet, RE-08)"
