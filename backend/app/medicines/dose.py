"""The dose as a code, and the arithmetic over it.

A dose is how much, how often, and at which anchors of his day — never a sentence. The codes
are the ones a dispensing label uses in Malaysia and Singapore (`1 tab BD`, `1 biji 2 kali
sehari`), and `parse_dose_text` reads those two languages deterministically; anything it
cannot read is not guessed, it is asked. `daily_amount`, `count_remaining` and `reorder_date`
are the sums the module doc names in sections 2 and 3, and nothing more.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from app.errors import Refusal


class Frequency(StrEnum):
    """How often, as the label writes it."""

    OD = "od"  # once a day
    BD = "bd"  # twice a day
    TDS = "tds"  # three times a day
    QDS = "qds"  # four times a day
    WEEKLY = "weekly"
    PRN = "prn"  # when needed


TIMES_PER_DAY: dict[Frequency, int] = {
    Frequency.OD: 1,
    Frequency.BD: 2,
    Frequency.TDS: 3,
    Frequency.QDS: 4,
}


class Anchor(StrEnum):
    """The moments of his day a dose hangs on. Set once; never a clock time."""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    BED = "bed"


DEFAULT_ANCHORS: dict[Frequency, tuple[Anchor, ...]] = {
    Frequency.OD: (Anchor.BREAKFAST,),
    Frequency.BD: (Anchor.BREAKFAST, Anchor.DINNER),
    Frequency.TDS: (Anchor.BREAKFAST, Anchor.LUNCH, Anchor.DINNER),
    Frequency.QDS: (Anchor.BREAKFAST, Anchor.LUNCH, Anchor.DINNER, Anchor.BED),
    Frequency.WEEKLY: (Anchor.BREAKFAST,),
    Frequency.PRN: (),
}


class NotADose(Refusal):
    """A dose is a positive amount, a unit, a frequency and anchors that agree with it."""


class DoseNotRead(Refusal):
    """The words on the label could not be read as a dose. Ask the person; guess nothing."""


UNITS = frozenset({"tablet", "capsule", "unit", "ml", "puff", "drop", "sachet"})


@dataclass(frozen=True, slots=True)
class Dose:
    amount: float
    unit: str
    frequency: Frequency
    anchors: tuple[Anchor, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not (self.amount > 0) or math.isinf(self.amount):
            raise NotADose("a dose is a positive amount")
        if self.unit not in UNITS:
            raise NotADose(f"unit must be one of {sorted(UNITS)}")
        times = TIMES_PER_DAY.get(self.frequency)
        if times is not None and self.anchors and len(self.anchors) != times:
            raise NotADose(f"{self.frequency} takes {times} anchors, not {len(self.anchors)}")
        if self.frequency is Frequency.PRN and self.anchors:
            raise NotADose("a when-needed dose has no anchors")
        if self.frequency is Frequency.WEEKLY and len(self.anchors) > 1:
            raise NotADose("a weekly dose has one anchor")

    @property
    def scheduled_anchors(self) -> tuple[Anchor, ...]:
        """The anchors doses hang on: the ones given, or the default for the frequency."""
        return self.anchors or DEFAULT_ANCHORS[self.frequency]

    def as_json(self) -> dict[str, Any]:
        return {
            "amount": self.amount,
            "unit": self.unit,
            "frequency": self.frequency.value,
            "anchors": [anchor.value for anchor in self.anchors],
        }

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> Dose:
        return cls(
            amount=float(value["amount"]),
            unit=str(value["unit"]),
            frequency=Frequency(value["frequency"]),
            anchors=tuple(Anchor(a) for a in value.get("anchors", [])),
        )

    def same_as(self, other: Dose) -> bool:
        """The same amount, unit and frequency. Anchors are his routine, not the doctor's."""
        return (self.amount, self.unit, self.frequency) == (
            other.amount,
            other.unit,
            other.frequency,
        )


def daily_amount(dose: Dose) -> float | None:
    """Units a day at this schedule; a week's dose spread over seven; None when needed."""
    times = TIMES_PER_DAY.get(dose.frequency)
    if times is not None:
        return dose.amount * times
    if dose.frequency is Frequency.WEEKLY:
        return dose.amount / 7
    return None


def count_remaining(dispensed: float, taken: float) -> float:
    """What is left: everything dispensed minus every dose confirmed taken, never below nought."""
    return max(0.0, dispensed - taken)


def days_left(remaining: float, dose: Dose) -> int | None:
    """Whole days the remaining count lasts at the schedule; None for a when-needed dose."""
    a_day = daily_amount(dose)
    if a_day is None or a_day <= 0:
        return None
    return int(remaining // a_day)


def reorder_date(today: date, remaining: float, dose: Dose, lead_time_days: int) -> date | None:
    """today + days left − lead time; None for a when-needed dose. Never before today."""
    left = days_left(remaining, dose)
    if left is None:
        return None
    due = today + timedelta(days=left - lead_time_days)
    return max(due, today)


def reorder_due(remaining: float, dose: Dose, threshold_days: int) -> bool:
    """Whether the reorder card shows: fewer days left than the threshold."""
    left = days_left(remaining, dose)
    return left is not None and left < threshold_days


# --- reading a label ------------------------------------------------------------------------

_HALF = {"½": 0.5, "1/2": 0.5, "half": 0.5, "setengah": 0.5, "separuh": 0.5}
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "satu": 1, "dua": 2, "tiga": 3, "empat": 4}
_UNIT_WORDS = {
    "tab": "tablet",
    "tabs": "tablet",
    "tablet": "tablet",
    "tablets": "tablet",
    "biji": "tablet",
    "cap": "capsule",
    "caps": "capsule",
    "capsule": "capsule",
    "capsules": "capsule",
    "kapsul": "capsule",
    "unit": "unit",
    "units": "unit",
    "ml": "ml",
    "puff": "puff",
    "puffs": "puff",
}
_FREQUENCY = [
    # The many-times codes first: "twice daily" contains "daily".
    (re.compile(r"\b(qds|qid|four times (a|per) day|four times daily)\b"), Frequency.QDS),
    (re.compile(r"\b(tds|tid|three times (a|per) day|three times daily)\b"), Frequency.TDS),
    (re.compile(r"\b(bd|bid|twice (a|per) day|twice daily)\b"), Frequency.BD),
    (
        re.compile(
            r"\b(od|om|on|once (a|per) day|once daily|daily|every (day|morning|night)|nocte|mane)\b"
        ),
        Frequency.OD,
    ),
    (
        re.compile(r"\b(weekly|once a week|every week|seminggu sekali|sekali seminggu)\b"),
        Frequency.WEEKLY,
    ),
    (
        re.compile(
            r"\b(prn|when (needed|necessary|required)|as (needed|required)|bila perlu|jika perlu)\b"
        ),
        Frequency.PRN,
    ),
]
_MALAY_TIMES = re.compile(
    r"\b([1-4]|satu|dua|tiga|empat)\s*(kali|x)\s*(sehari|se hari|setiap hari)\b"
)
_MALAY_ONCE = re.compile(r"\b(sekali|1 kali)\s*(sehari|se hari|setiap hari)\b")
_ANCHORS = [
    (re.compile(r"\b(breakfast|sarapan|pagi|morning|mane|om)\b"), Anchor.BREAKFAST),
    (re.compile(r"\b(lunch|tengah ?hari|noon|midday)\b"), Anchor.LUNCH),
    (re.compile(r"\b(dinner|makan malam|evening|petang)\b"), Anchor.DINNER),
    (re.compile(r"\b(bed|bedtime|before sleep|sebelum tidur|nocte|night|malam|on)\b"), Anchor.BED),
]
_AMOUNT = re.compile(
    r"(?P<amount>½|1/2|\d+(?:\.\d+)?|half|setengah|separuh|one|two|three|four|satu|dua|tiga|empat)"
    r"\s*(?P<unit>tabs?|tablets?|biji|caps?|capsules?|kapsul|units?|ml|puffs?)\b"
)
_MALAY_COUNT = {1: Frequency.OD, 2: Frequency.BD, 3: Frequency.TDS, 4: Frequency.QDS}


def parse_dose_text(text: str) -> Dose:
    """Read `1 tab BD`, `1 biji 2 kali sehari`, `½ tablet once daily` and the like.

    English and Malay, the way a dispensing label in Malaysia or Singapore writes them.
    Anything else raises `DoseNotRead`; nothing is filled in from a standard regimen.
    """
    words = " ".join(text.lower().replace(",", " ").split())
    amount_match = _AMOUNT.search(words)
    if amount_match is None:
        raise DoseNotRead("no amount and unit on the label")
    raw = amount_match.group("amount")
    amount = _HALF.get(raw) or _WORDS.get(raw) or float(raw)
    unit = _UNIT_WORDS[amount_match.group("unit")]
    rest = words[amount_match.end() :]

    frequency: Frequency | None = None
    malay = _MALAY_TIMES.search(rest)
    if malay is not None:
        times = _WORDS.get(malay.group(1)) or int(malay.group(1))
        frequency = _MALAY_COUNT[times]
    elif _MALAY_ONCE.search(rest):
        frequency = Frequency.OD
    else:
        for pattern, code in _FREQUENCY:
            if pattern.search(rest):
                frequency = code
                break
    if frequency is None:
        raise DoseNotRead("no frequency on the label")

    anchors: list[Anchor] = []
    for pattern, anchor in _ANCHORS:
        if pattern.search(rest) and anchor not in anchors:
            anchors.append(anchor)
    a_day = TIMES_PER_DAY.get(frequency)
    if frequency is Frequency.PRN or (a_day is not None and len(anchors) != a_day):
        anchors = []
    if frequency is Frequency.WEEKLY:
        anchors = anchors[:1]
    return Dose(amount=float(amount), unit=unit, frequency=frequency, anchors=tuple(anchors))
