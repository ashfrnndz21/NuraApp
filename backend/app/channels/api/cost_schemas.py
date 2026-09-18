"""The wire shape for the cost expectation (T3): `GET /profiles/{id}/visits/{appointment_id}/
cost`. `found=False` means no benchmark matched — `low_cents`, `high_cents` and `source` are
all null, never a guess. `covered_shown=False` means the caller does not hold `Scope.MONEY` —
`covered_low_cents` and `covered_high_cents` are null, and `note` names who to ask instead."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel


class CostSourceOut(BaseModel):
    publisher: str
    url: str
    fetched_at: date


class CostExpectationOut(BaseModel):
    appointment_id: uuid.UUID
    found: bool
    low_cents: int | None
    high_cents: int | None
    low_said: str | None
    high_said: str | None
    currency: str
    source: CostSourceOut | None
    covered_shown: bool
    covered_low_cents: int | None
    covered_high_cents: int | None
    covered_low_said: str | None
    covered_high_said: str | None
    note: list[str]
