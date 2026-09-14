"""The shapes on the wire. Every field here is one the app needs; none carries a secret."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import RecordConsent
from app.identity.models import Person, Profile
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import KeyRole, KeyWindow, Scope
from app.memory.models import ConfidenceState, Fact
from app.notes.models import NOTE_LENGTH, Note
from app.regions import Region

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
    """The profile as the caller holds it: its name, and what his key opens on it."""

    profile_id: uuid.UUID
    display_name: str
    language: str
    region: Region
    role: KeyRole | None
    scopes: list[Scope]

    @classmethod
    def of(cls, profile: Profile, context: KeyContext) -> ProfileOut:
        return cls(
            profile_id=profile.id,
            display_name=profile.display_name,
            language=profile.language,
            region=profile.region,
            role=context.role,
            scopes=sorted(context.scopes),
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
