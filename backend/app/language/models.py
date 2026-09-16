"""The pharmacist's review queue (E22-04): one table, and no profile in it.

A `ReviewItem` is one thing waiting for, or holding, a pharmacist's decision: a new source
for the learning cards (`kind` SOURCE, pointing at the `source` row it would allowlist), one
of the first fifty renderings of a kind of card (`kind` CARD), or a drug-interaction pair the
licensed registry flags but has not yet been checked by a pharmacist (`kind` INTERACTION,
E04-03). It is operator data, not
profile data — the same queue for every family on this deployment — so it is not
`ProfileScoped`, it names no profile and no person, and no patient key reaches it
(docs/adr/0007-the-pharmacist-review-queue.md).

A card sample is de-identified before the row is written (`review.deidentify`): every line
is matched back to the catalogue template it was filled from, and the words that went into
a person's slot are written as `{name}` (`{doctor}` for the doctor); a line that is not the
catalogue's — his own words, a memo — is not kept at all, except on a learning card or a
notice, whose lines are compressed from a public page. `lines` holds what is left; `digest`
is its sha256, so the same rendering is queued once.

The row is written once and decided once: `verdict`, `reason`, `proposed`, `decided_by` and
`decided_at` may be set, never unset, and `review.decide` refuses a second decision. A
rewrite is `proposed` — the lines as the reviewer would have them and the catalogue ids they
replace — and changes no production text: it is a proposed catalogue change for a person to
make in the source, through `make plain-words` and `make language` like any other.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, enum_column, frozen, utcnow


class ReviewKind(StrEnum):
    SOURCE = "source"
    """A publisher proposed for the allowlist; unused until approved."""
    CARD = "card"
    """One of the first fifty renderings of a kind of card, de-identified."""
    INTERACTION = "interaction"
    """A drug-interaction pair the licensed registry flags but has not yet been checked by a
    pharmacist (`app.drugs.registry.ReviewState.AWAITING_REVIEW`), queued the first time it is
    actually raised for a person (E04-03). It carries no profile: a pair of drug names and the
    source it should be checked against, never a person's own pair of medicines."""


class Verdict(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    """With a reason. A rejected source stays off the allowlist."""
    REWRITTEN = "rewritten"
    """A card's words, rewritten by the reviewer as a proposed catalogue change."""


class ReviewItem(Base):
    __tablename__ = "review_item"
    __table_args__ = (UniqueConstraint("digest", name="uq_review_item_digest"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[ReviewKind] = mapped_column(enum_column(ReviewKind, "review_kind"))
    card_type: Mapped[str | None] = mapped_column(String(32), default=None, index=True)
    sample_number: Mapped[int | None] = mapped_column(Integer, default=None)
    """For a card: which of the first fifty of its type this is, counting from 1."""
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source.id"), default=None)
    language: Mapped[str | None] = mapped_column(String(16), default=None)
    lines: Mapped[dict[str, Any]] = mapped_column(JSON)
    """A card's headline, body, voice and why, de-identified; a source's name and domain."""
    catalogue_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    """The translation-memory ids the card's lines were filled from (`app.language.memory`)."""
    digest: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[Verdict] = mapped_column(enum_column(Verdict, "review_verdict"))
    reason: Mapped[str | None] = mapped_column(String(500), default=None)
    proposed: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    decided_by: Mapped[str | None] = mapped_column(String(64), default=None)
    """The reviewer's handle from the staff list (`NURA_REVIEW_STAFF_TOKENS`), never a person
    id: staff are not people on anyone's record."""
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)


frozen(
    ReviewItem,
    except_for=frozenset({"verdict", "reason", "proposed", "decided_by", "decided_at"}),
)
