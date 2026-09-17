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

**Once it is his** (#184): setting it is a write on his record like any other, so it takes
his own yes — a `Confirmation` spent here, the way a dose change or a key change is, not
merely his key. `area_draft_for` is the preview: it makes the same checks `set_area` makes,
against a draft his yes is minted for (`app.drafts.AreaDraft`,
`ConfirmSubject.AREA`) at `POST /profiles/{id}/confirmations`; `set_area` then spends it,
recomputed from the area it is about to keep, so the yes binds to exactly that. Before the
claim the steward still sets it on the declared basis without one, as above — he cannot yet
be asked — and that path is unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read
from app.audit.models import Action, Outcome
from app.audit.trail import record
from app.delivery.feed.local import DISTRICTS, check_area
from app.delivery.feed.sources import require_manager
from app.drafts import AreaDraft
from app.errors import Refusal
from app.identity.models import Profile
from app.keys.context import KeyContext
from app.keys.scopes import Scope

AREA_TARGET = f"{Profile.__tablename__}.area"


class OnlyHeSetsHisArea(Refusal):
    """Where he lives is his to say: his own key, or the steward's before he claims the graph."""


class AreaNotConfirmed(Refusal):
    """Once the graph is his, setting his area is a write on his record like any other and
    takes his own yes (#184); the steward may still set it before his claim, without one."""


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


def _checked(area: str | None, context: KeyContext) -> str | None:
    """The coarse form of `area`, or None: shared by the preview and the write so the two
    can never land on a different value for what looks like the same ask."""
    return None if area is None or not area.strip() else check_area(area, context.region)


@audited(Action.WRITE, Scope.PROFILE, AREA_TARGET)
async def area_draft_for(
    session: AsyncSession, *, context: KeyContext, area: str | None
) -> tuple[str | None, AreaDraft]:
    """What setting his area to `area` would keep, and the draft his yes is minted for
    (#184): the coarse value `set_area` will write, refused first on the same terms it
    refuses on — his own key or the steward's before his claim (`OnlyHeSetsHisArea`), and an
    area that is not coarse (`NotACoarseArea`) — so a yes is never minted for what would be
    refused anyway. Read-only: nothing but the refusal, if any, reaches his trail."""
    if not (context.is_owner or context.is_steward):
        raise OnlyHeSetsHisArea(f"a {context.role} key does not set where he lives")
    kept = _checked(area, context)
    return kept, AreaDraft(area=kept)


async def set_area(
    session: AsyncSession,
    *,
    context: KeyContext,
    area: str | None,
    confirmation_id: uuid.UUID | None = None,
) -> AreaView:
    """Set his area on his yes, or clear it (None). Coarse or refused (`NotACoarseArea`).

    Once the graph is his, this write is his like any other on his record and takes his own
    yes: without `confirmation_id`, `AreaNotConfirmed`; spent here against the area actually
    kept, via `app.keys.confirm.consume_confirmation`, so the yes binds to exactly that
    (#184). Before his claim the steward sets it on the declared basis the stewardship rests
    on, as he cannot yet be asked, and that path takes no confirmation, unchanged.
    """
    from app.keys.confirm import consume_confirmation

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
        kept = _checked(area, context)
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
    if context.is_owner:
        if confirmation_id is None:
            unconfirmed = AreaNotConfirmed("setting his area, once it is his, takes his own yes")
            await record(
                session,
                context=context,
                action=Action.WRITE,
                scope=Scope.PROFILE,
                target=AREA_TARGET,
                outcome=Outcome.REFUSED,
                refused_because=type(unconfirmed).__name__,
            )
            unconfirmed.written_down = True
            raise unconfirmed
        try:
            await consume_confirmation(session, context, confirmation_id, AreaDraft(area=kept))
        except Refusal as refused:
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
