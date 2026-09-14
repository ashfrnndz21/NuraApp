"""Grants by part and window, as the family screen shows them (E12-01).

A `Grant` is a live key read as the chief manages it: who holds it, as what, which parts
of the record it opens and until when — rendered in the patient's words, the same words
the consent used. The presets say what each role opens by default, so the screen can
offer "helper" and mean the same thing every time. The helper list is the grants of the
helper role, with what she may do said in whole sentences.

Narrowing is `app.keys.grants.narrow_key`: fewer parts or a shorter window, on the chief's
own yes, never wider. Wider is a fresh consent and a new key.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, person_display_name
from app.consent.texts import what_lines
from app.db import as_utc, utcnow
from app.family.strings import (
    CAN_SEE,
    HELPER_CAN,
    NO_HELPER,
    ROLE_IS,
    ROLE_WORDS,
    UNTIL_DAY,
    WINDOW_LINES,
    language_of,
)
from app.keys.context import KeyContext
from app.keys.grants import list_keys
from app.keys.models import Key
from app.keys.scopes import DEFAULT_WINDOW, ROLE_SCOPES, KeyRole, KeyWindow, Scope, window_of
from app.medicines.strings import say_date
from app.regions import REGION_TZ


@dataclass(frozen=True, slots=True)
class RolePreset:
    """What a role opens by default, and for how long, in his words."""

    role: KeyRole
    scopes: frozenset[Scope]
    window: KeyWindow
    lines: list[str]


@dataclass(frozen=True, slots=True)
class Grant:
    """One live key as the chief manages it."""

    key: Key
    holder_name: str
    role: KeyRole
    scopes: frozenset[Scope]
    window: KeyWindow | None
    expires_at: datetime | None
    lines: list[str]


def _window_line(
    name: str, language: str, *, window: KeyWindow | None, expires_at: datetime | None
) -> str:
    if window is not None:
        return WINDOW_LINES[language][window].format(name=name)
    assert expires_at is not None  # a key with no end is the ALWAYS window
    return UNTIL_DAY[language].format(name=name, day=say_date(expires_at.date(), language))


def _grant_lines(
    name: str,
    role: KeyRole,
    scopes: frozenset[Scope],
    language: str,
    *,
    window: KeyWindow | None,
    expires_at: datetime | None,
) -> list[str]:
    """Who they are to him, the parts they see, and for how long — the consent's own shape."""
    lines = [ROLE_IS[language].format(name=name, role=ROLE_WORDS[language][role])]
    lines.append(CAN_SEE[language].format(name=name))
    lines.extend(f"- {part}" for part in what_lines(scopes - {Scope.PROFILE}, language))
    lines.append(_window_line(name, language, window=window, expires_at=expires_at))
    return lines


def role_presets(language: str | None, *, name: str) -> list[RolePreset]:
    """The six roles as the family screen offers them, each with its default parts and
    window, said as they would be for `name`."""
    words = language_of(language)
    return [
        RolePreset(
            role=role,
            scopes=ROLE_SCOPES[role],
            window=DEFAULT_WINDOW[role],
            lines=_grant_lines(
                name,
                role,
                ROLE_SCOPES[role],
                words,
                window=DEFAULT_WINDOW[role],
                expires_at=None,
            ),
        )
        for role in KeyRole
    ]


async def grants(
    session: AsyncSession, *, context: KeyContext, language: str | None = None
) -> list[Grant]:
    """Every live key on the profile, as a grant in his words — his language unless another
    is asked for. Owner and chief only, like the key list it is read from."""
    words = language_of(language or (await audited_profile_read(session, context)).language)
    moment = utcnow()
    found: list[Grant] = []
    for key in await list_keys(session, context=context):
        if not key.is_active(moment):
            continue
        found.append(await _grant(session, context, key, words))
    return sorted(found, key=lambda grant: as_utc(grant.key.granted_at))


async def _grant(session: AsyncSession, context: KeyContext, key: Key, language: str) -> Grant:
    name = await person_display_name(session, context, key.holder_person_id)
    expires_at = None if key.expires_at is None else as_utc(key.expires_at)
    window = window_of(as_utc(key.granted_at), expires_at)
    local_end = None if expires_at is None else expires_at.astimezone(REGION_TZ[context.region])
    return Grant(
        key=key,
        holder_name=name,
        role=key.role,
        scopes=key.scopes_held,
        window=window,
        expires_at=expires_at,
        lines=_grant_lines(
            name, key.role, key.scopes_held, language, window=window, expires_at=local_end
        ),
    )


@dataclass(frozen=True, slots=True)
class Helper:
    """Someone holding a helper key: who, what she may do, for how long."""

    key_id: uuid.UUID
    person_id: uuid.UUID
    name: str
    scopes: frozenset[Scope]
    lines: list[str]


async def helper_list(
    session: AsyncSession, *, context: KeyContext, language: str | None = None
) -> tuple[list[Helper], list[str]]:
    """Who holds a helper key and what each may do, in whole sentences; and the lines to
    show when nobody does."""
    words = language_of(language or (await audited_profile_read(session, context)).language)
    helpers: list[Helper] = []
    for grant in await grants(session, context=context, language=words):
        if grant.role is not KeyRole.HELPER:
            continue
        can = HELPER_CAN[words]
        lines = [ROLE_IS[words].format(name=grant.holder_name, role=ROLE_WORDS[words][grant.role])]
        lines.extend(
            can[scope].format(name=grant.holder_name) for scope in can if scope in grant.scopes
        )
        lines.append(grant.lines[-1])
        helpers.append(
            Helper(
                key_id=grant.key.id,
                person_id=grant.key.holder_person_id,
                name=grant.holder_name,
                scopes=grant.scopes,
                lines=lines,
            )
        )
    return helpers, ([] if helpers else [NO_HELPER[words]])


def scopes_in_words(scopes: Sequence[Scope] | frozenset[Scope], language: str | None) -> list[str]:
    """The parts of the record in his words, for any screen that lists them."""
    return what_lines(frozenset(scopes) - {Scope.PROFILE}, language_of(language))
