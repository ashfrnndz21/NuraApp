"""Alembic, pointed at one region's database and no other.

The URL is never written in alembic.ini: it is read from NURA_DATABASE_URL, next to
NURA_REGION, so a migration run cannot be aimed at the wrong region by editing a file.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.audit import models as audit_models  # noqa: F401
from app.consent import models as consent_models  # noqa: F401
from app.db import Base
from app.identity import models as identity_models  # noqa: F401
from app.keys import models as key_models  # noqa: F401
from app.memory import models as memory_models  # noqa: F401
from app.notes import models as note_models  # noqa: F401
from app.settings import load_settings

target_metadata = Base.metadata
settings = load_settings()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
