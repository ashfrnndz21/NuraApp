"""The content library's own service: seed it, queue it for a pharmacist, list and read it.

Four features (docs/design-direction.md), one table (`ContentItem`) and one rule that binds
all of them: **an unreviewed item is never shown as if it were checked.** `queue_content_item`
runs the moment a row is written — seeded now, curated by hand later — through the same
de-identification a card's first fifty go through (`app.language.review.deidentify`), under
the same `ReviewKind.CARD` and `card_type` a pharmacist already reads in `GET /review/items`.
Unlike a card's sampling, which never holds up the ninety-first rendering, a content item's
own `review_status` gates it: `list_content` and `read_content` answer `APPROVED` rows only,
in the caller's own region (never another's) and his own language (falling back to English
where his has none approved yet, the way a translation not yet done should not hide the
English one that is).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.delivery.content.models import CONTENT_TYPES, ContentItem
from app.delivery.feed.models import CardType, ReviewStatus
from app.errors import Refusal
from app.family.common import NotPlainWords
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.language.models import ReviewItem, ReviewKind, Verdict
from app.language.review import deidentify
from app.regions import Region
from app.safety.plain_words import Finding, verify

DEFAULT_LANGUAGE = "en"
LANGUAGES = ("en", "ms", "zh")


def language_of(asked: str | None) -> str:
    """One of the languages the content library is written in, or English when it is not."""
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


class NoSuchContentItem(Refusal):
    """No content item by that id — missing, pending review, or held in another region: the
    same refusal for all three, so a pending item's existence is never given away by asking."""


def check_lines(*, title: str, summary: str, body: Sequence[str], language: str) -> list[Finding]:
    """Every failing finding in an item's words, in its language (notes do not refuse it)."""
    found: list[Finding] = [*verify(title, language, "headline"), *verify(summary, language, "line")]
    for line in body:
        found.extend(verify(line, language, "line"))
    return [finding for finding in found if finding.severity == "fail"]


def _digest(*parts: Any) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def queue_content_item(session: AsyncSession, item: ContentItem) -> ReviewItem:
    """Queue this item for a pharmacist, de-identified the way a card is (ADR 0007), under
    its own `card_type`. Queued once: the same rendering (region, slug, language and words)
    is never queued twice, the way a card's is not."""
    sample = deidentify(
        item.content_type,
        item.language,
        headline=item.title,
        body=item.body,
        voice=item.body,
        why=item.summary,
    )
    digest = _digest("content", item.region.value, item.slug, item.language, sample.lines)
    existing_id = await session.scalar(select(ReviewItem.id).where(ReviewItem.digest == digest))
    if existing_id is not None:
        item.review_item_id = existing_id
        return await session.get(ReviewItem, existing_id)  # type: ignore[return-value]
    row = ReviewItem(
        kind=ReviewKind.CARD,
        card_type=item.content_type.value,
        language=item.language,
        lines=sample.lines,
        catalogue_ids=list(sample.catalogue_ids),
        digest=digest,
        verdict=Verdict.PENDING,
        created_at=utcnow(),
    )
    session.add(row)
    await session.flush()
    item.review_item_id = row.id
    return row


async def _reconcile_pending(session: AsyncSession, region: Region) -> None:
    """Bring every pending item in this region up to date with the pharmacist's decision on
    its review item, read on demand rather than by a hook.

    `app.language.review.decide` does not know the content library exists — ADR 0007's queue
    special-cases only `ReviewKind.SOURCE` to flip `source.allowlisted` — so this is the
    content module's own half of that handshake: whoever lists or reads the library first
    after a decision is what moves a newly-approved item from pending to shown, the way
    `review.queue_pending_sources` catches up a source put in the table any other way."""
    pending = (
        await session.scalars(
            select(ContentItem).where(
                ContentItem.region == region,
                ContentItem.review_status == ReviewStatus.PENDING,
                ContentItem.review_item_id.is_not(None),
            )
        )
    ).all()
    if not pending:
        return
    review_ids = {row.review_item_id for row in pending}
    decided = (
        await session.scalars(
            select(ReviewItem).where(
                ReviewItem.id.in_(review_ids), ReviewItem.verdict != Verdict.PENDING
            )
        )
    ).all()
    by_id = {row.id: row for row in decided}
    for item in pending:
        review_item = by_id.get(item.review_item_id) if item.review_item_id is not None else None
        if review_item is None:
            continue
        if review_item.verdict in (Verdict.APPROVED, Verdict.REWRITTEN):
            item.review_status = ReviewStatus.APPROVED
        elif review_item.verdict is Verdict.REJECTED:
            item.review_status = ReviewStatus.REJECTED
    await session.flush()


@dataclass(frozen=True, slots=True)
class NewContentItem:
    """One curated item to seed, before it is written and queued."""

    content_type: CardType
    region: Region
    slug: str
    language: str
    title: str
    summary: str
    body: tuple[str, ...]
    category: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


async def seed_content(
    session: AsyncSession, items: Sequence[NewContentItem]
) -> list[ContentItem]:
    """Write the curated fixture set, idempotently: a `(region, slug, language)` already on
    the table is left alone rather than duplicated or re-queued, so seeding twice on a dev
    box or in a test is harmless. Every new row is checked against docs/plain-words.md before
    it is written — the same check `make plain-words` runs statically, run again here with
    the exact words a person will read — and queued for the pharmacist in the same breath."""
    written: list[ContentItem] = []
    for new in items:
        if new.content_type not in CONTENT_TYPES:
            raise ValueError(f"{new.content_type} is not a content-library card type")
        already = await session.scalar(
            select(ContentItem).where(
                ContentItem.region == new.region,
                ContentItem.slug == new.slug,
                ContentItem.language == new.language,
            )
        )
        if already is not None:
            written.append(already)
            continue
        failures = check_lines(
            title=new.title, summary=new.summary, body=new.body, language=new.language
        )
        if failures:
            raise NotPlainWords([str(f) for f in failures])
        row = ContentItem(
            content_type=new.content_type,
            region=new.region,
            language=new.language,
            slug=new.slug,
            category=new.category,
            title=new.title,
            summary=new.summary,
            body=list(new.body),
            meta=dict(new.meta),
            review_status=ReviewStatus.PENDING,
            created_at=utcnow(),
        )
        session.add(row)
        await session.flush()
        await queue_content_item(session, row)
        written.append(row)
    return written


async def list_content(
    session: AsyncSession,
    *,
    context: KeyContext,
    content_types: Sequence[CardType],
    language: str | None = None,
    category: str | None = None,
) -> list[ContentItem]:
    """The approved items of these types, in his region, in his language — English where his
    has none approved yet. Every key holds `Scope.PROFILE` (holding any key means you may see
    whose graph it opens), and the library is not part of anyone's health record, so that is
    the only door here."""
    context.require(Scope.PROFILE)
    await _reconcile_pending(session, context.region)
    lang = language_of(language)
    rows = await _approved(session, context.region, content_types, lang, category)
    if not rows and lang != DEFAULT_LANGUAGE:
        rows = await _approved(session, context.region, content_types, DEFAULT_LANGUAGE, category)
    return rows


async def _approved(
    session: AsyncSession,
    region: Region,
    content_types: Sequence[CardType],
    language: str,
    category: str | None,
) -> list[ContentItem]:
    statement = select(ContentItem).where(
        ContentItem.content_type.in_([t.value for t in content_types]),
        ContentItem.region == region,
        ContentItem.language == language,
        ContentItem.review_status == ReviewStatus.APPROVED,
    )
    if category is not None:
        statement = statement.where(ContentItem.category == category)
    statement = statement.order_by(ContentItem.title)
    return list((await session.scalars(statement)).all())


async def read_content(
    session: AsyncSession,
    *,
    context: KeyContext,
    item_id: uuid.UUID,
    content_types: Sequence[CardType],
) -> ContentItem:
    """One item, his own region's and approved, or `NoSuchContentItem` — the same refusal
    whether it does not exist, is still pending, or belongs to another region."""
    context.require(Scope.PROFILE)
    await _reconcile_pending(session, context.region)
    item = await session.get(ContentItem, item_id)
    if (
        item is None
        or item.content_type not in content_types
        or item.region is not context.region
        or item.review_status is not ReviewStatus.APPROVED
    ):
        raise NoSuchContentItem(f"no content item {item_id}")
    return item
