"""Where a confirmed `Fact`'s own printed range still lives (D-1, audit-2026-09-22.md §3.1).

`Fact` (`app.memory.models`) carries no range of its own — only the `ReviewField` it was
confirmed from does (`app.ingestion.models.ReviewField.range`, defect #3's own fix). Nothing
here recomputes a range or asks a guideline table (`app.reasoning.ranges` answers a different
question — his own band against a published table, never what the paper itself prints): this
only ever matches a fact back to the field it was confirmed from, on the same artefact, by
subject and attribute, and reads the range exactly as that field carried it — the paper's own
row, never Nura's opinion of one.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.ingestion.extract import PrintedRange
from app.ingestion.models import ReviewCard, ReviewField
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Fact


async def printed_range_for_fact(
    session: AsyncSession, context: KeyContext, fact: Fact
) -> PrintedRange | None:
    """The range printed on the paper `fact` was read from, when the field it was confirmed
    from carried one — `None` when the fact did not come from a paper at all (an `event_id`
    fact, never an `artifact_id`), when no review field of the same subject and attribute is
    found on that paper, or when the field carried no range (most rows print none)."""
    if fact.artifact_id is None:
        return None
    cards = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.artifact_id == fact.artifact_id,),
    )
    card_ids = [card.id for card in cards]
    if not card_ids:
        return None
    fields = await audited_read(
        session,
        ReviewField,
        context,
        Scope.RECORDS,
        where=(
            ReviewField.card_id.in_(card_ids),
            ReviewField.subject == fact.subject,
            ReviewField.attribute == fact.attribute,
        ),
    )
    for field in fields:
        if field.range is not None:
            low = field.range.get("low")
            high = field.range.get("high")
            return PrintedRange(
                low=low if isinstance(low, float | int) else None,
                high=high if isinstance(high, float | int) else None,
                text=str(field.range.get("text") or ""),
            )
    return None


def band_of_printed(value: float, printed: PrintedRange) -> str:
    """`"within_range" | "above_range" | "below_range"`, from the paper's own printed bound(s)
    alone — the same inclusive-at-both-ends reading `app.reasoning.ranges.Range.band_of` uses
    for a guideline range, applied here to the paper's own numbers instead of a published
    table's. Never called when `printed` carries neither bound (that is "no range printed",
    handled by the caller, not here)."""
    if printed.low is not None and printed.high is not None:
        if value < printed.low:
            return "below_range"
        return "above_range" if value > printed.high else "within_range"
    if printed.high is not None:
        return "within_range" if value <= printed.high else "above_range"
    if printed.low is not None:
        return "within_range" if value >= printed.low else "below_range"
    return "within_range"  # pragma: no cover — caller checks low/high is-None first
