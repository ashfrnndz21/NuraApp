"""A yes is spent once even when two requests race for it on two connections.

`app.keys.confirm.consume_confirmation` spends a yes with one conditional UPDATE
(`… WHERE id = :id AND consumed_at IS NULL`) and refuses unless exactly one row changed. On
SQLite in the suite every session shares one connection, so two spends cannot overlap and the
second is refused by the plain read before it. On Postgres (the backend-postgres CI job,
NURA_TEST_DATABASE_URL) they can overlap, and this test makes them. Both requests read the yes
unspent. The second reaches the UPDATE while the first holds the row, and waits on its lock.
Once the first commits, the second's UPDATE finds no unspent row, asyncpg reports
`UPDATE 0`, and it is refused.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import text

from app.db import make_session_factory, take_keepers
from app.drafts import OnlyMeDraft
from app.identity.service import create_own_profile, register_person
from app.keys.confirm import AlreadySpent, confirm, consume_confirmation
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


async def test_two_spends_of_one_yes_race_and_only_one_lands() -> None:
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
            draft = OnlyMeDraft(scope="notes", only_me=True)
            yes = (await confirm(setup, owner, draft)).id
            await setup.commit()
            take_keepers(setup)

        async with sessions() as first, sessions() as second, engine.connect() as watch:
            spent = await consume_confirmation(first, owner, yes, draft)
            assert spent.consumed_at is not None  # the first holds the row, not yet committed

            racing = asyncio.create_task(consume_confirmation(second, owner, yes, draft))
            deadline = time.monotonic() + 8
            while (await watch.execute(text(WAITING))).scalar_one() < 1:
                assert not racing.done(), "the second spend finished without waiting"
                assert time.monotonic() < deadline, "the second spend never waited on the row"
                await asyncio.sleep(0.05)

            await first.commit()
            with pytest.raises(AlreadySpent):
                await racing
            await second.rollback()
            take_keepers(first)
            take_keepers(second)

        async with sessions() as after:
            spends = (
                await after.execute(
                    text("SELECT count(*) FROM confirmation WHERE consumed_at IS NOT NULL")
                )
            ).scalar_one()
            assert spends == 1
