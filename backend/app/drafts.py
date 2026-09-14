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
    QUESTION = "question"
    VISIT_SUMMARY = "visit_summary"
    KEY_CHANGE = "key_change"
    ONLY_ME = "only_me"
    TASK_DONE = "task_done"
    PUSH = "push"
    ROUTINE = "routine"
    PROPOSAL = "appointment_proposal"
    ATTACH = "attach"
    DRIVE = "drive"
    CLOSE_ACCOUNT = "close_account"


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
    corrected_by: uuid.UUID | None = None
    """Who typed the value kept, where it is not what was read: a field Nura could not read,
    typed in by a daughter before the patient says yes (E02-02). None for a value as read."""


@dataclass(frozen=True, slots=True)
class ReviewDraft:
    """A review card about to close: which card, which photo it came from, and every field
    with the person's decision on it (E02-07). The yes binds to all of them at once — one
    tap saves the card — so a decision changed after the yes was shown is a different yes."""

    card_id: uuid.UUID
    artifact_id: uuid.UUID
    fields: tuple[DecidedField, ...]
    episode_id: uuid.UUID | None = None
    """The open episode the card's facts and its photo hang off once confirmed (E03-02),
    when the person named one; part of the yes, so a card confirmed into an episode was
    shown as such."""

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
            "episode_id": self.episode_id,
            "fields": [
                {
                    "field_id": field.field_id,
                    "subject": field.subject,
                    "attribute": field.attribute,
                    "value": field.value,
                    "unit": field.unit,
                    "decision": field.decision,
                    "corrected_by": field.corrected_by,
                }
                for field in self.fields
            ],
        }


@dataclass(frozen=True, slots=True)
class QuestionDraft:
    """A question a person adds, edits or removes for one visit (E05-02): the visit, the
    line as he typed it (empty for a removal), the question it replaces when it replaces
    one, and whether it is a removal. The yes binds to the words, so an edit after the yes
    was shown is a different yes."""

    appointment_id: uuid.UUID
    text: str
    language: str
    supersedes_id: uuid.UUID | None
    removed: bool

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.QUESTION

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.appointment_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "appointment_id": self.appointment_id,
            "text": self.text,
            "language": self.language,
            "supersedes_id": self.supersedes_id,
            "removed": self.removed,
        }


@dataclass(frozen=True, slots=True)
class DecidedItem:
    """One item of a post-visit summary as the person decided it: kept or not."""

    item_id: uuid.UUID
    kind: str
    decision: str


@dataclass(frozen=True, slots=True)
class VisitSummaryDraft:
    """A post-visit summary about to close (E05-05): which card, which transcript it was read
    from, and every item with the person's decision on it. One tap saves the card, so the
    yes binds to all of them at once."""

    summary_id: uuid.UUID
    artifact_id: uuid.UUID
    items: tuple[DecidedItem, ...]

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.VISIT_SUMMARY

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.summary_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "summary_id": self.summary_id,
            "artifact_id": self.artifact_id,
            "items": [
                {"item_id": item.item_id, "kind": item.kind, "decision": item.decision}
                for item in self.items
            ],
        }


@dataclass(frozen=True, slots=True)
class KeyChangeDraft:
    """A key about to be narrowed (E12-01): which key, the parts it will open afterwards,
    and the window it will run for — by name, so the service works the end out at the write
    and a yes minted a minute earlier still binds. A yes to widening is not a thing: the
    service refuses a draft wider than the key before it looks for the yes."""

    key_id: uuid.UUID
    scopes: tuple[str, ...]
    window: str | None

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.KEY_CHANGE

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.key_id

    def confirmed_content(self) -> dict[str, Any]:
        return {"key_id": self.key_id, "scopes": list(self.scopes), "window": self.window}


@dataclass(frozen=True, slots=True)
class CloseDraft:
    """The owner about to close his account (#143): what he was told will happen, word for
    word, and the day his papers go. His yes binds to exactly these."""

    lines: tuple[str, ...]
    delete_on: str

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.CLOSE_ACCOUNT

    @property
    def subject_id(self) -> uuid.UUID | None:
        return None

    def confirmed_content(self) -> dict[str, Any]:
        return {"lines": list(self.lines), "delete_on": self.delete_on}


@dataclass(frozen=True, slots=True)
class OnlyMeDraft:
    """The owner about to mark a part of his record "only me", or to open it again (E12-04):
    which part, and which way."""

    scope: str
    only_me: bool

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.ONLY_ME

    @property
    def subject_id(self) -> uuid.UUID | None:
        return None

    def confirmed_content(self) -> dict[str, Any]:
        return {"scope": self.scope, "only_me": self.only_me}


@dataclass(frozen=True, slots=True)
class TaskDoneDraft:
    """A task about to be marked done by the person it was given to (E12-03). The tap is
    the doer's own: the yes is minted and spent by the same person, and the service refuses
    anyone but the one the task names."""

    task_id: uuid.UUID

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.TASK_DONE

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.task_id

    def confirmed_content(self) -> dict[str, Any]:
        return {"task_id": self.task_id}


@dataclass(frozen=True, slots=True)
class DriveDraft:
    """One person asked to drive him to one visit (E05-03): the chief's yes to a suggestion
    from the roster, or to anyone else on the profile. It becomes a family task naming the
    visit ("drive Pa to Dr Tan") given to that person."""

    appointment_id: uuid.UUID
    person_id: uuid.UUID

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.DRIVE

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.appointment_id

    def confirmed_content(self) -> dict[str, Any]:
        return {"appointment_id": self.appointment_id, "person_id": self.person_id}


@dataclass(frozen=True, slots=True)
class PushDraft:
    """A message to the patient about to be put on the calendar (E12-06): the lines exactly
    as he will read them, in his language, when, on which channel, and until when. The yes
    binds to the lines, so what the chief previewed is what is scheduled and nothing else."""

    language: str
    lines: tuple[str, ...]
    send_at: datetime
    channel: str
    expires_at: datetime

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.PUSH

    @property
    def subject_id(self) -> uuid.UUID | None:
        return None

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "lines": list(self.lines),
            "send_at": self.send_at,
            "channel": self.channel,
            "expires_at": self.expires_at,
        }



@dataclass(frozen=True, slots=True)
class RoutineDraft:
    """A day about to be set (E10): the clock times of his anchors, the readings he is
    prompted for and at which anchor, the walks, when the morning card comes, and which
    routine this one replaces. The dose schedule is not here: it is read off the medicine
    lines at render time, so setting the day never restates a dose."""

    anchors: dict[str, str]
    reading_prompts: tuple[tuple[str, str], ...]
    walks: tuple[str, ...]
    morning_card_at: str
    supersedes_id: uuid.UUID | None

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.ROUTINE

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.supersedes_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "anchors": dict(sorted(self.anchors.items())),
            "reading_prompts": [list(prompt) for prompt in self.reading_prompts],
            "walks": list(self.walks),
            "morning_card_at": self.morning_card_at,
            "supersedes_id": self.supersedes_id,
        }


@dataclass(frozen=True, slots=True)
class ProposalDraft:
    """A visit a calendar event suggested, about to be put on the spine (E18-02): which
    proposal, with whom, when and why — as shown. Accepting it books a PLANNED appointment
    on the same person's yes; nothing is booked from a calendar without one."""

    proposal_id: uuid.UUID
    provider_name: str
    scheduled_at: datetime
    purpose: str

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.PROPOSAL

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.proposal_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "provider_name": self.provider_name,
            "scheduled_at": self.scheduled_at,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class AttachDraft:
    """An artefact about to hang off an episode or a visit (E03-01, E03-02): which artefact,
    and which one thing it hangs off. Attaching is a person's word that this paper belongs
    to that concern or that visit, so it takes a yes like any other write that arranges the
    record; the ingestion confirm that names an open episode carries its own."""

    artifact_id: uuid.UUID
    episode_id: uuid.UUID | None
    appointment_id: uuid.UUID | None

    @property
    def confirm_subject(self) -> ConfirmSubject:
        return ConfirmSubject.ATTACH

    @property
    def subject_id(self) -> uuid.UUID | None:
        return self.artifact_id

    def confirmed_content(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "episode_id": self.episode_id,
            "appointment_id": self.appointment_id,
        }


Draft = (
    FactDraft
    | AppointmentDraft
    | StatusChange
    | ClaimDraft
    | ReviewDraft
    | QuestionDraft
    | VisitSummaryDraft
    | KeyChangeDraft
    | OnlyMeDraft
    | TaskDoneDraft
    | PushDraft
    | RoutineDraft
    | ProposalDraft
    | AttachDraft
    | DriveDraft
    | CloseDraft
)


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
