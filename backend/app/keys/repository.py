"""The calls every repository of profile data is built from.

Reading profile data without a key context is not something a caller can forget to do: there
is no other way to name a row. `scoped_select` puts the scope check and the profile filter in
the same expression, and `scoped_new` does the same for a write.

A table whose rows are written under more than one scope (`app.keys.rows.RowScoped`: the
artefacts, the events) is read row by row as well as table by table. The scope a caller names
is the door; the scope each row was written under is what the key must hold to see that row,
and `scoped_select` asks it in the same expression, for every reader. `scoped_new` writes the
scope of the write onto the row.

The model, the context and the scope are positional, so `**values` is free to carry a column
of any name.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import ColumnElement, Select, select

from app.db import ProfileScoped
from app.keys.context import KeyContext
from app.keys.rows import RowScoped
from app.keys.scopes import Column, Scope

WRITTEN_SCOPE = "written_scope"


def scoped_select[Row: ProfileScoped](
    model: type[Row], context: KeyContext, scope: Scope, /
) -> Select[tuple[Row]]:
    """A select over one profile's rows, refused unless the context covers the scope.

    For a `RowScoped` table, only the rows written under a scope the context holds: a read of
    the artefacts under the record's scope does not return the family's messages to a key
    that does not hold the family's scope.
    """
    context.require(scope)
    statement = select(model).where(model.profile_id == context.profile_id)
    if issubclass(model, RowScoped):
        row_scoped = cast(type[RowScoped], model)
        statement = statement.where(row_scoped.written_scope.in_(sorted(context.scopes)))
    return statement



def scoped_projection[Row: ProfileScoped](
    model: type[Row], context: KeyContext, scope: Scope, /
) -> Select[tuple[Row]]:
    """A select over one profile's rows for the one fixed projection a scope is defined to
    open across the parts of the record: ADR 0002's emergency card, which EMERGENCY opens.
    Refused unless the context covers the scope, and not narrowed by the scope each row was
    written under — the projection is the definition of the scope, and what it reads is named
    in the ADR. Only `app.safety.emergency_card` reads through it; `tests/test_row_scope.py`
    fails if anything else does. Every other read is `scoped_select`.
    """
    context.require(scope)
    return select(model).where(model.profile_id == context.profile_id)


def scoped_new[Row: ProfileScoped](
    model: type[Row], context: KeyContext, scope: Scope, /, **values: Any
) -> Row:
    """A new row pinned to the profile in the context, refused unless the scope allows it.

    A `RowScoped` row is written under `scope`, and says so: the scope of the write is the
    row's scope, decided here and never by the caller.
    """
    context.require(scope)
    if issubclass(model, RowScoped):
        if WRITTEN_SCOPE in values:
            raise TypeError("a row's written scope is the scope of its write; no caller names it")
        values[WRITTEN_SCOPE] = scope
    return model(profile_id=context.profile_id, **values)


def scoped_references[Row: ProfileScoped](
    column: Column,
    model: type[Row],
    context: KeyContext,
    scope: Scope,
    /,
    *where: ColumnElement[bool],
) -> ColumnElement[bool]:
    """Whether `column` names a row of `model` on this profile that matches `where`, of
    whatever scope that row was written under. Refused unless the context covers the scope.

    A predicate, never a read: it narrows the rows of another table by where their references
    land, and nothing of the rows it looks at comes back. It is for the checks that hold for
    every reference whether or not this key may follow it — the region pin on provenance
    (`app.memory.episodic`): a fact resting on bytes held in another region is served to
    nobody, while a fact resting on an artefact this key cannot see is still shown under its
    own scope, the artefact withheld by name. Anything that returns rows is `scoped_select`.
    """
    context.require(scope)
    ident = cast(Any, model).id
    return column.in_(select(ident).where(model.profile_id == context.profile_id, *where))
