"""The lab trend over HTTP (E09-01).

    GET /profiles/{id}/trends/{analyte}?language=   one analyte's results against his ranges

The door is the analyte's subject's scope (`scope_for_subject`): a key that does not reach
that part of the record is refused, and the refusal is on the trail. The trend is rendered
from the current State and written as a card that carries the boundary line; a State the key
cannot check against the record is refused (`StaleState`, 409).
"""

from __future__ import annotations

from fastapi import APIRouter, Path, Query, Request

from app.channels.api.daily_schemas import TrendOut
from app.channels.api.deps import Context, Db, providers_of
from app.reasoning.trends import trend

router = APIRouter(prefix="/profiles", tags=["trends"])


@router.get("/{profile_id}/trends/{analyte}")
async def lab_trend(
    request: Request,
    context: Context,
    session: Db,
    analyte: str = Path(max_length=32, pattern=r"^[a-z0-9_]+$"),
    language: str | None = Query(default=None, min_length=2, max_length=16),
) -> TrendOut:
    """His results for one analyte, oldest first, each against the range that fits him on the
    day, the direction over the last three, and the lines he reads, in `language` or his own."""
    found = await trend(
        session,
        context=context,
        ranges=providers_of(request).reference_ranges,
        analyte=analyte,
        language=language,
    )
    return TrendOut.of(found)
