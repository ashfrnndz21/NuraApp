"""The routine table (E10-01): one row per day as it was set, superseded, never edited.

No column holds prose: the anchors are codes with an `HH:MM` time on his wall clock
(`REGION_TZ`), the prompts are codes at anchors, the walks are anchors. The medicines are not
here — they are read off the medicine lines when the day is rendered, so setting the day
never restates a dose and a dose change never needs the day set again.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, frozen, utcnow
from app.memory.models import _row_of_profile, _tied_to_profile


class Routine(ProfileScoped, Base):
    """One day as it was set: anchors, prompts, walks, the morning card, and who set it."""

    __tablename__ = "routine"
    __table_args__ = (
        _row_of_profile("routine"),
        _tied_to_profile("routine", "supersedes_id", "routine"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    anchors: Mapped[dict[str, Any]] = mapped_column(JSON)
    reading_prompts: Mapped[list[Any]] = mapped_column(JSON, default=list)
    walks: Mapped[list[Any]] = mapped_column(JSON, default=list)
    morning_card_at: Mapped[str] = mapped_column(String(5))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("routine.id"), default=None)
    superseded_at: Mapped[datetime | None] = mapped_column(default=None)
    set_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    set_at: Mapped[datetime] = mapped_column(default=utcnow)


# Supersession is the one change a routine takes.
frozen(Routine, except_for=frozenset({"superseded_at"}))
