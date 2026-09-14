"""The connector tables (E18-02): a connector, and the proposals a scan leaves behind.

A `Connector` is one read-only source for one profile, resting on the consent for its kind
(`ConsentPurpose.CALENDAR`): the row names the consent, who connected it and when. It holds
no credentials and no copy of the calendar.

An `AppointmentProposal` is one calendar event that looked like a visit — it matched a
provider in his directory or a word on the health list — kept so a person can say yes or no.
It is never an appointment: accepting it books a PLANNED `Appointment` on a person's yes and
names it here. An event that matched nothing is never written anywhere. What a proposal
keeps of the event is the summary as a label, when, where as a label, and a digest of its
UID so a second scan does not propose it twice; never anyone else in it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.memory.models import LABEL_LENGTH, ProviderKind, _row_of_profile, _tied_to_profile


class ConnectorKind(StrEnum):
    CALENDAR = "calendar"


class ConnectorSource(StrEnum):
    """Where the connector's events come from. Only an uploaded file is built over HTTP."""

    ICS_FILE = "ics_file"
    FIXTURE = "fixture"


class Connector(ProfileScoped, Base):
    """One read-only source on one profile, on the consent for its kind."""

    __tablename__ = "connector"
    __table_args__ = (_row_of_profile("connector"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[ConnectorKind] = mapped_column(enum_column(ConnectorKind, "connector_kind"))
    source: Mapped[ConnectorSource] = mapped_column(
        enum_column(ConnectorSource, "connector_source")
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consent.id"))
    connected_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    connected_at: Mapped[datetime] = mapped_column(default=utcnow)


class ProposalStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class MatchedBy(StrEnum):
    PROVIDER = "provider"
    """The event names a provider already in his directory."""
    KEYWORD = "keyword"
    """The event carries a word on the health list."""


class AppointmentProposal(ProfileScoped, Base):
    """A calendar event that looked like a visit, waiting for a person's yes or no."""

    __tablename__ = "appointment_proposal"
    __table_args__ = (
        _row_of_profile("appointment_proposal"),
        _tied_to_profile("appointment_proposal", "connector_id", "connector"),
        _tied_to_profile("appointment_proposal", "provider_id", "provider"),
        _tied_to_profile("appointment_proposal", "appointment_id", "appointment"),
        UniqueConstraint("connector_id", "event_digest", name="uq_appointment_proposal_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("connector.id"), index=True)
    event_digest: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(LABEL_LENGTH))
    location: Mapped[str | None] = mapped_column(String(LABEL_LENGTH), default=None)
    starts_at: Mapped[datetime] = mapped_column(index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_by: Mapped[MatchedBy] = mapped_column(enum_column(MatchedBy, "proposal_matched_by"))
    keyword: Mapped[str | None] = mapped_column(String(32), default=None)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("provider.id"), default=None)
    provider_name: Mapped[str] = mapped_column(String(120))
    provider_kind: Mapped[ProviderKind] = mapped_column(enum_column(ProviderKind, "provider_kind"))
    status: Mapped[ProposalStatus] = mapped_column(enum_column(ProposalStatus, "proposal_status"))
    found_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(default=None)
    decided_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointment.id"), default=None
    )


frozen(Connector)
# A proposal takes one change: a person's yes (naming the visit it booked) or no.
frozen(
    AppointmentProposal,
    except_for=frozenset({"status", "decided_at", "decided_by_person_id", "appointment_id"}),
)
