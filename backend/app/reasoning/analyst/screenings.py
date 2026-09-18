"""Screenings due: a small, sourced guideline table, and the pure function that reads it.

The same standing as `app.reasoning.ranges`' fixture: published guidance, named by source id
here and cited below, awaiting a clinician's sign-off before it is used for anyone real
(`docs/trust/samd-boundary-review.md`, the `insight` row). Eligibility, then "already had it":
a screening a person is eligible for by age or by a condition he has told Nura about is due
unless `last_done` — the most recent matching fact the caller found on his record, by
`fact_subjects` below — falls inside `interval_months` of `today`. `fact_subjects` is never a
list of its own: it is `app.onboarding.gaps`'s own subject sets for exactly these three parts
of the record (cholesterol, sugar, kidney), the source of truth for what a lab panel or a
vital is filed under, so a subject the extractor learns to write under later still closes this
gap the moment it closes that one, never a second list to keep in step by hand
(`.claude/rules` — "a rule keyed on a hard-coded list ... must be checked against the source
of truth"). `eye_check` names no subject: nothing on the record today extracts an eye exam as
a fact, so it is read as never done, the same reading this module held to before this fix,
named here rather than silently assumed.

Sources:
- uspstf-lipid-2016: USPSTF, Screening for Lipid Disorders in Adults, 2016: screen adults 40
  and over for lipid disorders; a five-year repeat is the commonly cited interval for someone
  not already on treatment.
- ada-soc-2024-s3: American Diabetes Association, Standards of Care in Diabetes 2024, Section
  3, Table 3.1: screen adults 35 and over for type 2 diabetes; screen earlier and more often
  with a risk factor; repeat at a minimum of three-year intervals if normal.
- ada-soc-2024-s12: American Diabetes Association, Standards of Care in Diabetes 2024, Section
  12: annual comprehensive eye examination for people with diabetes.
- kdigo-2012-ckd-screen: KDIGO 2012 CKD guideline, Kidney Int Suppl 2013;3(1): screen adults
  with diabetes or high blood pressure for chronic kidney disease, at least annually.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.onboarding.gaps import CHOLESTEROL_SUBJECTS, KIDNEY_SUBJECTS, SUGAR_SUBJECTS


@dataclass(frozen=True, slots=True)
class ScreeningGuideline:
    key: str
    min_age: int | None
    condition_codes: tuple[str, ...]
    """Any one of these conditions (`app.onboarding.conditions`, by code) also makes the
    screening due, whatever his age — an empty tuple means age is the only door."""
    source_id: str
    interval_months: int
    """How often this screening repeats, from the same source (`source_id`): a screening
    found done, by a fact under `fact_subjects`, more recently than this is not due."""
    fact_subjects: frozenset[str] = frozenset()
    """Which `Fact.subject` names, read by the caller under RECORDS, count as this screening
    already being done — empty when no such subject exists yet (`eye_check`)."""


SCREENINGS: tuple[ScreeningGuideline, ...] = (
    ScreeningGuideline(
        "cholesterol_test",
        min_age=40,
        condition_codes=(),
        source_id="uspstf-lipid-2016",
        interval_months=60,
        fact_subjects=CHOLESTEROL_SUBJECTS,
    ),
    ScreeningGuideline(
        "diabetes_screening",
        min_age=35,
        condition_codes=("diabetes",),
        source_id="ada-soc-2024-s3",
        interval_months=36,
        fact_subjects=SUGAR_SUBJECTS,
    ),
    ScreeningGuideline(
        "eye_check",
        min_age=None,
        condition_codes=("diabetes",),
        source_id="ada-soc-2024-s12",
        interval_months=12,
    ),
    ScreeningGuideline(
        "kidney_check",
        min_age=None,
        condition_codes=("diabetes", "high_blood_pressure", "kidneys"),
        source_id="kdigo-2012-ckd-screen",
        interval_months=12,
        fact_subjects=KIDNEY_SUBJECTS,
    ),
)
"""The table. `min_age=None` with `condition_codes` set means the screening is due by a
condition alone, at any age (an eye check for diabetes)."""


def screenings_due(
    *,
    age: int | None,
    conditions: Sequence[str],
    last_done: Mapping[str, date] | None = None,
    today: date | None = None,
) -> tuple[ScreeningGuideline, ...]:
    """Every screening this table says is due for someone this age, with these conditions on
    file — age or any one condition code is enough; neither known says nothing is due, never
    a guess. Eligible, then not already done: `last_done` is the caller's own finding (the
    newest fact under each screening's `fact_subjects`, `app.reasoning.analyst.rule`), and a
    screening found done within `interval_months` of `today` is not due — `last_done` with no
    entry for a key, or `today` left `None`, means every eligible screening stays due, the
    same reading this function always gave before `last_done` existed."""
    held = frozenset(conditions)
    known_done = last_done or {}
    due: list[ScreeningGuideline] = []
    for row in SCREENINGS:
        by_age = row.min_age is not None and age is not None and age >= row.min_age
        by_condition = bool(held & set(row.condition_codes))
        if not (by_age or by_condition):
            continue
        done_on = known_done.get(row.key)
        if done_on is not None and today is not None and (today - done_on).days < row.interval_months * 30:
            continue
        due.append(row)
    return tuple(due)


__all__ = ["SCREENINGS", "ScreeningGuideline", "screenings_due"]
