"""The curated fixture set, assembled: every `catalogue.ItemSpec` in every language,
resolved against `strings.py`, as the `NewContentItem` rows `service.seed_content` writes.

This is fixture content — a small, realistic, curated set for a first deployment — not a
live feed of real events and services near a real person (docs/design-direction.md's feature
table names that as an external dependency). `seed()` is what `app.fixtures` and a test's
seeding call; it is idempotent, so calling it twice does not duplicate anything.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.content.catalogue import ITEMS
from app.delivery.content.models import ContentItem
from app.delivery.content.service import NewContentItem, seed_content
from app.delivery.content.strings import BODY, SUMMARIES, TITLES

LANGUAGES: tuple[str, ...] = ("en", "ms", "zh")


def fixture_items() -> list[NewContentItem]:
    """Every curated item, in every language, ready for `service.seed_content`."""
    items: list[NewContentItem] = []
    for spec in ITEMS:
        for language in LANGUAGES:
            items.append(
                NewContentItem(
                    content_type=spec.content_type,
                    region=spec.region,
                    slug=spec.slug,
                    language=language,
                    title=TITLES[language][spec.key],
                    summary=SUMMARIES[language][spec.key],
                    body=BODY[language][spec.resolved_body_key],
                    category=spec.category,
                    meta=dict(spec.meta),
                )
            )
    return items


async def seed(session: AsyncSession) -> Sequence[ContentItem]:
    """Write the curated fixture set and queue each item for the pharmacist. Idempotent: a
    `(region, slug, language)` already on the table is left alone."""
    return await seed_content(session, fixture_items())
