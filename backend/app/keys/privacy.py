"""Only me: the parts of his record the owner keeps from every key (E12-04).

A `Privacy` row says that one part of the record — the private notes, the insurance
letters — is the owner's alone from the moment it is marked until he lifts it. It is
enforced here, on the floor beside the keys, and nowhere else: `resolve_key_context` takes
the marked parts out of every key it resolves, so a caregiver reading the notes a second
after the mark is refused whatever her key row says, and `grant_key` cuts no new key into a
marked part. Nothing above this module can hand out a context that reaches a marked part.

The row is written and lifted by `app.family.privacy`, on the owner's own yes and on the
trail; this module only reads it, the way the resolver reads the key rows, before there is
a context to read anything with.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, as_utc, enum_column, utcnow
from app.keys.scopes import ALL_SCOPES, Scope


class Privacy(ProfileScoped, Base):
    """One part of the record marked "only me", from when until when, by whom.

    A lifted mark stays as a row, so the owner can read that the part was once his alone
    and when he opened it again. Marking the same part again is a new row.
    """

    __tablename__ = "privacy"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))
    marked_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    marked_at: Mapped[datetime] = mapped_column(default=utcnow)
    lifted_at: Mapped[datetime | None] = mapped_column(default=None)
    lifted_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )

    def is_marked(self, now: datetime) -> bool:
        return self.lifted_at is None or as_utc(self.lifted_at) > now


ONLY_ME_SCOPES: frozenset[Scope] = ALL_SCOPES - {Scope.PROFILE, Scope.EMERGENCY}
"""The parts an owner may mark "only me". Whose record it is (PROFILE) is not a part of it,
and every key opens that much. The emergency card is the one part that exists for the
moment he cannot speak: it is never hidden from the people he named to hold it — he closes
an emergency key instead, which is on the trail like any other closing."""


async def only_me_scopes(session: AsyncSession, *, profile_id: uuid.UUID) -> frozenset[Scope]:
    """The parts of this profile marked "only me" at this moment.

    Read without a context, like the key rows the resolver reads: this is what a context is
    narrowed by before it exists. Every caller is inside `app.keys`.
    """
    moment = utcnow()
    rows = await session.scalars(select(Privacy).where(Privacy.profile_id == profile_id))
    return frozenset(row.scope for row in rows if row.is_marked(moment))
