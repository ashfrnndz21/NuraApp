"""A closed account (#143): the closing that waits out its window, and the one record of it
that outlives the graph.

`AccountClosure` is a row of the profile: who closed it, when, and the moment after which his
papers are deleted. While it stands and is not undone, nobody opens the profile
(`app.keys.context.AccountClosing`) except its owner, to see the closing and to undo it.
`ErasureRecord` is written when the graph is deleted and is not a row of any profile — the
profile is gone — so it keeps what the PDPA data map says must outlive the erasure it
authorised (`docs/trust/pdpa-data-map.md` §4): the consent rows as they stood, and the one line
that says the graph was erased, for whom, asked by whom, and when.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, enum_column, frozen, utcnow
from app.memory.models import _row_of_profile
from app.regions import Region


class AccountClosure(ProfileScoped, Base):
    """The owner asked Nura to close his account and delete his papers."""

    __tablename__ = "account_closure"
    __table_args__ = (_row_of_profile("account_closure"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    requested_by_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    requested_at: Mapped[datetime] = mapped_column(default=utcnow)
    delete_after: Mapped[datetime] = mapped_column()
    undone_at: Mapped[datetime | None] = mapped_column(default=None)
    undone_by_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), default=None
    )


frozen(AccountClosure, except_for=frozenset({"undone_at", "undone_by_person_id"}))


class ErasureRecord(Base):
    """Outside the graph: the proof that survives the erasure it records."""

    __tablename__ = "erasure_record"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(index=True)
    """The erased profile's id, as a plain value: its row is gone."""
    region: Mapped[Region] = mapped_column(enum_column(Region, "region"))
    requested_by_person_id: Mapped[uuid.UUID] = mapped_column()
    """Who asked, as a plain reference: no foreign key, so a later request to delete his
    sign-in account is not held up by the record that his papers were erased."""
    requested_at: Mapped[datetime] = mapped_column()
    erased_at: Mapped[datetime] = mapped_column(default=utcnow)
    consents: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    """Every consent row the profile had, as it stood: what he agreed to and when he withdrew."""
    removed: Mapped[dict[str, int]] = mapped_column(JSON)
    """How many rows of each table went, and how many stored objects. Counts, no content."""


frozen(ErasureRecord)
