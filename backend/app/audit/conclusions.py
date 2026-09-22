"""D3 — a rejected or corrected AI conclusion is recorded, never thrown away (ADR 0019 point
7; `docs/design/NURA-BUILD-MASTER-SPEC.md` §39: "the system must preserve an auditable record
rather than simply dropping the state").

Two things happen when Nura's own words are refused, whether by a gate or by a person:

1. A line an `AuditEntry` (`app.audit.trail.record`, `Action.REVIEW`) — the trail's own
   discipline holds here exactly as it holds everywhere else in this table: *never a second
   copy of the record it guards*. `refused_because` carries a closed code
   (`ConclusionReasonCode` for a gate's own drop, `ConclusionResponseKind` for a person's tap)
   — never the dropped line, never a rule's own words, never what the person typed.
2. A `ConclusionReview` row, for the columns the audit trail itself has no room for and that
   are not free text either: which response kind this was, which reason code (for a gate
   drop), which plain-words rule (for a `plain_words` drop), and the state this profile stood
   at afterwards. Every column here is an enum, an id or a timestamp — the same discipline the
   audit trail already holds, just with two more columns than `AuditEntry` carries.

Nothing here writes the conclusion itself, its cites, or the person's corrected text. A
caller with something free-text to keep (a corrected value, say) keeps it exactly where it
already goes today — a `ReviewField.corrected_value`, never here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.audit.trail import record
from app.db import Base, enum_column, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope


class ConclusionResponseKind(StrEnum):
    """Who, or what, rejected the conclusion."""

    GATE_DROPPED = "gate_dropped"
    """A safety or plain-words gate dropped a model line before any person ever saw it."""
    USER_NO = "user_no"
    """A person tapped "No" on a read-back or a review card."""
    USER_FIX = "user_fix"
    """A person corrected a value on a review card ("Fix") rather than confirming it as read."""


class ConclusionReasonCode(StrEnum):
    """Which gate dropped the line, for a `GATE_DROPPED` row. The four gates D3 names
    (ADR 0019 point 7): `plain_words` (`docs/plain-words.md`; see `rule_id` for which numbered
    rule), the conclusion-or-advice blocklist both Ask (`app.llm.narrate.
    _has_conclusion_language`) and the Analyst (`app.reasoning.analyst.pipeline.blocked`)
    hold every rephrase to, the caregiver-voice check (a line about him said in his own voice
    to someone who is not him), and an uncited line (no cite the model named actually
    matched a real tool result)."""

    PLAIN_WORDS = "plain_words"
    CONCLUSION_LANGUAGE = "conclusion_language"
    CAREGIVER_VOICE = "caregiver_voice"
    NO_CITE_MATCHED = "no_cite_matched"


class ConclusionReview(Base):
    """D3's own columns: enum, id and timestamp only, never free text (module doc)."""

    __tablename__ = "conclusion_review"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile.id", ondelete="CASCADE"), index=True
    )
    audit_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_entry.id"), index=True)
    response_kind: Mapped[ConclusionResponseKind] = mapped_column(
        enum_column(ConclusionResponseKind, "conclusion_response_kind")
    )
    reason_code: Mapped[ConclusionReasonCode | None] = mapped_column(
        enum_column(ConclusionReasonCode, "conclusion_reason_code"), default=None
    )
    rule_id: Mapped[int | None] = mapped_column(Integer, default=None)
    """The `docs/plain-words.md` rule number, for a `PLAIN_WORDS` reason only — never which
    words broke it."""
    resulting_state_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("state_snapshot.id"), default=None
    )
    """The State this profile stood at once the drop was recorded — `None` when it could not
    be read under this call's own context (never a reason to fail the write)."""
    at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


CONCLUSION_REVIEW_TARGET = ConclusionReview.__tablename__


async def _resulting_state_id(session: AsyncSession, *, context: KeyContext) -> uuid.UUID | None:
    from app.errors import Refusal
    from app.state.service import current_state

    try:
        return (await current_state(session, context=context)).id
    except Refusal:
        return None


async def record_dropped_conclusion(
    session: AsyncSession,
    *,
    context: KeyContext,
    response_kind: ConclusionResponseKind,
    target: str,
    target_id: uuid.UUID,
    scope: Scope = Scope.RECORDS,
    reason_code: ConclusionReasonCode | None = None,
    rule_id: int | None = None,
    channel: Channel = Channel.APP,
) -> ConclusionReview:
    """D3's one writer: an `AuditEntry` (`Action.REVIEW`, `refused_because` the closed code
    only) and a `ConclusionReview` row beside it. `target`/`target_id` name what was
    concluded — a turn, a review field, a card — never the conclusion's own text. `scope` is
    the scope the dropped thing was under (`Scope.ASK` for a dropped answer line,
    `Scope.RECORDS` for a review card's field — the default). Never raises on its own
    account: a `Refusal` reading State for `resulting_state_id` is caught and the column left
    `None` rather than losing the row over it.
    """
    refused_because = reason_code.value if reason_code is not None else response_kind.value
    entry: AuditEntry = await record(
        session,
        context=context,
        action=Action.REVIEW,
        scope=scope,
        target=target,
        target_id=target_id,
        outcome=Outcome.REFUSED,
        channel=channel,
        refused_because=refused_because,
    )
    resulting_state_id = await _resulting_state_id(session, context=context)
    row = ConclusionReview(
        profile_id=context.profile_id,
        audit_entry_id=entry.id,
        response_kind=response_kind,
        reason_code=reason_code,
        rule_id=rule_id,
        resulting_state_id=resulting_state_id,
        at=utcnow(),
    )
    session.add(row)
    await session.flush()
    return row


__all__ = [
    "CONCLUSION_REVIEW_TARGET",
    "ConclusionReasonCode",
    "ConclusionResponseKind",
    "ConclusionReview",
    "record_dropped_conclusion",
]
