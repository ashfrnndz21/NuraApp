"""His commitments, from the visit loop's memos (E05), for the commitment nudge (E11-07).

A memo of kind ACTION is something he said he would do, filed in his words at the end of a
visit or a conversation (`app.reasoning.visits.memos`). The ones still current — not
superseded by consolidation — and filed in the last month are his commitments; the nudge
quotes each one's text exactly as the memo holds it, which is the text E05 rendered and
verified when it filed it. Nothing here rephrases, shortens or adds a target to it.

`memo_commitments` is registered on `handoff.commitment_sources` when this package is
imported, so the engine asks it and any other source the same way.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import as_utc, utcnow
from app.delivery.nudges.handoff import Commitment
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.models import MemoKind

COMMITMENT_WINDOW = timedelta(days=30)
"""A commitment is from the last month: an older one is not "how did today go"."""


async def memo_commitments(session: AsyncSession, *, context: KeyContext) -> Sequence[Commitment]:
    """His current action memos from the last month, as commitments, newest first. A key
    without the visits scope has none to read, and gets none."""
    if not context.allows(Scope.VISITS):
        return ()
    since = utcnow() - COMMITMENT_WINDOW
    return sorted(
        (
            Commitment(
                memo_id=memo.id,
                words=memo.text,
                language=memo.language,
                said_at=as_utc(memo.created_at),
            )
            for memo in await current_memos(session, context=context)
            if memo.kind is MemoKind.ACTION and as_utc(memo.created_at) > since
        ),
        key=lambda commitment: commitment.said_at,
        reverse=True,
    )
