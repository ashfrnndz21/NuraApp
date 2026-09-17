"""The content library: Activities, Care Services, Resources and Community (Local Events,
Volunteer, Support Groups) — docs/design-direction.md's "Everything in Reference B is added".

One table, `ContentItem`, discriminated by `content_type` (the same `CardType` the vertical
feed and the pharmacist's review queue use, `app.delivery.feed.models`): the four features
share one data model because they share every rule that matters — region, language, and the
pharmacist's review before anything is shown — and differ only in their vocabulary
(`category`) and a few descriptive fields (`meta`).

Global, not profile data, the way `Source` is (`app.delivery.feed.models.Source`): a row is
not about any one person, so it carries no `profile_id` and is not `ProfileScoped`. It is
pinned to one region (`region`) like every row in a one-backend-per-country deployment, and
a person only ever reads his own region's. It is pinned to one language (`language`); the
"same" item in another language is a second row sharing the item's `slug`, the way a card's
rendering and its translation memory key line up (`app.language.memory`).

**Review gates visibility, not sampling.** The pharmacist's queue elsewhere samples the
first fifty renderings of a card and does not hold up the rest (ADR 0007); a care service or
a support group is advice about where to get help, with no clinical sign-off behind it, so
here the owner asked for the stricter rule: `review_status` starts `PENDING` and a route
answers only `APPROVED` rows (`app.delivery.content.service`). An item is queued once, at
the moment it is written (`service.queue_content_item`), through the very same
`app.language.review.deidentify` a card's first fifty go through, under the very same
`ReviewKind.CARD` and `card_type` a pharmacist already reviews in `GET /review/items` — the
gate is this table's own `review_status`, decided by a pharmacist reading `GET /review/items`
and `POST /review/items/{id}/decide` like any other card.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, enum_column, utcnow
from app.delivery.feed.models import CardType, ReviewStatus
from app.regions import Region

LINE_LENGTH = 200
TITLE_LENGTH = 160
SUMMARY_LENGTH = 300
CATEGORY_LENGTH = 60
SLUG_LENGTH = 80

CONTENT_TYPES: tuple[CardType, ...] = (
    CardType.ACTIVITY,
    CardType.CARE_SERVICE,
    CardType.RESOURCE,
    CardType.LOCAL_EVENT,
    CardType.VOLUNTEER,
    CardType.SUPPORT_GROUP,
)
"""The content library's own card types, a subset of the feed's — the vocabulary this
module is allowed to write. `tests/test_content.py` checks every row's type is one of these."""

COMMUNITY_TYPES: tuple[CardType, ...] = (
    CardType.LOCAL_EVENT,
    CardType.VOLUNTEER,
    CardType.SUPPORT_GROUP,
)
"""Community's three kinds (design-direction.md), one feature with three sub-listings."""


class ContentItem(Base):
    """One item of the content library, in one region, in one language, pending or approved.

    `slug` is the item's own id, stable across its language rows and across a re-seed
    (`service.seed_content` upserts by `(region, slug, language)`, never duplicates a
    digest). `body` is the plain-words lines a patient reads; `meta` is structured,
    non-identifying detail a screen needs (a format, a duration, a day of the week, a kind of
    contact) — never a specific named organisation, phone number or address (this is fixture
    content; a real deployment's live source is an external dependency, see
    docs/design-direction.md's feature table).
    """

    __tablename__ = "content_item"
    __table_args__ = (
        UniqueConstraint("region", "slug", "language", name="uq_content_item_slug_language"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content_type: Mapped[CardType] = mapped_column(enum_column(CardType, "card_type"))
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    language: Mapped[str] = mapped_column(String(16))
    slug: Mapped[str] = mapped_column(String(SLUG_LENGTH))
    category: Mapped[str | None] = mapped_column(String(CATEGORY_LENGTH), default=None)
    title: Mapped[str] = mapped_column(String(TITLE_LENGTH))
    summary: Mapped[str] = mapped_column(String(SUMMARY_LENGTH))
    body: Mapped[list[str]] = mapped_column(JSON)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    review_status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "content_review_status"), default=ReviewStatus.PENDING
    )
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("review_item.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
