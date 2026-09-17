"""The pharmacist's review queue (E22-04): new sources, and the first fifty of each card.

Two things wait here for a pharmacist before they are trusted (docs/health-feed-spec.md §3.5
and §7): a publisher proposed for the learning cards' allowlist, and the first fifty
renderings of each kind of card a patient is shown. The queue is operator scope — staff on
the list in `NURA_REVIEW_STAFF_TOKENS`, never a patient's key — and holds no profile: the
access model and what de-identified means are docs/adr/0007-the-pharmacist-review-queue.md.

**Sources.** `propose_source` adds a publisher as a `source` row that is pending and not
allowlisted, with a review item for it. `feed.sources.usable` already uses only a source that
is allowlisted *and* approved, so a pending one is searched by no job and cited by no card:
nothing from a new source reaches a patient before review. Approving it allowlists it;
rejecting it (with a reason) keeps it off. A source put in the table any other way while
pending gets its review item the next time the queue is read.

**Cards.** `sample_card` runs as each card is written (`items.create_item`): for a patient's
card, or for a safety notice, whoever it is held for — a notice can reach the chief with a
clinical claim no pharmacist has read (#181), so it is sampled like the cards he reads, not
skipped the way the rest of a caregiver's or the memo's cards are. `sample_find_result` runs
the same first-fifty-then-a-flag against the same `CardType.LEARNING` budget for the ask bar's
on-demand Web and Videos results (#188, `feed.find.find`), which are never a `FeedItem` at
all — a new source's first pages are read by a pharmacist once, whether a search job found
them or a caregiver typed a word for them. Until fifty renderings of a card type are queued
(by either door), one more is kept — de-identified (`deidentify`), and only when that
rendering is not already queued. A card type whose first fifty are not all decided shows
`flag: true` in `status`.

**Decisions.** `decide` approves, rejects with a reason, or rewrites. A rewrite is a proposal:
the lines as the reviewer would have them, each checked by the plain-words verifier, with the
catalogue id of the line it would replace (`app.language.memory`). It changes no production
text; a person makes the change in the catalogue and it ships through `make plain-words` and
`make language` like any other. An item is decided once.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.delivery.feed.models import (
    CardType,
    DeliverTo,
    FeedItem,
    ReviewStatus,
    Source,
    SourceKind,
)
from app.drugs.registry import Interaction
from app.errors import Refusal
from app.family.common import NotPlainWords
from app.language.memory import SLOT_CLASSES, Memory, runtime_memory
from app.language.models import ReviewItem, ReviewKind, Verdict
from app.safety.plain_words import verify

log = logging.getLogger("nura.review")

FIRST = 50
"""How many renderings of each card type the pharmacist reads before it is trusted."""

REVIEWED_TYPES: tuple[CardType, ...] = (
    CardType.FLAG,
    CardType.NOW,
    CardType.READING,
    CardType.VISIT,
    CardType.VISIT_LOGISTICS,
    CardType.MEMO,
    CardType.REORDER,
    CardType.NOTICE,
    CardType.RECALL_ACTION,
    CardType.GATE,
    CardType.STORY,
    CardType.RECAP,
    CardType.LEARNING,
    CardType.CLIP,
    CardType.LOCAL,
    CardType.SEASONAL,
    CardType.FOOD,
)
"""The card types a patient is shown, plus one that is never his: the safety notice. The
doctor questions held for the memo never reach anyone unreviewed — E05 reads them off the
memo, not the feed — so they are not here; the caregiver's duty card is hers, not his, and
carries no clinical claim, so it is not here either. A safety notice (`CardType.NOTICE`) is
neither shown to him nor a duty card: it is held for the chief instead (#181,
docs/health-feed-spec.md §0 and §9), but it is still a clinical claim reaching a person, so it
stays in this list on purpose — `sample_card` sends it here however it is held, not only when
`deliver_to` is the patient's.

Every other type that `SUPPLY_OF` puts in a section the patient reads belongs here, the
feed's richer formats among them (F1): a clip, a local bulletin, a season coming and the
week's food card all carry lines compressed from an outside page, and the pharmacist's first
fifty is the only person who reads them before he does. `test_review_queue.py` asserts this
list against `SUPPLY_OF`, so a type added later cannot quietly skip the queue."""

KEPT_AS_WRITTEN: frozenset[CardType] = frozenset(
    {
        CardType.LEARNING,
        CardType.NOTICE,
        CardType.CLIP,
        CardType.LOCAL,
        CardType.SEASONAL,
        CardType.FOOD,
    }
)
"""Cards whose lines not from the catalogue are compressed from a public, allowlisted page —
the words the pharmacist most needs to read — and so are kept (with any name still taken
out). On every other card a line not from the catalogue is his record's own words (a memo,
a note, a letter, his own week) and is not kept at all."""

NOT_THE_CATALOGUES = "{words from his papers, not kept}"
"""What stands in a sample for a line that is his record's words rather than Nura's."""

_PERSON_SLOTS = next(names for label, names in SLOT_CLASSES if label == "person")
PERSON_WORDS_TABLES = frozenset({"YOUR_DOCTOR", "THE_DOCTOR", "YOU", "SOMEONE"})
"""The catalogue tables of his words for a person who is not named ("your doctor", "You",
"Someone"): what may fill a person's slot without being a name, and is never taken out."""
NAME_JOINERS = frozenset(
    {
        "and",
        "dan",
        "bin",
        "binti",
        "bt",
        "bte",
        "a/l",
        "a/p",
        "s/o",
        "d/o",
        "anak",
        "al",
        "van",
        "de",
    }
)
"""Words inside a name that are not capitalised: "Ahmad bin Ali", "Siva a/l Kumar", "Mei and
Kit"."""
TEMPLATE_SHARE = 0.4
"""On a learning card or a notice, a line at least this much of whose letters are a catalogue
template's own is that template, whatever filled its slots: its person slots are blanked even
when what filled them does not look like a name. A thinner match ("{name} is {value}.") is a
compressed page's own sentence and is kept as written."""
_DOCTOR = re.compile(r"\bDr\.?\s+[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)?")
_JOINED = re.compile(r",\s*|\s+and\s+|\s+dan\s+|和|、")


# --- who may -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Staff:
    """Someone on the staff list: a handle, never a person on anyone's record."""

    handle: str


class NotStaff(Refusal):
    """The review queue answers staff only. A patient's key, a session, or nothing is refused."""


class NoSuchReviewItem(Refusal):
    """No review item by that id."""


class AlreadyReviewed(Refusal):
    """An item is decided once."""


class NotARewrite(Refusal):
    """A source is approved or rejected, not rewritten; and a rewrite must change a line."""


class ReasonRequired(Refusal):
    """A rejection says why."""


class SourceAlreadyListed(Refusal):
    """That domain is already on the list, pending, approved or rejected."""


class RewriteNotPlainWords(NotPlainWords):
    """A rewrite is held to docs/plain-words.md like any line; this one is not, so nothing was
    kept. The findings say which line and why."""


def staff_for(token: str | None, staff: Sequence[tuple[str, str]]) -> Staff:
    """The staff member this bearer token belongs to, or `NotStaff`. Every token on the list
    is compared, in constant time, so the answer takes as long for a stranger as for staff."""
    found: str | None = None
    offered = (token or "").encode("utf-8")
    for handle, known in staff:
        if hmac.compare_digest(offered, known.encode("utf-8")) and token:
            found = handle
    if found is None:
        raise NotStaff("the review queue answers staff on NURA_REVIEW_STAFF_TOKENS only")
    return Staff(found)


# --- de-identifying a card -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Sample:
    lines: dict[str, Any]
    catalogue_ids: tuple[str, ...] = field(default=())


def _rebuild(template: str, values: Mapping[str, str], rendered: str) -> str:
    """The template again, with the words that went into a person's slot written as `{name}`
    (`{doctor}` for the doctor) and every other slot as it was filled."""

    def fill(match: re.Match[str]) -> str:
        name = match.group(1).strip().split("!")[0].split(":")[0]
        if name == "doctor":
            return "{doctor}"
        if name in _PERSON_SLOTS:
            return "{name}"
        return values.get(name, match.group(0))

    text = re.sub(r"(?<!\{)\{([^{}]*)\}(?!\})", fill, template.strip())
    if rendered[:1].isupper() and not text.startswith("{"):
        text = text[:1].upper() + text[1:]
    return text


def _name_like(value: str, people: frozenset[str]) -> bool:
    """Whether what filled a person's slot could be a person: his words for one ("your
    doctor", "You", "Someone"), a short name in Chinese, or one to five capitalised words
    ("Mei", "Dr Tan", "Mei and Kit"). "Blood pressure" is not, so a thin template ("{name} is
    {value}.") cannot take the words of a compressed page for a name."""
    said = value.strip()
    if not said:
        return False
    if said.lower() in people:
        return True
    if re.search(r"[㐀-鿿]", said):
        return len(said) <= 6 and not re.search(r"[A-Za-z0-9]", said)
    words = [w for w in re.split(r"[\s,]+", said) if w and w.lower() not in NAME_JOINERS]
    return 1 <= len(words) <= 6 and all(w[:1].isupper() for w in words)


def _plainly_a_template(
    table: Memory, line: str, language: str
) -> tuple[Any, dict[str, str]] | None:
    """The most specific template whose own letters are most of the line's (`TEMPLATE_SHARE`),
    or None: on a card kept as written, a line that is plainly the catalogue's loses whatever
    filled its person slots, name-shaped or not."""
    letters = len(re.findall(r"[^\W\d_]", line))
    for entry, values in table.fills_of(line, language):
        own = letters - sum(len(re.findall(r"[^\W\d_]", v)) for v in values.values())
        if letters and own / letters >= TEMPLATE_SHARE:
            return entry, values
    return None


def _scrub(text: str, names: set[str], doctors: set[str]) -> str:
    for doctor in sorted(doctors, key=len, reverse=True):
        text = text.replace(doctor, "{doctor}")
    text = _DOCTOR.sub("{doctor}", text)
    for name in sorted(names, key=len, reverse=True):
        if len(name) < 2:
            continue
        if re.search(r"[㐀-鿿]", name):
            text = text.replace(name, "{name}")
        else:
            text = re.sub(rf"(?<![\w{{]){re.escape(name)}(?![\w}}])", "{name}", text)
    return text


def deidentify(
    card_type: CardType,
    language: str,
    *,
    headline: str,
    body: Sequence[str],
    voice: Sequence[str],
    why: str,
    memory: Memory | None = None,
) -> Sample:
    """A card's words with nobody in them: lines only, no profile, no names.

    Each line is matched to the catalogue template it was filled from; what went into a
    person's slot — `{who}`, `{name}`, `{doctor}`, `{told}` … — is written as `{name}` or
    `{doctor}`, and every other slot keeps its value (a number, a day, a medicine's plain
    name). Every name found in a slot anywhere on the card is then taken out of every line,
    and so is anything shaped like "Dr Tan". A line that matches no template is kept only on
    a learning card or a notice (`KEPT_AS_WRITTEN`); elsewhere it is his record's own words
    and is replaced by `NOT_THE_CATALOGUES`."""
    table = memory if memory is not None else runtime_memory()
    people = frozenset(
        e.text.strip().lower()
        for e in table.entries
        if e.kind == "phrase" and e.key.split(".")[0] in PERSON_WORDS_TABLES
    )
    everything = [headline, *body, *voice, why]
    found: dict[str, tuple[str, str, dict[str, str]]] = {}
    names: set[str] = set()
    doctors: set[str] = set()
    for line in everything:
        if not line.strip() or line in found:
            continue
        filled = next(
            (
                (entry, values)
                for entry, values in table.fills_of(line, language)
                if all(
                    _name_like(value, people)
                    for slot, value in values.items()
                    if slot in _PERSON_SLOTS
                )
            ),
            None,
        )
        if filled is None and card_type in KEPT_AS_WRITTEN:
            filled = _plainly_a_template(table, line, language)
        if filled is None:
            continue
        entry, values = filled
        found[line] = (entry.id, entry.text, values)
        for slot, value in values.items():
            if value.strip().lower() in people:
                continue  # "your doctor", "You": his words, nobody's name
            parts = {part.strip() for part in _JOINED.split(value) if part.strip()}
            if slot == "doctor":
                doctors.update({value, *parts})
            elif slot in _PERSON_SLOTS:
                names.update({value, *parts})

    def one(line: str) -> str:
        if line in found:
            _, template, values = found[line]
            return _scrub(_rebuild(template, values, line), names, doctors)
        if card_type in KEPT_AS_WRITTEN:
            return _scrub(line, names, doctors)
        return NOT_THE_CATALOGUES

    return Sample(
        lines={
            "headline": one(headline),
            "body": [one(line) for line in body],
            "voice": [one(line) for line in voice],
            "why": one(why),
        },
        catalogue_ids=tuple(sorted({entry_id for entry_id, _, _ in found.values()})),
    )


def _digest(*parts: Any) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- the queue -----------------------------------------------------------------------------------


async def _count(session: AsyncSession, card_type: CardType) -> int:
    counted = await session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.kind == ReviewKind.CARD, ReviewItem.card_type == card_type.value)
    )
    return int(counted or 0)


async def sample_card(session: AsyncSession, item: FeedItem) -> ReviewItem | None:
    """Queue this card for review if it is one of the first fifty of its type, de-identified.
    A card of a type he is never shown, and a rendering already queued, are left alone. A card
    for the caregiver or the memo is left alone too — unless its words are compressed from an
    outside page (`KEPT_AS_WRITTEN`): a safety notice, held for the chief though it is, still
    carries a clinical claim reaching a person, so it is sampled whoever it is held for (#181).

    #236: the same is true of a learning, clip, local, seasonal or food card rerouted to the
    chief because its finding would change treatment (`app.delivery.feed.search.run_job`,
    `items.TreatmentChangingCard`) — it too is compressed from an outside page and reaches a
    person, so gating the queue on `DeliverTo.PATIENT` alone left every one of those rerouted
    cards unreviewed, the same hole #181 closed for the notice on its own branch. A card of his
    own record's words held for her (`REORDER`, `MEMO`, the caregiver's `DUTY`, which is not
    even in `REVIEWED_TYPES`) carries nothing compressed from outside, so it stays out.
    """
    if item.type not in REVIEWED_TYPES:
        return None
    if item.deliver_to is not DeliverTo.PATIENT and item.type not in KEPT_AS_WRITTEN:
        return None
    why = item.why.get("plain", "") if isinstance(item.why, dict) else ""
    return await _sample(
        session,
        card_type=item.type,
        language=item.language,
        headline=item.headline,
        body=item.body,
        voice=item.voice,
        why=str(why),
    )


async def sample_find_result(
    session: AsyncSession,
    *,
    language: str,
    headline: str,
    body: Sequence[str],
    why: str,
) -> ReviewItem | None:
    """Queue one of the ask bar's Web or Videos results for review (#188): the same first
    fifty, the same de-identified sample, the same `CardType.LEARNING` budget a scheduled
    search job's learning cards queue against — a new source's first pages are read by a
    pharmacist once, whether a search job found them or a caregiver typed a word for them.
    A result is never a `FeedItem` (nothing here is capped, ranked or shown again), so there
    is no `deliver_to` to gate on; the ask bar is caregiver-only already (`find.find`,
    `Scope.ASK`), which is exactly the audience a safety notice or a caregiver-delivered card
    would otherwise be skipped for — this is sampled on purpose, not despite that.
    """
    return await _sample(
        session,
        card_type=CardType.LEARNING,
        language=language,
        headline=headline,
        body=body,
        voice=(),
        why=why,
    )


async def _sample(
    session: AsyncSession,
    *,
    card_type: CardType,
    language: str,
    headline: str,
    body: Sequence[str],
    voice: Sequence[str],
    why: str,
) -> ReviewItem | None:
    count = await _count(session, card_type)
    if count >= FIRST:
        return None
    sample = deidentify(card_type, language, headline=headline, body=body, voice=voice, why=why)
    digest = _digest("card", card_type.value, language, sample.lines)
    if await session.scalar(select(ReviewItem.id).where(ReviewItem.digest == digest)):
        return None
    row = ReviewItem(
        kind=ReviewKind.CARD,
        card_type=card_type.value,
        sample_number=count + 1,
        language=language,
        lines=sample.lines,
        catalogue_ids=list(sample.catalogue_ids),
        digest=digest,
        verdict=Verdict.PENDING,
        created_at=utcnow(),
    )
    session.add(row)
    await session.flush()
    return row


def _source_lines(source: Source) -> dict[str, Any]:
    return {
        "name": source.name,
        "domain": source.domain,
        "kind": source.kind.value,
        "regions": list(source.regions),
        "languages": list(source.languages),
    }


async def _queue_source(session: AsyncSession, source: Source) -> ReviewItem:
    row = ReviewItem(
        kind=ReviewKind.SOURCE,
        source_id=source.id,
        lines=_source_lines(source),
        catalogue_ids=[],
        digest=_digest("source", str(source.id)),
        verdict=Verdict.PENDING,
        created_at=utcnow(),
    )
    session.add(row)
    await session.flush()
    return row


async def queue_pending_sources(session: AsyncSession) -> None:
    """Every source waiting for review has a review item: a pending row put in the table any
    other way is queued the next time the queue is read."""
    queued = set(
        (
            await session.scalars(
                select(ReviewItem.source_id).where(ReviewItem.kind == ReviewKind.SOURCE)
            )
        ).all()
    )
    pending = (
        await session.scalars(select(Source).where(Source.review_status == ReviewStatus.PENDING))
    ).all()
    for source in pending:
        if source.id not in queued:
            await _queue_source(session, source)


async def propose_source(
    session: AsyncSession,
    *,
    staff: Staff,
    name: str,
    domain: str,
    kind: SourceKind,
    regions: Sequence[str],
    languages: Sequence[str],
) -> ReviewItem:
    """A new publisher for the learning cards: on the list as pending and not allowlisted, so
    no job searches it and no card cites it until a pharmacist approves it."""
    wanted = domain.strip().lower()
    if await session.scalar(select(Source.id).where(Source.domain == wanted)):
        raise SourceAlreadyListed(f"{wanted} is already on the list")
    source = Source(
        name=name.strip(),
        domain=wanted,
        kind=kind,
        regions=list(regions),
        languages=list(languages),
        allowlisted=False,
        review_status=ReviewStatus.PENDING,
        added_at=utcnow(),
    )
    session.add(source)
    await session.flush()
    row = await _queue_source(session, source)
    log.info("review: source proposed item=%s by=%s", row.id, staff.handle)
    return row


def _interaction_lines(interaction: Interaction) -> dict[str, Any]:
    a, b = sorted(interaction.pair)
    return {
        "pair": [a, b],
        "severity": interaction.severity.value,
        "text_id": interaction.text_id,
        "source": interaction.source,
    }


async def queue_pending_interaction(
    session: AsyncSession, interaction: Interaction
) -> ReviewItem | None:
    """Queue this interaction pair for a pharmacist's review if it is not already queued
    (E04-03). Called the first time the pair is actually flagged for a person — not for every
    pair the registry could ever answer, only the ones that mattered to someone — and it
    carries no profile: two drug names, the severity the registry gave it, and the source a
    pharmacist would check it against. The pair is still shown to the patient the moment it is
    flagged (`app.medicines.story.interaction_question`); queuing it is separate from, and
    does not gate, that."""
    lines = _interaction_lines(interaction)
    digest = _digest("interaction", lines["pair"], lines["text_id"])
    if await session.scalar(select(ReviewItem.id).where(ReviewItem.digest == digest)):
        return None
    row = ReviewItem(
        kind=ReviewKind.INTERACTION,
        lines=lines,
        catalogue_ids=[],
        digest=digest,
        verdict=Verdict.PENDING,
        created_at=utcnow(),
    )
    session.add(row)
    await session.flush()
    log.info("review: interaction queued item=%s pair=%s", row.id, lines["pair"])
    return row


async def queue(
    session: AsyncSession,
    *,
    kind: ReviewKind | None = None,
    card_type: CardType | None = None,
    verdict: Verdict | None = Verdict.PENDING,
    limit: int = 100,
) -> Sequence[ReviewItem]:
    """The queue, oldest first: pending by default, or any verdict, narrowed by kind or type."""
    await queue_pending_sources(session)
    statement = select(ReviewItem).order_by(ReviewItem.created_at, ReviewItem.id).limit(limit)
    if kind is not None:
        statement = statement.where(ReviewItem.kind == kind)
    if card_type is not None:
        statement = statement.where(ReviewItem.card_type == card_type.value)
    if verdict is not None:
        statement = statement.where(ReviewItem.verdict == verdict)
    return (await session.scalars(statement)).all()


async def get_item(session: AsyncSession, item_id: uuid.UUID) -> ReviewItem:
    item = await session.get(ReviewItem, item_id)
    if item is None:
        raise NoSuchReviewItem(f"no review item {item_id}")
    return item


FIELDS = ("headline", "body", "voice", "why")


def _proposal(item: ReviewItem, rewrite: Mapping[str, Any]) -> dict[str, Any]:
    """The rewrite as a proposed catalogue change: every line it changes, the words now and the
    words proposed, and the catalogue id of the line it would replace where the old words are
    the catalogue's. Every proposed line passes the plain-words verifier first."""
    language = item.language or "en"
    changes: list[dict[str, Any]] = []
    failures: list[str] = []
    table = runtime_memory()
    for name in FIELDS:
        if rewrite.get(name) is None:
            continue
        before = item.lines.get(name)
        after = rewrite[name]
        pairs: list[tuple[int | None, str, str]]
        if isinstance(before, list):
            if not isinstance(after, list) or len(after) != len(before):
                raise NotARewrite(f"{name} is rewritten line for line: {len(before)} lines")
            pairs = [
                (i, str(b), str(a)) for i, (b, a) in enumerate(zip(before, after, strict=True))
            ]
        else:
            pairs = [(None, str(before or ""), str(after))]
        for index, old, new in pairs:
            if old == new:
                continue
            kind = "headline" if name == "headline" else "line"
            failures.extend(
                str(f)
                for f in verify(new, language, kind)  # type: ignore[arg-type]
                if f.severity == "fail"
            )
            matched = table.fill_of(old, language) if old != NOT_THE_CATALOGUES else None
            changes.append(
                {
                    "field": name,
                    "index": index,
                    "from": old,
                    "to": new,
                    "catalogue_id": matched[0].id if matched else None,
                }
            )
    if failures:
        raise RewriteNotPlainWords(failures)
    if not changes:
        raise NotARewrite("a rewrite changes at least one line")
    return {"language": language, "changes": changes}


async def decide(
    session: AsyncSession,
    *,
    staff: Staff,
    item_id: uuid.UUID,
    verdict: Verdict,
    reason: str | None = None,
    rewrite: Mapping[str, Any] | None = None,
) -> ReviewItem:
    """Approve, reject with a reason, or rewrite (a card only). A source's decision is the
    source's too: approved, it is allowlisted; rejected, it stays off. Decided once."""
    item = await get_item(session, item_id)
    if item.verdict is not Verdict.PENDING:
        raise AlreadyReviewed(f"review item {item_id} was decided {item.verdict.value}")
    said = (reason or "").strip() or None
    if verdict is Verdict.PENDING:
        raise NotARewrite("a decision approves, rejects or rewrites")
    if verdict is Verdict.REJECTED and said is None:
        raise ReasonRequired("a rejection says why")
    if verdict is Verdict.REWRITTEN:
        if item.kind is ReviewKind.SOURCE:
            raise NotARewrite("a source is approved or rejected, not rewritten")
        if item.kind is ReviewKind.INTERACTION:
            raise NotARewrite("an interaction pair is approved or rejected, not rewritten")
        item.proposed = _proposal(item, rewrite or {})
    if item.kind is ReviewKind.SOURCE and item.source_id is not None:
        source = await session.get(Source, item.source_id)
        if source is not None:
            approved = verdict is Verdict.APPROVED
            source.allowlisted = approved
            source.review_status = ReviewStatus.APPROVED if approved else ReviewStatus.REJECTED
    item.verdict = verdict
    item.reason = said
    item.decided_by = staff.handle
    item.decided_at = utcnow()
    await session.flush()
    log.info("review: %s item=%s by=%s", verdict.value, item.id, staff.handle)
    return item


async def proposals(session: AsyncSession) -> Sequence[ReviewItem]:
    """Every rewrite, oldest first: the proposed catalogue changes waiting for a person."""
    return (
        await session.scalars(
            select(ReviewItem)
            .where(ReviewItem.verdict == Verdict.REWRITTEN)
            .order_by(ReviewItem.decided_at, ReviewItem.id)
        )
    ).all()


@dataclass(frozen=True, slots=True)
class TypeStatus:
    card_type: str
    sampled: int
    pending: int
    approved: int
    rejected: int
    rewritten: int

    @property
    def reviewed(self) -> int:
        return self.sampled - self.pending

    @property
    def first_fifty_reviewed(self) -> bool:
        return self.sampled >= FIRST and self.pending == 0

    @property
    def flag(self) -> bool:
        """True until the first fifty of this card type are queued and every one is decided."""
        return not self.first_fifty_reviewed


@dataclass(frozen=True, slots=True)
class QueueStatus:
    card_types: tuple[TypeStatus, ...]
    sources_pending: int
    first: int = FIRST


async def status(session: AsyncSession) -> QueueStatus:
    """Where the first fifty of every card type stand, and how many sources wait."""
    await queue_pending_sources(session)
    rows = (
        await session.execute(
            select(ReviewItem.card_type, ReviewItem.verdict, func.count())
            .where(ReviewItem.kind == ReviewKind.CARD)
            .group_by(ReviewItem.card_type, ReviewItem.verdict)
        )
    ).all()
    counts: dict[str, dict[Verdict, int]] = {}
    for card_type, verdict, number in rows:
        counts.setdefault(str(card_type), {})[Verdict(verdict)] = int(number)
    types = []
    for card_type in REVIEWED_TYPES:
        by = counts.get(card_type.value, {})
        types.append(
            TypeStatus(
                card_type=card_type.value,
                sampled=sum(by.values()),
                pending=by.get(Verdict.PENDING, 0),
                approved=by.get(Verdict.APPROVED, 0),
                rejected=by.get(Verdict.REJECTED, 0),
                rewritten=by.get(Verdict.REWRITTEN, 0),
            )
        )
    waiting = await session.scalar(
        select(func.count())
        .select_from(ReviewItem)
        .where(ReviewItem.kind == ReviewKind.SOURCE, ReviewItem.verdict == Verdict.PENDING)
    )
    return QueueStatus(card_types=tuple(types), sources_pending=int(waiting or 0))
