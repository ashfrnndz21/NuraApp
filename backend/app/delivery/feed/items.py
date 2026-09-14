"""The one way a feed item is written.

Four things happen here and nowhere else. The lines are checked against the plain-words
standard in the profile's language — headline, body, voice and why, every one — and a card
with a failing line is not made (`NotPlainWords`, written to the trail). A learning card is
checked against the allowlist: no source, or one that is not usable, and it is not made
(`SourceNotAllowlisted`). A card of an inferring surface (`SURFACE_OF`: a learning card, a
notice) ends on the boundary line it carries, or it is not made (`NoBoundaryLine`, E16-01).
And the row is written through `render_from_state`, which stamps the State it was rendered
from, refuses a State the record has moved past, and writes the line on the row — refusing
it on a card that infers nothing. `autoplay` is written false, always: the schema carries
the promise the pager keeps.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard
from app.audit.models import Action
from app.db import nested_unit_of_work
from app.delivery.feed.models import (
    CAPS_OF,
    SUPPLY_OF,
    CardFormat,
    CardType,
    DeliverTo,
    FeedItem,
    Source,
)
from app.delivery.feed.sources import SourceNotAllowlisted, usable
from app.delivery.strings import Lines
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.safety.boundary import Surface
from app.safety.plain_words import Finding, verify
from app.state.service import NoBoundaryLine, StateView, render_from_state

FEED_TARGET = FeedItem.__tablename__

log = logging.getLogger("nura.delivery.feed")

PRIORITY: dict[CardType, int] = {
    CardType.FLAG: 100,
    CardType.NOW: 90,
    CardType.VISIT: 70,
    CardType.MEMO: 65,
    CardType.REORDER: 60,
    CardType.NOTICE: 75,
    CardType.READING: 50,
    CardType.GATE: 40,
    CardType.DUTY: 40,
    CardType.STORY: 30,
    CardType.LEARNING: 20,
    CardType.QUESTION: 0,
}
"""The base score by type; `compose` adds State's boosts. Ranking is within a section, so
the number never lifts a story card above the gate."""

SURFACE_OF: dict[CardType, Surface] = {
    CardType.LEARNING: Surface.LEARNING_CARD,
    CardType.NOTICE: Surface.LEARNING_CARD,
}
"""The feed's inferring surfaces (E16-01, `app.safety.boundary`). A learning card is an
explanation chosen for him from State and compressed from an allowlisted page; a notice is
the same compression of a regulator's page, so it carries the same line. Every other card
shows the record back — his reading, his tablets, his papers, the count, the gate, the
reorder date from the count, a red flag raised on his own word — and infers nothing, so it
names no surface and carries no line. The question a search reroutes is held for the memo
and never shown by the feed; it is E05's questions surface when it reaches him."""


def _ends_on_its_line(lines: Lines) -> bool:
    """Whether the card's body and voice both end on the boundary line it carries: the line
    on the row is the line he reads and hears."""
    if not lines.boundary:
        return False
    line = tuple(lines.boundary.splitlines())
    return tuple(lines.body[-len(line) :]) == line and tuple(lines.voice[-len(line) :]) == line


class NotPlainWords(Refusal):
    """A line on this card does not pass docs/plain-words.md. The card was not made."""

    def __init__(self, findings: Sequence[Finding]) -> None:
        super().__init__("; ".join(str(finding) for finding in findings))
        self.findings = tuple(findings)


@dataclass(frozen=True, slots=True)
class Why:
    """Why am I seeing this, by id: what the card was built from, and the plain sentence."""

    kind: str
    plain: str
    fact_ids: tuple[str, ...] = ()
    event_id: str | None = None
    artifact_id: str | None = None
    visit_id: str | None = None
    note_id: str | None = None
    memo_id: str | None = None
    memo_ids: tuple[str, ...] = ()
    brief_id: str | None = None
    flag_id: str | None = None
    source_id: str | None = None
    gap: str | None = None
    suppressed: str | None = None
    boosts: tuple[str, ...] = field(default=())

    def as_json(self) -> dict[str, Any]:
        return {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in asdict(self).items()
        }


def failures_in(lines: Lines) -> list[Finding]:
    """Every failing finding in a card's words, in its language. Notes do not fail a card."""
    found: list[Finding] = []
    found.extend(verify(lines.headline, lines.language, "headline"))
    for line in (*lines.body, *lines.voice, lines.why):
        found.extend(verify(line, lines.language, "line"))
    return [finding for finding in found if finding.severity == "fail"]


async def create_item(
    session: AsyncSession,
    *,
    context: KeyContext,
    state: StateView,
    type: CardType,
    lines: Lines,
    why: Why,
    scope: Scope,
    deliver_to: DeliverTo,
    day: str,
    dedupe_key: str,
    expires_at: datetime,
    format: CardFormat = CardFormat.TEXT,
    priority: int | None = None,
    source: Source | None = None,
    cite: dict[str, Any] | None = None,
    search_job_id: uuid.UUID | None = None,
    surface: Surface | None = None,
) -> FeedItem:
    """Write one card, or refuse it.

    A card for the patient has every line verified first; a card for the caregiver or the
    memo keeps her fuller words. A learning card names a usable source or is refused. A
    card of an inferring surface ends on its boundary line and carries it (`lines.boundary`);
    a card that infers nothing carries none. The row is rendered from `state`, so a snapshot
    the record has moved past is refused too. Every refusal here is written down under the
    card's own scope.
    """
    async with audited_guard(session, context, Action.WRITE, scope, FEED_TARGET):
        if deliver_to is DeliverTo.PATIENT:
            failing = failures_in(lines)
            if failing:
                raise NotPlainWords(failing)
        if type is CardType.LEARNING and (source is None or not usable(source, context.region)):
            raise SourceNotAllowlisted("a learning card names an allowlisted source")
        # A card whose words come from an inferring surface elsewhere — the visit brief, the
        # memos — names it; otherwise its type decides (`SURFACE_OF`).
        surface = surface if surface is not None else SURFACE_OF.get(type)
        if surface is not None and not _ends_on_its_line(lines):
            raise NoBoundaryLine(f"a {type.value} card ends on the boundary line it carries")
        item = await render_from_state(
            session,
            FeedItem,
            context,
            scope,
            state=state,
            surface=surface,
            boundary=lines.boundary,
            type=type,
            supply=SUPPLY_OF[type],
            caps_class=CAPS_OF[type],
            deliver_to=deliver_to,
            scope=scope,
            language=lines.language,
            format=format,
            headline=lines.headline,
            body=list(lines.body),
            voice=list(lines.voice),
            why=why.as_json(),
            priority=PRIORITY[type] if priority is None else priority,
            autoplay=False,
            source_id=None if source is None else source.id,
            cite=cite,
            search_job_id=search_job_id,
            day=day,
            dedupe_key=dedupe_key,
            expires_at=expires_at,
        )
    await _sample(session, item)
    return item


async def _sample(session: AsyncSession, item: FeedItem) -> None:
    """One of the first fifty renderings of its type goes to the pharmacist's queue, de-identified
    (E22-04, `app.language.review`). In a savepoint of its own, and whatever goes wrong in it —
    a refusal, the database, a file the catalogue scan cannot read, a bug — is written to the
    log and rolled back: a sample never costs him the card, a red flag's least of all."""
    from app.language.review import sample_card

    try:
        async with nested_unit_of_work(session):
            await sample_card(session, item)
    except Exception as skipped:  # noqa: BLE001 — nothing in a sample may cost him the card
        log.warning("review sample skipped: %s", type(skipped).__name__)
