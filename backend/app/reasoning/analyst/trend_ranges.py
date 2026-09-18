"""A small, sourced band table for the two blood-pressure numbers RE-03's series reads
(`app.reasoning.patterns.series.SeriesKind.BP_SYSTOLIC`/`BP_DIASTOLIC`), for "what changed".

This is deliberately its own table, not an addition to `app.reasoning.ranges.FixtureRanges`
(the lab trend's own fixture, E09-01): that fixture's analytes are lab-panel results
(cholesterol, HbA1c, kidney, haemoglobin, TSH), and `tests/test_trends.py` asserts the exact
set of analyte ids and the exact set of `trend_strings.NAMES` keys against it — adding an
analyte there would mean editing that feature's own test file, another story's, for a table
this one only reads two rows of. Same standing as the lab fixture (a source id, cited below,
awaiting a clinician's sign-off before it is used for anyone real), just kept apart so the two
features' own tests never have to agree on one shared shape.

Source: Whelton PK et al. 2017 ACC/AHA/AAPA/ABC/ACPM/AGS/APhA/ASH/ASPC/NMA/PCNA Guideline for
High Blood Pressure. Hypertension 2018;71(6):e13-e115: normal blood pressure is under 120/80
mmHg; 120 mmHg or more systolic, or 80 mmHg or more diastolic, is elevated or higher.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Band(StrEnum):
    IN = "in"
    ABOVE = "above"


SOURCE_ID = "acc-aha-2017-htn"


@dataclass(frozen=True, slots=True)
class BpBand:
    upper: int
    """120 mmHg or more (systolic) / 80 mmHg or more (diastolic) is `Band.ABOVE`; below it is
    `Band.IN`. Adults only (18 and over) — the one guideline this table holds."""


SYSTOLIC = BpBand(upper=120)
DIASTOLIC = BpBand(upper=80)


def band_of(value: float, band: BpBand) -> Band:
    return Band.IN if value < band.upper else Band.ABOVE


__all__ = ["DIASTOLIC", "SOURCE_ID", "SYSTOLIC", "Band", "BpBand", "band_of"]
