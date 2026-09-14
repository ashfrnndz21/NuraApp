"""What the trend, routine and calendar tests share: a Pa with his papers confirmed through
the review card, and a look at every row in the database."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEntry, Outcome
from app.db import Base
from app.ingestion.extract import extraction_from_fixture
from app.ingestion.models import FieldState
from app.ingestion.review import (
    Decision,
    card_fields,
    card_from,
    confirm_review_card,
    review_draft_for,
)
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from tests.medicines_support import artefact
from tests.paper import fixture


async def confirm_paper(session: AsyncSession, context: KeyContext, label: str) -> None:
    """The review-card path: a photo, its card, every field confirmed as read, one yes."""
    photo = await artefact(session, context)
    card = await card_from(
        session, context=context, artifact=photo, extraction=extraction_from_fixture(fixture(label))
    )
    fields = await card_fields(session, context=context, card_id=card.id)
    decisions = [Decision(field_id=f.id, decision=FieldState.CONFIRMED) for f in fields]
    draft = await review_draft_for(session, context=context, card_id=card.id, decisions=decisions)
    yes = await confirm(session, context, draft)
    await confirm_review_card(
        session, context=context, card_id=card.id, decisions=decisions, confirmation_id=yes.id
    )


async def refusals(session: AsyncSession, context: KeyContext, name: str) -> list[AuditEntry]:
    found = await session.scalars(
        select(AuditEntry).where(
            AuditEntry.profile_id == context.profile_id,
            AuditEntry.outcome == Outcome.REFUSED,
            AuditEntry.refused_because == name,
        )
    )
    return list(found)


async def every_value(session: AsyncSession) -> list[Any]:
    """Every value in every column of every table: where a word would be if it were kept."""
    values: list[Any] = []
    for table in Base.metadata.sorted_tables:
        for row in (await session.execute(select(table))).all():
            values.extend(row)
    return values
