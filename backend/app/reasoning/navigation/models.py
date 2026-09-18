"""The shapes care navigation passes between `needs.py`, a drafter and the route.

Nothing here carries a dose or a diagnosis: `Need` names where the need came from (one
evidence row, by id and table, so a caller can re-read it under the same key) and the bare
facts a drafter is allowed to speak — who, which doctor, when — never the record's own words
for what is wrong or how much of a medicine he takes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol


class NeedKind(StrEnum):
    """The four kinds of real need this story drafts for (T3)."""

    FOLLOW_UP = "follow_up"
    """A letter named a check-up date (`subject="follow_up", attribute="date"`, #257)."""
    NEW_MEDICINE = "new_medicine"
    """A new line at the pharmacy — the label's own doctor, never its dose."""
    TEST_DUE = "test_due"
    """An upcoming visit at a lab provider (RE-06's `test_coming`)."""
    HOME_CARE = "home_care"
    """A care-service category on Services: nursing, physio, meals or transport
    (`app.memory.models.HomeCareCategory`, PR #264)."""


@dataclass(frozen=True, slots=True)
class Need:
    """One real thing on the record a message could be drafted for.

    `evidence_kind`/`evidence_id` name the one row this need rests on — a `Fact`, a
    `MedicationLine`, an `Appointment` or a `Provider` — so a draft can cite it and a caller
    can re-read it under the same key. `doctor` is a name already on the record (a
    prescriber, a provider), never invented; `when` is a date already on the record, or
    `None` when the need has no date of its own (a care-service request)."""

    id: str
    kind: NeedKind
    evidence_kind: str
    evidence_id: uuid.UUID
    provider_id: uuid.UUID | None
    doctor: str | None
    when: date | None
    category: str | None = None
    """`HomeCareCategory.value` for a `HOME_CARE` need; `None` for every other kind."""


@dataclass(frozen=True, slots=True)
class ContactLink:
    """One way to reach the provider, built from the directory's own contact — never a
    number or address invented for the occasion."""

    kind: str
    """`"sms"` or `"whatsapp"`."""
    href: str


@dataclass(frozen=True, slots=True)
class Draft:
    """A drafted message: text only, never sent. `copy_only` is true when the provider has
    no phone on file, so `links` is empty and the sheet offers "Copy" alone."""

    need_id: str
    kind: NeedKind
    language: str
    text: str
    drafted_by: str
    """`"self"` (his own voice) or `"caregiver"` (a chief drafting in her own name)."""
    links: tuple[ContactLink, ...]
    copy_only: bool
    cites: tuple[str, ...]
    """One string per evidence row the text rests on, `"<table>:<id>"` — never the row's own
    content, only where it came from."""


class Drafter(Protocol):
    """The port every drafter answers: catalogue templates, or a model behind the same
    shape. Never a dose, never a diagnosis — see the module docstring."""

    async def draft(
        self,
        *,
        need: Need,
        language: str,
        patient_name: str,
        drafter_name: str | None,
        is_self: bool,
    ) -> str: ...
