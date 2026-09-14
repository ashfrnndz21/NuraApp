"""Person and Profile.

A Person is an account: a phone number or an email, a language, a region. A Profile is a
health graph with exactly one owner, and a Person owns at most one. Everything else about a
person's reach into someone else's graph is a Key, never a column here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, enum_column, utcnow
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
