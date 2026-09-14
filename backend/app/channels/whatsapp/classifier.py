"""The classifier: what kind of message this is, and what it proposes (E19-02).

Every inbound message is one of four kinds — a document, a health event, coordination, or
everything else — plus the two the thread itself needs: an answer to an open question, and
"ignore", which is honoured absolutely. The classifier never writes anything. For a health
event it returns a *proposal*: the fact it heard (subject, attribute, value, unit) and the
event it would rest on, for the poster to confirm. `Classifier` is a port; `RuleClassifier`
is the rule-based adapter that ships, and a model behind the same protocol can replace it
without the thread changing: the thread reads a `Classification`, never the rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from app.memory.models import EventKind


class Kind(StrEnum):
    DOCUMENT = "document"
    HEALTH_EVENT = "health_event"
    COORDINATION = "coordination"
    ANSWER = "answer"
    IGNORE = "ignore"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class HealthEvent:
    """What was heard, as the fact it would become and the event it would rest on.

    `said` names the read-back the poster is asked (`strings.REPLIES["propose_<said>"]`),
    with `words` as its slots. `word` is the feeling word, when there is one, from the fixed
    vocabulary and no other.
    """

    subject: str
    attribute: str
    value: Any
    unit: str | None
    event_kind: EventKind
    said: str
    words: Mapping[str, str]
    word: str | None = None


@dataclass(frozen=True, slots=True)
class Classification:
    kind: Kind
    event: HealthEvent | None = None
    answer: bool | None = None
    """For an ANSWER: True for yes, False for no."""
    matched: str | None = None
    """Which rule matched, for a test and the log. Never shown to a person."""


class Classifier(Protocol):
    def classify(self, *, text: str | None, content_type: str | None) -> Classification: ...


IGNORE_PREFIX = re.compile(r"^\s*(?:ignore|abaikan|忽略)\b", re.IGNORECASE)

YES = re.compile(
    r"^\s*(?:yes|ya|betul|ok|okay|yup|correct|对|是|是的|好|✅|👍)\s*[.!]?\s*$", re.IGNORECASE
)
NO = re.compile(
    r"^\s*(?:no|nope|tidak|tak|salah|bukan|不|不是|不对|错|❌|👎)\s*[.!]?\s*$", re.IGNORECASE
)

BLOOD_PRESSURE = re.compile(
    r"(?:\bbp\b|blood pressure|tekanan(?: darah)?|血压)\D{0,24}?(\d{2,3})\s*[/／比]\s*(\d{2,3})"
    r"|(?<![\d/])(\d{2,3})\s*/\s*(\d{2,3})(?![\d/])",
    re.IGNORECASE,
)
BLOOD_SUGAR = re.compile(
    r"(?:\bsugar\b|glucose|\bgula\b|血糖)\D{0,24}?(\d{1,2}(?:[.,]\d)?)", re.IGNORECASE
)
WEIGHT = re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*(?:kg|kilo|kilos|公斤)\b", re.IGNORECASE)
TAKEN = re.compile(
    r"\b(?:took|taken|has taken|had|ate|dah makan|sudah makan|sudah ambil|dah ambil)\b.{0,30}?"
    r"\b(?:pill|pills|tablet|tablets|medicine|medicines|meds|ubat|药)|吃了药|吃过药|吃药了",
    re.IGNORECASE,
)
FEELING: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pain", re.compile(r"\b(?:pain|painful|hurts?|sakit|痛)\b|痛", re.IGNORECASE)),
    ("tired", re.compile(r"\b(?:tired|weak|letih|penat|lemah|累)\b|累", re.IGNORECASE)),
    (
        "ok",
        re.compile(r"^\s*(?:ok|okay|fine|good|baik|sihat|好|还好|很好)\s*[.!]?\s*$", re.IGNORECASE),
    ),
)
SYMPTOM = re.compile(
    r"\b(?:dizzy|giddy|vomit|vomited|vomiting|fever|feverish|cough|coughing|diarrh(?:o)?ea|"
    r"pening|muntah|demam|batuk|cirit)\b|(?:头晕|发烧|呕吐|咳嗽|拉肚子)",
    re.IGNORECASE,
)
COORDINATION = re.compile(
    r"\b(?:who is taking|who will take|who can|can you|could you|i can (?:drive|take|bring|fetch)|"
    r"i'?ll (?:drive|take|bring|fetch)|pick (?:him|her|pa|ma) up|fetch|drive|"
    r"siapa (?:bawa|ambil|boleh)|boleh (?:tak|ke)|saya boleh|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|next week|"
    r"isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|esok|minggu depan)\b|"
    r"(?:谁带|谁送|谁去|你可以|我可以|明天|下星期|星期[一二三四五六日天])",
    re.IGNORECASE,
)
IMAGE = re.compile(r"^image/", re.IGNORECASE)
PDF = "application/pdf"


def _number(text: str) -> float:
    return float(text.replace(",", "."))


class RuleClassifier:
    """Rules, in the order they are tried: ignore, answer, document, health event,
    coordination, other. The first to match decides."""

    def classify(self, *, text: str | None, content_type: str | None) -> Classification:
        body = (text or "").strip()
        if body and IGNORE_PREFIX.match(body):
            return Classification(Kind.IGNORE, matched="ignore")
        if body and YES.match(body):
            return Classification(Kind.ANSWER, answer=True, matched="yes")
        if body and NO.match(body):
            return Classification(Kind.ANSWER, answer=False, matched="no")
        if content_type and (IMAGE.match(content_type) or content_type.lower() == PDF):
            return Classification(Kind.DOCUMENT, matched="media")
        if not body:
            return Classification(Kind.OTHER, matched="empty")
        event = self._health_event(body)
        if event is not None:
            return Classification(Kind.HEALTH_EVENT, event=event, matched=event.said)
        if COORDINATION.search(body):
            return Classification(Kind.COORDINATION, matched="coordination")
        return Classification(Kind.OTHER, matched="other")

    def _health_event(self, body: str) -> HealthEvent | None:
        pressure = BLOOD_PRESSURE.search(body)
        if pressure:
            top, bottom = (g for g in pressure.groups() if g is not None)
            return HealthEvent(
                subject="blood_pressure",
                attribute="reading",
                value={"systolic": int(top), "diastolic": int(bottom)},
                unit="mmHg",
                event_kind=EventKind.READING,
                said="blood_pressure",
                words={"top": top, "bottom": bottom},
            )
        weight = WEIGHT.search(body)
        if weight:
            kilos = _number(weight.group(1))
            shown = str(int(kilos)) if kilos.is_integer() else str(kilos)
            return HealthEvent(
                subject="weight",
                attribute="reading",
                value=kilos,
                unit="kg",
                event_kind=EventKind.READING,
                said="weight",
                words={"weight": shown},
            )
        sugar = BLOOD_SUGAR.search(body)
        if sugar:
            level = _number(sugar.group(1))
            shown = str(int(level)) if level.is_integer() else str(level)
            return HealthEvent(
                subject="blood_sugar",
                attribute="reading",
                value=level,
                unit="mmol/L",
                event_kind=EventKind.READING,
                said="blood_sugar",
                words={"value": shown},
            )
        if TAKEN.search(body):
            return HealthEvent(
                subject="medication",
                attribute="taken",
                value={"reported": True},
                unit=None,
                event_kind=EventKind.DOSE_TAKEN,
                said="taken",
                words={},
            )
        for word, pattern in FEELING:
            if pattern.search(body):
                return HealthEvent(
                    subject="feeling",
                    attribute="reported",
                    value=word,
                    unit=None,
                    event_kind=EventKind.SYMPTOM,
                    said="feeling",
                    words={},
                    word=word,
                )
        if SYMPTOM.search(body):
            return HealthEvent(
                subject="feeling",
                attribute="reported",
                value="unwell",
                unit=None,
                event_kind=EventKind.SYMPTOM,
                said="unwell",
                words={},
            )
        return None
