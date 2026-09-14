"""The Note: a short line the patient wrote for himself.

Everywhere else on the graph a text column is a label: a name for a thing that lives in the
object store. A note is different, and it is the one exception: its content *is* what the
patient typed, on purpose, for himself. That is why this table has a text column at all, and
why it is short — a note is a line, never a document. Documents are artefacts.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, ProfileScoped, utcnow

NOTE_LENGTH = 280
"""The most a note may hold. A line, chosen by the patient; not a place to keep a letter."""


class Note(ProfileScoped, Base):
    __tablename__ = "note"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The patient's own words, kept under Scope.NOTES, which only he and a chief preset to
    # it can open. This is the one short text column the graph allows; see the module doc.
    text: Mapped[str] = mapped_column(String(NOTE_LENGTH))
    written_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
