"""The rendered lab trend (E09-01): one row each time a trend is shown to a person.

A trend is an inferring surface, so what was shown is kept the way every rendered thing is:
the State it was rendered from (`RenderedFromState.state_id`), the boundary line it carried
(`RenderedFromState.boundary`, `Surface.TREND`), the facts it drew, the direction it said and
the lines as he read them. Nothing here is free text from outside: the lines are templates
from `app.delivery.trend_strings`, filled and verified.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.memory.models import _row_of_profile, _tied_to_profile
from app.state.models import RenderedFromState


class Direction(StrEnum):
    """How the last three results moved, by arithmetic."""

    UP = "up"
    DOWN = "down"
    STEADY = "steady"
    """The last differs from the first of the three by no more than `STEADY_WITHIN`."""
    MIXED = "mixed"
    ONE = "one"
    """One result: nothing to compare yet."""
    NONE = "none"
    """No result on the record."""


class TrendCard(RenderedFromState, ProfileScoped, Base):
    """One lab trend as it was shown: which analyte, in which language, from which facts."""

    __tablename__ = "trend_card"
    __table_args__ = (
        _row_of_profile("trend_card"),
        _tied_to_profile("trend_card", "state_id", "state_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analyte: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16))
    fact_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    direction: Mapped[Direction] = mapped_column(enum_column(Direction, "trend_direction"))
    lines: Mapped[list[str]] = mapped_column(JSON, default=list)
    rendered_for_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    rendered_at: Mapped[datetime] = mapped_column(default=utcnow)


# What was shown is what was shown.
frozen(TrendCard)
