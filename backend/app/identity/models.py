"""Person and Profile, the Stewardship that holds a Profile until its owner claims it, and
the two rows that get a person signed in.

A Person is an account: a phone number or an email, a language, a region. A Profile is a
health graph with exactly one owner, and a Person owns at most one. Before the owner has
claimed it, a steward holds it on a declared basis (E01): the Profile has no owner yet, the
number it was set up against says who may claim it, and the Stewardship says who holds it
meanwhile and on what footing. Everything else about a person's reach into someone else's
graph is a Key, never a column here.

A LoginChallenge is one attempt to prove a phone number or an email address; a LoginSession
is what the proof earns. Neither holds a secret in the clear.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.consent.models import ConsentBasis
from app.db import Base, ProfileScoped, as_utc, enum_column, monotonic, utcnow
from app.regions import Region


class Person(Base):
    """An account. Registered by phone number or email; no passwords, ever."""

    __tablename__ = "person"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    display_name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(16), default="en")
    phone_e164: Mapped[str | None] = mapped_column(String(20), unique=True, default=None)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    named_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )
    """Who typed `display_name`, while it is somebody else's word for him: set when the owner
    lets in a number that is not an account yet (the words he agreed to need a name), and
    cleared when the person signs in and gives his own (`app.identity.login`)."""


class Profile(Base):
    """The health graph. Pinned to a region at creation and owned by exactly one Person.

    `owner_person_id` is empty only while the graph is stewarded: set up for someone by his
    number, not yet claimed by him. `patient_phone_e164` is that number — the owner's own
    when he opened the graph himself — and there is one graph per number, ever: that is how
    two siblings cannot set up two graphs for one father.
    """

    __tablename__ = "profile"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    display_name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(16), default="en")
    owner_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), unique=True, default=None
    )
    patient_phone_e164: Mapped[str | None] = mapped_column(String(20), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    area: Mapped[str | None] = mapped_column(String(40), default=None)
    """Where he lives, coarsely: a town or district, or the first digits of a postcode —
    never a street or a whole postcode (`app.delivery.feed.area`). Set on his own yes; read by him
    and the chief who manages his feed; used only to match local alerts (E09-07), on this
    server, and never sent to a searcher."""

    @property
    def is_stewarded(self) -> bool:
        return self.owner_person_id is None


class Stewardship(ProfileScoped, Base):
    """Who holds a graph for the patient until he claims it, and on what footing.

    Opened when a profile is set up for someone (`app.identity.doors`), closed by his claim.
    `key_id` is the chief key the steward holds meanwhile; `consent_id` is the agreement to
    Nura keeping the record that the steward gave on the patient's behalf, and that row
    carries the document or the recording behind `basis`. `relationship` is who the
    steward said he is to the patient, in the steward's words, for the claim to name him
    ("Mei, your daughter"). The row stays after the claim, closed, naming who claimed it.
    """

    __tablename__ = "stewardship"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    steward_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("key.id"))
    consent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("consent.id"))
    basis: Mapped[ConsentBasis] = mapped_column(enum_column(ConsentBasis, "consent_basis"))
    relationship: Mapped[str | None] = mapped_column(String(80), default=None)
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(default=None)
    claimed_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )

    def is_open(self, now: datetime) -> bool:
        return self.closed_at is None or as_utc(self.closed_at) > now


class LoginChannel(StrEnum):
    """How the one-time secret went out: a code by SMS or WhatsApp, or a link by email."""

    PHONE = "phone"
    EMAIL = "email"


@monotonic
class LoginChallenge(Base):
    """One request to sign in: a hashed secret, a window, a count of tries, and who it became.

    The code itself is never written down. What is stored is a hash keyed by the challenge's
    own id, so two people sent the same six digits do not share a row that could be matched.
    A challenge is one use: `consumed_at` closes it, and so does a newer one for the same
    address — the newest open one, `issued_at` tied by `seq` (#192/#218), is the one a code is
    checked against. `person_id` is filled in on the verify that succeeded, and by nothing
    else.
    """

    __tablename__ = "login_challenge"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    channel: Mapped[LoginChannel] = mapped_column(enum_column(LoginChannel, "login_channel"))
    phone_e164: Mapped[str | None] = mapped_column(String(20), index=True, default=None)
    email: Mapped[str | None] = mapped_column(String(320), index=True, default=None)
    code_hash: Mapped[str] = mapped_column(String(64))
    # What the person said about himself when he asked; used only if this makes a new account.
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    language: Mapped[str | None] = mapped_column(String(16), default=None)
    issued_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(default=None)
    person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("person.id"), default=None)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class LoginSession(Base):
    """A signed-in person on one device, for thirty days or until he logs out.

    The token is random, handed over once on verify and never stored: the row holds its hash.
    It is pinned to the region that issued it, like everything else.
    """

    __tablename__ = "session"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)

    def is_open(self, now: datetime) -> bool:
        if self.revoked_at is not None and as_utc(self.revoked_at) <= now:
            return False
        return now < as_utc(self.expires_at)
