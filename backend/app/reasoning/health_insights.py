"""Health Insights (design-direction.md, Health tab): cards built from his own records.

Each card is a true statement about what he did — doses steady this week, days checked in,
today's steps, today's water — never a speculation and never advice; nothing here diagnoses
or grades him (`docs/plain-words.md`, the boundary in `app.safety.boundary`). Composed from
the same numbers `app.reasoning.health_overview` renders the ring and the metric rows from, so
an insight and the overview it explains never disagree.

An insight is shown only when there is something true to say: no doses this week because he
has no active medicine yet, no steps because he has not logged any today — the card is left
out, never filled with an invented "no data" line that would itself be a kind of claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.health_strings import active_insight, checked_in_insight, doses_insight, water_insight
from app.keys.context import KeyContext
from app.lifestyle.metrics import MetricKind, metric_row
from app.reasoning.health_overview import check_ins_this_week, doses_this_week


@dataclass(frozen=True, slots=True)
class Insight:
    kind: str
    headline: str
    detail: str


async def health_insights(
    session: AsyncSession, *, context: KeyContext, language: str | None = None, patient: str = ""
) -> list[Insight]:
    """Every card there is a true thing to say, in the order a person would want to hear them:
    how the week's medicine went, whether he has been in touch, then today's numbers."""
    cards: list[Insight] = []
    doses = await doses_this_week(session, context=context)
    if doses.total > 0:
        headline, detail = doses_insight(doses.taken, doses.total, language=language)
        cards.append(Insight(kind="doses", headline=headline, detail=detail))
    check_ins = await check_ins_this_week(session, context=context)
    if check_ins.days > 0:
        headline, detail = checked_in_insight(check_ins.days, language=language)
        cards.append(Insight(kind="check_ins", headline=headline, detail=detail))
    steps = await metric_row(session, context=context, kind=MetricKind.STEPS)
    if steps.value:
        headline, detail = active_insight(steps.value, language=language)
        cards.append(Insight(kind="steps", headline=headline, detail=detail))
    water = await metric_row(session, context=context, kind=MetricKind.WATER)
    if water.value:
        headline, detail = water_insight(water.value, language=language)
        cards.append(Insight(kind="water", headline=headline, detail=detail))
    return cards


__all__ = ["Insight", "health_insights"]
