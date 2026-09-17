"""The demo's own Pa and Mei (`app.demo_seed`): a fresh sign-in opens onto a living record.

Idempotent (seeding twice changes nothing), every seeded row is on Pa's own trail, Mei's
chief key reads what her scopes allow, and the seed refuses to run outside a declared demo
or dev run — the same gate every other fixture provider is held to.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry
from app.channels.api import Providers
from app.channels.whatsapp.provider import FixtureProvider
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.demo_numbers import DEMO_NUMBERS, mei_number, pa_number
from app.demo_seed import DemoSeedOutsideDevOrDemo, require_seedable, seed_demo
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import LoggingCodeSender
from app.identity.service import find_person_by_phone
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.speakers import FixtureSeparator
from app.ingestion.transcribe import FixtureTranscriber
from app.keys.context import owned_profile, resolve_key_context
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.service import active_lines
from app.reasoning.ranges import FixtureRanges
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings
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
