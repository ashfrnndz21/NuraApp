"""The Key: the grant that attaches a family account to someone else's health graph."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, as_utc, enum_column, utcnow
from app.keys.scopes import KeyRole, Scope


class Key(ProfileScoped, Base):
    """One person's scoped reach into one profile.

    A key has a role, a scope, a window and a basis, and it names who cut it. The owner of
    the profile needs no key: the graph is his.
    """

    __tablename__ = "key"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    holder_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    role: Mapped[KeyRole] = mapped_column(enum_column(KeyRole, "key_role"))
    scopes: Mapped[list[str]] = mapped_column(JSON)
    basis: Mapped[str] = mapped_column(String(64))
    granted_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    granted_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def scopes_held(self) -> frozenset[Scope]:
        return frozenset(Scope(name) for name in self.scopes)

    def is_active(self, now: datetime) -> bool:
        """A key works while it is unrevoked and inside its window."""
        if self.revoked_at is not None and as_utc(self.revoked_at) <= now:
            return False
        return self.expires_at is None or now < as_utc(self.expires_at)
