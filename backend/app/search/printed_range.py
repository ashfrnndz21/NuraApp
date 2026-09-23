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
from app.ingestion.models import FieldState, ReviewCard, ReviewField
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.models import Fact


async def printed_range_for_fact(
    session: AsyncSession, context: KeyContext, fact: Fact
) -> PrintedRange | None:
    """The range printed on the paper `fact` was read from, when the field it was confirmed
    from carried one — `None` when the fact did not come from a paper at all (an `event_id`
    fact, never an `artifact_id`), when no CONFIRMED review field of the same subject and
    attribute is found on that paper, or when the field carried no range (most rows print
    none).

    Only a field the person actually confirmed may answer (review blocker 3): a REJECTED or
    still-PROPOSED field's range is not his own yes, and a subject/attribute match alone —
    same paper, same code — is not enough to trust it, since two rows can share both (two
    passes of the same panel, a correction). The field this fact was itself confirmed from
    (`ReviewField.fact_id == fact.id`) is preferred when one is on file; only when none is
    does a same-subject-and-attribute CONFIRMED field on the same paper stand in.

    A low bound over the high one is never trusted (review blocker 4): `band_of_printed`
    assumes `low <= high`, and a range this backwards is a misread, not a real one — treated
    as no range printed, the same refusal `parse_printed_range`/`_printed_range_of` already
    give a backwards range at extraction time; this is the belt for a row that reached the
    database some other way."""
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
            ReviewField.state == FieldState.CONFIRMED,
        ),
    )
    by_fact = [field for field in fields if field.fact_id == fact.id]
    for field in by_fact or fields:
        if field.range is not None:
            low = field.range.get("low")
            high = field.range.get("high")
            low = low if isinstance(low, float | int) else None
            high = high if isinstance(high, float | int) else None
            if low is not None and high is not None and low > high:
                low, high = None, None
            return PrintedRange(low=low, high=high, text=str(field.range.get("text") or ""))
    return None


def band_of_printed(value: float, printed: PrintedRange) -> str | None:
    """`"within_range" | "above_range" | "below_range"`, from the paper's own printed bound(s)
    alone — the same inclusive-at-both-ends reading `app.reasoning.ranges.Range.band_of` uses
    for a guideline range, applied here to the paper's own numbers instead of a published
    table's. `None` — treat exactly as "no range printed" — when neither bound is on file, or
    (review blocker 4, belt over `printed_range_for_fact`'s own guard) a low bound over the
    high one: a range printed backwards is a misread, never a real comparison to make."""
    if printed.low is not None and printed.high is not None and printed.low > printed.high:
        return None
    if printed.low is not None and printed.high is not None:
        if value < printed.low:
            return "below_range"
        return "above_range" if value > printed.high else "within_range"
    if printed.high is not None:
        return "within_range" if value <= printed.high else "above_range"
    if printed.low is not None:
        return "within_range" if value >= printed.low else "below_range"
    return None
