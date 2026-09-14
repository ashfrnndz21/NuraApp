"""The shapes on the wire. Every field here is one the app needs; none carries a secret."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.consent.models import (
    DOCUMENTED_BASES,
    Consent,
    ConsentBasis,
    ConsentChannel,
    ConsentPurpose,
)
from app.consent.service import RecordConsent
from app.db import as_utc
from app.drafts import ConfirmSubject
from app.identity.doors import Claimable, Doors, Evidence
from app.identity.models import Person, Profile, Stewardship
from app.ingestion.extract import DocumentKind
from app.ingestion.models import FieldState, ReviewCard, ReviewField
from app.ingestion.photos import MAX_PHOTO_BYTES
from app.ingestion.review import Decision
from app.keys.confirm import Confirmation
from app.keys.context import KeyContext, Standing
from app.keys.models import Key
from app.keys.scopes import KeyRole, KeyWindow, Scope
from app.memory.models import ArtifactKind, ConfidenceState, Event, Fact
from app.notes.models import NOTE_LENGTH, Note
from app.regions import Region
from app.state.models import Dimension, Posture, StateTrigger
from app.state.service import StateView


def utc(moment: datetime) -> datetime:
    """A stored moment as the wire carries it: UTC, whichever clock it was written on or
    whichever database dropped the timezone on the way back."""
    return as_utc(moment).astimezone(UTC)


PHONE = r"^\+[1-9][0-9]{7,14}$"
"""E.164: a plus, then eight to fifteen digits. Spaces and dashes are the app's to strip."""
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
"""An address with one @ and a dot after it. The link that goes to it is the real check."""

# --- signing in --------------------------------------------------------------------------


class PhoneStart(BaseModel):
    phone_e164: str = Field(pattern=PHONE)
    display_name: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=16)


class PhoneVerify(BaseModel):
    phone_e164: str = Field(pattern=PHONE)
    code: str = Field(pattern=r"^[0-9]{6}$")


class EmailStart(BaseModel):
    email: str = Field(pattern=EMAIL, max_length=320)
    display_name: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=16)


class EmailVerify(BaseModel):
    email: str = Field(pattern=EMAIL, max_length=320)
    token: str = Field(min_length=1, max_length=128)


class Started(BaseModel):
    """The code went out, and for how long it works.

    The number is for the app's own clock; the line the screen shows is
    `app.channels.strings.CODE_WORKS_FOR`, in words. Never the seconds.
    """

    expires_in_seconds: int


class SessionOut(BaseModel):
    """The token, once. It is not stored anywhere in the clear and cannot be asked for again."""

    token: str
    person_id: uuid.UUID
    region: Region


class MeOut(BaseModel):
    person_id: uuid.UUID
    display_name: str
    language: str
    region: Region
    phone_e164: str | None
    email: str | None
    profile_id: uuid.UUID | None

    @classmethod
    def of(cls, person: Person, profile: Profile | None) -> MeOut:
        return cls(
            person_id=person.id,
            display_name=person.display_name,
            language=person.language,
            region=person.region,
            phone_e164=person.phone_e164,
            email=person.email,
            profile_id=None if profile is None else profile.id,
        )


# --- profiles ----------------------------------------------------------------------------


class ConsentIn(BaseModel):
    """The agreement the owner gave to Nura holding his record, as the app captured it.

    Which words (by version), in which language he read them, and how — in the app, on
    WhatsApp, on paper, or spoken and witnessed. It becomes the `HOLD_HEALTH_RECORD`
    consent recorded on the new profile in the same transaction (E00-02); words that are
    not today's words on file refuse before a profile exists.
    """

    wording_version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z._-]+$")
    language: str = Field(min_length=2, max_length=16)
    captured_via: ConsentChannel

    def as_record(self) -> RecordConsent:
        return RecordConsent(
            text_version=self.wording_version,
            language=self.language,
            captured_via=self.captured_via,
        )


class SharingConsentIn(BaseModel):
    """The owner lets one person in: who, to which parts, and who they are to him.

    The words the patient reads are rendered with that name and those parts and kept as
    read. A key for this person can only be cut once this is in force, and never wider.
    """

    holder_phone_e164: str | None = Field(default=None, pattern=PHONE)
    holder_person_id: uuid.UUID | None = None
    scopes: list[Scope] = Field(min_length=1)
    relationship: str | None = Field(default=None, min_length=1, max_length=80)
    language: str = Field(min_length=2, max_length=16)
    captured_via: ConsentChannel
    wording_version: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[0-9A-Za-z._-]+$"
    )

    @model_validator(mode="after")
    def _one_holder(self) -> SharingConsentIn:
        if (self.holder_phone_e164 is None) == (self.holder_person_id is None):
            raise ValueError("name the holder by phone number or by person id, one of the two")
        return self


class ConsentOut(BaseModel):
    """One agreement on the profile, as the owner or his chief reads it back."""

    consent_id: uuid.UUID
    purpose: ConsentPurpose
    person_id: uuid.UUID
    holder_person_id: uuid.UUID | None
    scopes: list[Scope] | None
    text_version: str
    language: str
    wording_text: str
    captured_via: ConsentChannel
    basis: ConsentBasis
    granted_at: datetime
    revoked_at: datetime | None
    revoked_by_person_id: uuid.UUID | None

    @classmethod
    def of(cls, consent: Consent) -> ConsentOut:
        return cls(
            consent_id=consent.id,
            purpose=consent.purpose,
            person_id=consent.person_id,
            holder_person_id=consent.holder_person_id,
            scopes=(
                sorted(Scope(name) for name in consent.scopes)
                if consent.scopes is not None
                else None
            ),
            text_version=consent.text_version,
            language=consent.language,
            wording_text=consent.wording_text,
            captured_via=consent.captured_via,
            basis=consent.basis,
            granted_at=consent.granted_at,
            revoked_at=consent.revoked_at,
            revoked_by_person_id=consent.revoked_by_person_id,
        )


class ProfileCreate(BaseModel):
    consent: ConsentIn
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    language: str | None = Field(default=None, min_length=1, max_length=16)


class ProfileOut(BaseModel):
    """The profile as the caller holds it: its name, what his key opens on it, and on what
    footing he reaches it — its owner, a key holder, its steward until the patient claims
    it, or the patient before he has (`app.keys.context.Standing`)."""

    profile_id: uuid.UUID
    display_name: str
    language: str
    region: Region
    role: KeyRole | None
    scopes: list[Scope]
    standing: Standing

    @classmethod
    def of(cls, profile: Profile, context: KeyContext) -> ProfileOut:
        return cls(
            profile_id=profile.id,
            display_name=profile.display_name,
            language=profile.language,
            region=profile.region,
            role=context.role,
            scopes=sorted(context.scopes),
            standing=context.standing,
        )


# --- for someone I care for, and the claim ----------------------------------------------


class EvidenceIn(BaseModel):
    """The document behind a documented basis — the lasting power of attorney, the doctor's
    letter — already stored in the region; it becomes the first artefact on the graph."""

    kind: ArtifactKind
    storage_key: str = Field(min_length=1, max_length=512)
    content_type: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    captured_at: datetime

    def as_evidence(self) -> Evidence:
        return Evidence(
            kind=self.kind,
            storage_key=self.storage_key,
            content_type=self.content_type,
            sha256=self.sha256.lower(),
            captured_at=self.captured_at,
        )


class ProfileForSomeone(BaseModel):
    """Set up a graph for someone by their phone number, held by the caller until claimed.

    `consent` is the agreement to Nura keeping the record as the caller read it; `basis`
    is what entitles him to give it for the patient: the patient asked (his claim is the
    proof to come), or a lasting power of attorney or a doctor's letter, with `evidence`.
    `relationship` is who the caller is to the patient, in the caller's words, for the
    claim to name him by.
    """

    patient_phone_e164: str = Field(pattern=PHONE)
    display_name: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=2, max_length=16)
    consent: ConsentIn
    basis: ConsentBasis
    relationship: str | None = Field(default=None, min_length=1, max_length=80)
    evidence: EvidenceIn | None = None

    @model_validator(mode="after")
    def _a_document_for_a_documented_basis(self) -> ProfileForSomeone:
        documented = self.basis in DOCUMENTED_BASES
        if documented and self.evidence is None:
            raise ValueError(f"{self.basis.value} needs the document as evidence")
        if not documented and self.evidence is not None:
            raise ValueError(f"{self.basis.value} takes no document")
        return self


class StewardshipOut(BaseModel):
    """Who holds this graph for the patient, on what footing, and whether he has claimed it."""

    stewardship_id: uuid.UUID
    profile_id: uuid.UUID
    steward_person_id: uuid.UUID
    steward_display_name: str
    relationship: str | None
    basis: ConsentBasis
    key_id: uuid.UUID
    consent_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None
    claimed_by_person_id: uuid.UUID | None

    @classmethod
    def of(cls, stewardship: Stewardship, steward_display_name: str) -> StewardshipOut:
        return cls(
            stewardship_id=stewardship.id,
            profile_id=stewardship.profile_id,
            steward_person_id=stewardship.steward_person_id,
            steward_display_name=steward_display_name,
            relationship=stewardship.relationship,
            basis=stewardship.basis,
            key_id=stewardship.key_id,
            consent_id=stewardship.consent_id,
            opened_at=stewardship.opened_at,
            closed_at=stewardship.closed_at,
            claimed_by_person_id=stewardship.claimed_by_person_id,
        )


class ClaimableOut(BaseModel):
    """A graph set up for the caller, waiting for his OK: who set it up, what they keep
    seeing once it is his, and the words he is agreeing to, in the language asked for.
    The claim's confirmation is minted for exactly these fields (`POST
    /profiles/{id}/confirmations` with subject `claim` and this `language`)."""

    profile_id: uuid.UUID
    display_name: str
    language: str
    stewardship_id: uuid.UUID
    steward_person_id: uuid.UUID
    set_up_by: str
    relationship: str | None
    parts: list[Scope]
    words_language: str
    hold_wording_version: str
    hold_words: str
    sharing_wording_version: str
    sharing_words: str

    @classmethod
    def of(cls, claimable: Claimable) -> ClaimableOut:
        return cls(
            profile_id=claimable.profile.id,
            display_name=claimable.profile.display_name,
            language=claimable.profile.language,
            stewardship_id=claimable.stewardship.id,
            steward_person_id=claimable.stewardship.steward_person_id,
            set_up_by=claimable.steward.display_name,
            relationship=claimable.stewardship.relationship,
            parts=[Scope(name) for name in claimable.draft.scopes],
            words_language=claimable.draft.language,
            hold_wording_version=claimable.draft.hold_wording_version,
            hold_words=claimable.hold_words,
            sharing_wording_version=claimable.draft.sharing_wording_version,
            sharing_words=claimable.sharing_words,
        )


class ClaimConfirmIn(BaseModel):
    """A yes to claiming this graph, as shown: the words in `language`. The draft itself is
    recomputed from the graph, so nothing here can name a different steward or wider parts."""

    subject: Literal[ConfirmSubject.CLAIM]
    language: str = Field(min_length=2, max_length=16)


class DecisionIn(BaseModel):
    """What the person said about one field of a review card: confirmed as read, corrected
    to what the paper says (with the value), or rejected."""

    field_id: uuid.UUID
    decision: Literal[FieldState.CONFIRMED, FieldState.CORRECTED, FieldState.REJECTED]
    corrected_value: Any | None = None

    @model_validator(mode="after")
    def _a_correction_says_what_to(self) -> DecisionIn:
        corrected = self.decision is FieldState.CORRECTED
        if corrected and self.corrected_value is None:
            raise ValueError("a correction says what the value should be")
        if not corrected and self.corrected_value is not None:
            raise ValueError("only a correction carries a value")
        return self

    def as_decision(self) -> Decision:
        return Decision(
            field_id=self.field_id,
            decision=FieldState(self.decision),
            corrected_value=self.corrected_value,
        )


class ReviewCardConfirmIn(BaseModel):
    """A yes to closing a review card with exactly these decisions. The draft is recomputed
    from the card, so the yes binds to every field as shown and every decision as made."""

    subject: Literal[ConfirmSubject.REVIEW_CARD]
    card_id: uuid.UUID
    decisions: list[DecisionIn]


ConfirmIn = Annotated[ClaimConfirmIn | ReviewCardConfirmIn, Field(discriminator="subject")]
"""What `POST /profiles/{id}/confirmations` takes, by subject: the claim, or a review card
with its decisions. Facts and visits are minted by the surfaces that show them once those
exist."""


class ConfirmationOut(BaseModel):
    """The yes, handed once to the person who said it, so he can spend it."""

    confirmation_id: uuid.UUID
    subject: ConfirmSubject
    expires_at: datetime

    @classmethod
    def of(cls, confirmation: Confirmation) -> ConfirmationOut:
        return cls(
            confirmation_id=confirmation.id,
            subject=confirmation.subject,
            expires_at=confirmation.expires_at,
        )


class ClaimIn(BaseModel):
    """Claim the graph with the yes minted for it, in the language the words were read in."""

    confirmation_id: uuid.UUID
    language: str = Field(min_length=2, max_length=16)
    captured_via: ConsentChannel = ConsentChannel.APP


class DoorsOut(BaseModel):
    """Which doors apply to the caller: his own graph, graphs set up for him waiting for
    his claim, graphs he was let in to by a key, and graphs he holds for someone."""

    own: ProfileOut | None
    claimable: list[ClaimableOut]
    invited: list[ProfileOut]
    stewarding: list[ProfileOut]

    @classmethod
    def of(cls, doors: Doors) -> DoorsOut:
        return cls(
            own=None if doors.own is None else ProfileOut.of(doors.own.profile, doors.own.context),
            claimable=[ClaimableOut.of(each) for each in doors.claimable],
            invited=[ProfileOut.of(each.profile, each.context) for each in doors.invited],
            stewarding=[ProfileOut.of(each.profile, each.context) for each in doors.stewarding],
        )


# --- keys --------------------------------------------------------------------------------


class KeyGrant(BaseModel):
    """Cut a key: for whom, as what, over which parts, for how long.

    The key rests on the sharing consent the owner gave for this person
    (`POST /profiles/{id}/consents/sharing`); without one in force it is refused.
    """

    holder_phone_e164: str | None = Field(default=None, pattern=PHONE)
    holder_person_id: uuid.UUID | None = None
    role: KeyRole
    scopes: list[Scope] | None = None
    window: KeyWindow | None = None

    @model_validator(mode="after")
    def _one_holder(self) -> KeyGrant:
        if (self.holder_phone_e164 is None) == (self.holder_person_id is None):
            raise ValueError("name the holder by phone number or by person id, one of the two")
        return self


class KeyOut(BaseModel):
    key_id: uuid.UUID
    profile_id: uuid.UUID
    holder_person_id: uuid.UUID
    role: KeyRole
    scopes: list[Scope]
    consent_id: uuid.UUID | None
    granted_by_person_id: uuid.UUID
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def of(cls, key: Key) -> KeyOut:
        return cls(
            key_id=key.id,
            profile_id=key.profile_id,
            holder_person_id=key.holder_person_id,
            role=key.role,
            scopes=sorted(key.scopes_held),
            consent_id=key.consent_id,
            granted_by_person_id=key.granted_by_person_id,
            granted_at=key.granted_at,
            expires_at=key.expires_at,
            revoked_at=key.revoked_at,
        )


# --- the audit trail ---------------------------------------------------------------------


class AuditOut(BaseModel):
    """One line of the trail: what was touched and by whom, never what it said."""

    entry_id: uuid.UUID
    at: datetime
    actor_person_id: uuid.UUID
    actor_role: KeyRole | None
    key_id: uuid.UUID | None
    action: Action
    scope: Scope
    channel: Channel
    target: str
    target_id: uuid.UUID | None
    rows: int
    outcome: Outcome
    refused_because: str | None
    shared_with_person_id: uuid.UUID | None
    shared_with_label: str | None

    @classmethod
    def of(cls, entry: AuditEntry) -> AuditOut:
        return cls(
            entry_id=entry.id,
            at=entry.at,
            actor_person_id=entry.actor_person_id,
            actor_role=entry.actor_role,
            key_id=entry.key_id,
            action=entry.action,
            scope=entry.scope,
            channel=entry.channel,
            target=entry.target,
            target_id=entry.target_id,
            rows=entry.rows,
            outcome=entry.outcome,
            refused_because=entry.refused_because,
            shared_with_person_id=entry.shared_with_person_id,
            shared_with_label=entry.shared_with_label,
        )


# --- notes and medicines -----------------------------------------------------------------


class NoteIn(BaseModel):
    text: str = Field(max_length=NOTE_LENGTH)


class NoteOut(BaseModel):
    note_id: uuid.UUID
    text: str
    written_at: datetime

    @classmethod
    def of(cls, note: Note) -> NoteOut:
        return cls(note_id=note.id, text=note.text, written_at=note.written_at)


class MedicineOut(BaseModel):
    """A current fact with subject "medicine", with its provenance and its confidence.

    Nothing infers without provenance: the artefact or event the fact was read from travels
    with it, so a screen can always show where a value came from. The real medicine line
    arrives with E04.
    """

    fact_id: uuid.UUID
    attribute: str
    value: Any
    unit: str | None
    confidence: float
    confidence_state: ConfidenceState
    artifact_id: uuid.UUID | None
    event_id: uuid.UUID | None
    valid_from: datetime
    valid_to: datetime | None

    @classmethod
    def of(cls, fact: Fact) -> MedicineOut:
        return cls(
            fact_id=fact.id,
            attribute=fact.attribute,
            value=fact.value,
            unit=fact.unit,
            confidence=fact.confidence,
            confidence_state=fact.confidence_state,
            artifact_id=fact.artifact_id,
            event_id=fact.event_id,
            valid_from=fact.valid_from,
            valid_to=fact.valid_to,
        )


# --- readings and State ------------------------------------------------------------------


class ReadingIn(BaseModel):
    """A blood pressure the person typed in: the two numbers, and when it was taken.

    Thin on purpose: the real capture — photo of the book, device, review card with
    confidence per field — is E02. This is what checkpoint 3 needs: one reading, as one
    event with one fact resting on it, so that State has something to recompute from.
    """

    systolic: int = Field(ge=40, le=300)
    diastolic: int = Field(ge=20, le=200)
    taken_at: datetime | None = None


class ReadingOut(BaseModel):
    """What the reading became: the event it is, and the fact that names it."""

    event_id: uuid.UUID
    fact_id: uuid.UUID
    taken_at: datetime

    @classmethod
    def of(cls, event: Event, fact: Fact) -> ReadingOut:
        return cls(event_id=event.id, fact_id=fact.id, taken_at=event.occurred_at)


class TriggerOut(BaseModel):
    """Why this snapshot was computed, and the fact that caused it when a fact did."""

    kind: StateTrigger
    fact_id: uuid.UUID | None


class WithheldOut(BaseModel):
    """What the key did not open: whole dimensions, and the scopes of subjects taken out of
    the ones it did."""

    dimensions: list[Dimension]
    scopes: list[Scope]


class StateOut(BaseModel):
    """The current State as the caller's key reads it.

    Each dimension is the snapshot's own JSON — short codes, ids and the values of the facts
    folded in — or null where the key does not cover it. `stale` is false when the record
    was checked against this snapshot, true when it has moved on, null when the key was too
    narrow to check. `state_id` is what every card names.
    """

    state_id: uuid.UUID
    profile_id: uuid.UUID
    sequence: int
    computed_at: datetime
    posture: Posture
    trigger: TriggerOut
    supersedes_id: uuid.UUID | None
    stale: bool | None
    stale_after: datetime | None
    dimensions: dict[Dimension, dict[str, Any] | None]
    withheld: WithheldOut

    @classmethod
    def of(cls, view: StateView) -> StateOut:
        return cls(
            state_id=view.id,
            profile_id=view.profile_id,
            sequence=view.sequence,
            computed_at=view.computed_at,
            posture=view.posture,
            trigger=TriggerOut(kind=view.trigger, fact_id=view.trigger_fact_id),
            supersedes_id=view.supersedes_id,
            stale=view.stale,
            stale_after=view.stale_after,
            dimensions={
                dimension: None if held is None else dict(held)
                for dimension, held in view.dimensions.items()
            },
            withheld=WithheldOut(
                dimensions=sorted(view.withheld), scopes=sorted(view.withheld_scopes)
            ),
        )


# --- capture: photos and review cards ----------------------------------------------------


class PhotoIn(BaseModel):
    """A photo of a page, as the app sends it: the bytes in base64, what kind of image, and
    when it was taken. The bytes go to the region's object store; nothing of them is kept
    on any row."""

    data: str = Field(min_length=1, max_length=MAX_PHOTO_BYTES * 4 // 3 + 4)
    content_type: str = Field(min_length=1, max_length=128)
    captured_at: datetime

    @field_validator("data")
    @classmethod
    def _base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as not_base64:
            raise ValueError("data is base64") from not_base64
        return value

    def as_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


class ReviewFieldOut(BaseModel):
    """One proposed statement on the card: what was read, how sure, whether it needs the
    person's eye (`needs_confirm`: shown dotted), and what he said about it."""

    field_id: uuid.UUID
    position: int
    subject: str
    attribute: str
    value: Any
    unit: str | None
    confidence: float
    needs_confirm: bool
    span: dict[str, float] | None
    state: FieldState
    corrected_value: Any | None
    fact_id: uuid.UUID | None

    @classmethod
    def of(cls, field: ReviewField) -> ReviewFieldOut:
        return cls(
            field_id=field.id,
            position=field.position,
            subject=field.subject,
            attribute=field.attribute,
            value=field.value,
            unit=field.unit,
            confidence=field.confidence,
            needs_confirm=field.needs_confirm,
            span=field.span,
            state=field.state,
            corrected_value=field.corrected_value,
            fact_id=field.fact_id,
        )


class ReviewCardOut(BaseModel):
    """A review card: the photo it came from, what kind of paper and its date, whether the
    label rule guards the drug it names, its fields, and — once confirmed — by whom."""

    card_id: uuid.UUID
    profile_id: uuid.UUID
    artifact_id: uuid.UUID
    document_kind: DocumentKind
    document_date: date | None
    high_risk_class: str | None
    created_at: datetime
    confirmed_at: datetime | None
    confirmed_by_person_id: uuid.UUID | None
    fields: list[ReviewFieldOut]

    @classmethod
    def of(cls, card: ReviewCard, fields: Sequence[ReviewField]) -> ReviewCardOut:
        return cls(
            card_id=card.id,
            profile_id=card.profile_id,
            artifact_id=card.artifact_id,
            document_kind=card.document_kind,
            document_date=card.document_date,
            high_risk_class=card.high_risk_class,
            created_at=utc(card.created_at),
            confirmed_at=None if card.confirmed_at is None else utc(card.confirmed_at),
            confirmed_by_person_id=card.confirmed_by_person_id,
            fields=[ReviewFieldOut.of(field) for field in fields],
        )


class ReviewConfirmIn(BaseModel):
    """Close the card: the decisions, and the yes minted for exactly them."""

    decisions: list[DecisionIn]
    confirmation_id: uuid.UUID


class FactOut(BaseModel):
    """A current fact with its provenance, its confidence and who confirmed it."""

    fact_id: uuid.UUID
    subject: str
    attribute: str
    value: Any
    unit: str | None
    confidence: float
    confidence_state: ConfidenceState
    confirmed_by_person_id: uuid.UUID | None
    artifact_id: uuid.UUID | None
    event_id: uuid.UUID | None
    valid_from: datetime
    valid_to: datetime | None
    asserted_at: datetime

    @classmethod
    def of(cls, fact: Fact) -> FactOut:
        return cls(
            fact_id=fact.id,
            subject=fact.subject,
            attribute=fact.attribute,
            value=fact.value,
            unit=fact.unit,
            confidence=fact.confidence,
            confidence_state=fact.confidence_state,
            confirmed_by_person_id=fact.confirmed_by_person_id,
            artifact_id=fact.artifact_id,
            event_id=fact.event_id,
            valid_from=utc(fact.valid_from),
            valid_to=None if fact.valid_to is None else utc(fact.valid_to),
            asserted_at=utc(fact.asserted_at),
        )


class ReviewConfirmedOut(BaseModel):
    """What closing the card did: the card as it stands, and the facts it wrote."""

    card: ReviewCardOut
    facts: list[FactOut]
