"""Marking a part of the record "only me", and opening it again (E12-04).

The owner, on his own yes for exactly this part and this direction, writes a `Privacy`
row; from that flush on, `app.keys.context.resolve_key_context` takes the part out of every
key on the profile, and `app.keys.grants.grant_key` cuts no new key into it. Lifting the
mark closes the row and the keys open the part again as they were cut. Both are on the
trail under the family scope; the chief may read which parts are marked (that a part is
his alone is not its content), and nobody may mark or lift but him.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.db import utcnow
from app.drafts import OnlyMeDraft
from app.errors import Refusal
from app.keys.confirm import consume_confirmation
from app.keys.context import KeyContext
from app.keys.privacy import ONLY_ME_SCOPES, Privacy
from app.keys.scopes import Scope

PRIVACY_TARGET = Privacy.__tablename__


class NotTheOwner(Refusal):
    """Only the patient marks a part of his record his alone, or opens it again."""


class NotAPartToMark(Refusal):
    """Whose record it is, and the emergency card, are never hidden from a key."""


class AlreadyMarked(Refusal):
    """This part is already his alone."""


class NotMarked(Refusal):
    """This part is not marked "only me", so there is nothing to lift."""


def only_me_draft(scope: Scope, *, only_me: bool) -> OnlyMeDraft:
    """What the owner says yes to: this part, this way."""
    return OnlyMeDraft(scope=scope.value, only_me=only_me)


def _the_owner(context: KeyContext) -> None:
    if not context.is_owner:
        raise NotTheOwner("only the owner marks a part of his record only me")


async def marked(session: AsyncSession, *, context: KeyContext) -> Sequence[Privacy]:
    """Every mark ever made on this profile, lifted ones included, oldest first."""
    rows = await audited_read(session, Privacy, context, Scope.FAMILY)
    return sorted(rows, key=lambda row: row.marked_at)


async def _live_mark(session: AsyncSession, context: KeyContext, scope: Scope) -> Privacy | None:
    moment = utcnow()
    rows = await audited_read(
        session, Privacy, context, Scope.FAMILY, where=(Privacy.scope == scope,)
    )
    for row in rows:
        if row.is_marked(moment):
            return row
    return None


@audited(Action.WRITE, Scope.FAMILY, PRIVACY_TARGET)
async def mark_only_me(
    session: AsyncSession, *, context: KeyContext, scope: Scope, confirmation_id: uuid.UUID
) -> Privacy:
    """The owner keeps one part of his record to himself, from now until he says otherwise.

    Every key on the profile stops opening that part the moment the row is flushed — the
    resolver reads the marks before it hands out a context — and no new key is cut into it.
    The yes is the owner's own, for exactly this part; it is spent last.
    """
    _the_owner(context)
    if scope not in ONLY_ME_SCOPES:
        raise NotAPartToMark(f"{scope} is not a part a key can be kept from")
    if await _live_mark(session, context, scope) is not None:
        raise AlreadyMarked(f"{scope} is already only me")
    await consume_confirmation(
        session, context, confirmation_id, only_me_draft(scope, only_me=True)
    )
    return await audited_write(
        session,
        Privacy,
        context,
        Scope.FAMILY,
        scope=scope,
        marked_by_person_id=context.person_id,
        marked_at=utcnow(),
    )


@audited(Action.WRITE, Scope.FAMILY, PRIVACY_TARGET)
async def lift_only_me(
    session: AsyncSession, *, context: KeyContext, scope: Scope, confirmation_id: uuid.UUID
) -> Privacy:
    """The owner opens a part again. The keys open it as they were cut; the row stays,
    closed, so the trail can say it was once his alone and when that ended."""
    _the_owner(context)
    live = await _live_mark(session, context, scope)
    if live is None:
        raise NotMarked(f"{scope} is not marked only me")
    await consume_confirmation(
        session, context, confirmation_id, only_me_draft(scope, only_me=False)
    )
    moment = utcnow()
    live.lifted_at = moment
    live.lifted_by_person_id = context.person_id
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.FAMILY,
        target=PRIVACY_TARGET,
        target_id=live.id,
        rows=1,
    )
    return live
