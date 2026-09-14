"""A yes is spent once even when two spends race for it on two connections.

`app.keys.confirm.consume_confirmation` spends a yes with one conditional UPDATE
(`… WHERE id = :id AND consumed_at IS NULL`) and refuses unless exactly one row changed. On
SQLite in the suite every session shares one connection, so two spends cannot overlap; the
refusal of a second, later spend is covered there and on Postgres by the memory-review tests.
This test makes them overlap on Postgres (the backend-postgres CI job, NURA_TEST_DATABASE_URL),
with that same UPDATE on two connections of their own:

- The first changes one row and holds it.
- The second waits on the row lock, and is seen waiting from a third connection.
- Once the first commits, the second changes no row: asyncpg reports `UPDATE 0`, so its
  rowcount is 0, which is the count `consume_confirmation` refuses on.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import select, text, update

from app.clock import now
from app.db import make_session_factory, take_keepers
from app.drafts import OnlyMeDraft
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import Confirmation, confirm
from app.keys.context import resolve_key_context
from app.regions import Region
from tests.conftest import ON_POSTGRES, regional_database
from tests.support import OPENING_CONSENT

pytestmark = pytest.mark.skipif(
    not ON_POSTGRES, reason="two connections racing need a database server"
)

WAITING = (
    "SELECT count(*) FROM pg_stat_activity "
    "WHERE wait_event_type = 'Lock' AND query ILIKE 'UPDATE confirmation%'"
)


def _spend(yes_id: object):  # the statement consume_confirmation runs, as it runs it
    return (
        update(Confirmation)
        .where(Confirmation.id == yes_id, Confirmation.consumed_at.is_(None))
        .values(consumed_at=now())
    )


async def test_two_spends_of_one_yes_race_and_only_one_changes_the_row() -> None:
    async with regional_database() as engine:
        sessions = make_session_factory(engine)
        async with sessions() as setup:
            pa = await register_person(
                setup, region=Region.SG, display_name="Pa", phone_e164="+6591110001", language="en"
            )
            profile = await create_own_profile(
                setup, region=Region.SG, owner=pa, consent=OPENING_CONSENT
            )
            owner = await resolve_key_context(
                setup, region=Region.SG, person_id=pa.id, profile_id=profile.id
            )
            yes = (await confirm(setup, owner, OnlyMeDraft(scope="notes", only_me=True))).id
            await setup.commit()
            take_keepers(setup)

        async with engine.connect() as first, engine.connect() as second:
            assert (await first.execute(_spend(yes))).rowcount == 1  # held, not yet committed

            racing = asyncio.create_task(second.execute(_spend(yes)))
            async with engine.connect() as watch:
                deadline = time.monotonic() + 8
                while (await watch.execute(text(WAITING))).scalar_one() < 1:
                    assert not racing.done(), "the second spend finished without waiting"
                    assert time.monotonic() < deadline, "the second spend never waited on the row"
                    await asyncio.sleep(0.05)
                await watch.rollback()

            await first.commit()
            assert (await racing).rowcount == 0  # the count consume_confirmation refuses on
            await second.rollback()

        async with engine.connect() as after:
            spent = (
                await after.execute(select(Confirmation.consumed_at).where(Confirmation.id == yes))
            ).scalar_one()
            assert spent is not None
            await after.rollback()
