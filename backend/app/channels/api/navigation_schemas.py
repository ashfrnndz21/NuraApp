"""The shapes on the wire for care navigation's drafted messages (T3)."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel

from app.reasoning.navigation.models import ContactLink, Draft, Need, NeedKind


class NeedOut(BaseModel):
    """One real need a message could be drafted for — no drafted text yet."""

    id: str
    kind: NeedKind
    evidence_kind: str
    evidence_id: uuid.UUID
    provider_id: uuid.UUID | None
    doctor: str | None
    when: date | None
    category: str | None

    @classmethod
    def of(cls, need: Need) -> NeedOut:
        return cls(
            id=need.id,
            kind=need.kind,
            evidence_kind=need.evidence_kind,
            evidence_id=need.evidence_id,
            provider_id=need.provider_id,
            doctor=need.doctor,
            when=need.when,
            category=need.category,
        )


class ContactLinkOut(BaseModel):
    kind: str
    href: str

    @classmethod
    def of(cls, link: ContactLink) -> ContactLinkOut:
        return cls(kind=link.kind, href=link.href)


class DraftOut(BaseModel):
    """The drafted message: text only. `links` is empty when the provider has no phone on
    file (`copy_only` says so plainly) — Nura never sends either way."""

    need_id: str
    kind: NeedKind
    language: str
    text: str
    drafted_by: str
    links: list[ContactLinkOut]
    copy_only: bool
    cites: list[str]

    @classmethod
    def of(cls, draft: Draft) -> DraftOut:
        return cls(
            need_id=draft.need_id,
            kind=draft.kind,
            language=draft.language,
            text=draft.text,
            drafted_by=draft.drafted_by,
            links=[ContactLinkOut.of(link) for link in draft.links],
            copy_only=draft.copy_only,
            cites=list(draft.cites),
        )
