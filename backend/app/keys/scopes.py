"""What a key covers: the scopes, the roles that preset them, and the window that ends them."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, and_, not_, or_
from sqlalchemy.orm import QueryableAttribute


class Scope(StrEnum):
    """The categories a key can cover. One per kind of thing on the profile."""

    MEDICINES = "medicines"
    VISITS = "visits"
    READINGS = "readings"
    RECORDS = "records"
    NOTES = "notes"
    MONEY = "money"
    FAMILY = "family"
    EMERGENCY = "emergency"
    ASK = "ask"
    SEND = "send"
    PROFILE = "profile"
    """The profile row itself: whose graph this is, its name and language. Every key holds
    it, because holding any key means you may see whose graph it opens."""


ALL_SCOPES = frozenset(Scope)


class KeyRole(StrEnum):
    """Who the key holder is to the patient. The role presets the scopes; it does not fix them."""

    CHIEF = "chief"
    CAREGIVER = "caregiver"
    VIEWER = "viewer"
    HELPER = "helper"
    EMERGENCY = "emergency"
    CLINIC = "clinic"


ROLE_SCOPES: dict[KeyRole, frozenset[Scope]] = {
    KeyRole.CHIEF: ALL_SCOPES,
    KeyRole.CAREGIVER: frozenset(
        {
            Scope.PROFILE,
            Scope.MEDICINES,
            Scope.VISITS,
            Scope.READINGS,
            Scope.RECORDS,
            Scope.EMERGENCY,
            Scope.ASK,
            Scope.SEND,
        }
    ),
    KeyRole.VIEWER: frozenset(
        {Scope.PROFILE, Scope.MEDICINES, Scope.VISITS, Scope.READINGS, Scope.EMERGENCY}
    ),
    KeyRole.HELPER: frozenset({Scope.PROFILE, Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND}),
    KeyRole.EMERGENCY: frozenset({Scope.PROFILE, Scope.EMERGENCY}),
    KeyRole.CLINIC: frozenset(
        {Scope.PROFILE, Scope.MEDICINES, Scope.VISITS, Scope.READINGS, Scope.RECORDS}
    ),
}
"""Private notes and money are the patient's own: only a chief is ever preset to them.
Every role holds PROFILE: a key that opens nothing of whose graph it is opens nothing."""

STEWARD_SCOPES = ALL_SCOPES - {Scope.NOTES}
"""What the person who set a graph up for someone holds until that person claims it: a chief
key over everything but the notes. Private notes are the patient's own words for himself,
and there is no patient here yet to have written any or to have let anyone read them."""


_SUBJECT_SCOPES: dict[str, Scope] = {
    "medicine": Scope.MEDICINES,
    "medication": Scope.MEDICINES,
    "blood_pressure": Scope.READINGS,
    "blood_sugar": Scope.READINGS,
    "heart_rate": Scope.READINGS,
    "oxygen": Scope.READINGS,
    "temperature": Scope.READINGS,
    "weight": Scope.READINGS,
    "steps": Scope.READINGS,
    "sleep": Scope.READINGS,
    "water": Scope.READINGS,
    # The owner's deliberate call (design-direction.md follow-up, 2026-09-17): whoever can
    # see his readings — a helper included — can see whether he has eaten. Weighed against
    # keeping meals under the general record so a helper could not see them; the owner chose
    # practicality over that extra privacy line. If this ever changes, it is this one line —
    # every reader of a meal fact goes through `scope_for_subject`, not its own scope check.
    # Subject "meal" per docs/recommendation-engine.md §2.7 ("Meals are one fact per meal
    # slot. Subject `meal`, attribute `breakfast | lunch | dinner | snack`").
    "meal": Scope.READINGS,
}


READING_PREFIX = "reading:"
"""A subject named `reading:<thing>` is a reading, whatever the thing."""

NAMED_SUBJECTS = frozenset(_SUBJECT_SCOPES)
"""Every subject this module names a scope for; any other sits under RECORDS."""


FACT_SCOPES: tuple[Scope, ...] = (Scope.READINGS, Scope.MEDICINES, Scope.RECORDS)
"""The scopes a fact can sit under (`scope_for_subject`). A reader of more than one subject
reads each on its own, under its own scope, and names the ones the key does not hold."""


def subjects_under(scope: Scope) -> frozenset[str]:
    """The named subjects whose facts sit under `scope`. READINGS also takes every subject
    starting `reading:`, and RECORDS every subject not named here (`scope_for_subject`), so
    a query narrowing facts to one scope says the same thing this module says."""
    return frozenset(subject for subject, held in _SUBJECT_SCOPES.items() if held is scope)


Column = ColumnElement[Any] | QueryableAttribute[Any]
"""A column to narrow on: a Core column or an ORM attribute."""


def subject_is_under(subject: Column, scope: Scope) -> ColumnElement[bool]:
    """The rows whose `subject` sits under `scope`, as `scope_for_subject` decides it, said as
    SQL — so a query narrowing rows to one scope says the same thing this module says."""
    if scope is Scope.RECORDS:
        return and_(
            subject.not_in(sorted(NAMED_SUBJECTS)),
            not_(subject.startswith(READING_PREFIX)),
        )
    named = subject.in_(sorted(subjects_under(scope)))
    if scope is Scope.READINGS:
        return or_(named, subject.startswith(READING_PREFIX))
    return named


def scope_for_subject(subject: str | None) -> Scope:
    """Which scope a fact about `subject` sits under. Decided here, never by the caller.

    A medicine fact is read and written under MEDICINES, a reading under READINGS, and
    anything else — or the whole record, when no subject is named — under RECORDS.
    """
    if subject is None:
        return Scope.RECORDS
    if subject.startswith(READING_PREFIX):
        return Scope.READINGS
    return _SUBJECT_SCOPES.get(subject, Scope.RECORDS)


class KeyWindow(StrEnum):
    """How long a key lives. Every key states one; `ALWAYS` is the only one without an end."""

    ALWAYS = "always"
    ONE_DAY = "one_day"
    THIRTY_DAYS = "thirty_days"
    SEVENTY_TWO_HOURS = "seventy_two_hours"


_WINDOW_LENGTHS: dict[KeyWindow, timedelta] = {
    KeyWindow.ONE_DAY: timedelta(days=1),
    KeyWindow.THIRTY_DAYS: timedelta(days=30),
    KeyWindow.SEVENTY_TWO_HOURS: timedelta(hours=72),
}

DEFAULT_WINDOW: dict[KeyRole, KeyWindow] = {
    KeyRole.CHIEF: KeyWindow.ALWAYS,
    KeyRole.CAREGIVER: KeyWindow.ALWAYS,
    KeyRole.VIEWER: KeyWindow.THIRTY_DAYS,
    KeyRole.HELPER: KeyWindow.ALWAYS,
    KeyRole.EMERGENCY: KeyWindow.ALWAYS,
    KeyRole.CLINIC: KeyWindow.SEVENTY_TWO_HOURS,
}


def window_ends_at(window: KeyWindow, granted_at: datetime) -> datetime | None:
    """When a key cut now stops working, or None for a key that runs until it is revoked."""
    length = _WINDOW_LENGTHS.get(window)
    return None if length is None else granted_at + length


def window_outlasts(window: KeyWindow, than: KeyWindow) -> bool:
    """True when `window` runs longer than `than`: `ALWAYS` outlasts every timed window, and
    among the timed ones, more days does. Used to refuse a key cut for longer than the words
    a consent named agreed to (`app.keys.grants.grant_key`, #185)."""
    if window is than:
        return False
    if window is KeyWindow.ALWAYS:
        return True
    if than is KeyWindow.ALWAYS:
        return False
    return _WINDOW_LENGTHS[window] > _WINDOW_LENGTHS[than]


def window_of(granted_at: datetime, expires_at: datetime | None) -> KeyWindow | None:
    """The preset window a key was cut for, read back from its dates, or None when its end
    is not one of the presets — a key that was shortened to a day of its own (E12-01)."""
    if expires_at is None:
        return KeyWindow.ALWAYS
    length = expires_at - granted_at
    for window, preset in _WINDOW_LENGTHS.items():
        if length == preset:
            return window
    return None
