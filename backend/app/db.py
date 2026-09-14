"""The declarative base, the column types every table shares, and the regional engine.

`ProfileScoped` is the mixin every table of profile data carries. It is what makes the
patient node the owner of all data: there is no route to a row that does not name a profile,
and `app.keys.repository` is the only place allowed to fill that column in or filter on it.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Now, always with a timezone. Every timestamp Nura stores is UTC."""
    return datetime.now(UTC)


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


def make_engine(url: str) -> AsyncEngine:
    """The engine for one region's database. A process serves exactly one region."""
    return create_async_engine(url)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
