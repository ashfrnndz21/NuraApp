"""The review card: the one thing a person edits.

A card is made from one photo's extraction and names that photo. Each of its fields is a
proposed statement — subject, attribute, value, unit — with the extractor's confidence and,
below the threshold, a mark that it needs the person's eye. A person decides every field:
confirmed as proposed, corrected to what the paper says, or rejected. On his yes the card
closes and each kept field names the Fact it became; a rejected one names nothing.

Facts are never edited (`app.memory.models`), so this is where editing happens instead, and
it happens once: a field takes its decision, a card takes its close, and neither takes a
second — `frozen`, and only while `review.confirm_review_card` is the one making the change.
Every row is the profile's and is tied to its photo on the same profile, the way provenance
is tied in memory.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.ingestion.extract import DocumentKind
from app.memory.models import _row_of_profile, _tied_to_profile

CONFIDENCE_THRESHOLD = 0.8
"""Below this a field is shown dotted and asked, never assumed (docs/medications-module.md §9)."""


class FieldState(StrEnum):
    """Where a field stands. PROPOSED until the person decides; then one of the other three."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


DECISIONS = frozenset({FieldState.CONFIRMED, FieldState.CORRECTED, FieldState.REJECTED})
"""What a person may say about a field. PROPOSED is where it starts, not something he says."""

REVIEW_IN_PROGRESS = "review_card_confirm"
"""`session.info` key: the id of the one card `review.confirm_review_card` is closing right
now. The only time a card or its fields may change."""


def _review_is_in_progress(session: Any, row: Any) -> bool:
    card_id = getattr(row, "card_id", None) or row.id
    return session is not None and session.info.get(REVIEW_IN_PROGRESS) == card_id


class ReviewCard(ProfileScoped, Base):
    """One photo, read into fields, waiting for — or closed by — a person's yes.

    `high_risk_class` is not something the extractor proposed and not the person's to
    reject: it is looked up in `app.safety.high_risk` from the drug the card names, and
    shown so that the person knows the dose he is about to confirm is one the label rule
    guards. `document_date` is the date on the paper, and becomes `valid_from` on the facts.
    """

    __tablename__ = "review_card"
    __table_args__ = (
        _row_of_profile("review_card"),
        _tied_to_profile("review_card", "artifact_id", "artifact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artifact.id"), index=True)
    document_kind: Mapped[DocumentKind] = mapped_column(enum_column(DocumentKind, "document_kind"))
    document_date: Mapped[date | None] = mapped_column(default=None)
    high_risk_class: Mapped[str | None] = mapped_column(String(32), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(default=None)
    confirmed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )

    @property
    def is_open(self) -> bool:
        return self.confirmed_at is None


class ReviewField(ProfileScoped, Base):
    """One proposed statement on a card, and what the person said about it.

    `value` is what the extractor proposed and is never overwritten: a correction goes in
    `corrected_value`, so the card shows both what was read and what the person said. The
    value is JSON like a fact's, and short (`extract.VALUE_LENGTH`): a name for a thing on
    the page, never the page.
    """

    __tablename__ = "review_field"
    __table_args__ = (
        _row_of_profile("review_field"),
        _tied_to_profile("review_field", "card_id", "review_card"),
        _tied_to_profile("review_field", "fact_id", "fact"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("review_card.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(64))
    attribute: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32), default=None)
    confidence: Mapped[float] = mapped_column(Float)
    span: Mapped[dict[str, float] | None] = mapped_column(JSON(none_as_null=True), default=None)
    state: Mapped[FieldState] = mapped_column(
        enum_column(FieldState, "review_field_state"), default=FieldState.PROPOSED
    )
    corrected_value: Mapped[Any | None] = mapped_column(JSON(none_as_null=True), default=None)
    fact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fact.id"), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def needs_confirm(self) -> bool:
        """Shown dotted: the extractor was not sure enough for this to pass on a glance."""
        return self.confidence < CONFIDENCE_THRESHOLD

    @property
    def decided_value(self) -> Any:
        """What the person kept: his correction where he made one, the proposal otherwise."""
        return self.corrected_value if self.state is FieldState.CORRECTED else self.value


# A card takes one change, its close; a field takes one, its decision. Both only while the
# review service is making them.
frozen(
    ReviewCard,
    except_for=frozenset({"confirmed_at", "confirmed_by_person_id"}),
    only_when=_review_is_in_progress,
)
frozen(
    ReviewField,
    except_for=frozenset({"state", "corrected_value", "fact_id", "decided_at"}),
    only_when=_review_is_in_progress,
)
