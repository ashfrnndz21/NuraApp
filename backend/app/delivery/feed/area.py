"""His area (E09-07): where he lives, coarsely, so a dengue bulletin near him reaches him.

A town or district from the region's list, or the first digits of a postcode — never a
street, a house or a whole postcode (`app.delivery.feed.local.check_area`). It is set on his
own yes: his own key, or the steward's who holds the graph for him until he claims it; a chief
reads it, so she can see why a local card came, and asks him to change it. It is kept on the
profile, classed as an identifier (docs/trust/pdpa-data-map.md), and used only here, to match
bulletins fetched for the whole region: it is never sent to a searcher, never written into a
search job and never on the trail's words — the trail says that it was set, not what to.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.delivery.feed.local import DISTRICTS, check_area
from app.delivery.feed.sources import require_manager
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.scopes import Scope

AREA_TARGET = f"{Profile.__tablename__}.area"


class OnlyHeSetsHisArea(Refusal):
    """Where he lives is his to say: his own key, or the steward's before he claims the graph."""


@dataclass(frozen=True, slots=True)
class AreaView:
    area: str | None
    districts: tuple[str, ...]
    may_set: bool


async def read_area(session: AsyncSession, *, context: KeyContext) -> AreaView:
    """His area, and the towns and districts it may be, for him and the chief who manages his
    feed (`NotTheirsToManage` for anyone else, on the trail)."""
    await require_manager(session, context=context, target=AREA_TARGET)
    profile = await audited_profile_read(session, context)
    return AreaView(
        area=profile.area,
        districts=DISTRICTS[context.region],
        may_set=context.is_owner or context.is_steward,
    )


async def set_area(session: AsyncSession, *, context: KeyContext, area: str | None) -> AreaView:
    """Set his area on his yes, or clear it (None). Coarse or refused (`NotACoarseArea`)."""
    if not (context.is_owner or context.is_steward):
        refusal = OnlyHeSetsHisArea(f"a {context.role} key does not set where he lives")
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.PROFILE,
            target=AREA_TARGET,
            outcome=Outcome.REFUSED,
            refused_because=type(refusal).__name__,
        )
        refusal.written_down = True
        raise refusal
    kept = None if area is None or not area.strip() else check_area(area, context.region)
    profile = await audited_profile_read(session, context)
    profile.area = kept
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.PROFILE,
        target=AREA_TARGET,
        rows=1,
        target_id=profile.id,
    )
    return AreaView(area=kept, districts=DISTRICTS[context.region], may_set=True)
