"""What a key covers: the scopes, the roles that preset them, and the window that ends them."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum


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
}


def scope_for_subject(subject: str | None) -> Scope:
    """Which scope a fact about `subject` sits under. Decided here, never by the caller.

    A medicine fact is read and written under MEDICINES, a reading under READINGS, and
    anything else — or the whole record, when no subject is named — under RECORDS.
    """
    if subject is None:
        return Scope.RECORDS
    if subject.startswith("reading:"):
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
