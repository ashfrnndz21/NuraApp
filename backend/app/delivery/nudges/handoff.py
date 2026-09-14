"""The seam between the nudges and delivery (E11), and between the nudges and the memos (E05).

A nudge is made here and sent by E11's engine, which owns the triggers, the channels, the caps
across every kind of message and the escalation ladder (`app/delivery/triggers/`). E11 is not
on main as this is written, so the handoff is a small protocol, kept here where the nudges
are: a `NudgeDraft` is everything delivery needs — the lines and their spoken twin in his
language, the kind, the cap class (`CapsClass.ONE`: one of its kind a day, counted against the
smart-nudge cap), why he is seeing it, the earliest moment it may go (never inside his quiet
hours) and when it stops being worth sending. `engine.hand_over` writes the `Nudge` row and
calls each registered `NudgeDelivery`; with none registered the row is the queue, and E11
reads it. When E11 lands, it appends its engine to `deliveries`; nothing here changes.

The commitment nudge quotes his own words from a memo (E11-07). Memos are E05's (the visit
loop); a `CommitmentSource` gives the nudges what he said and the memo it is in —
`commitments.memo_commitments` reads E05's current action memos and is registered on
`commitment_sources` when `app.delivery.nudges` is imported. The nudges never rephrase,
shorten or add a target to what he said: the line is his, as the memo holds it.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.feed.models import CapsClass
from app.delivery.nudges.models import Nudge, NudgeKind
from app.keys.context import KeyContext
from app.keys.scopes import Scope


@dataclass(frozen=True, slots=True)
class NudgeDraft:
    """One nudge, ready for delivery. Every line passed the plain-words verifier."""

    kind: NudgeKind
    lines: tuple[str, ...]
    voice: tuple[str, ...]
    language: str
    why: str
    """Why he is seeing this, in one plain line (docs/smart-nudges.md §1)."""
    reason: Mapping[str, Any]
    """The same, by code and id: what the nudge rests on. No words, no values."""
    cap_class: CapsClass
    scope: Scope
    """The part of the record the nudge was built from; a key without it does not see it."""
    day: date
    send_after: datetime
    """The earliest moment it may go: his check-in time that day, never in quiet hours."""
    expires_at: datetime
    """The end of his day. A nudge not sent by then is dropped, never queued."""
    state_id: uuid.UUID
    priority: int
    dedupe_key: str
    memo_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class Held:
    """A nudge that could have been made and was not, and why — shown, never dropped quietly."""

    kind: NudgeKind
    because: str
    priority: int | None = None
    reason: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NudgePlan:
    """The day's plan: what goes (at most one), and what was held back and why."""

    day: date
    drafts: tuple[NudgeDraft, ...]
    held: tuple[Held, ...]
    none_because: str | None = None
    """When nothing at all may go that day: a red flag, or the night."""


class NudgeDelivery(Protocol):
    """E11's side of the handoff: take a nudge that has been written down, and deliver it on
    the channel and at the moment its own rules choose, no earlier than `send_after`."""

    async def take(
        self, session: AsyncSession, *, context: KeyContext, nudge: Nudge, draft: NudgeDraft
    ) -> None: ...


deliveries: list[NudgeDelivery] = []
"""Registered by the delivery engine (E11). Empty until then: the `nudge` row is the queue."""


@dataclass(frozen=True, slots=True)
class Commitment:
    """Something he said he would do, in his own words, and the memo it is in."""

    memo_id: uuid.UUID
    words: str
    language: str
    said_at: datetime


class CommitmentSource(Protocol):
    """Where his commitments come from: the current action memos on his profile (E05)."""

    async def __call__(
        self, session: AsyncSession, *, context: KeyContext
    ) -> Sequence[Commitment]: ...


commitment_sources: list[CommitmentSource] = []
"""Where commitments come from: E05's memos (`commitments.memo_commitments`), registered when
`app.delivery.nudges` is imported, and any other source that appends itself."""
