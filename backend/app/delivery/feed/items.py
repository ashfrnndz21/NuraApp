"""The one way a feed item is written.

Seven things happen here and nowhere else. A card whose words would start, stop or change a
medicine is refused outright, whoever it is for (`TreatmentChangingCard`, #236): the one
choke point every card passes through, so a caller cannot address a treatment-changing
finding to anyone by building around the patient-only check below. A safety notice is refused
outright for the patient (`NoticeNotForPatient`, #181): it is held for the chief or rerouted
to the memo, never a card he reads, whichever job asked for it and whatever a caller sets
`deliver_to` to. The lines are checked against the plain-words standard in the profile's
language — headline, body, voice and why, every one — and a card with a failing line is not
made (`NotPlainWords`, written to the trail). A learning card is checked against the
allowlist: no source, or one that is not usable, and it is not made (`SourceNotAllowlisted`).
A card of an inferring surface
(`SURFACE_OF`: a learning card, a notice) ends on the boundary line it carries, or it is not
made (`NoBoundaryLine`, E16-01). And the row is written through `render_from_state`, which
stamps the State it was rendered from, refuses a State the record has moved past, and writes
the line on the row — refusing it on a card that infers nothing. And the card grammar is
checked (E11-03, `grammar`): one number, one direction, one colour — the State wash — and one
action, written as columns. `autoplay` is written false, always: the schema carries the
promise the pager keeps.
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
from app.delivery.feed.compress import changes_treatment
from app.delivery.feed.grammar import Action as CardAction
from app.delivery.feed.grammar import (
    Direction,
    Grammar,
    action_for,
    colour_for,
)
from app.delivery.feed.grammar import check as check_grammar
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
    CardType.VISIT_LOGISTICS: 80,
    CardType.VISIT: 70,
    CardType.MEMO: 65,
    CardType.REORDER: 60,
    CardType.NOTICE: 75,
    CardType.RECALL_ACTION: 75,
    CardType.READING: 50,
    CardType.GATE: 40,
    CardType.DUTY: 40,
    CardType.LOCAL: 72,
    CardType.RECAP: 35,
    CardType.STORY: 30,
    CardType.CLIP: 25,
    CardType.SEASONAL: 22,
    CardType.FOOD: 21,
    CardType.LEARNING: 20,
    CardType.QUESTION: 0,
}
"""The base score by type; `compose` adds State's boosts. Ranking is within a section, so
the number never lifts a story card above the gate."""

SURFACE_OF: dict[CardType, Surface] = {
    CardType.LEARNING: Surface.LEARNING_CARD,
    CardType.NOTICE: Surface.LEARNING_CARD,
    # A clip, a local alert, a seasonal card and a food card are each an allowlisted page
    # compressed to the part chosen for him, the way a learning card is: the same line.
    CardType.CLIP: Surface.LEARNING_CARD,
    CardType.LOCAL: Surface.LEARNING_CARD,
    CardType.SEASONAL: Surface.LEARNING_CARD,
    CardType.FOOD: Surface.LEARNING_CARD,
    # The one card built from a notice (#183): its words are the catalogue's own, never the
    # notice's compressed page, but the notice is still what State surfaced that made this
    # card exist, so it carries the same line the notice would have.
    CardType.RECALL_ACTION: Surface.LEARNING_CARD,
}
"""The feed's inferring surfaces (E16-01, `app.safety.boundary`). A learning card is an
explanation chosen for him from State and compressed from an allowlisted page; a notice is
the same compression of a regulator's page, so it carries the same line. Every other card
shows the record back — his reading, his tablets, his papers, the count, the gate, the
reorder date from the count, a red flag raised on his own word — and infers nothing, so it
names no surface and carries no line. The question a search reroutes is held for the memo
and never shown by the feed; it is E05's questions surface when it reaches him. The weekly
recap repeats the lines of his own story cards and infers nothing."""

SOURCED: frozenset[CardType] = frozenset(
    {CardType.LEARNING, CardType.CLIP, CardType.LOCAL, CardType.SEASONAL, CardType.FOOD}
)
"""The cards compressed from an allowlisted page: each names a usable source, or is not made.
A clip built by `app.delivery.feed.clipmaker` from his own record and the catalogue, not from
a page — `self_made=True` below — is the one exception: it names no publisher because it read
none, and `create_item` never asks it to invent one."""


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


class NoticeNotForPatient(Refusal):
    """A safety notice is never a card in the patient's feed, batch match or not (#181,
    docs/health-feed-spec.md §0 and §9): it is held for the chief, or rerouted to the memo as
    a doctor question. This is the one place every card is written, so it is the one place
    this is refused — a caller cannot route a notice to `DeliverTo.PATIENT` by mistake or by
    a later change to a search job. The card was not made."""


class TreatmentChangingCard(Refusal):
    """A card whose words would start, stop or change a medicine is never written, for any
    audience (docs/health-feed-spec.md §7, `.claude/rules/safety.md`: "anything that would
    change treatment is rerouted as a doctor question"). #236's review found the choke point
    missing here: `search.run_job` addressed the compressed words themselves to the chief
    instead of rerouting them, on the reasoning that `DeliverTo.CAREGIVER` "keeps her fuller
    words" (docs/plain-words.md §3) — but §3 is about *wording*, not about whether advice to
    change a medicine may appear at all. It may not, on any card, whoever it is held for. A
    caller that finds a treatment-changing line builds the caregiver a card that says a
    finding needs her doctor's look and points at the question filed for him
    (`app.delivery.strings.needs_doctor_look_lines`) — never the finding's own words. This is
    the one place every card is written, so it is the one place this is refused, whatever a
    caller's `deliver_to` or `type`. The card was not made."""


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
    photo_id: str | None = None
    """A family photo a story card shows (E21-05): the client reads it through the thread."""
    memo_id: str | None = None
    memo_ids: tuple[str, ...] = ()
    brief_id: str | None = None
    flag_id: str | None = None
    source_id: str | None = None
    gap: str | None = None
    suppressed: str | None = None
    boosts: tuple[str, ...] = field(default=())
    rule: str | None = None
    """The recommendation rule this card came from (RE-07, `app.delivery.recommend.rules`):
    set only for a card the broker's slate proposed, never invented by a search job of its
    own — the broker writes no words, only this reference to the rule that found it."""
    topic: str | None = None
    """The catalogue topic (RE-04) this card is about, for a broker-proposed card only: the
    same code `app.delivery.recommend.models.Candidate.topic` carried, kept here so "not for
    me" can be read back at the topic he actually declined (`app.delivery.feed.engagement`),
    with no new column — `why` is already a JSON field every card writes."""

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
    number: str | None = None,
    direction: Direction | None = None,
    action: CardAction | None = None,
    private_to: uuid.UUID | None = None,
    self_made: bool = False,
) -> FeedItem:
    """Write one card, or refuse it.

    A card for the patient has every line verified first; a card for the caregiver or the
    memo keeps her fuller words. A learning card names a usable source or is refused. A
    card of an inferring surface ends on its boundary line and carries it (`lines.boundary`);
    a card that infers nothing carries none. The row is rendered from `state`, so a snapshot
    the record has moved past is refused too. Every refusal here is written down under the
    card's own scope.

    `private_to`, when set, is his alone (RE-01): `rank._visible_to` drops the row for every
    other person, whatever her scopes — the one exception a `Scope` cannot express.

    `self_made`, when set, is a clip `app.delivery.feed.clipmaker` built from his own record
    and the catalogue, never from a page (RE-07, item 1): the one `SOURCED` card that names
    no `source`, because it read none.
    """
    async with audited_guard(session, context, Action.WRITE, scope, FEED_TARGET):
        if changes_treatment([lines.headline, *lines.body]):
            raise TreatmentChangingCard(
                f"a {type.value} card's words would start, stop or change a medicine"
            )
        if type is CardType.NOTICE and deliver_to is DeliverTo.PATIENT:
            raise NoticeNotForPatient(f"a {type.value} card is never delivered to the patient")
        if deliver_to is DeliverTo.PATIENT:
            failing = failures_in(lines)
            if failing:
                raise NotPlainWords(failing)
        if (
            type in SOURCED
            and not self_made
            and (source is None or not usable(source, context.region))
        ):
            raise SourceNotAllowlisted(f"a {type.value} card names an allowlisted source")
        if self_made and type is not CardType.CLIP:
            raise ValueError("only a clip is ever self-made")
        # A card whose words come from an inferring surface elsewhere — the visit brief, the
        # memos — names it; otherwise its type decides (`SURFACE_OF`).
        surface = surface if surface is not None else SURFACE_OF.get(type)
        if surface is not None and not _ends_on_its_line(lines):
            raise NoBoundaryLine(f"a {type.value} card ends on the boundary line it carries")
        grammar = Grammar(
            colour=colour_for(state.posture),
            action=action or action_for(type, scope, deliver_to),
            number=number,
            direction=direction,
        )
        check_grammar(grammar, headline=lines.headline, body=lines.body)
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
            number=grammar.number,
            direction=None if grammar.direction is None else grammar.direction.value,
            colour=grammar.colour.value,
            action=grammar.action.value,
            private_to=private_to,
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
