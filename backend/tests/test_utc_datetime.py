"""Times keep their offset: every datetime is stored as UTC (ADR 0009).

SQLite drops the offset Postgres keeps. A visit booked at 09:00+08:00 was stored as a bare
09:00, read back as 09:00 UTC, and said to him as 5 in the afternoon. Every datetime column
is now `UTCDateTime`: an aware time goes in as UTC, comes out as UTC, and a naive one is
refused rather than taken to be UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, insert, select
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db import Base, NaiveDatetime, UTCDateTime
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591110091"
NINE_IN_SINGAPORE = "2026-09-10T09:00:00+08:00"
"""Thursday 10 September, 9 in the morning on his wall clock: 01:00 UTC."""
NINE_AS_UTC = datetime(2026, 9, 10, 1, 0, tzinfo=UTC)


async def _book(deployment: Deployment, his: dict[str, str], profile_id: str, at: str) -> str:
    doctor = await deployment.client.post(
        f"/profiles/{profile_id}/providers", json={"name": "Dr Tan", "kind": "doctor"}, headers=his
    )
    assert doctor.status_code == 201, doctor.text
    booking = {
        "provider_id": doctor.json()["provider_id"],
        "scheduled_at": at,
        "purpose": "blood pressure check",
    }
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "appointment", **booking},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    booked = await deployment.client.post(
        f"/profiles/{profile_id}/appointments",
        json={**booking, "confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert booked.status_code == 201, booked.text
    appointment_id: str = booked.json()["appointment_id"]
    return appointment_id


async def test_a_visit_at_nine_in_singapore_is_nine_in_the_morning(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    reading = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=his
    )
    assert reading.status_code == 201, reading.text
    appointment_id = await _book(deployment, his, profile_id, NINE_IN_SINGAPORE)

    # Read back from the database, in a request of its own: the same instant, not 09:00 UTC.
    listed = await deployment.client.get(f"/profiles/{profile_id}/appointments", headers=his)
    assert listed.status_code == 200, listed.text
    (visit,) = [one for one in listed.json() if one["appointment_id"] == appointment_id]
    back = datetime.fromisoformat(visit["scheduled_at"])
    assert back == datetime.fromisoformat(NINE_IN_SINGAPORE) == NINE_AS_UTC

    # And said to him on his clock: 9 in the morning, never 5 in the afternoon.
    brief = await deployment.client.get(
        f"/profiles/{profile_id}/appointments/{appointment_id}/brief", headers=his
    )
    assert brief.status_code == 200, brief.text
    lines = [line["text"] for line in brief.json()["lines"]]
    assert any("9 in the morning" in line for line in lines), lines
    assert not any("in the afternoon" in line for line in lines), lines


async def test_a_visit_sent_with_no_offset_is_refused_at_the_door(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    doctor = await deployment.client.post(
        f"/profiles/{profile_id}/providers", json={"name": "Dr Tan", "kind": "doctor"}, headers=his
    )
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "appointment",
            "provider_id": doctor.json()["provider_id"],
            "scheduled_at": "2026-09-10T09:00:00",
            "purpose": "blood pressure check",
        },
        headers=his,
    )
    assert refused.status_code == 422, refused.text


_MOMENTS = MetaData()
_MOMENT = Table(
    "moment", _MOMENTS, Column("id", Integer, primary_key=True), Column("at", UTCDateTime())
)
"""A table of its own, off the app's metadata, holding one datetime column."""


async def _engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(_MOMENTS.create_all)
    return engine


@pytest.mark.parametrize(
    "offset", [timedelta(hours=8), timedelta(0), timedelta(hours=-5)], ids=["+08", "utc", "-05"]
)
async def test_the_same_instant_comes_back_whatever_offset_it_went_in_with(
    offset: timedelta,
) -> None:
    at = datetime(2026, 9, 10, 9, 0, tzinfo=timezone(offset))
    engine = await _engine()
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(_MOMENT).values(id=1, at=at))
            back = (await connection.execute(select(_MOMENT.c.at))).scalar_one()
            # Compared in SQL too: the stored value is that instant, whatever offset asks.
            found = await connection.execute(
                select(_MOMENT.c.id).where(_MOMENT.c.at == at.astimezone(timezone(-offset)))
            )
            assert found.scalar_one() == 1
    finally:
        await engine.dispose()
    assert back == at
    assert back.utcoffset() == timedelta(0) and back.tzinfo is UTC


async def test_a_naive_datetime_is_refused_never_taken_as_utc() -> None:
    engine = await _engine()
    try:
        async with engine.begin() as connection:
            naive = datetime(2026, 9, 10, 9, 0)  # noqa: DTZ001 — the bug this refuses
            with pytest.raises(StatementError) as refused:
                await connection.execute(insert(_MOMENT).values(id=1, at=naive))
    finally:
        await engine.dispose()
    assert isinstance(refused.value.orig, NaiveDatetime)


def test_every_datetime_column_is_stored_as_utc() -> None:
    """Every datetime column on the app's tables is `UTCDateTime`, whether it came through the
    type map or was declared by hand: none is a bare `DateTime` that would drop the offset."""
    columns = [column for table in Base.metadata.tables.values() for column in table.columns]
    bare = [f"{c.table.name}.{c.name}" for c in columns if isinstance(c.type, DateTime)]
    assert bare == []
    assert any(isinstance(c.type, UTCDateTime) for c in columns)
