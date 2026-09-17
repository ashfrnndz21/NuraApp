"""The Consent: one agreement, to one purpose, in one version of the words, by one person.

A consent is never edited. Withdrawing it marks `revoked_at` and leaves the row, so the
record can show that it was once given and when it stopped. New wording is a new row, so
the record can show which words were agreed to each time — and the words themselves are
kept on the row, so the record says what was read even if the catalogue is ever wrong.
The row holds no health content: it says what was agreed to, never what the graph says.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, as_utc, enum_column, monotonic, utcnow


class ConsentPurpose(StrEnum):
    """What a consent is for. One row covers one of these and nothing wider.

    Research is not here on purpose: nothing trains on user data and nothing is studied
    from it, so there is no such consent to ask for.
    """

    HOLD_HEALTH_RECORD = "hold_health_record"
    # Stored as "share_with_family" (the value shipped in 0003); named for what it is, one
    # named person — a daughter, a helper, a clinic, a neighbour — let in to named parts.
    SHARE_WITH_PERSON = "share_with_family"
    RECORDING = "recording"
    WHATSAPP = "whatsapp"
    CALENDAR = "calendar"
    """A read-only connector to his calendar (E18-02): events that look like visits become
    proposals for a person to accept. One consent per connector kind, for the profile."""


PER_HOLDER = frozenset({ConsentPurpose.SHARE_WITH_PERSON})
"""Purposes agreed to one person at a time: the row names who may hold a key and to what.
The rest are agreed to for the profile as a whole."""


class ConsentChannel(StrEnum):
    """How the agreement was captured, so the record can say so."""

    APP = "app"
    WHATSAPP = "whatsapp"
    PAPER = "paper"
    VERBAL_WITNESSED = "verbal_witnessed"


class ConsentBasis(StrEnum):
    """What entitles the person giving it to give it.

    `OWNER` is the patient agreeing for himself. The others are the declared basis on which
    someone else agrees for him, and each has something behind it: the lasting power of
    attorney or the doctor's letter as an artefact on the profile, or his own spoken
    agreement with the person who heard it named and, where there is one, the recording.

    `PATIENT_ASKED` is narrower than the rest: the patient has a phone and asked for the
    record to be set up, and the proof is his claim, still to come. It carries a steward's
    agreement to Nura keeping the record until then (E01) and nothing else — not a key for
    anyone, not a recording, not sending: those wait for his OK or for a document.
    """

    OWNER = "owner"
    LPA = "lpa"
    MEDICAL_LETTER = "medical_letter"
    VERBAL_RECORDED = "verbal_recorded"
    PATIENT_ASKED = "patient_asked"


PROXY_BASES = frozenset(ConsentBasis) - {ConsentBasis.OWNER, ConsentBasis.PATIENT_ASKED}
"""The bases on which someone other than the owner may agree on his behalf to anything."""

STEWARDSHIP_BASES = frozenset(
    {ConsentBasis.PATIENT_ASKED, ConsentBasis.LPA, ConsentBasis.MEDICAL_LETTER}
)
"""The bases a graph may be set up for someone on. A spoken agreement is not among them:
its witness must hold a key on the graph, and a graph being set up has no keys yet."""

DOCUMENTED_BASES = frozenset({ConsentBasis.LPA, ConsentBasis.MEDICAL_LETTER})
"""The bases that are a document: the artefact of it is required."""


@monotonic
class Consent(ProfileScoped, Base):
    """One agreement on one profile.

    `person_id` is who gave it — the owner, or the chief acting for him on the recorded
    `basis`. `text_version` and `wording_text` are the words they saw, `language` the
    language they saw them in. `holder_person_id` is set only for a per-holder purpose and
    names the person the agreement is about and `scopes` the parts it lets them see.
    `basis_artifact_id` is the document behind a
    documented basis, or the recording behind a spoken one; `witness_person_id` is who
    heard a spoken agreement.

    `app.consent.service.require_consent` picks the newest one in force for its purpose —
    `granted_at`, tied by `seq` (#192/#218) — and a key is cut resting on whichever that is:
    two consents for the same person granted in one request, or under a frozen clock, used
    to tie and let the older, narrower one win at random (checkpoint 13's exact failure,
    the same one #190 reported and could not reproduce).
    """

    __tablename__ = "consent"

    # Not cascaded with the profile, unlike every other table of profile data: the proof of
    # what was agreed and withdrawn outlives the graph. Deleting a profile first exports
    # and archives its consents (the PDPA erasure story); until then the database refuses.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profile.id", ondelete="RESTRICT"), index=True
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    purpose: Mapped[ConsentPurpose] = mapped_column(enum_column(ConsentPurpose, "consent_purpose"))
    holder_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None, index=True
    )
    # For a per-holder purpose: the parts of the record the words let that person see, as
    # scope names. A key cut under this consent is never wider than these.
    scopes: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    text_version: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(16))
    wording_text: Mapped[str] = mapped_column(Text)
    # Named for how it was captured, not `channel`: that word is the audit door's own.
    captured_via: Mapped[ConsentChannel] = mapped_column(
        enum_column(ConsentChannel, "consent_channel")
    )
    basis: Mapped[ConsentBasis] = mapped_column(enum_column(ConsentBasis, "consent_basis"))
    basis_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifact.id"), default=None
    )
    witness_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    granted_at: Mapped[datetime] = mapped_column(default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    def is_active(self, now: datetime) -> bool:
        """Not withdrawn by this moment. Says nothing about the version, like `Key.is_active`."""
        return self.revoked_at is None or as_utc(self.revoked_at) > now
