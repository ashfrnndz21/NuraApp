"""The cost expectation's cached benchmark table (T3): a small, hand-reviewed catalogue of
public fee benchmarks — Singapore's MOH fee-benchmark comparisons and hospital published
bills, Malaysia's MOH fee schedules — each row naming the publisher, the page it came from
and the day it was last checked. This is data, refreshed by a person re-reading the publisher's
page and editing the numbers below, never a number Nura invents or averages from something it
was not told. `RuleEstimator` (`app.insurance.cost_expectation`) is the only reader.

A row is matched to a visit or a procedure by keyword, case-insensitively, against whatever
plain words name it (an `Appointment.purpose`, or a procedure a letter named): the first row
in table order whose keyword appears in that text wins, so two runs over the same words always
pick the same row (the "any latest query needs a deterministic tie-breaker" rule — there is no
tie here to begin with, since table order is fixed and a `find_benchmark` call never sees the
same text match two rows differently between runs).

Every amount is in minor units (cents/sen), the same unit the rest of the insurance module
already keeps money in (`app.insurance.strings.say_money`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.regions import Region

__all__ = ["BENCHMARKS", "BenchmarkEntry", "find_benchmark"]


@dataclass(frozen=True, slots=True)
class BenchmarkEntry:
    """One public fee benchmark: a typical low-to-high range, in minor units, as one
    publisher's page states it on the day it was last read."""

    keywords: tuple[str, ...]
    region: Region
    low_cents: int
    high_cents: int
    publisher: str
    url: str
    fetched_at: date


# The seed table (2026-03-01 read). A pharmacist or the ops reviewer refreshes a row by
# re-reading the publisher's own page and editing its numbers and `fetched_at` here — the
# same "data, reviewed, not a code change made in passing" discipline `app.delivery.feed.
# sources.SEED` already keeps for the allowlist these publishers sit on.
BENCHMARKS: tuple[BenchmarkEntry, ...] = (
    BenchmarkEntry(
        keywords=("consult", "follow-up", "follow up", "review", "check-up", "checkup"),
        region=Region.SG,
        low_cents=3800,
        high_cents=21500,
        publisher="Ministry of Health Singapore",
        url="https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("blood test", "lab test", "lab panel", "blood panel"),
        region=Region.SG,
        low_cents=4000,
        high_cents=15000,
        publisher="Ministry of Health Singapore",
        url="https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("x-ray", "xray", "scan", "imaging", "mri", "ct "),
        region=Region.SG,
        low_cents=8000,
        high_cents=45000,
        publisher="Ministry of Health Singapore",
        url="https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("physio", "physiotherapy", "rehab"),
        region=Region.SG,
        low_cents=6000,
        high_cents=18000,
        publisher="Ministry of Health Singapore",
        url="https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("surgery", "operation", "procedure", "admission"),
        region=Region.SG,
        low_cents=500_000,
        high_cents=3_000_000,
        publisher="Ministry of Health Singapore — Hospital Bill Browser",
        url="https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("consult", "follow-up", "follow up", "review", "check-up", "checkup"),
        region=Region.MY,
        low_cents=3000,
        high_cents=15000,
        publisher="Ministry of Health Malaysia",
        url="https://www.moh.gov.my/index.php/pages/view/153",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("blood test", "lab test", "lab panel", "blood panel"),
        region=Region.MY,
        low_cents=2500,
        high_cents=12000,
        publisher="Ministry of Health Malaysia",
        url="https://www.moh.gov.my/index.php/pages/view/153",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("x-ray", "xray", "scan", "imaging", "mri", "ct "),
        region=Region.MY,
        low_cents=4000,
        high_cents=35000,
        publisher="Ministry of Health Malaysia",
        url="https://www.moh.gov.my/index.php/pages/view/153",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("physio", "physiotherapy", "rehab"),
        region=Region.MY,
        low_cents=3500,
        high_cents=12000,
        publisher="Ministry of Health Malaysia",
        url="https://www.moh.gov.my/index.php/pages/view/153",
        fetched_at=date(2026, 3, 1),
    ),
    BenchmarkEntry(
        keywords=("surgery", "operation", "procedure", "admission"),
        region=Region.MY,
        low_cents=300_000,
        high_cents=2_000_000,
        publisher="Ministry of Health Malaysia",
        url="https://www.moh.gov.my/index.php/pages/view/153",
        fetched_at=date(2026, 3, 1),
    ),
)


def find_benchmark(visit_or_procedure: str, region: Region) -> BenchmarkEntry | None:
    """The first row, in table order, whose keyword appears in these words, for this region —
    or None, said plainly by the caller as "no typical fee found" rather than guessed at."""
    words = visit_or_procedure.lower()
    for entry in BENCHMARKS:
        if entry.region is not region:
            continue
        if any(keyword in words for keyword in entry.keywords):
            return entry
    return None
