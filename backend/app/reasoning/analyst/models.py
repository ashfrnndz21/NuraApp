"""The Health Analyst's report (migration 0049): one row each time a report is written,
weekly by the job (`app.reasoning.analyst.weekly_job`) or on demand by
`POST /profiles/{id}/insights/stream`, which saves what it streams the moment it finishes.

Nothing here is free text from outside: `boundary` and `sections` are what
`app.reasoning.analyst.port.Report` already composed and verified before this row is
written — the same discipline `TrendCard.lines` and `state_snapshot.computed_from` already
keep, JSON because a report's shape (sections, each with insights, each with evidence) is a
tree, not a table `ProfileScoped` rows already model well.

`@monotonic` because `GET /profiles/{id}/insights` is a "latest wins" read
(`app.db.monotonic`): two reports written in the same request, or under a frozen clock in a
test or a checkpoint, must resolve to one winner, never an arbitrary one.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, monotonic, utcnow
from app.memory.models import _row_of_profile


@monotonic
class InsightReport(ProfileScoped, Base):
    """One Health Analyst report, as it was shown: the week it covers, the boundary line it
    carried, and its sections — each already the plain words a person read, already cited."""

    __tablename__ = "insight_report"
    __table_args__ = (_row_of_profile("insight_report"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    generated_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    week_of: Mapped[date] = mapped_column()
    language: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    """Which `Analyst` wrote it: `"rule"` or `"claude"` (`app.reasoning.analyst.provider`)."""
    boundary: Mapped[list[str]] = mapped_column(JSON, default=list)
    sections: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


__all__ = ["InsightReport"]
