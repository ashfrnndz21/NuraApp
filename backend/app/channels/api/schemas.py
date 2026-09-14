"""The shapes on the wire. Every field here is one the app needs; none carries a secret."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime, time
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.channels.api.daily_schemas import ProposalConfirmIn, RoutineConfirmIn
from app.channels.api.voice_schemas import VoiceScriptOut
from app.channels.strings import lines
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
from app.family.documents import Backing, DocumentView
from app.family.grants import Grant, Helper, RolePreset
from app.family.models import (
    CardKind,
    DocumentTag,
    PushChannel,
    RosterSlot,
    ScheduledPush,
    Task,
    ThreadMessage,
)
from app.family.pushes import Preview
from app.family.roster import OnDuty
from app.family.thread import Digest, DigestEntry
from app.family.trail import TrailDay, TrailLine
from app.identity.doors import Claimable, Doors, Evidence
from app.identity.models import Person, Profile, Stewardship
from app.ingestion.consult import Notice as RecordingNotice
from app.ingestion.documents import MAX_PDF_BYTES
from app.ingestion.extract import DOCUMENT_HINTS, PHOTO_HINTS, DocumentKind
from app.ingestion.models import (
    ConsultRecording,
    ConsultSegment,
    DocumentSource,
    FieldState,
    NoteKind,
    ReviewCard,
    ReviewField,
)
from app.ingestion.notes import MAX_VOICE_BYTES, NoteView
from app.ingestion.photos import MAX_PHOTO_BYTES
from app.ingestion.review import Decision, Notice, notice_of
from app.keys.confirm import Confirmation
from app.keys.context import KeyContext, Standing
from app.keys.models import Key
from app.keys.privacy import Privacy
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
from app.memory.episodic import WITHHELD_ARTIFACT, WITHHELD_EVENT
from app.memory.models import (
    LABEL_LENGTH,
    Appointment,
    AppointmentStatus,
    ArtifactKind,
    ConfidenceState,
    Event,
    Fact,
)
from app.notes.models import NOTE_LENGTH, Note
from app.reasoning.visits.logistics import Logistics
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
    language: Literal["en", "ms", "zh"] | None = None
    """The language picked on the sign-in screen, which the code's message is sent in. Only
    a language Nura's messages are written in (`app.channels.strings.LANGUAGES`); anything
    else is a 422 at the door. Without one, the message is in his number's last known
    language (`app.identity.login.start_phone_login`)."""


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
    holder_display_name: str | None = Field(default=None, max_length=80)
    """The name the words use, as the owner calls the person: needed when he names them by
    phone (`HolderNeedsAName` without it). A number that is not an account yet keeps it until
    the person signs in and gives his own."""
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


class SharingPreviewIn(BaseModel):
    """The words the owner would agree to by `POST /consents/sharing`, for this person and
    these parts, before he agrees: the same fields, nothing kept."""

    holder_phone_e164: str | None = Field(default=None, pattern=PHONE)
    holder_person_id: uuid.UUID | None = None
    holder_display_name: str | None = Field(default=None, max_length=80)
    scopes: list[Scope] = Field(min_length=1)
    relationship: str | None = Field(default=None, min_length=1, max_length=80)
    language: str = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def _one_holder(self) -> SharingPreviewIn:
        if (self.holder_phone_e164 is None) == (self.holder_person_id is None):
            raise ValueError("name the holder by phone number or by person id, one of the two")
        return self


class SharingPreviewOut(BaseModel):
    """The lines he will read, one idea each, and the version to agree to them by."""

    wording_version: str
    language: str
    lines: list[str]


class WhatsAppConsentIn(BaseModel):
    """The owner agrees to Nura sending him his Today page on WhatsApp (E19): which words,
    in which language, captured how. Profile-wide, his own basis, and what every WhatsApp
    thread and every send on this profile rests on."""

    language: str = Field(min_length=2, max_length=16)
    captured_via: ConsentChannel
    wording_version: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[0-9A-Za-z._-]+$"
    )


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


class WordingOut(BaseModel):
    """Today's words for one consent purpose, one line per idea, as `GET /consent/wording`
    answers them; `version` is what `ConsentIn.wording_version` must carry."""

    purpose: ConsentPurpose
    version: str
    language: str
    region: Region
    lines: list[str]


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
    key_id: uuid.UUID | None = None
    """The key the caller reaches it with, or none for its owner: what a client binds any
    copy it keeps to, so a closed or narrowed key never shows what it once opened."""

    @classmethod
    def of(cls, profile: Profile, context: KeyContext) -> ProfileOut:
        return cls(
            key_id=context.key_id,
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
    captured_at: AwareDatetime

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
    episode_id: uuid.UUID | None = None
    """The open episode the card goes into once confirmed (E03-02), part of what is said yes
    to: its facts name the episode and its photo hangs off it."""


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
    scheduled_at: AwareDatetime
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


class KeyChangeConfirmIn(BaseModel):
    """A yes to narrowing one key to these parts and this window (E12-01). The draft is
    recomputed from the key, so a yes cannot be minted for anything wider than it opens."""

    subject: Literal[ConfirmSubject.KEY_CHANGE]
    key_id: uuid.UUID
    scopes: list[Scope] | None = None
    window: KeyWindow | None = None


class OnlyMeConfirmIn(BaseModel):
    """The owner's yes to keeping one part of his record to himself, or opening it again."""

    subject: Literal[ConfirmSubject.ONLY_ME]
    scope: Scope
    only_me: bool = True


class DriveConfirmIn(BaseModel):
    """The chief's yes to one person driving him to one visit (E05-03)."""

    subject: Literal[ConfirmSubject.DRIVE]
    appointment_id: uuid.UUID
    person_id: uuid.UUID


class InsurerConfirmIn(BaseModel):
    """A yes to his insurer on the emergency card exactly as typed (E13-01); no name takes it
    off the card. The typer's own yes: his, the steward's or his chief's."""

    subject: Literal[ConfirmSubject.INSURER]
    name: str | None = Field(default=None, min_length=1, max_length=120)
    policy_reference: str | None = Field(default=None, min_length=1, max_length=40)


class TaskDoneConfirmIn(BaseModel):
    """The doer's yes to her own task being done. Anyone else's finds no task."""

    subject: Literal[ConfirmSubject.TASK_DONE]
    task_id: uuid.UUID


class PushComposeIn(BaseModel):
    """What a chief composes: a template with its slots, or a memo of a few lines, in a
    language (his, unless another is asked for)."""

    template_id: str | None = Field(default=None, min_length=1, max_length=48)
    slots: dict[str, str] = Field(default_factory=dict)
    memo_lines: list[str] | None = Field(default=None, max_length=6)
    language: str | None = Field(default=None, min_length=2, max_length=16)

    @model_validator(mode="after")
    def _a_template_or_a_memo(self) -> PushComposeIn:
        if (self.template_id is None) == (self.memo_lines is None):
            raise ValueError("a message is a template or a memo, one of the two")
        return self


class PushScheduleIn(PushComposeIn):
    """When, on which channel, and until when a composed message is worth sending."""

    send_at: AwareDatetime
    channel: PushChannel = PushChannel.APP
    expires_at: AwareDatetime


class PushConfirmIn(PushScheduleIn):
    """A yes to exactly the previewed lines, then, there, until (E12-06)."""

    subject: Literal[ConfirmSubject.PUSH]


class StatusConfirmIn(BaseModel):
    """A yes to one step of a visit's status: this visit, to this status."""

    subject: Literal[ConfirmSubject.APPOINTMENT_STATUS]
    appointment_id: uuid.UUID
    status: AppointmentStatus


class AttachConfirmIn(BaseModel):
    """A yes to hanging this artefact off exactly one thing: an episode or a visit."""

    subject: Literal[ConfirmSubject.ATTACH]
    artifact_id: uuid.UUID
    episode_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_thing(self) -> AttachConfirmIn:
        if (self.episode_id is None) == (self.appointment_id is None):
            raise ValueError("a paper hangs off an episode or a visit, one of the two")
        return self


ConfirmIn = Annotated[
    ClaimConfirmIn
    | ReviewCardConfirmIn
    | MedicineConfirmIn
    | AppointmentConfirmIn
    | QuestionConfirmIn
    | SummaryConfirmIn
    | KeyChangeConfirmIn
    | OnlyMeConfirmIn
    | TaskDoneConfirmIn
    | PushConfirmIn
    | StatusConfirmIn
    | AttachConfirmIn
    | RoutineConfirmIn
    | ProposalConfirmIn
    | DriveConfirmIn
    | InsurerConfirmIn,
    Field(discriminator="subject"),
]
"""What `POST /profiles/{id}/confirmations` takes, by subject: the claim (E01), a review card
with its decisions (E02), a medicine label against the list (E04), a visit booking, a question
for a visit and a post-visit summary (E05), and the family's yeses (E12): narrowing a key,
marking a part only me, a task done, a message to him; the day's routine (E10) and a
visit a calendar proposed (E18); his insurer on the emergency card (E13-01)."""


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
    holder_display_name: str | None = None
    """Who holds it, by name, for the owner reading his own keys: the person to call."""

    @classmethod
    def of(cls, key: Key, holder_display_name: str | None = None) -> KeyOut:
        return cls(
            holder_display_name=holder_display_name,
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


WITHHELD_TARGET = "target"


class AuditOut(BaseModel):
    """One line of the trail: what was touched and by whom, never what it said."""

    entry_id: uuid.UUID
    at: datetime
    actor_person_id: uuid.UUID | None
    """None for Nura's own reach (channel `system`): the delivery engine acting for him."""
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
    withheld: list[str] = []
    """`target` when the line was written under a scope the reader's key does not hold: the
    line is there — who, when, what kind, under which scope — and the row's id is not."""

    @classmethod
    def of(cls, entry: AuditEntry, withheld: Sequence[str] = ()) -> AuditOut:
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
            target_id=None if WITHHELD_TARGET in withheld else entry.target_id,
            rows=entry.rows,
            outcome=entry.outcome,
            refused_because=entry.refused_because,
            shared_with_person_id=entry.shared_with_person_id,
            shared_with_label=entry.shared_with_label,
            withheld=list(withheld),
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
    dispensed_at: AwareDatetime | None = None
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
    due_now: bool = False
    missed: bool = False
    source: str = ""
    """Where the line came from and on which day, in his words: the card's source line."""
    withheld: list[str] = []
    """The source the reader's key may not read — `artifact` (the label photo is the
    record's), `event` — by name, its id left out."""

    @classmethod
    def of(cls, view: LineView, withheld: Sequence[str] = ()) -> LineOut:
        return cls(
            **cls._columns(view.line, withheld),
            name=view.name,
            count=CountOut.of(view.count),
            flags=[FlaggedOut.of(flag) for flag in view.flags],
            duplicate_of=view.duplicate_of,
            doctor_question=view.doctor_question,
            taken_label=view.taken_label,
            due_now=view.due_now,
            missed=view.missed,
            source=view.source,
            withheld=list(withheld),
        )

    @classmethod
    def history_of(cls, line: MedicationLine, withheld: Sequence[str] = ()) -> LineOut:
        return cls(
            **cls._columns(line, withheld),
            name=line.generic,
            count=None,
            flags=[],
            duplicate_of=[],
            doctor_question=[],
            taken_label=None,
            withheld=list(withheld),
        )

    @staticmethod
    def _columns(line: MedicationLine, withheld: Sequence[str] = ()) -> dict[str, Any]:
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
            "source_artifact_id": (
                None if WITHHELD_ARTIFACT in withheld else line.source_artifact_id
            ),
            "source_event_id": None if WITHHELD_EVENT in withheld else line.source_event_id,
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
    due_now: bool
    """Its window is open now and it is not yet tapped: the one thing to do."""
    missed: bool
    """Its window has closed untapped; `if_forgotten` says what the story says to do."""
    if_forgotten: list[str]
    source: str
    """Where the medicine came from and on which day: the card's source line."""

    @classmethod
    def of(cls, slot: Slot) -> SlotOut:
        return cls(
            line_id=slot.line.id,
            generic=slot.line.generic,
            anchor=slot.anchor,
            card=slot.card,
            taken=slot.taken,
            taken_label=slot.taken_label,
            due_now=slot.due_now,
            missed=slot.missed,
            if_forgotten=slot.if_forgotten,
            source=slot.source,
        )


class ProudOut(BaseModel):
    """The proud number (`GET /profiles/{id}/proud`): days with a tablet taken, and when it
    was counted. The client shows this number and nothing it worked out itself."""

    days: int
    as_of: datetime


# --- readings and State ------------------------------------------------------------------


class ReadingIn(BaseModel):
    """A blood pressure the person typed in: the two numbers, and when it was taken.

    Thin on purpose: the real capture — photo of the book, device, review card with
    confidence per field — is E02. This is what checkpoint 3 needs: one reading, as one
    event with one fact resting on it, so that State has something to recompute from.
    """

    systolic: int = Field(ge=40, le=300)
    diastolic: int = Field(ge=20, le=200)
    taken_at: AwareDatetime | None = None
    episode_id: uuid.UUID | None = None
    """The open episode this reading was taken during, if any (E03-02)."""


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
    narrow to check. `state_id` is what every card names. `boundary` is the line the
    posture is shown under (E16-01, `app.safety.boundary`): what Nura did, that it is not
    a doctor's advice, and whom to ask — in the profile's language, or the one asked for.
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
    boundary: str

    @classmethod
    def of(cls, view: StateView, *, boundary: str) -> StateOut:
        return cls(
            boundary=boundary,
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


def _is_base64(value: str) -> str:
    try:
        base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as not_base64:
        raise ValueError("data is base64") from not_base64
    return value


class ScreenPhotoIn(BaseModel):
    """A photo of a machine's screen — a blood pressure machine, a glucometer, a scale — as
    the app sends it (E02-08): the bytes in base64, what kind of image, when it was taken."""

    data: str = Field(min_length=1, max_length=MAX_PHOTO_BYTES * 4 // 3 + 4)
    content_type: str = Field(min_length=1, max_length=128)
    captured_at: AwareDatetime

    _base64 = field_validator("data")(classmethod(lambda cls, value: _is_base64(value)))

    def as_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


class PhotoIn(ScreenPhotoIn):
    """A photo of a page, as the app sends it: the bytes in base64, what kind of image, and
    when it was taken. The bytes go to the region's object store; nothing of them is kept
    on any row. `document_kind` is what the person says the page is — a clinic slip, a
    prescription written by hand (E02-02) — passed to the extractor as a hint, never taken
    as the answer."""

    document_kind: DocumentKind | None = None

    @field_validator("document_kind")
    @classmethod
    def _a_paper(cls, value: DocumentKind | None) -> DocumentKind | None:
        if value is not None and value not in PHOTO_HINTS:
            raise ValueError(f"a photo of a page may be offered as one of {sorted(PHOTO_HINTS)}")
        return value


class ImportIn(BaseModel):
    """A PDF from a hospital portal, an email or another app's share sheet (E02-03): the
    bytes in base64, their content type, when it came, where from, and — if the person says
    — what kind of paper it is, as a hint to the extractor."""

    data: str = Field(min_length=1, max_length=MAX_PDF_BYTES * 4 // 3 + 4)
    content_type: str = Field(min_length=1, max_length=128)
    captured_at: AwareDatetime
    source: DocumentSource
    document_kind: DocumentKind | None = None

    _base64 = field_validator("data")(classmethod(lambda cls, value: _is_base64(value)))

    @field_validator("document_kind")
    @classmethod
    def _a_document(cls, value: DocumentKind | None) -> DocumentKind | None:
        if value is not None and value not in DOCUMENT_HINTS:
            raise ValueError(f"a PDF may be offered as one of {sorted(DOCUMENT_HINTS)}")
        return value

    def as_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


class TypedIn(BaseModel):
    """The value a person typed into one field of an open card: what the paper says."""

    value: Any

    @field_validator("value")
    @classmethod
    def _something(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("a typed value says what the paper says")
        return value


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
    unreadable: bool
    """Nura saw this field and could not read it: `value` is null and `prompt` asks for it."""
    prompt: list[str] | None
    """The lines the card shows beside a field nobody has typed yet (E02-02)."""
    page: int | None
    """For a PDF of several pages, the page the field was read on, counting from 1."""
    span: dict[str, float | int] | None
    state: FieldState
    corrected_value: Any | None
    corrected_by_person_id: uuid.UUID | None
    """Who typed or corrected the value kept, where it is not what was read."""
    fact_id: uuid.UUID | None

    @classmethod
    def of(cls, field: ReviewField, *, language: str) -> ReviewFieldOut:
        waiting = (
            field.unreadable
            and field.corrected_value is None
            and field.state is FieldState.PROPOSED
        )
        return cls(
            unreadable=field.unreadable,
            prompt=list(lines("could_not_read", language)) if waiting else None,
            page=field.page,
            corrected_by_person_id=field.corrected_by_person_id,
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


NOTICE_LINES: dict[Notice, str] = {
    Notice.NOT_A_HEALTH_PAPER: "not_a_health_paper",
    Notice.NOT_A_MACHINE_SCREEN: "not_a_machine_screen",
}
"""The key in `app.channels.strings.TEXT` of the lines each notice is said in."""


class ReviewCardOut(BaseModel):
    """A review card: the photo or PDF it came from, what kind of paper and its date, what
    it was offered as and where it came from, whether the label rule guards the drug it
    names, a notice where the page is not what it was offered as, its fields, and — once
    confirmed — by whom."""

    card_id: uuid.UUID
    profile_id: uuid.UUID
    artifact_id: uuid.UUID
    document_kind: DocumentKind
    document_date: date | None
    asked_as: DocumentKind | None
    source: DocumentSource | None
    notice: list[str] | None
    high_risk_class: str | None
    created_at: datetime
    confirmed_at: datetime | None
    confirmed_by_person_id: uuid.UUID | None
    fields: list[ReviewFieldOut]

    @classmethod
    def of(cls, card: ReviewCard, fields: Sequence[ReviewField], *, language: str) -> ReviewCardOut:
        """The card, its notice and its fields' prompts in `language`: his settings' (the
        channel reads them, `app.channels.api.capture.capture_language`)."""
        return cls(
            card_id=card.id,
            profile_id=card.profile_id,
            artifact_id=card.artifact_id,
            document_kind=card.document_kind,
            document_date=card.document_date,
            asked_as=card.asked_as,
            source=card.source,
            notice=_notice_lines(card, language),
            high_risk_class=card.high_risk_class,
            created_at=utc(card.created_at),
            confirmed_at=None if card.confirmed_at is None else utc(card.confirmed_at),
            confirmed_by_person_id=card.confirmed_by_person_id,
            fields=[ReviewFieldOut.of(field, language=language) for field in fields],
        )


def _notice_lines(card: ReviewCard, language: str) -> list[str] | None:
    notice = notice_of(card)
    return None if notice is None else list(lines(NOTICE_LINES[notice], language))


class ReviewConfirmIn(BaseModel):
    """Close the card: the decisions, and the yes minted for exactly them."""

    decisions: list[DecisionIn]
    confirmation_id: uuid.UUID
    episode_id: uuid.UUID | None = None
    """The open episode the yes named, if it named one (E03-02)."""


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
    withheld: list[str] = []
    """What the fact cites that the reader's key may not follow, by name — `artifact`,
    `event` — its id left out (`app.memory.episodic.withheld_provenance`)."""

    @classmethod
    def of(cls, fact: Fact, withheld: Sequence[str] = ()) -> FactOut:
        return cls(
            fact_id=fact.id,
            subject=fact.subject,
            attribute=fact.attribute,
            value=fact.value,
            unit=fact.unit,
            confidence=fact.confidence,
            confidence_state=fact.confidence_state,
            confirmed_by_person_id=fact.confirmed_by_person_id,
            artifact_id=None if WITHHELD_ARTIFACT in withheld else fact.artifact_id,
            event_id=None if WITHHELD_EVENT in withheld else fact.event_id,
            withheld=list(withheld),
            valid_from=utc(fact.valid_from),
            valid_to=None if fact.valid_to is None else utc(fact.valid_to),
            asserted_at=utc(fact.asserted_at),
        )


class ReviewConfirmedOut(BaseModel):
    """What closing the card did: the card as it stands, the facts it wrote, and the event
    it recorded — the reading off a machine's screen, the discharge a hospital letter
    records, the visit of a clinic slip — which those facts name."""

    card: ReviewCardOut
    facts: list[FactOut]
    event_id: uuid.UUID | None = None


# --- capture: notes on an event (E02-06) -------------------------------------------------


class EventNoteIn(BaseModel):
    """A note on one event: a voice note or a scribble, its bytes in base64, their content
    type, when it was made, whether it is private (the notes scope) or shared with whoever
    holds the record, and an optional label of one short line."""

    kind: NoteKind
    data: str = Field(min_length=1, max_length=MAX_VOICE_BYTES * 4 // 3 + 4)
    content_type: str = Field(min_length=1, max_length=128)
    captured_at: AwareDatetime
    private: bool = False
    label: str | None = Field(default=None, max_length=LABEL_LENGTH * 4)

    _base64 = field_validator("data")(classmethod(lambda cls, value: _is_base64(value)))

    def as_bytes(self) -> bytes:
        return base64.b64decode(self.data, validate=True)


class TranscriptOut(BaseModel):
    """The words the transcriber heard, how sure it was, in which language. Never a fact."""

    text: str
    confidence: float
    language: str | None


class EventNoteOut(BaseModel):
    """A note as recall shows it: what it is, whose eyes it is for, its label, the artefact
    to hear or see again (`…/notes/{note_id}/content`), and the words heard in a voice note
    — or, for a voice note nothing was heard in, the lines that say so."""

    note_id: uuid.UUID
    event_id: uuid.UUID
    kind: NoteKind
    private: bool
    label: str | None
    artifact_id: uuid.UUID
    content_type: str
    transcript: TranscriptOut | None
    notice: list[str] | None
    written_by_person_id: uuid.UUID
    written_at: datetime

    @classmethod
    def of(cls, view: NoteView, *, language: str) -> EventNoteOut:
        note, heard = view.note, view.transcript
        unheard = note.kind is NoteKind.VOICE and heard is None
        return cls(
            note_id=note.id,
            event_id=note.event_id,
            kind=note.kind,
            private=note.private,
            label=note.label,
            artifact_id=note.artifact_id,
            content_type=view.artifact.content_type,
            transcript=None
            if heard is None
            else TranscriptOut(
                text=heard.text, confidence=heard.confidence, language=heard.language
            ),
            notice=list(lines("could_not_hear", language)) if unheard else None,
            written_by_person_id=note.written_by_person_id,
            written_at=utc(note.written_at),
        )


# --- the visit loop (E05) ------------------------------------------------------------------------


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
    """One line of the brief: which section, which template, the words as printed and as
    spoken (the bracketed chemical name is not read aloud), what it rests on."""

    section: str
    key: str
    text: str
    spoken: str
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
    boundary: str | None
    """The boundary line the brief ends on (E16-01), whole, as the row records it."""
    voice_script: VoiceScriptOut
    """The brief as it is said (E22-03): each line's spoken words, a pause after each, a longer
    one before the boundary."""

    @classmethod
    def of(cls, brief: Brief) -> BriefOut:
        lines = [BriefLineOut(**{"spoken": line["text"], **line}) for line in brief.lines]
        return cls(
            brief_id=brief.id,
            appointment_id=brief.appointment_id,
            language=brief.language,
            state_id=brief.state_id,
            since_state_id=brief.since_state_id,
            built_at=utc(brief.built_at),
            lines=lines,
            boundary=brief.boundary,
            voice_script=VoiceScriptOut.of(
                [line.spoken for line in lines], brief.language, brief.boundary
            ),
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
    """The current questions for the caregiver, and the one card for him — as printed, and
    as spoken."""

    questions: list[QuestionOut]
    card: list[str]
    spoken_card: list[str]


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
    captured_at: AwareDatetime | None = None

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
    clip_start_s: float | None = None
    clip_end_s: float | None = None
    """Where in the consult recording this was said, in seconds (E02-05); None when typed."""

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
            clip_start_s=item.clip_start_s,
            clip_end_s=item.clip_end_s,
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
    spoken: list[str]
    boundary: str | None
    """The boundary line the card ends on (E16-01), whole, as the row records it."""
    voice_script: VoiceScriptOut
    """`spoken` as it is said (E22-03)."""
    items: list[SummaryItemOut]
    created_at: datetime
    confirmed_at: datetime | None
    confirmed_by_person_id: uuid.UUID | None
    recording_artifact_id: uuid.UUID | None = None
    """The consult recording the transcript was heard from, whose clips the items carry."""

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
            spoken=[str(line.get("spoken", line["text"])) for line in summary.lines],
            boundary=summary.boundary,
            voice_script=VoiceScriptOut.of(
                [str(line.get("spoken", line["text"])) for line in summary.lines],
                summary.language,
                summary.boundary,
            ),
            items=[SummaryItemOut.of(item) for item in items],
            created_at=utc(summary.created_at),
            confirmed_at=None if summary.confirmed_at is None else utc(summary.confirmed_at),
            confirmed_by_person_id=summary.confirmed_by_person_id,
            recording_artifact_id=summary.recording_artifact_id,
        )


# --- the visit day (E05-03, E05-04, E02-05, E03-05) ----------------------------------------------


class LogisticsLineOut(BaseModel):
    """One line of the logistics card: its part (when, place, note, driver, bring), its
    template, the words as printed and as spoken."""

    section: str
    key: str
    text: str
    spoken: str


class PlaceNoteOut(BaseModel):
    """The chief's own note about the place, as she wrote it, under "Mei's note"."""

    note_id: uuid.UUID
    label: str
    text: str
    by_person_id: uuid.UUID
    by_name: str
    written_at: datetime


class DriverOut(BaseModel):
    """Who drives him: a task given (`assigned`), the roster's person on duty then waiting for
    the chief's yes (`suggested`, `needs_yes`), nobody, or not read by this key (`withheld`)."""

    status: str
    person_id: uuid.UUID | None
    name: str | None
    task_id: uuid.UUID | None
    needs_yes: bool
    can_say_yes: bool


class LogisticsOut(BaseModel):
    """The logistics card for one visit (E05-03), composed from the record and State."""

    appointment_id: uuid.UUID
    provider_id: uuid.UUID
    doctor: str
    language: str
    scheduled_at: datetime
    state_id: uuid.UUID
    place: str | None
    note: PlaceNoteOut | None
    driver: DriverOut
    lines: list[LogisticsLineOut]
    spoken: list[str]
    withheld: list[Scope]

    @classmethod
    def of(cls, found: Logistics) -> LogisticsOut:
        note = found.note
        return cls(
            appointment_id=found.appointment_id,
            provider_id=found.provider_id,
            doctor=found.doctor,
            language=found.language,
            scheduled_at=utc(found.scheduled_at),
            state_id=found.state_id,
            place=found.place,
            note=None
            if note is None
            else PlaceNoteOut(
                note_id=note.note_id,
                label=note.label,
                text=note.text,
                by_person_id=note.by_person_id,
                by_name=note.by_name,
                written_at=utc(note.written_at),
            ),
            driver=DriverOut(
                status=found.driver.status.value,
                person_id=found.driver.person_id,
                name=found.driver.name,
                task_id=found.driver.task_id,
                needs_yes=found.driver.needs_yes,
                can_say_yes=found.driver.can_say_yes,
            ),
            lines=[LogisticsLineOut(**line.as_json()) for line in found.lines],
            spoken=found.spoken,
            withheld=list(found.withheld),
        )


class DriverIn(BaseModel):
    """The chief's yes, spent: this person drives him to this visit."""

    person_id: uuid.UUID
    confirmation_id: uuid.UUID


class NoticeOut(BaseModel):
    """What the Start button shows and speaks before the microphone opens (E16-02): the
    notice in his language to the doctor by name, the printed card for the desk, and what he
    is told on a no. Handed back only once the gate has passed."""

    appointment_id: uuid.UUID
    doctor: str
    language: str
    spoken: list[str]
    printed: list[str]
    when_no: list[str]
    consent_id: uuid.UUID

    @classmethod
    def of(cls, notice: RecordingNotice) -> NoticeOut:
        return cls(
            appointment_id=notice.appointment_id,
            doctor=notice.doctor,
            language=notice.language,
            spoken=list(notice.spoken),
            printed=list(notice.printed),
            when_no=list(notice.when_no),
            consent_id=notice.consent_id,
        )


class SegmentOut(BaseModel):
    """One stretch of a recording: who spoke, when in the audio, where in the transcript."""

    segment_id: uuid.UUID
    position: int
    speaker: str
    start_s: float
    end_s: float
    char_start: int
    char_end: int

    @classmethod
    def of(cls, segment: ConsultSegment) -> SegmentOut:
        return cls(
            segment_id=segment.id,
            position=segment.position,
            speaker=segment.speaker.value,
            start_s=segment.start_s,
            end_s=segment.end_s,
            char_start=segment.char_start,
            char_end=segment.char_end,
        )


class RecordingOut(BaseModel):
    """One recording of a visit as kept: the artefacts, the consent it rested on, how long,
    whether it was heard, and who spoke when. No words."""

    recording_id: uuid.UUID
    appointment_id: uuid.UUID
    artifact_id: uuid.UUID
    transcript_artifact_id: uuid.UUID | None
    consent_id: uuid.UUID
    duration_s: float
    started_at: datetime
    notice_language: str
    doctor_named: bool
    heard: bool
    heard_confidence: float | None
    recorded_by_person_id: uuid.UUID
    segments: list[SegmentOut]

    @classmethod
    def of(cls, recording: ConsultRecording, segments: Sequence[ConsultSegment]) -> RecordingOut:
        return cls(
            recording_id=recording.id,
            appointment_id=recording.appointment_id,
            artifact_id=recording.artifact_id,
            transcript_artifact_id=recording.transcript_artifact_id,
            consent_id=recording.consent_id,
            duration_s=recording.duration_s,
            started_at=utc(recording.started_at),
            notice_language=recording.notice_language,
            doctor_named=recording.doctor_named,
            heard=recording.transcript_artifact_id is not None,
            heard_confidence=recording.heard_confidence,
            recorded_by_person_id=recording.recorded_by_person_id,
            segments=[SegmentOut.of(one) for one in segments],
        )


class ConsultOut(BaseModel):
    """What one upload kept, and the post-visit card it ended in — or why there is no card
    (`summary_refused`, the refusal's name), with the recording kept either way."""

    recording: RecordingOut
    summary: SummaryOut | None
    summary_refused: str | None


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
    """The memo card: the current memos, the lines as printed, and as he hears them."""

    memos: list[MemoOut]
    card: list[str]
    spoken_card: list[str]


# --- family (E12) --------------------------------------------------------------------------


class KeyNarrowIn(BaseModel):
    """Narrow a key: fewer parts, a shorter window, or both, with the yes minted for it."""

    scopes: list[Scope] | None = None
    window: KeyWindow | None = None
    confirmation_id: uuid.UUID


class RolePresetOut(BaseModel):
    role: KeyRole
    scopes: list[Scope]
    window: KeyWindow
    lines: list[str]

    @classmethod
    def of(cls, preset: RolePreset) -> RolePresetOut:
        return cls(
            role=preset.role,
            scopes=sorted(preset.scopes),
            window=preset.window,
            lines=preset.lines,
        )


class GrantOut(BaseModel):
    """One live key as the chief manages it, with the lines the family screen shows."""

    key_id: uuid.UUID
    holder_person_id: uuid.UUID
    holder_name: str
    role: KeyRole
    scopes: list[Scope]
    window: KeyWindow | None
    granted_at: datetime
    expires_at: datetime | None
    lines: list[str]

    @classmethod
    def of(cls, grant: Grant) -> GrantOut:
        return cls(
            key_id=grant.key.id,
            holder_person_id=grant.key.holder_person_id,
            holder_name=grant.holder_name,
            role=grant.role,
            scopes=sorted(grant.scopes),
            window=grant.window,
            granted_at=utc(grant.key.granted_at),
            expires_at=grant.expires_at,
            lines=grant.lines,
        )


class HelperOut(BaseModel):
    key_id: uuid.UUID
    person_id: uuid.UUID
    name: str
    scopes: list[Scope]
    lines: list[str]

    @classmethod
    def of(cls, helper: Helper) -> HelperOut:
        return cls(
            key_id=helper.key_id,
            person_id=helper.person_id,
            name=helper.name,
            scopes=sorted(helper.scopes),
            lines=helper.lines,
        )


class HelpersOut(BaseModel):
    helpers: list[HelperOut]
    lines: list[str]
    """What to show when there is no helper; empty otherwise."""


class ThreadMessageIn(BaseModel):
    """A short message to the family: the one free text here, at most 280 characters."""

    text: str = Field(min_length=1, max_length=280)


class ThreadCardIn(BaseModel):
    """A card into the thread: which kind, and for a task card which task."""

    card_kind: CardKind
    task_id: uuid.UUID | None = None


ThreadPostIn = ThreadMessageIn | ThreadCardIn


class ThreadEntryOut(BaseModel):
    message_id: uuid.UUID
    author_person_id: uuid.UUID
    posted_at: datetime
    text: str | None
    card_kind: CardKind | None
    state_id: uuid.UUID | None
    task_id: uuid.UUID | None

    @classmethod
    def of(cls, entry: ThreadMessage) -> ThreadEntryOut:
        return cls(
            message_id=entry.id,
            author_person_id=entry.author_person_id,
            posted_at=utc(entry.posted_at),
            text=entry.text,
            card_kind=entry.card_kind,
            state_id=entry.state_id,
            task_id=entry.task_id,
        )


class ThreadPageOut(BaseModel):
    """A page of the thread, newest first, and the cursor for the page before it."""

    entries: list[ThreadEntryOut]
    next_cursor: datetime | None


class DigestEntryOut(BaseModel):
    kind: str
    at: datetime
    lines: list[str]
    text: str | None
    message_id: uuid.UUID | None

    @classmethod
    def of(cls, entry: DigestEntry) -> DigestEntryOut:
        return cls(
            kind=entry.kind,
            at=entry.at,
            lines=entry.lines,
            text=entry.text,
            message_id=entry.message_id,
        )


class DigestOut(BaseModel):
    language: str
    since: datetime
    headline: str
    entries: list[DigestEntryOut]
    on_duty: list[str]
    lines: list[str]

    @classmethod
    def of(cls, digest: Digest) -> DigestOut:
        return cls(
            language=digest.language,
            since=digest.since,
            headline=digest.headline,
            entries=[DigestEntryOut.of(entry) for entry in digest.entries],
            on_duty=digest.on_duty,
            lines=digest.lines,
        )


class RosterSlotIn(BaseModel):
    """Put one person on duty: weekdays (0 Monday to 6 Sunday) or a date range, between two
    times on the patient's clock. An end at or before the start runs past midnight."""

    person_id: uuid.UUID
    role: KeyRole
    weekdays: list[int] | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    from_time: time
    to_time: time


class RosterSlotOut(BaseModel):
    slot_id: uuid.UUID
    person_id: uuid.UUID
    role: KeyRole
    weekdays: list[int] | None
    starts_on: date | None
    ends_on: date | None
    from_time: time
    to_time: time
    added_by_person_id: uuid.UUID
    added_at: datetime
    ended_at: datetime | None

    @classmethod
    def of(cls, slot: RosterSlot) -> RosterSlotOut:
        return cls(
            slot_id=slot.id,
            person_id=slot.person_id,
            role=slot.role,
            weekdays=slot.weekdays,
            starts_on=slot.starts_on,
            ends_on=slot.ends_on,
            from_time=slot.from_time,
            to_time=slot.to_time,
            added_by_person_id=slot.added_by_person_id,
            added_at=utc(slot.added_at),
            ended_at=None if slot.ended_at is None else utc(slot.ended_at),
        )


class OnDutyOut(BaseModel):
    slot_id: uuid.UUID
    person_id: uuid.UUID
    role: KeyRole

    @classmethod
    def of(cls, duty: OnDuty) -> OnDutyOut:
        return cls(slot_id=duty.slot_id, person_id=duty.person_id, role=duty.role)


class TaskIn(BaseModel):
    """One thing for one person to do: a label in plain words, who, by when."""

    what: str = Field(min_length=1, max_length=80)
    assigned_person_id: uuid.UUID
    due_at: AwareDatetime | None = None


class TaskDoneIn(BaseModel):
    confirmation_id: uuid.UUID


class TaskOut(BaseModel):
    task_id: uuid.UUID
    what: str
    assigned_person_id: uuid.UUID
    due_at: datetime | None
    created_by_person_id: uuid.UUID
    created_at: datetime
    done_at: datetime | None
    done_by_person_id: uuid.UUID | None
    appointment_id: uuid.UUID | None = None
    errand: str | None = None
    """`drive` for "drive Pa to Dr Tan", a visit's logistics (E05-03); else none."""

    @classmethod
    def of(cls, task: Task) -> TaskOut:
        return cls(
            task_id=task.id,
            what=task.what,
            assigned_person_id=task.assigned_person_id,
            due_at=None if task.due_at is None else utc(task.due_at),
            created_by_person_id=task.created_by_person_id,
            created_at=utc(task.created_at),
            done_at=None if task.done_at is None else utc(task.done_at),
            done_by_person_id=task.done_by_person_id,
            appointment_id=task.appointment_id,
            errand=None if task.errand is None else task.errand.value,
        )


class TrailLineOut(BaseModel):
    at: datetime
    who: str
    sentences: list[str]
    outcome: Outcome
    detail: list[str] = []
    """For the chief, under Nura's folded line: what it checked, and how often."""

    @classmethod
    def of(cls, line: TrailLine) -> TrailLineOut:
        return cls(
            at=line.at,
            who=line.who,
            sentences=line.sentences,
            outcome=line.outcome,
            detail=list(line.detail),
        )


class TrailDayOut(BaseModel):
    """One day of the trail as he reads it: the day in words, and what happened on it."""

    day: date
    day_words: str
    lines: list[TrailLineOut]

    @classmethod
    def of(cls, day: TrailDay) -> TrailDayOut:
        return cls(
            day=day.day, day_words=day.day_words, lines=[TrailLineOut.of(l) for l in day.lines]
        )


class OnlyMeIn(BaseModel):
    """Mark one part of the record only me, with the owner's yes for exactly that."""

    scope: Scope
    confirmation_id: uuid.UUID


class LiftOnlyMeIn(BaseModel):
    confirmation_id: uuid.UUID


class PrivacyOut(BaseModel):
    privacy_id: uuid.UUID
    scope: Scope
    marked_by_person_id: uuid.UUID
    marked_at: datetime
    lifted_at: datetime | None
    lifted_by_person_id: uuid.UUID | None

    @classmethod
    def of(cls, row: Privacy) -> PrivacyOut:
        return cls(
            privacy_id=row.id,
            scope=row.scope,
            marked_by_person_id=row.marked_by_person_id,
            marked_at=utc(row.marked_at),
            lifted_at=None if row.lifted_at is None else utc(row.lifted_at),
            lifted_by_person_id=row.lifted_by_person_id,
        )


class PushPreviewOut(BaseModel):
    """Exactly what he will see, and the verifier's notes on it."""

    language: str
    template_id: str | None
    lines: list[str]
    notes: list[str]

    @classmethod
    def of(cls, preview: Preview) -> PushPreviewOut:
        return cls(
            language=preview.language,
            template_id=preview.template_id,
            lines=preview.lines,
            notes=preview.notes,
        )


class PushIn(PushScheduleIn):
    """Schedule the previewed message with the yes minted for exactly it."""

    confirmation_id: uuid.UUID


class PushOut(BaseModel):
    push_id: uuid.UUID
    state_id: uuid.UUID
    composed_by_person_id: uuid.UUID
    composed_at: datetime
    language: str
    template_id: str | None
    lines: list[str]
    send_at: datetime
    channel: PushChannel
    expires_at: datetime

    @classmethod
    def of(cls, push: ScheduledPush) -> PushOut:
        return cls(
            push_id=push.id,
            state_id=push.state_id,
            composed_by_person_id=push.composed_by_person_id,
            composed_at=utc(push.composed_at),
            language=push.language,
            template_id=push.template_id,
            lines=push.lines,
            send_at=utc(push.send_at),
            channel=push.via_channel,
            expires_at=utc(push.expires_at),
        )


class DocumentIn(BaseModel):
    """A document as the app sends it: the bytes in base64, a PDF or a photo, when it was
    captured, and what kind of paper it is."""

    data: str = Field(min_length=1, max_length=MAX_PHOTO_BYTES * 4 // 3 + 4)
    content_type: str = Field(min_length=1, max_length=128)
    captured_at: AwareDatetime
    tag: DocumentTag

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


class BackingOut(BaseModel):
    kind: str
    id: uuid.UUID
    basis: ConsentBasis
    purpose: str | None
    active: bool

    @classmethod
    def of(cls, backing: Backing) -> BackingOut:
        return cls(
            kind=backing.kind,
            id=backing.id,
            basis=backing.basis,
            purpose=backing.purpose,
            active=backing.active,
        )


class DocumentOut(BaseModel):
    """A paper kept by reference: the artefact, its tag, and what it backs."""

    artifact_id: uuid.UUID
    kind: ArtifactKind
    content_type: str
    sha256: str
    captured_at: datetime
    tag: DocumentTag | None
    added_by_person_id: uuid.UUID | None
    added_at: datetime | None
    backs: list[BackingOut]

    @classmethod
    def of(cls, view: DocumentView) -> DocumentOut:
        return cls(
            artifact_id=view.artifact.id,
            kind=view.artifact.kind,
            content_type=view.artifact.content_type,
            sha256=view.artifact.sha256,
            captured_at=utc(view.artifact.captured_at),
            tag=view.tag,
            added_by_person_id=view.added_by_person_id,
            added_at=view.added_at,
            backs=[BackingOut.of(backing) for backing in view.backs],
        )
