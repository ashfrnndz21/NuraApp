"""The two calls every repository of profile data is built from.

Reading profile data without a key context is not something a caller can forget to do: there
is no other way to name a row. `scoped_select` puts the scope check and the profile filter in
the same expression, and `scoped_new` does the same for a write.

The model, the context and the scope are positional, so `**values` is free to carry a column
of any name.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select

from app.db import ProfileScoped
from app.keys.context import KeyContext
from app.keys.scopes import Scope


def scoped_select[Row: ProfileScoped](
    model: type[Row], context: KeyContext, scope: Scope, /
) -> Select[tuple[Row]]:
    """A select over one profile's rows, refused unless the context covers the scope."""
    context.require(scope)
    return select(model).where(model.profile_id == context.profile_id)


def scoped_new[Row: ProfileScoped](
    model: type[Row], context: KeyContext, scope: Scope, /, **values: Any
) -> Row:
    """A new row pinned to the profile in the context, refused unless the scope allows it."""
    context.require(scope)
    return model(profile_id=context.profile_id, **values)
