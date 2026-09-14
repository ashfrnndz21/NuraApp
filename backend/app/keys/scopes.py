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


ALL_SCOPES = frozenset(Scope)


def scope_for_subject(subject: str) -> Scope:
    """The scope a fact is held under, from what it is about.

    A medicine is the medicines scope, a reading the readings scope, everything else the
    records scope — so a key cut for the visits and the readings reaches no dose.
    """
    head = subject.split(".", 1)[0].strip().lower()
    if head in {"medicine", "medicines", "medication", "medications"}:
        return Scope.MEDICINES
    if head in {"reading", "readings"}:
        return Scope.READINGS
    return Scope.RECORDS


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
        {Scope.MEDICINES, Scope.VISITS, Scope.READINGS, Scope.EMERGENCY}
    ),
    KeyRole.HELPER: frozenset({Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND}),
    KeyRole.EMERGENCY: frozenset({Scope.EMERGENCY}),
    KeyRole.CLINIC: frozenset(
        {Scope.MEDICINES, Scope.VISITS, Scope.READINGS, Scope.RECORDS}
    ),
}
"""Private notes and money are the patient's own: only a chief is ever preset to them."""


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
