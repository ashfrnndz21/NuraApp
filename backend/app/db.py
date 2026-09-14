"""The declarative base, the column types every table shares, and the regional engine.

`ProfileScoped` is the mixin every table of profile data carries. It is what makes the
patient node the owner of all data: there is no route to a row that does not name a profile,
and `app.keys.repository` is the only place allowed to fill that column in or filter on it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid, event, inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, object_session

from app import clock
from app.errors import Refusal


def utcnow() -> datetime:
    """Now, from the one clock (`app.clock`), always with a timezone. Every timestamp Nura
    stores is UTC, and none of them comes from a caller."""
    return clock.now()


def as_utc(moment: datetime) -> datetime:
    """Read a timestamp back as UTC-aware, whichever database dropped the timezone."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def enum_column[E: PyEnum](enum_class: type[E], name: str) -> Enum:
    """Store an enum by its value as a checked string, so the same DDL runs everywhere."""
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class ImmutableRow(Refusal):
    """What came in is what came in. A wrong fact is superseded, never edited."""


OnlyWhen = Callable[[Any, Any], bool]
"""(session, row) -> whether the one change a frozen row takes may happen right now."""


def frozen(
    model: type[Any],
    *,
    except_for: frozenset[str] = frozenset(),
    only_when: OnlyWhen | None = None,
) -> None:
    """Refuse any update to a row of this table beyond the columns named.

    The columns in `except_for` may be set, never unset — a superseded fact is not
    resurrected, a closed episode not reopened, a spent yes not un-spent, by writing None
    over the moment it happened. With `only_when`, even those columns change only while the
    service that owns the change says so (through `session.info`), so a bare assignment
    flushed from anywhere else is refused too.
    """

    @event.listens_for(model, "before_update")
    def _refuse(mapper: Any, connection: Any, target: Any) -> None:
        changed = {
            attribute.key: attribute.history
            for attribute in inspect(target).attrs
            if attribute.history.has_changes()
        }
        if not changed:
            return
        if changed.keys() - except_for:
            raise ImmutableRow(f"{model.__tablename__} rows are not edited")
        if any(history.added == [None] for history in changed.values()):
            raise ImmutableRow(f"{model.__tablename__} rows are not un-done")
        if only_when is not None and not only_when(object_session(target), target):
            raise ImmutableRow(f"{model.__tablename__} rows change only through their service")


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        uuid.UUID: Uuid(),
        datetime: DateTime(timezone=True),
    }


class ProfileScoped:
    """Mixin for every table that holds profile data.

    Read it through `app.keys.repository.scoped_select` and write it through `scoped_new`.
    Nothing else may set or filter `profile_id`.
    """

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True
    )

    if TYPE_CHECKING:
        # Every table carrying this mixin also inherits Base, which is where the real
        # constructor and table name come from. Declaring them here is what lets
        # `scoped_new` and the audit trail stay generic over any table of profile data.
        __tablename__: str

        def __init__(self, **values: Any) -> None: ...


Keeper = Callable[[AsyncSession], Awaitable[None]]
"""Something to re-do in a session after the work it was part of has been rolled back."""

_KEPT = "keep_on_refusal"


def keep_on_refusal(session: AsyncSession, keeper: Keeper) -> None:
    """Register work that must land even if the unit of work it was written in is rolled back.

    A refusal is an exception, and a channel runs each request inside a savepoint that it
    rolls back on a Refusal — which would take the refused audit line down with it. So the
    trail registers a keeper here as well as writing the line; the channel rolls the savepoint
    back, then replays the keepers and commits. On success the keepers are dropped.
    """
    session.info.setdefault(_KEPT, []).append(keeper)


def take_keepers(session: AsyncSession) -> list[Keeper]:
    """The keepers registered on this session, removed from it. Replay them, or drop them."""
    return session.info.pop(_KEPT, [])


class KeepersNotReplayed(RuntimeError):
    """A session closed with refused audit lines nobody replayed: a request ran outside
    `unit_of_work`, and the refusal it carried would have been lost with the rollback."""


@asynccontextmanager
async def unit_of_work(session: AsyncSession) -> AsyncIterator[None]:
    """The request boundary: one unit of work, in a savepoint, with the keepers handled.

    On a `Refusal` the savepoint is rolled back — nothing the request wrote survives — then
    the keepers are replayed and flushed, so the refused lines land, and the refusal goes on
    up to the channel. On any other exception the savepoint is rolled back and the keepers
    are dropped with it. On success the savepoint is released and the keepers are dropped:
    the lines they would have re-written are already there.

    Channels own the boundary: the API's request dependency wraps each request in this, and
    nothing in the core calls it — the core raises, the channel decides. The guard against a
    channel forgetting is `KeptSession`: a session closed with keepers still on it raises
    `KeepersNotReplayed`, so a path that skips the boundary fails loudly instead of losing a
    refusal quietly.
    """
    savepoint = await session.begin_nested()
    try:
        yield
    except Refusal:
        await savepoint.rollback()
        for keeper in take_keepers(session):
            await keeper(session)
        await session.flush()
        raise
    except BaseException:
        await savepoint.rollback()
        take_keepers(session)
        raise
    else:
        await savepoint.commit()
        take_keepers(session)


@asynccontextmanager
async def nested_unit_of_work(session: AsyncSession) -> AsyncIterator[None]:
    """A unit of work inside a request, for a caller that means to catch a refusal and go on.

    The promise of `unit_of_work`, one level down: on a `Refusal` its own savepoint is rolled
    back — nothing written inside it survives — the keepers registered inside it are replayed
    and flushed, so the refused lines land, and the refusal goes on up to the caller. Keepers
    registered before it are left to the request's boundary. On success the savepoint is
    released and its keepers stay registered: the request around it may still be refused.
    """
    kept: list[Keeper] = session.info.setdefault(_KEPT, [])
    mark = len(kept)
    savepoint = await session.begin_nested()
    try:
        yield
    except Refusal:
        await savepoint.rollback()
        inside = kept[mark:]
        del kept[mark:]
        for keeper in inside:
            await keeper(session)
        await session.flush()
        raise
    except BaseException:
        await savepoint.rollback()
        del kept[mark:]
        raise
    else:
        await savepoint.commit()


class KeptSession(AsyncSession):
    """A session that will not close quietly over refused lines nobody replayed.

    This is the loud guard behind `unit_of_work`: whatever channel runs a request, if it lets
    a refusal escape without replaying the keepers, closing the session raises here.
    """

    async def close(self) -> None:
        kept = take_keepers(self)
        await super().close()
        if kept:
            raise KeepersNotReplayed(
                f"{len(kept)} refused audit line(s) were registered and never replayed; "
                "run the request inside app.db.unit_of_work"
            )


SQLITE_LOCK_WAIT_SECONDS = 30
"""How long a SQLite transaction waits for the one before it to finish (laptop and CI only)."""


def _no_implicit_begin(dbapi_connection: Any, _record: Any) -> None:
    # The driver would begin a transaction on its own, as a reader; let SQLAlchemy begin it.
    dbapi_connection.isolation_level = None


def _begin_immediate(connection: Any) -> None:
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def make_engine(url: str) -> AsyncEngine:
    """The engine for one region's database. A process serves exactly one region.

    On SQLite — the laptop's and CI's database, never a deployment's — every transaction
    begins IMMEDIATE and waits for the one before it. Left to itself SQLite begins a
    transaction as a reader and upgrades it at its first write, and of two requests that
    each read and then write (every audited read writes its line) one fails at once with
    "database is locked": the 500 a reopened page met while the page before it was still
    writing its feed cards. Postgres needs none of this: its writers wait on row locks, not
    on the whole file, and none of the listeners below is installed on it. A deployment's
    Postgres sits behind a platform's network, which may close an idle connection; the pool
    checks a connection is alive before handing it out."""
    if not url.startswith("sqlite"):
        return create_async_engine(url, pool_pre_ping=True)
    engine = create_async_engine(url, connect_args={"timeout": SQLITE_LOCK_WAIT_SECONDS})
    event.listen(engine.sync_engine, "connect", _no_implicit_begin)
    event.listen(engine.sync_engine, "begin", _begin_immediate)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[KeptSession]:
    return async_sessionmaker(engine, class_=KeptSession, expire_on_commit=False)
