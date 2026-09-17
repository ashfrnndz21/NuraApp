"""`app.db.monotonic`'s `seq` must not serialise unrelated requests, and must not deadlock.

#228 first gave `seq` out with a shared counter row, taken with `UPDATE ... RETURNING` inside
the asking transaction. An independent review proved that unsafe on a real Postgres 16 before
it ever ran under load: a Postgres row lock from an `UPDATE` is held until the transaction
that took it commits or rolls back, and this app runs one transaction per HTTP request
(`app.channels.api.deps.db`) that, through `app.audit.trail.record`, writes an `audit_entry` —
one of the twelve `@monotonic` tables — on nearly every read and write. So the counter row for
`audit_entry` was in effect locked from a request's first audited line until the whole request
finished, and every other request, on every profile, queued behind it; two requests taking two
tables' counter rows in opposite order deadlocked outright.

On Postgres, `monotonic` now reads `seq` from a real `SEQUENCE` instead (`nextval()`), which
takes no row lock held for the asking transaction's life. This file proves both failure modes
are gone, against a live Postgres (skipped everywhere else: two connections racing need a
database server) — see `tests/test_confirm_race.py` for the sibling test of the mechanism
this replaced, and the same technique (`pg_stat_activity`) this one starts from but does not
need, since the whole point is that nothing ever waits.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import grant_consent
from app.db import make_session_factory
from app.identity.service import create_own_profile, register_person
from app.keys.context import resolve_key_context
from app.keys.scopes import Scope
from app.regions import Region
from tests.conftest import ON_POSTGRES, regional_database
from tests.support import OPENING_CONSENT

pytestmark = pytest.mark.skipif(
    not ON_POSTGRES, reason="two connections racing need a database server"
)

BLOCKED_LONG_ENOUGH_TO_NOTICE = 1.0
"""If a second, unrelated transaction's insert takes longer than this while the first is
still open, something is once again taking a lock held for the first transaction's life."""


async def _owner(sessions: object) -> object:
    async with sessions() as setup:  # type: ignore[operator]
        pa = await register_person(
            setup, region=Region.SG, display_name="Pa", phone_e164="+6591110002", language="en"
        )
        profile = await create_own_profile(
            setup, region=Region.SG, owner=pa, consent=OPENING_CONSENT
        )
        owner = await resolve_key_context(
            setup, region=Region.SG, person_id=pa.id, profile_id=profile.id
        )
        await setup.commit()
        return owner


async def test_two_transactions_write_the_trail_without_one_blocking_the_other() -> None:
    """The exact shape the review reproduced: request A's transaction stays open (it has not
    reached the end of `app.channels.api.deps.db` yet); request B, for the same profile, must
    still get its own audited line without waiting for A to finish."""
    async with regional_database() as engine:
        sessions = make_session_factory(engine)
        owner = await _owner(sessions)

        async with sessions() as first, sessions() as second:
            await record(first, context=owner, action=Action.READ, scope=Scope.PROFILE, target="a")
            # `first` stays open — no commit — the way a request's session does until
            # `app.channels.api.deps.db` reaches its own `await session.commit()`.

            started = time.monotonic()
            await asyncio.wait_for(
                record(second, context=owner, action=Action.READ, scope=Scope.PROFILE, target="b"),
                timeout=5,
            )
            elapsed = time.monotonic() - started
            assert elapsed < BLOCKED_LONG_ENOUGH_TO_NOTICE, (
                f"the second request's audit line took {elapsed:.2f}s while the first was "
                "still open — seq is once again taking a lock held for a transaction's life"
            )

            await first.commit()
            await second.commit()


async def test_opposite_order_across_two_sequenced_tables_does_not_deadlock() -> None:
    """The other failure mode the review reproduced: two transactions each touching two
    `@monotonic` tables, in opposite order, used to deadlock on the shared counter rows.
    `audit_entry` and `consent` here, in reversed order between the two transactions —
    `nextval()` takes no row lock at all, so there is nothing left to deadlock on."""
    async with regional_database() as engine:
        sessions = make_session_factory(engine)
        owner = await _owner(sessions)

        async def consent_row(session: object) -> None:
            await grant_consent(
                session,  # type: ignore[arg-type]
                context=owner,  # type: ignore[arg-type]
                purpose=ConsentPurpose.HOLD_HEALTH_RECORD,
                captured_via=ConsentChannel.APP,
                basis=ConsentBasis.OWNER,
                language="en",
                text_version=OPENING_CONSENT.text_version,
            )

        async with sessions() as first, sessions() as second:

            async def first_order() -> None:
                await record(
                    first, context=owner, action=Action.READ, scope=Scope.PROFILE, target="a"
                )
                await consent_row(first)
                await first.commit()

            async def second_order() -> None:
                await consent_row(second)
                await record(
                    second, context=owner, action=Action.READ, scope=Scope.PROFILE, target="b"
                )
                await second.commit()

            # Run genuinely concurrently: a deadlock is a race, not a guaranteed order.
            await asyncio.wait_for(
                asyncio.gather(first_order(), second_order()), timeout=10
            )
