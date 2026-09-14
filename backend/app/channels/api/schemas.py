"""The shapes on the wire. Every field here is one the app needs; none carries a secret."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Sequence
from dataclasses import asdict
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
from app.medicines.dose import Anchor, Dose, Frequency, parse_dose_text
from app.medicines.models import (
    ChangeKind,
    DoseTaken,
    InteractionFlag,
    LineStatus,
    MedicationLine,
    SourceKind,
    Supply,
)
from app.medicines.service import (
    Count,
    FlagView,
    Label,
    LineView,
    Plan,
    Reconciled,
    Slot,
)
from app.medicines.service import Outcome as MedicineOutcome
from app.medicines.story import Story
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    ArtifactKind,
    ConfidenceState,
    Event,
    Fact,
    Provider,
    ProviderKind,
)
from app.notes.models import NOTE_LENGTH, Note
from app.reasoning.visits.models import (
    LINE_LENGTH,
    Brief,
    ItemState,
    Memo,
    Question,
    SummaryItem,
    VisitSummary,
)
from app.reasoning.visits.summary import MAX_TRANSCRIPT_BYTES
from app.reasoning.visits.summary import Decision as ItemDecision
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


class MedicineConfirmIn(BaseModel):
    """A yes to what a label means for the list, as shown by `POST /medicines/draft`.

    The draft is recomputed from the label and the list — a new line, a refill, a dose change
    naming the line it supersedes — so the yes binds to exactly what `POST /medicines` will
    write with it, and nothing here can name a different medicine or amount.
    """

    subject: Literal["medicine"]
    label: LabelIn
    source_artifact_id: uuid.UUID


class AppointmentConfirmIn(BaseModel):
    """A yes to booking a visit: with whom, when, why — exactly what `POST /appointments`
    will write (E05, the spine's `book_appointment`)."""

    subject: Literal[ConfirmSubject.APPOINTMENT]
    provider_id: uuid.UUID
    scheduled_at: datetime
    purpose: str = Field(min_length=1, max_length=80)


class QuestionConfirmIn(BaseModel):
    """A yes to adding, editing or removing one question for a visit (E05-02): the words as
    typed (none for a removal) and the question they replace, if any. The draft is
    recomputed from the visit, so the yes binds to the words as shown."""

    subject: Literal[ConfirmSubject.QUESTION]
    appointment_id: uuid.UUID
    text: str | None = Field(default=None, min_length=1, max_length=LINE_LENGTH)
    question_id: uuid.UUID | None = None
    remove: bool = False


class ItemDecisionIn(BaseModel):
    """What the person said about one item of a post-visit summary: kept, or not."""

    item_id: uuid.UUID
    decision: Literal[ItemState.CONFIRMED, ItemState.REJECTED]

    def as_decision(self) -> ItemDecision:
        return ItemDecision(item_id=self.item_id, decision=ItemState(self.decision))


class SummaryConfirmIn(BaseModel):
    """A yes to a whole post-visit summary as shown: every item, decided (E05-05)."""

    subject: Literal[ConfirmSubject.VISIT_SUMMARY]
    summary_id: uuid.UUID
    decisions: list[ItemDecisionIn]


ConfirmIn = Annotated[
    ClaimConfirmIn
    | ReviewCardConfirmIn
    | MedicineConfirmIn
    | AppointmentConfirmIn
    | QuestionConfirmIn
    | SummaryConfirmIn,
    Field(discriminator="subject"),
]
"""What `POST /profiles/{id}/confirmations` takes, by subject: the claim (E01), a review card
with its decisions (E02), a medicine label against the list (E04), a visit booking, a question
for a visit and a post-visit summary (E05)."""


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


class DoseIn(BaseModel):
    """How much, how often, at which moments of his day. A code, never a sentence."""

    amount: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=16)
    frequency: Frequency
    anchors: list[Anchor] = Field(default_factory=list)

    def as_dose(self) -> Dose:
        return Dose(
            amount=self.amount,
            unit=self.unit,
            frequency=self.frequency,
            anchors=tuple(self.anchors),
        )


class LabelIn(BaseModel):
    """What one label or pack said. The dose comes as a code or as the label's own words
    (`dose_text`: "1 tab BD", "1 biji 2 kali sehari"), one of the two. Nothing here is a
    patient's name: the label's patient line is checked by ingestion and never stored."""

    generic: str | None = Field(default=None, min_length=1, max_length=64)
    brand: str | None = Field(default=None, min_length=1, max_length=80)
    strength: str | None = Field(default=None, min_length=1, max_length=32)
    form: str | None = Field(default=None, min_length=1, max_length=32)
    registration_no: str | None = Field(default=None, min_length=1, max_length=32)
    dose: DoseIn | None = None
    dose_text: str | None = Field(default=None, min_length=1, max_length=120)
    quantity: int | None = Field(default=None, gt=0)
    prescriber: str | None = Field(default=None, min_length=1, max_length=80)
    dispensed_at: datetime | None = None
    source_kind: SourceKind = SourceKind.RETAIL
    confidence: float = Field(default=1.0, ge=0, le=1)

    @model_validator(mode="after")
    def _one_dose(self) -> LabelIn:
        if (self.dose is None) == (self.dose_text is None):
            raise ValueError("give the dose as a code or as the label's words, one of the two")
        if self.generic is None and self.brand is None and self.registration_no is None:
            raise ValueError("a label names the medicine: registration number, brand or generic")
        return self

    def as_label(self) -> Label:
        dose = (
            self.dose.as_dose() if self.dose is not None else parse_dose_text(self.dose_text or "")
        )
        return Label(
            dose=dose,
            generic=self.generic,
            brand=self.brand,
            strength=self.strength,
            form=self.form,
            registration_no=self.registration_no,
            quantity=self.quantity,
            prescriber=self.prescriber,
            dispensed_at=self.dispensed_at,
            source_kind=self.source_kind,
            confidence=self.confidence,
        )


class MedicineDraftIn(BaseModel):
    """Ask what this label would do to the list, before anyone says yes."""

    label: LabelIn
    source_artifact_id: uuid.UUID


class MedicineIn(BaseModel):
    """Write what the label means, with the yes minted for exactly that."""

    label: LabelIn
    source_artifact_id: uuid.UUID
    confirmation_id: uuid.UUID


class DrugMatchOut(BaseModel):
    """The product the licensed register identified. Never a guess."""

    registration_no: str
    brand: str
    generic: str
    strength: str
    form: str
    drug_class: str
    high_risk: bool


class FlaggedOut(BaseModel):
    """One pair the licensed data flagged: which other line, how much it matters, and the
    question for the doctor in the patient's words."""

    other_line_id: uuid.UUID
    other_generic: str
    severity: str
    text_id: str
    question: list[str]

    @classmethod
    def of(cls, view: FlagView) -> FlaggedOut:
        return cls(
            other_line_id=view.other.id,
            other_generic=view.other.generic,
            severity=view.flag.severity.value,
            text_id=view.flag.text_id,
            question=view.question,
        )


class MedicineDraftOut(BaseModel):
    """What the label means against the list, before anything is written.

    `flagged` names the interactions that would be recorded with a new line, severity and
    both medicines. `needs_label_photo` is the high-risk rule: this class is saved only from
    a label photo, and the artefact given is not one.
    """

    outcome: MedicineOutcome
    match: DrugMatchOut
    matched_line_id: uuid.UUID | None
    flagged: list[FlaggedOut]
    needs_label_photo: bool
    lead_time_days: int

    @classmethod
    def of(cls, plan: Plan, questions: list[list[str]]) -> MedicineDraftOut:
        return cls(
            outcome=plan.outcome,
            match=DrugMatchOut(**asdict(plan.match)),
            matched_line_id=None if plan.matched_line is None else plan.matched_line.id,
            flagged=[
                FlaggedOut(
                    other_line_id=each.other_line.id,
                    other_generic=each.other_line.generic,
                    severity=each.interaction.severity.value,
                    text_id=each.interaction.text_id,
                    question=question,
                )
                for each, question in zip(plan.flagged, questions, strict=True)
            ],
            needs_label_photo=plan.needs_label_photo,
            lead_time_days=plan.lead_time_days,
        )


class CountOut(BaseModel):
    """The running count and the reorder date, with what they rest on, and the same in his
    words. `basis` is `taps` (dispensed minus Taken) or `none` (nothing dispensed yet)."""

    remaining: float
    unit: str
    dispensed: float
    taken: float
    daily_amount: float | None
    days_left: int | None
    reorder_date: date | None
    reorder_due: bool
    lead_time_days: int
    basis: str
    lines: list[str]
    reorder: list[str]
    reorder_actions: dict[str, str]

    @classmethod
    def of(cls, count: Count) -> CountOut:
        return cls(**asdict(count))


class LineOut(BaseModel):
    """One line of the reconciled list: what the register identified, the dose the label
    said, where it came from and how sure, its count, its flags, and the other active lines
    of the same medicine (two strengths in the cupboard)."""

    line_id: uuid.UUID
    fact_id: uuid.UUID
    name: str
    generic: str
    brand: str | None
    strength: str
    form: str
    registration_no: str | None
    drug_class: str
    high_risk: bool
    dose: DoseIn
    prescriber: str | None
    source_kind: SourceKind
    source_artifact_id: uuid.UUID | None
    source_event_id: uuid.UUID | None
    confidence: float
    confidence_state: ConfidenceState
    status: LineStatus
    change_kind: ChangeKind
    started_at: datetime
    supersedes_id: uuid.UUID | None
    superseded_at: datetime | None
    confirmed_by_person_id: uuid.UUID
    count: CountOut | None
    flags: list[FlaggedOut]
    duplicate_of: list[uuid.UUID]
    doctor_question: list[str]
    taken_label: str | None

    @classmethod
    def of(cls, view: LineView) -> LineOut:
        return cls(
            **cls._columns(view.line),
            name=view.name,
            count=CountOut.of(view.count),
            flags=[FlaggedOut.of(flag) for flag in view.flags],
            duplicate_of=view.duplicate_of,
            doctor_question=view.doctor_question,
            taken_label=view.taken_label,
        )

    @classmethod
    def history_of(cls, line: MedicationLine) -> LineOut:
        return cls(
            **cls._columns(line),
            name=line.generic,
            count=None,
            flags=[],
            duplicate_of=[],
            doctor_question=[],
            taken_label=None,
        )

    @staticmethod
    def _columns(line: MedicationLine) -> dict[str, Any]:
        dose = Dose.from_json(line.dose)
        return {
            "line_id": line.id,
            "fact_id": line.fact_id,
            "generic": line.generic,
            "brand": line.brand,
            "strength": line.strength,
            "form": line.form,
            "registration_no": line.registration_no,
            "drug_class": line.drug_class,
            "high_risk": line.high_risk,
            "dose": DoseIn(
                amount=dose.amount,
                unit=dose.unit,
                frequency=dose.frequency,
                anchors=list(dose.anchors),
            ),
            "prescriber": line.prescriber,
            "source_kind": line.source_kind,
            "source_artifact_id": line.source_artifact_id,
            "source_event_id": line.source_event_id,
            "confidence": line.confidence,
            "confidence_state": line.confidence_state,
            "status": line.status,
            "change_kind": line.change_kind,
            "started_at": line.started_at,
            "supersedes_id": line.supersedes_id,
            "superseded_at": line.superseded_at,
            "confirmed_by_person_id": line.confirmed_by_person_id,
        }


class SupplyOut(BaseModel):
    supply_id: uuid.UUID
    line_id: uuid.UUID
    fact_id: uuid.UUID
    quantity: int
    dispensed_at: datetime
    artifact_id: uuid.UUID | None

    @classmethod
    def of(cls, supply: Supply) -> SupplyOut:
        return cls(
            supply_id=supply.id,
            line_id=supply.line_id,
            fact_id=supply.fact_id,
            quantity=supply.quantity,
            dispensed_at=supply.dispensed_at,
            artifact_id=supply.artifact_id,
        )


class FlagOut(BaseModel):
    flag_id: uuid.UUID
    line_id: uuid.UUID
    other_line_id: uuid.UUID
    severity: str
    text_id: str

    @classmethod
    def of(cls, flag: InteractionFlag) -> FlagOut:
        return cls(
            flag_id=flag.id,
            line_id=flag.line_id,
            other_line_id=flag.other_line_id,
            severity=flag.severity.value,
            text_id=flag.text_id,
        )


class ReconciledOut(BaseModel):
    """What the label became: the outcome, the line it landed on, the supply and the flags."""

    outcome: MedicineOutcome
    line_id: uuid.UUID
    fact_id: uuid.UUID
    generic: str
    strength: str
    high_risk: bool
    change_kind: ChangeKind
    supersedes_id: uuid.UUID | None
    supply: SupplyOut | None
    flags: list[FlagOut]

    @classmethod
    def of(cls, done: Reconciled) -> ReconciledOut:
        return cls(
            outcome=done.outcome,
            line_id=done.line.id,
            fact_id=done.line.fact_id,
            generic=done.line.generic,
            strength=done.line.strength,
            high_risk=done.line.high_risk,
            change_kind=done.line.change_kind,
            supersedes_id=done.line.supersedes_id,
            supply=None if done.supply is None else SupplyOut.of(done.supply),
            flags=[FlagOut.of(flag) for flag in done.flags],
        )


class TakenIn(BaseModel):
    anchor: Anchor | None = None
    amount: float | None = Field(default=None, gt=0)


class TakenOut(BaseModel):
    dose_taken_id: uuid.UUID
    line_id: uuid.UUID
    event_id: uuid.UUID
    anchor: str | None
    amount: float
    taken_at: datetime
    by_person_id: uuid.UUID

    @classmethod
    def of(cls, taken: DoseTaken) -> TakenOut:
        return cls(
            dose_taken_id=taken.id,
            line_id=taken.line_id,
            event_id=taken.event_id,
            anchor=taken.anchor,
            amount=taken.amount,
            taken_at=taken.taken_at,
            by_person_id=taken.by_person_id,
        )


class StoryOut(BaseModel):
    """The medication story as a card and a script: each section a few whole sentences,
    `lines` the whole thing in order for the voice."""

    line_id: uuid.UUID
    language: str
    name: str
    generic: str
    strength: str
    purpose: list[str]
    how_to_take: list[str]
    watch_out: list[str]
    avoid: list[str]
    if_forgotten: list[str]
    boundary: list[str]
    doctor_question: list[str]
    lines: list[str]

    @classmethod
    def of(cls, line_id: uuid.UUID, story: Story) -> StoryOut:
        return cls(
            line_id=line_id,
            language=story.language,
            name=story.name,
            generic=story.generic,
            strength=story.strength,
            purpose=story.purpose,
            how_to_take=story.how_to_take,
            watch_out=story.watch_out,
            avoid=story.avoid,
            if_forgotten=story.if_forgotten,
            boundary=story.boundary,
            doctor_question=story.doctor_question,
            lines=story.lines,
        )


class SlotOut(BaseModel):
    """One dose card at one moment of his day."""

    line_id: uuid.UUID
    generic: str
    anchor: str
    card: str
    taken: bool
    taken_label: str

    @classmethod
    def of(cls, slot: Slot) -> SlotOut:
        return cls(
            line_id=slot.line.id,
            generic=slot.line.generic,
            anchor=slot.anchor,
            card=slot.card,
            taken=slot.taken,
            taken_label=slot.taken_label,
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


# --- the visit loop (E05) ------------------------------------------------------------------------


class ProviderIn(BaseModel):
    """A doctor, clinic, hospital or pharmacy to add to the profile's own directory."""

    name: str = Field(min_length=1, max_length=120)
    kind: ProviderKind = ProviderKind.DOCTOR
    phone_e164: str | None = Field(default=None, pattern=PHONE)
    address: str | None = Field(default=None, max_length=300)


class ProviderOut(BaseModel):
    provider_id: uuid.UUID
    name: str
    kind: ProviderKind
    region: Region

    @classmethod
    def of(cls, provider: Provider) -> ProviderOut:
        return cls(
            provider_id=provider.id, name=provider.name, kind=provider.kind, region=provider.region
        )


class AppointmentIn(BaseModel):
    """Write down a visit a person has arranged, with the yes minted for exactly it."""

    provider_id: uuid.UUID
    scheduled_at: datetime
    purpose: str = Field(min_length=1, max_length=80)
    confirmation_id: uuid.UUID


class AppointmentOut(BaseModel):
    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    scheduled_at: datetime
    status: AppointmentStatus
    purpose: str
    confirmed_by_person_id: uuid.UUID

    @classmethod
    def of(cls, appointment: Appointment) -> AppointmentOut:
        return cls(
            appointment_id=appointment.id,
            provider_id=appointment.provider_id,
            scheduled_at=utc(appointment.scheduled_at),
            status=appointment.status,
            purpose=appointment.purpose,
            confirmed_by_person_id=appointment.confirmed_by_person_id,
        )


class BriefLineOut(BaseModel):
    """One line of the brief: which section, which template, the words, what it rests on."""

    section: str
    key: str
    text: str
    sources: list[str]


class BriefOut(BaseModel):
    """The pre-visit brief as rendered: every line passed the plain-words verifier, and the
    row names the State it was rendered from and the one it was measured against."""

    brief_id: uuid.UUID
    appointment_id: uuid.UUID
    language: str
    state_id: uuid.UUID
    since_state_id: uuid.UUID | None
    built_at: datetime
    lines: list[BriefLineOut]

    @classmethod
    def of(cls, brief: Brief) -> BriefOut:
        return cls(
            brief_id=brief.id,
            appointment_id=brief.appointment_id,
            language=brief.language,
            state_id=brief.state_id,
            since_state_id=brief.since_state_id,
            built_at=utc(brief.built_at),
            lines=[BriefLineOut(**line) for line in brief.lines],
        )


class QuestionOut(BaseModel):
    """One question to ask, with its source (E05-02: questions carry their source)."""

    question_id: uuid.UUID
    appointment_id: uuid.UUID
    text: str
    language: str
    source: str
    source_kind: str | None
    source_ids: list[str]
    priority: int
    added_by_person_id: uuid.UUID | None
    supersedes_id: uuid.UUID | None
    removed: bool
    state_id: uuid.UUID
    created_at: datetime

    @classmethod
    def of(cls, question: Question) -> QuestionOut:
        return cls(
            question_id=question.id,
            appointment_id=question.appointment_id,
            text=question.text,
            language=question.language,
            source=question.source.value,
            source_kind=question.source_kind,
            source_ids=list(question.source_ids),
            priority=question.priority,
            added_by_person_id=question.added_by_person_id,
            supersedes_id=question.supersedes_id,
            removed=question.removed,
            state_id=question.state_id,
            created_at=utc(question.created_at),
        )


class QuestionsOut(BaseModel):
    """The current questions for the caregiver, and the one card for him."""

    questions: list[QuestionOut]
    card: list[str]


class QuestionChangeIn(BaseModel):
    """Add a question (`text`), edit one (`text` and `question_id`) or remove one
    (`question_id` and `remove`), with the yes minted for exactly that."""

    text: str | None = Field(default=None, min_length=1, max_length=LINE_LENGTH)
    question_id: uuid.UUID | None = None
    remove: bool = False
    confirmation_id: uuid.UUID


class TranscriptIn(BaseModel):
    """A visit's transcript as the app sends it: the text in base64 and when the visit was.
    The text goes to the region's object store; nothing of it is kept on any row."""

    data: str = Field(min_length=1, max_length=MAX_TRANSCRIPT_BYTES * 4 // 3 + 4)
    captured_at: datetime | None = None

    @field_validator("data")
    @classmethod
    def _base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as not_base64:
            raise ValueError("data is base64") from not_base64
        return value

    def as_text(self) -> str:
        return base64.b64decode(self.data, validate=True).decode("utf-8", errors="replace")


class SummaryItemOut(BaseModel):
    """One thing heard: the line for him, the structure behind it, where in the transcript
    and how sure; once confirmed, what it became."""

    item_id: uuid.UUID
    position: int
    kind: str
    text: str
    payload: dict[str, Any]
    span: dict[str, int] | None
    confidence: float
    state: ItemState
    memo_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    fact_id: uuid.UUID | None
    flag_id: uuid.UUID | None

    @classmethod
    def of(cls, item: SummaryItem) -> SummaryItemOut:
        return cls(
            item_id=item.id,
            position=item.position,
            kind=item.kind.value,
            text=item.text,
            payload=item.payload,
            span=item.span,
            confidence=item.confidence,
            state=item.state,
            memo_id=item.memo_id,
            appointment_id=item.appointment_id,
            fact_id=item.fact_id,
            flag_id=item.flag_id,
        )


class SummaryOut(BaseModel):
    """The post-visit summary card: the transcript it was read from, whether a red-flag word
    was heard, the lines for him, and the items waiting for his yes."""

    summary_id: uuid.UUID
    appointment_id: uuid.UUID
    artifact_id: uuid.UUID
    language: str
    red_flag: bool
    state_id: uuid.UUID
    lines: list[str]
    items: list[SummaryItemOut]
    created_at: datetime
    confirmed_at: datetime | None
    confirmed_by_person_id: uuid.UUID | None

    @classmethod
    def of(cls, summary: VisitSummary, items: Sequence[SummaryItem]) -> SummaryOut:
        return cls(
            summary_id=summary.id,
            appointment_id=summary.appointment_id,
            artifact_id=summary.artifact_id,
            language=summary.language,
            red_flag=summary.red_flag,
            state_id=summary.state_id,
            lines=[str(line["text"]) for line in summary.lines],
            items=[SummaryItemOut.of(item) for item in items],
            created_at=utc(summary.created_at),
            confirmed_at=None if summary.confirmed_at is None else utc(summary.confirmed_at),
            confirmed_by_person_id=summary.confirmed_by_person_id,
        )


class SummaryConfirmBodyIn(BaseModel):
    """Close the summary: the decisions, and the yes minted for exactly them."""

    decisions: list[ItemDecisionIn]
    confirmation_id: uuid.UUID


class MemoOut(BaseModel):
    memo_id: uuid.UUID
    appointment_id: uuid.UUID | None
    kind: str
    source: str
    text: str
    language: str
    state_id: uuid.UUID
    created_at: datetime

    @classmethod
    def of(cls, memo: Memo) -> MemoOut:
        return cls(
            memo_id=memo.id,
            appointment_id=memo.appointment_id,
            kind=memo.kind.value,
            source=memo.source.value,
            text=memo.text,
            language=memo.language,
            state_id=memo.state_id,
            created_at=utc(memo.created_at),
        )


class SummaryConfirmedOut(BaseModel):
    """What the yes wrote: the card as it stands, the memos, the visits planned, the facts
    with the transcript as provenance, and the flags — never a medicine."""

    summary: SummaryOut
    memos: list[MemoOut]
    appointments: list[AppointmentOut]
    facts: list[FactOut]
    flag_ids: list[uuid.UUID]


class MemoCardOut(BaseModel):
    """The memo card: the current memos and the lines as he hears them."""

    memos: list[MemoOut]
    card: list[str]
