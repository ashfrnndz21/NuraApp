"""Reference ranges: the port the lab trend reads them through, and the fixture behind it.

A range is looked up for one analyte, for one person, on one day: his age band, his sex when
the record holds it, and the lab when the report names one. A lab's own printed range wins
over the guideline table for that analyte; otherwise the guideline row for his band answers.
Where the table needs a fact the record does not hold — a sex-specific range and no sex on
file, an age-specific one and no birth year — there is no range, and the reason says which.
Nothing is filled in from a default person.

The fixture (`FixtureRanges`) reads `backend/tests/fixtures/labs/ranges.json`. Its rows come
from published tables, named by source id in the file and cited here:

- ncep-atp3-2001: NCEP ATP III, JAMA 2001;285:2486-97, Table 2 (lipids).
- ada-soc-2024-s2: ADA Standards of Care in Diabetes 2024, Section 2, Table 2.5 (HbA1c).
- kdigo-2012-ckd: KDIGO 2012 CKD guideline, Kidney Int Suppl 2013;3(1), Figure 2 (eGFR).
- aacb-harmonised-2014: Tate et al., Clin Biochem Rev 2014;35:213-35 (potassium, creatinine).
- who-2011-haemoglobin: WHO/NMH/NHD/MNM/11.1, Table 1 (haemoglobin).
- surks-hollowell-2007: J Clin Endocrinol Metab 2007;92:4575-82 (TSH by age).

The fixture needs a clinician's sign-off (LDL target, TSH age bands) before it is used
for anyone real.

A licensed table arrives as a second class behind the same port, chosen in
`reference_ranges_for`, and nothing above this module changes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Protocol

from app.settings import Settings

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "labs" / "ranges.json"
FIXTURE = "fixture"
ADULT_AGE = 18


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class RangeSource(StrEnum):
    """Where a range came from: the lab's own printed range, or the guideline table."""

    LAB = "lab"
    GUIDELINE = "guideline"


class Band(StrEnum):
    """Where one value sits against its range. Arithmetic, not a judgement."""

    IN = "in"
    ABOVE = "above"
    BELOW = "below"
    NOT_COMPARED = "not_compared"
    """No range fits him, or the number is in a unit the range cannot be put in."""


class NoRangeBecause(StrEnum):
    NEEDS_AGE = "needs_age"
    NEEDS_SEX = "needs_sex"
    NONE_ON_FILE = "none_on_file"


@dataclass(frozen=True, slots=True)
class Analyte:
    """One thing a blood test measures, the fact it is stored as, and its units."""

    id: str
    subject: str
    attribute: str
    unit: str
    factors: Mapping[str, float]
    """Multiply a value in this unit by the factor to get it in `unit`."""

    def factor_for(self, unit: str | None) -> float | None:
        """How to bring a value in `unit` to the analyte's own unit, or None when it cannot be."""
        if unit is None or unit == self.unit:
            return 1.0
        return self.factors.get(unit)


@dataclass(frozen=True, slots=True)
class Range:
    """The range for one analyte, in the analyte's own unit, and where it came from."""

    analyte: str
    lower: float | None
    upper: float | None
    unit: str
    source: RangeSource
    source_id: str
    min_age: int | None
    max_age: int | None
    sex: Sex | None
    lab: str | None = None

    def band_of(self, value: float) -> Band:
        """Upper-only ranges read "under" (exclusive), lower-only "or more" (inclusive), and a
        two-sided range is inclusive at both ends — the way the tables print them."""
        if self.lower is not None and self.upper is not None:
            if value < self.lower:
                return Band.BELOW
            return Band.ABOVE if value > self.upper else Band.IN
        if self.upper is not None:
            return Band.IN if value < self.upper else Band.ABOVE
        if self.lower is not None:
            return Band.IN if value >= self.lower else Band.BELOW
        return Band.NOT_COMPARED


@dataclass(frozen=True, slots=True)
class RangeAnswer:
    range: Range | None
    because: NoRangeBecause | None = None


class ReferenceRanges(Protocol):
    """The port: which analytes there are, and the range that fits one person on one day."""

    def analytes(self) -> Sequence[Analyte]: ...

    def analyte(self, analyte_id: str) -> Analyte | None: ...

    def range_for(
        self, analyte_id: str, *, age: int | None, sex: Sex | None, lab: str | None
    ) -> RangeAnswer: ...


def age_from_decade(birth_year: int, on: date) -> int:
    """His age on `on`, read from the decade he was born in: the middle of the decade stands
    for the year. Born 1951 is born in the 1950s, so 68 in 2023 and 70 in 2025. The exact year
    never enters the band; only the decade does."""
    return on.year - (birth_year // 10 * 10 + 5)


def _fits(row: Mapping[str, Any], *, age: int | None, sex: Sex | None) -> bool | NoRangeBecause:
    lo, hi = row.get("min_age"), row.get("max_age")
    specific_age = (lo is not None and lo > ADULT_AGE) or hi is not None
    if age is None:
        if specific_age:
            return NoRangeBecause.NEEDS_AGE
    elif (lo is not None and age < lo) or (hi is not None and age > hi):
        return False
    wanted = row.get("sex")
    if wanted is not None:
        if sex is None:
            return NoRangeBecause.NEEDS_SEX
        return Sex(wanted) is sex
    return True


def _pick(
    rows: Sequence[Mapping[str, Any]], *, age: int | None, sex: Sex | None
) -> Mapping[str, Any] | NoRangeBecause:
    missing: NoRangeBecause | None = None
    for row in rows:
        fits = _fits(row, age=age, sex=sex)
        if fits is True:
            return row
        if isinstance(fits, NoRangeBecause):
            missing = missing or fits
    return missing or NoRangeBecause.NONE_ON_FILE


class FixtureRanges:
    """The fixture table, read from one JSON file. Pure lookups; nothing is written."""

    FIXTURE: ClassVar[bool] = True
    """A fixture: runs only on a declared dev run or demo (`app.fixtures`)."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = data
        self._analytes = {
            key: Analyte(
                id=key,
                subject=str(entry["subject"]),
                attribute=str(entry["attribute"]),
                unit=str(entry["unit"]),
                factors={unit: float(factor) for unit, factor in entry.get("factors", {}).items()},
            )
            for key, entry in data["analytes"].items()
        }

    @classmethod
    def load(cls, path: Path = FIXTURE_PATH) -> FixtureRanges:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def sources(self) -> Mapping[str, str]:
        found: Mapping[str, str] = self._data.get("sources", {})
        return found

    def analytes(self) -> Sequence[Analyte]:
        return list(self._analytes.values())

    def analyte(self, analyte_id: str) -> Analyte | None:
        return self._analytes.get(analyte_id)

    def range_for(
        self, analyte_id: str, *, age: int | None, sex: Sex | None, lab: str | None
    ) -> RangeAnswer:
        analyte = self._analytes.get(analyte_id)
        if analyte is None:
            return RangeAnswer(None, NoRangeBecause.NONE_ON_FILE)
        if lab is not None:
            printed = self._data.get("labs", {}).get(lab, {}).get("analytes", {}).get(analyte_id)
            if printed:
                row = _pick(printed, age=age, sex=sex)
                if not isinstance(row, NoRangeBecause):
                    return RangeAnswer(self._range(analyte, row, RangeSource.LAB, f"lab:{lab}", lab))
        rows = self._data["analytes"][analyte_id]["bands"]
        row = _pick(rows, age=age, sex=sex)
        if isinstance(row, NoRangeBecause):
            return RangeAnswer(None, row)
        return RangeAnswer(self._range(analyte, row, RangeSource.GUIDELINE, str(row["source"])))

    @staticmethod
    def _range(
        analyte: Analyte,
        row: Mapping[str, Any],
        source: RangeSource,
        source_id: str,
        lab: str | None = None,
    ) -> Range:
        def number(key: str) -> float | None:
            value = row.get(key)
            return None if value is None else float(value)

        return Range(
            analyte=analyte.id,
            lower=number("lower"),
            upper=number("upper"),
            unit=analyte.unit,
            source=source,
            source_id=source_id,
            min_age=row.get("min_age"),
            max_age=row.get("max_age"),
            sex=None if row.get("sex") is None else Sex(row["sex"]),
            lab=lab,
        )


class NoReferenceRanges(RuntimeError):
    """The deployment names a range table this build does not have."""


def reference_ranges_for(settings: Settings) -> ReferenceRanges:
    """The table a deployment runs on. Only the fixture is built; anything else refuses to
    start rather than show a range that is not what it says."""
    if settings.reference_ranges == FIXTURE:
        return FixtureRanges.load()
    raise NoReferenceRanges(
        f"no reference ranges named {settings.reference_ranges!r}; only {FIXTURE!r} is built. "
        "Set NURA_REFERENCE_RANGES=fixture for a local run"
    )
