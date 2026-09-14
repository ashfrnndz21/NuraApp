"""The scope a row was written under, for the tables whose rows are of more than one kind.

Most tables of profile data hold one kind of thing, read and written under one scope, so the
scope the caller names at the door is the scope of every row behind it. Two do not. An
artefact is a paper under the record's scope, a family message under the family's, the words
of a fall under the emergency scope, a question asked of Nura under the ask scope; an event is
a moment of the record's, a reading taken (the readings'), a tablet taken (the medicines'), a
family message (the family's). For those, each row says the scope it was written under, and a
key reads the rows written under scopes it holds and no others, whatever scope the caller
named (`app.keys.repository.scoped_select`).

The facts need no column: a fact sits under the scope of its subject
(`app.keys.scopes.scope_for_subject`), and every reader of more than one subject reads them
one scope at a time, for the scopes the key holds (`app.memory.semantic.fact_is_under`). The
table's door stays the caller's, because EMERGENCY's card is one fixed projection across
subjects (ADR 0002).
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from app.db import enum_column
from app.keys.scopes import Scope


class RowScoped:
    """Mixin for a table of profile data whose rows are written under more than one scope.

    `written_scope` is the scope of the write that made the row: `scoped_new` sets it from the
    scope it is called with, and a caller cannot name another. `scoped_select` reads a row only
    when the key holds its written scope, in the same expression as the profile filter, so no
    reader can forget to ask.
    """

    written_scope: Mapped[Scope] = mapped_column(enum_column(Scope, "scope"))

