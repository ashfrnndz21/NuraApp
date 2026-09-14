"""What a person is asked to say yes to, as one value.

A confirm binds to its content: the surface shows the person a draft, writes the yes down
with a digest of that draft, and the service that acts recomputes the digest from what it
is actually about to write. If the two differ, the yes was for something else. The digest is
a sha256 of a canonical JSON of the fields a person can see and mean — for a fact, what it
says and where it came from; for a visit, with whom, when and why; for a change of status,
which visit and to what. Every draft is what the service will write, so labels are already
trimmed and units already carried over when it is built.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from app.memory.models import AppointmentStatus, ConfidenceState


class ConfirmSubject(StrEnum):
    """What a confirm is for."""

    FACT = "fact"
    APPOINTMENT = "appointment"
    APPOINTMENT_STATUS = "appointment_status"
    CLAIM = "claim"
    REVIEW_CARD = "review_card"


@dataclass(frozen=True, slots=True)
class FactDraft:
    """A fact about to be written, as a person confirms it and as the hooks see it."""

    subject: str
    attribute: str
    value: Any
    unit: str | None
    confidence: float
    confidence_state: ConfidenceState
    artifact_id: uuid.UUID | None
    event_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.FACT

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.supersedes_id

    def confirmed_content(self) -> dict[str, Any]:
        """What the person said yes to: the statement and its provenance, not the bookkeeping."""
        return {
            "subject": self.subject,
            "attribute": self.attribute,
            "value": self.value,
            "unit": self.unit,
            "artifact_id": self.artifact_id,
            "event_id": self.event_id,
        }


@dataclass(frozen=True, slots=True)
class AppointmentDraft:
    """A visit about to be booked: with whom, when, why."""

    provider_id: uuid.UUID
    scheduled_at: datetime
    purpose: str

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.APPOINTMENT

    @property
    def subject_id(self) -> uuid.UUID | None:
        return None

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "scheduled_at": self.scheduled_at,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class StatusChange:
    """A visit about to change status: which one, to what."""

    appointment_id: uuid.UUID
    status: AppointmentStatus

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.APPOINTMENT_STATUS

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.appointment_id

    def confirmed_content(self) -> dict[str, Any]:
        return {"appointment_id": self.appointment_id, "status": self.status}


@dataclass(frozen=True, slots=True)
class ClaimDraft:
    """A graph about to become the patient's own: which stewardship ends, who set it up,
    which parts that person keeps seeing, and the words — which version, in which
    language — the patient read before saying it is his (E01)."""

    stewardship_id: uuid.UUID
    steward_person_id: uuid.UUID
    scopes: tuple[str, ...]
    language: str
    hold_wording_version: str
    sharing_wording_version: str

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.CLAIM

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.stewardship_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "stewardship_id": self.stewardship_id,
            "steward_person_id": self.steward_person_id,
            "scopes": list(self.scopes),
            "language": self.language,
            "hold_wording_version": self.hold_wording_version,
            "sharing_wording_version": self.sharing_wording_version,
        }


@dataclass(frozen=True, slots=True)
class DecidedField:
    """One field of a review card as the person decided it: which field, what it says once
    his decision is applied, and what the decision was (`app.ingestion.models.FieldState`)."""

    field_id: uuid.UUID
    subject: str
    attribute: str
    value: Any
    unit: str | None
    decision: str


@dataclass(frozen=True, slots=True)
class ReviewDraft:
    """A review card about to close: which card, which photo it came from, and every field
    with the person's decision on it (E02-07). The yes binds to all of them at once — one
    tap saves the card — so a decision changed after the yes was shown is a different yes."""

    card_id: uuid.UUID
    artifact_id: uuid.UUID
    fields: tuple[DecidedField, ...]

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.REVIEW_CARD

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.card_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "artifact_id": self.artifact_id,
            "fields": [
                {
                    "field_id": field.field_id,
                    "subject": field.subject,
                    "attribute": field.attribute,
                    "value": field.value,
                    "unit": field.unit,
                    "decision": field.decision,
                }
                for field in self.fields
            ],
        }


Draft = FactDraft | AppointmentDraft | StatusChange | ClaimDraft | ReviewDraft


def _canonical(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} has no canonical form")


def digest_of(draft: Draft) -> str:
    """The sha256 of the canonical JSON of what was confirmed. Same draft, same digest."""
    canonical = json.dumps(
        draft.confirmed_content(), sort_keys=True, separators=(",", ":"), default=_canonical
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
