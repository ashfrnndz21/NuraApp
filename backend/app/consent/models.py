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

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, as_utc, enum_column, utcnow


class ConsentPurpose(StrEnum):
    """What a consent is for. One row covers one of these and nothing wider.

    Research is not here on purpose: nothing trains on user data and nothing is studied
    from it, so there is no such consent to ask for.
    """

    HOLD_HEALTH_RECORD = "hold_health_record"
    SHARE_WITH_FAMILY = "share_with_family"
    RECORDING = "recording"
    WHATSAPP = "whatsapp"


PER_HOLDER = frozenset({ConsentPurpose.SHARE_WITH_FAMILY})
"""Purposes agreed to one person at a time: the row names who may hold a key. The rest are
agreed to for the profile as a whole."""


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
    """

    OWNER = "owner"
    LPA = "lpa"
    MEDICAL_LETTER = "medical_letter"
    VERBAL_RECORDED = "verbal_recorded"


PROXY_BASES = frozenset(ConsentBasis) - {ConsentBasis.OWNER}
"""The bases on which someone other than the owner may agree on his behalf."""

DOCUMENTED_BASES = frozenset({ConsentBasis.LPA, ConsentBasis.MEDICAL_LETTER})
"""The bases that are a document: the artefact of it is required."""


class Consent(ProfileScoped, Base):
    """One agreement on one profile.

    `person_id` is who gave it — the owner, or the chief acting for him on the recorded
    `basis`. `text_version` and `wording_text` are the words they saw, `language` the
    language they saw them in. `holder_person_id` is set only for a per-holder purpose and
    names the person the agreement is about. `basis_artifact_id` is the document behind a
    documented basis, or the recording behind a spoken one; `witness_person_id` is who
    heard a spoken agreement.
    """

    __tablename__ = "consent"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    purpose: Mapped[ConsentPurpose] = mapped_column(enum_column(ConsentPurpose, "consent_purpose"))
    holder_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None, index=True
    )
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

    def is_active(self, now: datetime) -> bool:
        """Not withdrawn by this moment. Says nothing about the version, like `Key.is_active`."""
        return self.revoked_at is None or as_utc(self.revoked_at) > now
