"""The logging code sender runs on a laptop and nowhere else.

It prints login codes to the server log, which is how you sign in under `make dev` and how
someone takes over an account anywhere else. So the process refuses to start on it unless
the deployment says, explicitly, that it is a dev run.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.channels.api import Providers, create_app
from app.channels.strings import CODE_WORKS_FOR, phone_code_message
from app.channels.whatsapp.provider import FixtureProvider
from app.db import make_session_factory
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.providers import (
    DevSenderInProduction,
    LoggingCodeSender,
    NoCodeSender,
    code_sender_for,
)
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings, load_settings
from tests.conftest import FEED, VISITS
from tests.paper import PAPER

ENV = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}


def _providers(sender: LoggingCodeSender, tmp: Path) -> Providers:
    return Providers(
        code_sender=sender,
        object_store=LocalObjectStore(tmp, Region.SG),
        extractor=FixtureExtractor(PAPER),
        summariser=FixtureSummariser(VISITS),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=FixtureRegistry.load(),
        whatsapp=FixtureProvider(secret="test"),
    )


def test_the_flag_is_off_unless_set_to_exactly_one() -> None:
    assert load_settings(ENV).dev_code_sender is False
    assert load_settings({**ENV, "NURA_DEV_CODE_SENDER": "true"}).dev_code_sender is False
    assert load_settings({**ENV, "NURA_DEV_CODE_SENDER": "1"}).dev_code_sender is True


def test_without_the_flag_there_is_no_sender_and_the_process_does_not_start() -> None:
    with pytest.raises(NoCodeSender):
        code_sender_for(load_settings(ENV))
    revealed = code_sender_for(load_settings({**ENV, "NURA_DEV_CODE_SENDER": "1"}))
    assert isinstance(revealed, LoggingCodeSender) and revealed.reveal


async def test_create_app_refuses_the_logging_sender_outside_a_dev_run(tmp_path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    sessions = make_session_factory(engine)
    production = Settings(region=Region.SG, database_url="sqlite+aiosqlite://")
    with pytest.raises(DevSenderInProduction):
        create_app(production, sessions, _providers(LoggingCodeSender(), tmp_path))
    with pytest.raises(DevSenderInProduction):
        create_app(production, sessions, _providers(LoggingCodeSender(reveal=True), tmp_path))
    dev = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True)
    assert create_app(dev, sessions, _providers(LoggingCodeSender(), tmp_path)) is not None
    await engine.dispose()


async def test_the_sender_never_logs_the_code_beside_the_number_unless_told_to(
    caplog: pytest.LogCaptureFixture,
) -> None:
    quiet = LoggingCodeSender()
    with caplog.at_level(logging.INFO, logger="nura.identity.sender"):
        await quiet.send_phone_code("+6591110001", "123456")
        await quiet.send_email_link("pa@example.sg", "tok-en")
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "123456" not in logged and "+6591110001" not in logged
    assert "tok-en" not in logged and "pa@example.sg" not in logged
    assert quiet.last_code("+6591110001") == "123456"

    caplog.clear()
    loud = LoggingCodeSender(reveal=True)
    with caplog.at_level(logging.INFO, logger="nura.identity.sender"):
        await loud.send_phone_code("+6591110001", "123456")
    assert "login code for +6591110001: 123456" in caplog.text


def test_the_words_the_phone_receives() -> None:
    assert phone_code_message("481302").splitlines() == [
        "Your Nura code is 481302.",
        "Type it into the Nura app to sign in.",
        "The code works for 10 minutes.",
        "Nura will never call you to ask for it.",
    ]
    assert phone_code_message("481302", asked_by="Ash").splitlines() == [
        "Your Nura code is 481302.",
        "Ash asked for this code, to sign you in.",
        "Type it into the Nura app.",
        "The code works for 10 minutes.",
        "If you did not expect this, call Ash first.",
    ]
    assert CODE_WORKS_FOR == "The code works for 10 minutes."
    assert "481302" not in CODE_WORKS_FOR
