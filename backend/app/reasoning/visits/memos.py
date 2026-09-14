"""Memos: one line in his words, filed against the next appointment (E05-06).

    Every conversation Ash or Dad has with the agent ends in a memo in Dad's own words:
    "Bring the BP log Thursday. Lighter dinners. Ask Dr Tan about the dosage." Filed against
    the next appointment. — docs/stage1-product-design.md

A memo is rendered from a template and verified before it is a row; it names the State it
was rendered from and where it came from (a visit, a conversation, the person). Memos are
never edited: consolidation collapses two that say the same thing by marking the older one
superseded, and the memo card is the current list, verified again on the way out.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_profile_read, audited_read
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc, utcnow
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.visits.models import MEMO_LENGTH, Memo, MemoKind, MemoSource
from app.reasoning.visits.strings import language_for, say, verified
from app.state.service import StateView, render_from_state

MEMO = Memo.__tablename__

KIND_ORDER: tuple[MemoKind, ...] = (MemoKind.TELL, MemoKind.ACTION, MemoKind.BRING, MemoKind.ASK)
"""The order of the card: who to tell today first, then what to do, what to bring, what to ask."""


class NotAMemo(Refusal):
    """A memo is one line of at most eighty characters. This rendered longer than that."""


def _same(memo: Memo) -> tuple[str, str, str, str]:
    return (
        memo.kind.value,
        memo.key,
        json.dumps(memo.slots, sort_keys=True, default=str),
        memo.language,
    )


@audited(Action.WRITE, Scope.VISITS, MEMO)
async def write_memo(
    session: AsyncSession,
    *,
    context: KeyContext,
    kind: MemoKind,
    key: str,
    slots: Mapping[str, Any],
    source: MemoSource,
    source_id: uuid.UUID | None = None,
    appointment_id: uuid.UUID | None = None,
    state: StateView | None = None,
    language: str | None = None,
) -> Memo:
    """Render one memo from a template in the profile's language, verify it, and file it.

    `language` defaults to the profile's. The line is refused if it fails the verifier
    (`NotPlainEnough`) or runs past `MEMO_LENGTH`; a memo that is not plain is not filed.
    """
    lang = language_for(
        language
        if language is not None
        else (await audited_profile_read(session, context)).language
    )
    text = say(key, lang, **slots)
    if len(text) > MEMO_LENGTH:
        raise NotAMemo(f"a memo is one line of at most {MEMO_LENGTH} characters")
    return await render_from_state(
        session,
        Memo,
        context,
        Scope.VISITS,
        state=state,
        appointment_id=appointment_id,
        kind=kind,
        source=source,
        source_id=source_id,
        key=key,
        slots=dict(slots),
        text=text,
        language=lang,
        created_at=utcnow(),
    )


@audited(Action.READ, Scope.VISITS, MEMO)
async def current_memos(
    session: AsyncSession, *, context: KeyContext, appointment_id: uuid.UUID | None = None
) -> Sequence[Memo]:
    """The memos not yet superseded, in card order; narrowed to one visit when asked."""
    where: list[Any] = [Memo.superseded_at.is_(None)]
    if appointment_id is not None:
        where.append(Memo.appointment_id == appointment_id)
    found = await audited_read(session, Memo, context, Scope.VISITS, where=where)
    return sorted(
        found, key=lambda memo: (KIND_ORDER.index(memo.kind), as_utc(memo.created_at), str(memo.id))
    )


@audited(Action.WRITE, Scope.VISITS, MEMO)
async def consolidate_memos(session: AsyncSession, *, context: KeyContext) -> Sequence[Memo]:
    """Collapse duplicates into the current list: of two memos saying the same thing, the
    newer stands and the older is marked superseded by it. Returns the current list."""
    current = list(await current_memos(session, context=context))
    moment = utcnow()
    newest: dict[tuple[str, str, str, str], Memo] = {}
    for memo in sorted(current, key=lambda m: (as_utc(m.created_at), str(m.id))):
        newest[_same(memo)] = memo
    kept: list[Memo] = []
    for memo in current:
        if newest[_same(memo)] is memo:
            kept.append(memo)
            continue
        memo.superseded_at = moment
        await session.flush()
        await record(
            session,
            context=context,
            action=Action.WRITE,
            scope=Scope.VISITS,
            target=MEMO,
            target_id=memo.id,
            rows=1,
        )
    return kept


@audited(Action.READ, Scope.VISITS, MEMO)
async def memo_card(session: AsyncSession, *, context: KeyContext) -> list[str]:
    """The memo card at the end of every conversation: the current memos, each line verified
    again on the way out, in card order."""
    memos = await consolidate_memos(session, context=context)
    return [verified(memo.text, memo.language) for memo in memos]
