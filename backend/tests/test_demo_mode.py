"""Demo mode (ADR 0008): fixtures allowed, a banner everywhere, test numbers only, wiped nightly.

The demo is served here the way a deployment serves it — `create_app` with demo settings and
the demo code sender — on the suite's database (SQLite, or a Postgres schema in CI).
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.channels.api import create_app
from app.clock import FrozenClock
from app.db import KeptSession, make_session_factory
from app.demo import (
    DEMO_NUMBER,
    DemoNumbersOnly,
    is_demo_number,
    last_wipe_boundary,
    real_numbers_in,
    wipe_if_due,
)
from app.identity.models import LoginChallenge, Person
from app.identity.providers import (
    DemoCodeSender,
    DemoSenderOutsideDemo,
    LoggingCodeSender,
    NoCodeSender,
    code_sender_for,
)
from app.regions import Region
from app.settings import DemoAndDevTogether, MissingSetting, Settings, load_settings
from tests.conftest import regional_database
from tests.whatsapp_support import deployment as fixture_deployment

CODE = "246810"
PA = "+6500001234"
MEI = "+6500005678"
ENV = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}


def test_the_test_range_is_numbers_no_phone_can_have() -> None:
    for number in ("+6500001234", "+6509999999", "+60012345678", "+600123456789"):
        assert is_demo_number(number), number
    for number in ("+6591234567", "+6561234567", "+60123456789", "+650123456", "+44700900000"):
        assert not is_demo_number(number), number
    assert DEMO_NUMBER.pattern.startswith("^")


def test_demo_settings_are_strict() -> None:
    demo = load_settings({**ENV, "NURA_DEMO_MODE": "1", "NURA_DEMO_LOGIN_CODE": CODE})
    assert demo.demo_mode and demo.fixtures_allowed and demo.demo_login_code == CODE
    assert load_settings({**ENV, "NURA_DEMO_MODE": "true"}).demo_mode is False
    with pytest.raises(MissingSetting, match="NURA_DEMO_LOGIN_CODE"):
        load_settings({**ENV, "NURA_DEMO_MODE": "1"})
    with pytest.raises(MissingSetting, match="six digits"):
        load_settings({**ENV, "NURA_DEMO_MODE": "1", "NURA_DEMO_LOGIN_CODE": "12345"})
    with pytest.raises(MissingSetting, match="demo only"):
        load_settings({**ENV, "NURA_DEMO_LOGIN_CODE": CODE})
    with pytest.raises(DemoAndDevTogether):
        load_settings(
            {**ENV, "NURA_DEMO_MODE": "1", "NURA_DEMO_LOGIN_CODE": CODE, "NURA_DEV_CODE_SENDER": "1"}
        )
    with pytest.raises(NoCodeSender):
        code_sender_for(load_settings(ENV))
    assert isinstance(code_sender_for(demo), DemoCodeSender)


def test_a_frozen_clock_is_refused_on_a_demo() -> None:
    with pytest.raises(RuntimeError, match="dev run only"):
        load_settings(
            {
                **ENV,
                "NURA_DEMO_MODE": "1",
                "NURA_DEMO_LOGIN_CODE": CODE,
                "NURA_FROZEN_CLOCK": "2026-09-14T10:00:00+08:00",
            }
        )


def test_json_carrying_a_real_number_anywhere_is_caught() -> None:
    assert real_numbers_in({"phone_e164": "+6591234567"})
    assert real_numbers_in({"helpers": [{"name": "Siti", "phone": "+60123456789"}]})
    assert not real_numbers_in({"phone_e164": PA, "note": "call me at 9123 4567", "n": 6591234567})


@dataclass
class Demo:
    client: AsyncClient
    sessions: async_sessionmaker[KeptSession]
    settings: Settings
    objects: Path


DEMO = Settings(
    region=Region.SG,
    database_url="sqlite+aiosqlite://",
    demo_mode=True,
    demo_login_code=CODE,
    whatsapp_dev_secret="demo-webhook-secret",
)


@pytest.fixture
async def demo() -> AsyncIterator[Demo]:
    root = Path(tempfile.mkdtemp(prefix="nura-demo-"))
    _, fixtures = fixture_deployment(root)
    providers = type(fixtures)(
        **{
            **{name: getattr(fixtures, name) for name in fixtures.__dataclass_fields__},
            "code_sender": DemoCodeSender(CODE),
        }
    )
    async with regional_database() as engine:
        sessions = make_session_factory(engine)
        app = create_app(DEMO, sessions, providers)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://demo.test") as c:
            yield Demo(c, sessions, DEMO, root / Region.SG.value)


async def _sign_in(client: AsyncClient, phone: str) -> dict[str, str]:
    started = await client.post("/api/auth/phone/start", json={"phone_e164": phone})
    assert started.status_code == 202, started.text
    assert CODE not in started.text
    verified = await client.post("/api/auth/phone/verify", json={"phone_e164": phone, "code": CODE})
    assert verified.status_code == 200, verified.text
    return {"Authorization": f"Bearer {verified.json()['token']}"}


async def test_a_test_number_signs_in_with_the_operators_code(
    demo: Demo, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        await _sign_in(demo.client, PA)
    assert CODE not in caplog.text and PA not in caplog.text
    wrong = await demo.client.post("/auth/phone/verify", json={"phone_e164": MEI, "code": CODE})
    assert wrong.status_code != 200  # no challenge was asked for this number


async def test_a_real_number_is_refused_before_anything_is_written(demo: Demo) -> None:
    refused = await demo.client.post("/auth/phone/start", json={"phone_e164": "+6591234567"})
    assert refused.status_code == 403 and refused.json() == {"refusal": "NotInTheDemo"}
    async with demo.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(LoginChallenge)) == 0


async def test_the_sender_refuses_a_real_number_even_past_the_guard() -> None:
    sender = DemoCodeSender(CODE)
    with pytest.raises(Exception, match="test numbers"):
        sender.shared_code("+6591234567")
    with pytest.raises(Exception, match="test numbers"):
        await sender.send_phone_code("+6591234567", CODE)
    assert sender.shared_code(PA) == CODE


async def test_email_sign_in_is_refused_on_a_demo(demo: Demo) -> None:
    refused = await demo.client.post("/auth/email/start", json={"email": "pa@example.com"})
    assert refused.status_code == 403 and refused.json() == {"refusal": "NotInTheDemo"}


async def test_a_real_number_in_any_json_body_is_refused(demo: Demo) -> None:
    headers = await _sign_in(demo.client, PA)
    refused = await demo.client.post(
        "/profiles/for-someone", headers=headers, json={"patient_phone_e164": "+6591234567"}
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NotInTheDemo"}


async def test_the_web_client_is_told_it_is_a_demo(demo: Demo) -> None:
    for path in ("/deployment", "/api/deployment"):
        assert (await demo.client.get(path)).json() == {"region": "SG", "demo": True}
    assert (await demo.client.get("/api/health/ready")).json() == {"status": "ok"}
    page = (await demo.client.get("/openapi.json")).json()
    assert "not for real health information" in page["info"]["title"]


async def test_dev_routes_stay_shut_on_a_demo(demo: Demo) -> None:
    assert (await demo.client.get("/dev/clock")).status_code in (403, 404)
    inbound = await demo.client.post("/dev/whatsapp/inbound", json={"from_e164": PA, "text": "hi"})
    assert inbound.status_code == 404


def test_the_demo_sender_is_refused_outside_a_demo(tmp_path: Path) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    _, fixtures = fixture_deployment(tmp_path)
    providers = type(fixtures)(
        **{
            **{name: getattr(fixtures, name) for name in fixtures.__dataclass_fields__},
            "code_sender": DemoCodeSender(CODE),
        }
    )
    dev = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True)
    with pytest.raises(DemoSenderOutsideDemo):
        create_app(dev, make_session_factory(create_async_engine("sqlite+aiosqlite://")), providers)


async def test_the_logging_sender_is_refused_on_a_demo(tmp_path: Path) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.identity.providers import DevSenderInProduction

    _, fixtures = fixture_deployment(tmp_path)
    assert isinstance(fixtures.code_sender, LoggingCodeSender)
    engine = create_async_engine("sqlite+aiosqlite://")
    with pytest.raises(DevSenderInProduction):
        create_app(DEMO, make_session_factory(engine), fixtures)
    await engine.dispose()


def test_the_night_is_three_in_the_morning_on_the_wall_clock() -> None:
    # 02:00 UTC on 15 September is 10:00 in Singapore: the last wipe was 03:00 that morning.
    assert last_wipe_boundary(datetime(2026, 9, 15, 2, 0, tzinfo=UTC), Region.SG) == datetime(
        2026, 9, 14, 19, 0, tzinfo=UTC
    )
    # 18:59 UTC is 02:59 the next morning in Singapore: still the night before's boundary.
    assert last_wipe_boundary(datetime(2026, 9, 15, 18, 59, tzinfo=UTC), Region.SG) == datetime(
        2026, 9, 14, 19, 0, tzinfo=UTC
    )
    assert last_wipe_boundary(datetime(2026, 9, 15, 19, 0, tzinfo=UTC), Region.MY) == datetime(
        2026, 9, 15, 19, 0, tzinfo=UTC
    )


async def test_the_night_wipes_every_row_and_the_morning_starts_empty(
    demo: Demo, clock: FrozenClock
) -> None:
    clock.set(datetime(2026, 9, 15, 2, 0, tzinfo=UTC))  # 10:00 in Singapore
    headers = await _sign_in(demo.client, PA)
    assert (await demo.client.get("/me", headers=headers)).status_code == 200
    demo.objects.mkdir(parents=True, exist_ok=True)
    (demo.objects / "left-over").write_bytes(b"x")

    # The same day: nothing is older than this morning's 03:00, so nothing goes.
    clock.step(timedelta(hours=16))  # 02:00 the next morning in Singapore
    assert await wipe_if_due(demo.sessions, Region.SG, demo.objects) is False

    clock.step(timedelta(hours=1, minutes=1))  # 03:01: the night has come
    assert await wipe_if_due(demo.sessions, Region.SG, demo.objects) is True
    async with demo.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Person)) == 0
        assert await session.scalar(select(func.count()).select_from(LoginChallenge)) == 0
    assert not demo.objects.exists()
    assert (await demo.client.get("/me", headers=headers)).status_code == 401
    assert await wipe_if_due(demo.sessions, Region.SG, demo.objects) is False

    # The next visitor signs in on the empty demo as if it were new.
    await _sign_in(demo.client, MEI)


async def test_the_lifespan_checks_for_the_wipe_before_serving(clock: FrozenClock) -> None:
    root = Path(tempfile.mkdtemp(prefix="nura-demo-"))
    _, fixtures = fixture_deployment(root)
    providers = type(fixtures)(
        **{
            **{name: getattr(fixtures, name) for name in fixtures.__dataclass_fields__},
            "code_sender": DemoCodeSender(CODE),
        }
    )
    async with regional_database() as engine:
        sessions = make_session_factory(engine)
        app = create_app(DEMO, sessions, providers)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://d.test") as c:
            await _sign_in(c, PA)
        clock.step(timedelta(days=1))
        async with app.router.lifespan_context(app), sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Person)) == 0
    assert any(m.cls is DemoNumbersOnly for m in app.user_middleware)


async def test_the_printable_card_says_demo_first(demo: Demo) -> None:
    headers = await _sign_in(demo.client, PA)
    words = (await demo.client.get("/consent/wording", params={"language": "en"})).json()
    opened = await demo.client.post(
        "/profiles/mine",
        headers=headers,
        json={
            "consent": {
                "wording_version": words["version"],
                "language": "en",
                "captured_via": "app",
            },
            "display_name": "Pa",
            "language": "en",
        },
    )
    assert opened.status_code == 201, opened.text
    page = await demo.client.get(
        f"/profiles/{opened.json()['profile_id']}/emergency-card.html", headers=headers
    )
    assert page.status_code == 200, page.text
    body = page.text
    assert body.index("Demo — not for real health information") < body.index("<h1>")
