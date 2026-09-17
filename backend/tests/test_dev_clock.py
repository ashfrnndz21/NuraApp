"""The dev run's frozen clock: NURA_FROZEN_CLOCK and POST /dev/clock, and the gate on both.

End-to-end runs freeze the backend's clock so the dose windows, the quiet hours and "today"
do not drift with the hour the suite runs at. A frozen clock anywhere but a declared dev run
would make every key window, confirm and expiry read a moment that is not now, so the setting
refuses to start a process that is not a dev run, and the route does not exist on one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app import clock
from app.channels.api import dev_clock
from app.clock import FrozenClock, FrozenClockOutsideDev, SystemClock, install_frozen, use_clock
from app.regions import Region
from app.settings import Settings, load_settings
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import FROZEN_AT, Deployment

ENV = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}
TEN_AM = "2026-09-14T10:00:00+08:00"


def test_the_setting_is_read_only_on_a_dev_run() -> None:
    assert load_settings(ENV).frozen_clock is None
    assert load_settings({**ENV, "NURA_DEV_CODE_SENDER": "1"}).frozen_clock is None
    frozen = load_settings(
        {**ENV, "NURA_DEV_CODE_SENDER": "1", "NURA_FROZEN_CLOCK": TEN_AM}
    ).frozen_clock
    assert frozen == datetime(2026, 9, 14, 2, 0, tzinfo=UTC)


def test_the_setting_refuses_to_start_a_process_that_is_not_a_dev_run() -> None:
    with pytest.raises(FrozenClockOutsideDev):
        load_settings({**ENV, "NURA_FROZEN_CLOCK": TEN_AM})
    with pytest.raises(FrozenClockOutsideDev):
        load_settings({**ENV, "NURA_DEV_CODE_SENDER": "true", "NURA_FROZEN_CLOCK": TEN_AM})


def test_the_setting_is_an_instant_with_an_offset_or_nothing_starts() -> None:
    dev = {**ENV, "NURA_DEV_CODE_SENDER": "1"}
    with pytest.raises(FrozenClockOutsideDev):
        load_settings({**dev, "NURA_FROZEN_CLOCK": "2026-09-14T10:00:00"})
    with pytest.raises(FrozenClockOutsideDev):
        load_settings({**dev, "NURA_FROZEN_CLOCK": "ten in the morning"})


def test_startup_installs_it_only_on_a_dev_run() -> None:
    at = datetime.fromisoformat(TEN_AM)
    with use_clock(SystemClock()):
        # No setting: the clock is left as it is.
        assert isinstance(install_frozen(None, dev_run=False), SystemClock)
        # Not a dev run: refused, and the real clock stays.
        with pytest.raises(FrozenClockOutsideDev):
            install_frozen(at, dev_run=False)
        assert isinstance(clock.current(), SystemClock)
        # A naive instant is refused even on a dev run.
        with pytest.raises(FrozenClockOutsideDev):
            install_frozen(at.replace(tzinfo=None), dev_run=True)
        # A dev run: frozen at exactly that instant.
        installed = install_frozen(at, dev_run=True)
        assert isinstance(installed, FrozenClock)
        assert clock.current() is installed
        assert clock.now() == at


def test_a_clock_frozen_in_singapore_time_answers_in_utc() -> None:
    """What the dev run met: a clock given `+08:00` answered in +08:00, SQLite stored the bare
    wall time, and a key revoked "at 10:00" read back as 10:00 UTC — eight hours ahead — so it
    still opened the papers. The clock answers in UTC; what is stored is UTC."""
    with use_clock(SystemClock()):
        install_frozen(datetime.fromisoformat(TEN_AM), dev_run=True)
        assert clock.now().utcoffset() == timedelta(0)
        assert clock.now() == datetime(2026, 9, 14, 2, 0, tzinfo=UTC)
        frozen = clock.current()
        assert isinstance(frozen, FrozenClock)
        frozen.set(datetime.fromisoformat("2026-09-14T22:30:00+08:00"))
        assert clock.now().isoformat() == "2026-09-14T14:30:00+00:00"


async def test_a_key_closed_on_a_frozen_clock_no_longer_opens_the_papers(
    deployment: Deployment,
) -> None:
    """The refusal a revoked key meets, on a clock frozen in Singapore time, at the very
    instant it was closed (the same second: the clock does not move by itself)."""
    http = deployment.client
    await http.post("/dev/clock", json={"at": TEN_AM})
    pa = await register_by_phone(deployment, "+6591110001")
    mei = await register_by_phone(deployment, "+6591110002")
    profile_id = await own_profile(deployment, pa)
    await let_in(deployment, pa, profile_id, "+6591110002", ["medicines", "records"], role="caregiver")
    cut = await http.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": "+6591110002",
            "role": "caregiver",
            "scopes": ["medicines", "records"],
        },
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text
    key_id = cut.json()["key_id"]
    assert (
        await http.get(f"/profiles/{profile_id}", headers=bearer(mei["token"]))
    ).status_code == 200
    closed = await http.delete(f"/profiles/{profile_id}/keys/{key_id}", headers=bearer(pa["token"]))
    assert closed.status_code == 200
    refused = await http.get(f"/profiles/{profile_id}", headers=bearer(mei["token"]))
    assert refused.status_code == 403
    assert refused.json()["refusal"] == "NoKey"


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.include_router(dev_clock.router)
    return app


async def test_there_is_no_clock_route_outside_a_dev_run() -> None:
    production = Settings(region=Region.SG, database_url="sqlite+aiosqlite://")
    before = clock.now()
    async with AsyncClient(
        transport=ASGITransport(app=_app(production)), base_url="http://nura.test"
    ) as http:
        assert (await http.get("/dev/clock")).status_code == 404
        assert (await http.post("/dev/clock", json={"at": TEN_AM})).status_code == 404
        assert (await http.post("/dev/clock", json={"step_seconds": 3600})).status_code == 404
    assert clock.now() == before


async def test_a_dev_run_on_the_real_clock_cannot_freeze_it_over_http() -> None:
    dev = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True)
    with use_clock(SystemClock()):
        async with AsyncClient(
            transport=ASGITransport(app=_app(dev)), base_url="http://nura.test"
        ) as http:
            assert (await http.get("/dev/clock")).json()["frozen"] is False
            assert (await http.post("/dev/clock", json={"at": TEN_AM})).status_code == 409
        assert isinstance(clock.current(), SystemClock)


async def test_a_dev_run_moves_its_frozen_clock(deployment: Deployment) -> None:
    http = deployment.client
    read = (await http.get("/dev/clock")).json()
    assert read["frozen"] is True
    assert datetime.fromisoformat(read["now"]) == FROZEN_AT
    moved = await http.post("/dev/clock", json={"at": "2026-09-14T22:30:00+08:00"})
    assert moved.status_code == 200
    assert datetime.fromisoformat(moved.json()["now"]) == datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    assert clock.now() == datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    stepped = await http.post("/api/dev/clock", json={"step_seconds": 5400})
    assert datetime.fromisoformat(stepped.json()["now"]) == datetime(2026, 9, 14, 16, 0, tzinfo=UTC)
    assert clock.now() - timedelta(seconds=5400) == datetime(2026, 9, 14, 14, 30, tzinfo=UTC)


async def test_the_clock_route_takes_exactly_one_move_and_an_instant_with_an_offset(
    deployment: Deployment,
) -> None:
    http = deployment.client
    assert (await http.post("/dev/clock", json={})).status_code == 422
    assert (
        await http.post("/dev/clock", json={"at": TEN_AM, "step_seconds": 60})
    ).status_code == 422
    assert (await http.post("/dev/clock", json={"at": "2026-09-14T10:00:00"})).status_code == 422
    assert clock.now() == FROZEN_AT
