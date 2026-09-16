"""His area (E09-07): where he lives, coarsely, so a dengue bulletin near him reaches him.

A town or district from the region's list, or the first digits of a postcode — never a
street, a house or a whole postcode (`app.delivery.feed.local.check_area`). It is kept on the
profile, classed as an identifier (docs/trust/pdpa-data-map.md), and used only here, to match
bulletins fetched for the whole region: it is never sent to a searcher, never written into a
search job and never on the trail's words — the trail says that it was set, not what to.

**Who may set it.** Where he lives is location data about him, so it is his to say:

* Once he has claimed his profile, only his own key. `Standing.STEWARD` is granted only while
  `profile.owner_person_id is None` (`app.keys.context`), so the moment he claims the graph
  the steward's key becomes a `HOLDER` and this refuses it — the chief who manages his feed
  reads his area, so she can see why a local card came, and asks him to change it.
* Before the claim, the steward may set it on the declared basis the proxy model rests on
  (`stewardship.consent_id`), as he cannot yet be asked.

The trail says which of the two it was without anything extra being written: the owner reads
and writes his own graph with no key, so his line carries no `key_id` and no `actor_role`,
while the steward's carries both (`app.audit.trail`). `test_feed_formats.py` holds that.

**Still owed** (operator's decision, 2026-09-16): after the claim this should take his *yes* —
a `Confirmation` spent here, the way a dose change or a key change is — not merely his key.
That needs a new `ConfirmSubject` and `Draft`, a `confirmation_id` on the route and the two
steps in the Me screen, so it is filed on its own rather than folded in here.
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
    try:
        kept = None if area is None or not area.strip() else check_area(area, context.region)
    except Refusal as refused:
        # A street, a house or a whole postcode: refused, and the refusal is on his trail like
        # every other. What was asked for is never written down — only that it was not coarse.
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.PROFILE,
            target=AREA_TARGET,
            outcome=Outcome.REFUSED,
            refused_because=type(refused).__name__,
        )
        refused.written_down = True
        raise
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
