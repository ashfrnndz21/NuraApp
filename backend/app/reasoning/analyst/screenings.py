"""Screenings due: a small, sourced guideline table, and the pure function that reads it.

The same standing as `app.reasoning.ranges`' fixture: published guidance, named by source id
here and cited below, awaiting a clinician's sign-off before it is used for anyone real
(`docs/trust/samd-boundary-review.md`, the `insight` row). Eligibility only — this build does
not track when a screening was last done (no such fact exists on the record yet), so a
screening a person is eligible for by age or by a condition he has told Nura about is "due" in
every report until the record holds a reason to say otherwise; that is a deliberate, narrower
reading than a real screening reminder would give, named in the PR this shipped with.

Sources:
- uspstf-lipid-2016: USPSTF, Screening for Lipid Disorders in Adults, 2016: screen adults 40
  and over for lipid disorders.
- ada-soc-2024-s3: American Diabetes Association, Standards of Care in Diabetes 2024, Section
  3, Table 3.1: screen adults 35 and over for type 2 diabetes; screen earlier and more often
  with a risk factor.
- ada-soc-2024-s12: American Diabetes Association, Standards of Care in Diabetes 2024, Section
  12: annual comprehensive eye examination for people with diabetes.
- kdigo-2012-ckd-screen: KDIGO 2012 CKD guideline, Kidney Int Suppl 2013;3(1): screen adults
  with diabetes or high blood pressure for chronic kidney disease.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScreeningGuideline:
    key: str
    min_age: int | None
    condition_codes: tuple[str, ...]
    """Any one of these conditions (`app.onboarding.conditions`, by code) also makes the
    screening due, whatever his age — an empty tuple means age is the only door."""
    source_id: str


SCREENINGS: tuple[ScreeningGuideline, ...] = (
    ScreeningGuideline("cholesterol_test", min_age=40, condition_codes=(), source_id="uspstf-lipid-2016"),
    ScreeningGuideline(
        "diabetes_screening",
        min_age=35,
        condition_codes=("diabetes",),
        source_id="ada-soc-2024-s3",
    ),
    ScreeningGuideline(
        "eye_check", min_age=None, condition_codes=("diabetes",), source_id="ada-soc-2024-s12"
    ),
    ScreeningGuideline(
        "kidney_check",
        min_age=None,
        condition_codes=("diabetes", "high_blood_pressure", "kidneys"),
        source_id="kdigo-2012-ckd-screen",
    ),
)
"""The table. `min_age=None` with `condition_codes` set means the screening is due by a
condition alone, at any age (an eye check for diabetes)."""


def screenings_due(
    *, age: int | None, conditions: Sequence[str]
) -> tuple[ScreeningGuideline, ...]:
    """Every screening this table says is due for someone this age, with these conditions on
    file — age or any one condition code is enough; neither known says nothing is due, never
    a guess."""
    held = frozenset(conditions)
    due: list[ScreeningGuideline] = []
    for row in SCREENINGS:
        by_age = row.min_age is not None and age is not None and age >= row.min_age
        by_condition = bool(held & set(row.condition_codes))
        if by_age or by_condition:
            due.append(row)
    return tuple(due)


__all__ = ["SCREENINGS", "ScreeningGuideline", "screenings_due"]
