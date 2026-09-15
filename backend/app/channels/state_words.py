"""The State in words, for the chief's Home hero (docs/design-system.md §4, Hero).

The State arranges what is known and does not judge it (`app/state/dimensions.py`): its
posture is a code and its reasons are codes and ids. Here those codes are said in plain words
and nothing more — the posture as one word and one line, and what raised it as short chips
(a condition a clinician's own word put at watch, an open episode, the week of a visit). A code
this table has no words for is left out, never turned into text: a line is never assembled
from a code. Every word is here in English, Malay and Chinese, under the same key, so the
translation memory (`make language`) holds the three to one another.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.state.models import Dimension, Posture

LANGUAGES = ("en", "ms", "zh")

# @patient headline
POSTURE_WORD: Mapping[str, Mapping[str, str]] = {
    "en": {"stable": "Stable", "watch": "Watch", "act": "Act today"},
    "ms": {"stable": "Stabil", "watch": "Perhatikan", "act": "Bertindak hari ini"},
    "zh": {"stable": "平稳", "watch": "留意", "act": "今天要处理"},
}
"""The posture as one word, large on the wash."""

# @patient
POSTURE_LINE: Mapping[str, Mapping[str, str]] = {
    "en": {
        "stable": "Nothing needs you today.",
        "watch": "Something is worth a look this week.",
        "act": "Someone should look at this today.",
    },
    "ms": {
        "stable": "Tiada apa yang perlu anda buat hari ini.",
        "watch": "Ada perkara yang elok dilihat minggu ini.",
        "act": "Seseorang perlu melihat perkara ini hari ini.",
    },
    "zh": {
        "stable": "今天没有需要您处理的事。",
        "watch": "这周有件事值得看一看。",
        "act": "今天需要有人看一看。",
    },
}
"""The one line under the word."""

# @patient phrase
SUBJECT_CHIP: Mapping[str, Mapping[str, str]] = {
    "en": {
        "blood_pressure": "Blood pressure",
        "hypertension": "Blood pressure",
        "blood_sugar": "Sugar",
        "diabetes": "Sugar",
        "kidney": "Kidneys",
        "heart": "Heart",
        "lipid_panel": "Cholesterol",
        "weight": "Weight",
        "mobility": "Walking",
        "falls": "Falls",
    },
    "ms": {
        "blood_pressure": "Tekanan darah",
        "hypertension": "Tekanan darah",
        "blood_sugar": "Gula",
        "diabetes": "Gula",
        "kidney": "Buah pinggang",
        "heart": "Jantung",
        "lipid_panel": "Kolesterol",
        "weight": "Berat badan",
        "mobility": "Berjalan",
        "falls": "Jatuh",
    },
    "zh": {
        "blood_pressure": "血压",
        "hypertension": "血压",
        "blood_sugar": "血糖",
        "diabetes": "血糖",
        "kidney": "肾",
        "heart": "心脏",
        "lipid_panel": "胆固醇",
        "weight": "体重",
        "mobility": "走路",
        "falls": "跌倒",
    },
}
"""A subject a clinician's word put at watch or act, as a chip."""

# @patient phrase
EPISODE_CHIP: Mapping[str, Mapping[str, str]] = {
    "en": {"illness": "Not well", "recovery": "Getting better", "admission": "In hospital"},
    "ms": {"illness": "Tidak sihat", "recovery": "Semakin pulih", "admission": "Di hospital"},
    "zh": {"illness": "身体不舒服", "recovery": "正在好转", "admission": "在住院"},
}
"""An open episode that raised the State, as a chip."""

# @patient phrase
PHASE_CHIP: Mapping[str, Mapping[str, str]] = {
    "en": {
        "before_visit": "A visit this week",
        "in_visit": "At a visit now",
        "after_visit": "Back from a visit",
        "after_discharge": "Home from hospital",
    },
    "ms": {
        "before_visit": "Lawatan minggu ini",
        "in_visit": "Sedang di lawatan",
        "after_visit": "Baru balik dari lawatan",
        "after_discharge": "Baru keluar hospital",
    },
    "zh": {
        "before_visit": "这周要看医生",
        "in_visit": "正在看医生",
        "after_visit": "刚看完医生",
        "after_discharge": "刚出院",
    },
}
"""Where he is in the rhythm of visits and discharges, when it is not a steady week."""


@dataclass(frozen=True, slots=True)
class Driver:
    key: str
    text: str
    tone: str | None


@dataclass(frozen=True, slots=True)
class Said:
    word: str
    line: str
    drivers: tuple[Driver, ...]


def _language(asked: str | None) -> str:
    code = (asked or "").lower()[:2]
    return code if code in LANGUAGES else "en"


def _tone(value: Any) -> str | None:
    return value if value in (Posture.WATCH.value, Posture.ACT.value) else None


def drivers(
    dimensions: Mapping[Dimension, Mapping[str, Any] | None], language: str
) -> list[Driver]:
    """What raised the posture, from the dimensions this key reads: every reason a dimension
    gives (`because`) that this table has words for, then the phase of the visit rhythm. Once
    each, in the order the State gives them."""
    lang = _language(language)
    found: list[Driver] = []
    seen: set[str] = set()

    def add(key: str, text: str | None, tone: str | None) -> None:
        if text is None or key in seen:
            return
        seen.add(key)
        found.append(Driver(key=key, text=text, tone=tone))

    for dimension in Dimension:
        held = dimensions.get(dimension)
        if not held:
            continue
        because: Sequence[Mapping[str, Any]] = held.get("because") or ()
        for reason in because:
            tone = _tone(reason.get("posture"))
            subject = reason.get("subject")
            kind = reason.get("episode_kind")
            phase = reason.get("phase")
            if isinstance(subject, str):
                add(f"subject:{subject}", SUBJECT_CHIP[lang].get(subject), tone)
            elif isinstance(kind, str):
                add(f"episode:{kind}", EPISODE_CHIP[lang].get(kind), tone)
            elif isinstance(phase, str):
                add(f"phase:{phase}", PHASE_CHIP[lang].get(phase), tone)
    situational = dimensions.get(Dimension.SITUATIONAL) or {}
    phase = situational.get("phase")
    if isinstance(phase, str):
        add(f"phase:{phase}", PHASE_CHIP[lang].get(phase), None)
    return found


def said(
    posture: Posture, dimensions: Mapping[Dimension, Mapping[str, Any] | None], language: str | None
) -> Said:
    """The posture's word and line, and its drivers, in `language` (English when Nura does not
    speak it)."""
    lang = _language(language)
    return Said(
        word=POSTURE_WORD[lang][posture.value],
        line=POSTURE_LINE[lang][posture.value],
        drivers=tuple(drivers(dimensions, lang)),
    )
