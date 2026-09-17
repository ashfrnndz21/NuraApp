"""Demo mode (docs/adr/0008-demo-mode.md): a deployment on the fixtures, said so everywhere.

`NURA_DEMO_MODE=1` is the one way a deployment that is not a laptop may run on the fixture
providers — the paper extractor, the transcriber, the summariser, the feed's searcher and
compressor, the drug registry, the reference ranges and the WhatsApp sandbox — none of which is
real yet. In exchange it holds four promises, each enforced here or at startup:

1. It says so on every screen: the web client asks `GET /deployment` and shows the banner;
   the printable card prints it; the API's own page is titled as a demo.
2. It takes no real phone number. A number is accepted only from the reserved test range
   (`is_demo_number`): the login code sender refuses any other, and `DemoNumbersOnly`
   refuses any JSON body that carries one, whatever route it is for.
3. Nobody receives a code. `app.identity.providers.DemoCodeSender` sends nothing; the one code
   that signs a test number in is the operator's (`NURA_DEMO_LOGIN_CODE`), given to the people
   he invites.
4. It forgets. Every row is wiped each night at 03:00 on the region's wall clock (`wipe_if_due`,
   run at startup and every few minutes after), and so is a local object store; a bucket
   expires its objects by its own lifecycle rule (docs/deploy.md).

Demo mode and a dev run are exclusive: a demo never prints a login code and never freezes
the clock.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import exists, inspect, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import clock
from app.errors import Refusal
from app.regions import REGION_TZ, Region

log = logging.getLogger("nura.demo")

DEMO_NUMBER = re.compile(r"^\+(?:650[0-9]{7}|600[0-9]{8,9})$")
"""The reserved test range: a Singapore number `+65 0xxx xxxx` or a Malaysian `+60 0…`.
Neither country gives a subscriber number that begins with 0 — in both, 0 is the trunk
prefix that E.164 drops — so no number in this range reaches a real phone."""

PHONE_SHAPE = re.compile(r"^\+[1-9][0-9]{7,14}$")
"""What the API accepts as a phone number (`app.channels.api.schemas.PHONE`)."""

WIPE_AT = time(3, 0)
"""When a demo forgets, on the region's wall clock."""

WIPE_CHECK_SECONDS = 300
"""How often a running demo asks whether the night's wipe is due."""


class NotInTheDemo(Refusal):
    """A demo deployment takes test numbers only (+65 0… or +60 0…), and signs in by phone."""


def is_demo_number(phone_e164: str) -> bool:
    return DEMO_NUMBER.match(phone_e164) is not None


def refuse_unless_demo_number(phone_e164: str) -> None:
    if not is_demo_number(phone_e164):
        raise NotInTheDemo("a demo takes test numbers only: +65 0xxx xxxx or +60 0…")


def real_numbers_in(value: Any) -> bool:
    """Whether any string in this JSON value is shaped like a phone number and is not a test one."""
    if isinstance(value, str):
        return PHONE_SHAPE.match(value) is not None and not is_demo_number(value)
    if isinstance(value, dict):
        return any(real_numbers_in(item) for item in value.values())
    if isinstance(value, list):
        return any(real_numbers_in(item) for item in value)
    return False


Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REFUSED = json.dumps({"refusal": NotInTheDemo.__name__}).encode()


class DemoNumbersOnly:
    """ASGI middleware on a demo deployment: a JSON body carrying a real-looking phone number
    is refused (403, `{"refusal": "NotInTheDemo"}`) before any route reads it.

    One place, so a new route that takes a number — a helper's, a clinic's, a stranger's on
    WhatsApp — is covered the day it is written. A body that is not JSON, or not valid JSON,
    goes on to the route unread, which answers it as it would anywhere else.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        content_type = dict(scope.get("headers") or []).get(b"content-type", b"")
        if not content_type.split(b";")[0].strip().endswith(b"json"):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            more = bool(message.get("more_body"))
        body = b"".join(chunks)
        try:
            refused = real_numbers_in(json.loads(body)) if body else False
        except ValueError:
            refused = False
        if refused:
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": REFUSED})
            return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


# --- the night's wipe ----------------------------------------------------------------------


def last_wipe_boundary(now: datetime, region: Region) -> datetime:
    """The most recent 03:00 on the region's wall clock at or before `now`, in UTC."""
    local = now.astimezone(REGION_TZ[region])
    boundary = datetime.combine(local.date(), WIPE_AT, tzinfo=REGION_TZ[region])
    if boundary > local:
        boundary -= timedelta(days=1)
    return boundary.astimezone(UTC)


async def wipe_due(session: AsyncSession, region: Region) -> bool:
    """Whether anything is older than the last 03:00: an account, or a login asked for.

    Every row a demo holds hangs off a person, and nobody becomes a person without a login
    challenge first, so these two tables are enough to know the night has come and gone
    since something was written. Nothing else is looked at, and nothing is kept to remember
    the last wipe: the data is its own record of it.
    """
    from app.identity.models import LoginChallenge, Person

    boundary = last_wipe_boundary(clock.now(), region)
    older = select(
        or_(
            exists().where(Person.created_at < boundary),
            exists().where(LoginChallenge.issued_at < boundary),
        )
    )
    return bool(await session.scalar(older))


async def wipe(session: AsyncSession, object_root: Path | None = None) -> list[str]:
    """Every row of every table, and a local object store's bytes, gone. The schema stays
    (alembic's version table with it), so the demo is at once ready for the next visitor.
    Demo only: `wipe_if_due` and the app's lifespan are the only callers."""

    def names(sync_session: Any) -> list[str]:
        connection = sync_session.connection()
        ordered = [
            name
            for name, _ in inspect(connection).get_sorted_table_and_fkc_names()
            if name is not None
        ]
        return [name for name in ordered if name != "alembic_version"]

    tables: list[str] = await session.run_sync(names)
    if not tables:
        return []
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        quoted = ", ".join(f'"{name}"' for name in tables)
        await session.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))
    else:
        for name in reversed(tables):
            await session.execute(text(f'DELETE FROM "{name}"'))
    if object_root is not None and object_root.is_dir():
        shutil.rmtree(object_root, ignore_errors=True)
    return tables


async def wipe_if_due(
    sessions: async_sessionmaker[Any],
    region: Region,
    object_root: Path | None = None,
    *,
    after_wipe: Callable[[], Awaitable[None]] | None = None,
) -> bool:
    """Wipe the demo if the night's 03:00 has passed since anything in it was written.

    `after_wipe`, when given, runs once the wipe has committed — `app.demo_seed.seed_demo`,
    on a deployment seeded with NURA_DEMO_SEED=1, so Pa's profile and Mei as his chief are
    there again the moment the tables are empty, not only at the process's own start."""
    async with sessions() as session:
        if not await wipe_due(session, region):
            return False
        wiped = await wipe(session, object_root)
        await session.commit()
    log.info("demo: the night's wipe emptied %d tables", len(wiped))
    if after_wipe is not None:
        await after_wipe()
    return True


async def keep_wiping(
    sessions: async_sessionmaker[Any],
    region: Region,
    object_root: Path | None = None,
    *,
    after_wipe: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """The demo's night watch: every few minutes, for as long as it runs. The app's lifespan
    checks once before it serves; this is every check after that."""
    while True:
        await asyncio.sleep(WIPE_CHECK_SECONDS)
        await wipe_quietly(sessions, region, object_root, after_wipe=after_wipe)


async def wipe_quietly(
    sessions: async_sessionmaker[Any],
    region: Region,
    object_root: Path | None = None,
    *,
    after_wipe: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """`wipe_if_due`, where a failure is logged and tried again later: the demo keeps serving
    with its database away, and `/health/ready` is what says so."""
    try:
        await wipe_if_due(sessions, region, object_root, after_wipe=after_wipe)
    except Exception:
        log.exception("demo: the wipe check failed; trying again shortly")
