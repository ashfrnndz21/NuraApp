"""The content library over HTTP: Activities, Care Services, Resources and Community."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.delivery.content.models import ContentItem


class ContentItemOut(BaseModel):
    """One item of the content library: a title, a summary, and the plain-words lines a
    patient reads. `meta` is structured, non-identifying detail the screen needs (a format,
    a duration, a day of the week, a kind of contact) — see docs/design-direction.md's
    feature table for what a real deployment would put behind it."""

    id: uuid.UUID
    content_type: str
    category: str | None
    language: str
    title: str
    summary: str
    body: list[str]
    meta: dict[str, Any]
    created_at: datetime

    @classmethod
    def of(cls, item: ContentItem) -> ContentItemOut:
        return cls(
            id=item.id,
            content_type=item.content_type.value,
            category=item.category,
            language=item.language,
            title=item.title,
            summary=item.summary,
            body=list(item.body),
            meta=dict(item.meta),
            created_at=item.created_at,
        )


class ContentListOut(BaseModel):
    items: list[ContentItemOut]

    @classmethod
    def of(cls, items: list[ContentItem]) -> ContentListOut:
        return cls(items=[ContentItemOut.of(item) for item in items])
