"""Every fixture provider refuses to start outside a declared dev run or demo.

A fixture stands in for a provider Nura does not have yet. Each is marked `@fixture`, and
`create_app` refuses a process that is neither a dev run (NURA_DEV_CODE_SENDER=1) nor a demo
(NURA_DEMO_MODE=1, ADR 0008) when any of them is among its providers (`app.fixtures`). This
file finds every class named `Fixture…` under `app/` by walking the package, so a fixture
added tomorrow without the mark fails here, not in production.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import app
from app.channels.api import create_app
from app.db import make_session_factory
from app.drugs.client import drug_registry_for
from app.fixtures import (
    FixtureOutsideDevOrDemo,
    check_fixtures,
    fixtures_in,
    is_fixture,
    is_fixture_class,
)
from app.identity.providers import DemoCodeSender, LoggingCodeSender
from app.ingestion.objects import LocalObjectStore
from app.ingestion.s3 import S3ObjectStore
from app.ingestion.stores import object_store_for
from app.reasoning.ranges import reference_ranges_for
from app.regions import Region
from app.search.retrieve import KeywordRetriever
from app.settings import MissingSetting, Settings
from tests.whatsapp_support import deployment as fixture_deployment

ALSO_FIXTURES = {LoggingCodeSender, LocalObjectStore}
"""Fixtures whose names do not say so: the laptop's code sender and its directory store."""


def _every_class_under_app() -> set[type]:
    found: set[type] = set()
    for info in pkgutil.walk_packages(app.__path__, prefix="app."):
        if info.name == "app.main":  # reads the environment at import; it is the process
            continue
        module = importlib.import_module(info.name)
        for _, value in inspect.getmembers(module, inspect.isclass):
            if value.__module__ == info.name:
                found.add(value)
    return found


def test_every_fixture_under_app_carries_the_mark() -> None:
    classes = _every_class_under_app()
    named = {cls for cls in classes if cls.__name__.startswith("Fixture") and not issubclass(cls, BaseException)}
    assert {cls.__name__ for cls in named} >= {
        "FixtureProvider",
        "FixtureRegistry",
        "FixtureExtractor",
        "FixtureSummariser",
        "FixtureTranscriber",
        "FixtureSearcher",
        "FixtureCompressor",
        "FixtureRanges",
        "FixtureCalendar",
        "FixtureRetriever",
    }
    for cls in named | ALSO_FIXTURES:
        assert is_fixture_class(cls), f"{cls.__module__}.{cls.__name__} is not marked @fixture"


def test_the_real_ones_are_not_marked() -> None:
    assert not is_fixture_class(KeywordRetriever)
    assert not is_fixture_class(S3ObjectStore)
    assert not is_fixture_class(DemoCodeSender)


PRODUCTION = Settings(region=Region.SG, database_url="sqlite+aiosqlite://")
DEV = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True)
DEMO = Settings(
    region=Region.SG,
    database_url="sqlite+aiosqlite://",
    demo_mode=True,
    demo_login_code="246810",
)


def test_the_test_deployment_is_all_fixtures_but_the_retriever(tmp_path: Path) -> None:
    _, providers = fixture_deployment(tmp_path)
    assert fixtures_in(providers) == [
        "code_sender",
        "object_store",
        "extractor",
        "summariser",
        "transcriber",
        "searcher",
        "compressor",
        "drug_registry",
        "whatsapp",
        "reference_ranges",
    ]
    assert not is_fixture(providers.retriever)


def test_outside_a_dev_run_or_demo_every_fixture_is_named_and_refused(tmp_path: Path) -> None:
    _, providers = fixture_deployment(tmp_path)
    with pytest.raises(FixtureOutsideDevOrDemo) as refused:
        check_fixtures(PRODUCTION, providers)
    for name in fixtures_in(providers):
        assert name in str(refused.value)
    check_fixtures(DEV, providers)
    check_fixtures(DEMO, providers)


async def test_create_app_refuses_fixtures_in_production(tmp_path: Path) -> None:
    _, providers = fixture_deployment(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite://")
    # The code sender is refused first, by name; with it out of the way, the rest are.
    with pytest.raises(RuntimeError, match="LoggingCodeSender"):
        create_app(PRODUCTION, make_session_factory(engine), providers)
    await engine.dispose()


def test_the_selectors_build_fixtures_that_the_check_then_refuses() -> None:
    # The drug registry and the ranges default to `fixture`; the selector builds it, and it
    # is `create_app`'s check, the one place, that keeps it off a deployment.
    assert is_fixture(drug_registry_for(PRODUCTION))
    assert is_fixture(reference_ranges_for(PRODUCTION))


def test_a_deployment_names_its_bucket_or_refuses_to_start(tmp_path: Path) -> None:
    with pytest.raises(MissingSetting, match="no object store"):
        object_store_for(PRODUCTION)
    local = object_store_for(
        Settings(region=Region.SG, database_url="x", object_store_root=str(tmp_path))
    )
    assert isinstance(local, LocalObjectStore) and is_fixture(local)
    with pytest.raises(MissingSetting, match="NURA_OBJECT_BUCKET_REGION"):
        object_store_for(
            Settings(region=Region.SG, database_url="x", object_bucket_url="https://b.example")
        )
    bucket = object_store_for(
        Settings(
            region=Region.SG,
            database_url="x",
            object_bucket_url="https://nura-sg.s3.ap-southeast-1.amazonaws.com",
            object_bucket_region="ap-southeast-1",
            object_access_key_id="AKID",
            object_secret_access_key="not-a-secret",
        )
    )
    assert isinstance(bucket, S3ObjectStore) and bucket.region is Region.SG
