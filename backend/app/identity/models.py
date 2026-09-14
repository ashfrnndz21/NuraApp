"""Person and Profile, and the two rows that get a person signed in.

A Person is an account: a phone number or an email, a language, a region. A Profile is a
health graph with exactly one owner, and a Person owns at most one. Everything else about a
person's reach into someone else's graph is a Key, never a column here.

A LoginChallenge is one attempt to prove a phone number or an email address; a LoginSession
is what the proof earns. Neither holds a secret in the clear.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, as_utc, enum_column, utcnow
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


class Profile(Base):
    """The health graph. Pinned to a region at creation and owned by exactly one Person."""

    __tablename__ = "profile"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    display_name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(16), default="en")
    owner_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class LoginChannel(StrEnum):
    """How the one-time secret went out: a code by SMS or WhatsApp, or a link by email."""

    PHONE = "phone"
    EMAIL = "email"


class LoginChallenge(Base):
    """One request to sign in: a hashed secret, a window, a count of tries, and who it became.

    The code itself is never written down. What is stored is a hash keyed by the challenge's
    own id, so two people sent the same six digits do not share a row that could be matched.
    A challenge is one use: `consumed_at` closes it, and so does a newer one for the same
    address. `person_id` is filled in on the verify that succeeded, and by nothing else.
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
