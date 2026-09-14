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
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.memory.models import AppointmentStatus, ConfidenceState


class ConfirmSubject(StrEnum):
    """What a confirm is for."""

    FACT = "fact"
    APPOINTMENT = "appointment"
    APPOINTMENT_STATUS = "appointment_status"


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


Draft = FactDraft | AppointmentDraft | StatusChange


def _canonical(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} has no canonical form")


def digest_of(draft: Draft) -> str:
    """The sha256 of the canonical JSON of what was confirmed. Same draft, same digest."""
    canonical = json.dumps(
        draft.confirmed_content(), sort_keys=True, separators=(",", ":"), default=_canonical
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
