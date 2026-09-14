"""Extraction: what a photo says, as fields with confidence, behind one interface.

An `Extractor` takes the bytes and answers with an `Extraction`: a guess at what kind of
document it is, the date on the document, and fields — each a proposed statement (subject,
attribute, value, unit) with how sure the extractor is and, where it can say, where on the
page it read it. Nothing here is a fact: a field is a proposal for the review card, and only
a person's yes turns it into one (`app.ingestion.review`).

The real extractor — OCR and a vision model in the profile's region — is a later adapter.
`FixtureExtractor` is what runs in the tests and on a laptop: it knows a handful of redacted
papers by the digest of their bytes and answers from a JSON file for each
(`backend/tests/fixtures/paper/`). A photo it does not know is `UNKNOWN` with no fields,
which is also the honest answer a real extractor gives when it cannot read a page.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from app.errors import Refusal
from app.ingestion.objects import sha256_of
from app.regions import Region


class DocumentKind(StrEnum):
    """What kind of paper this looks like. A guess, shown on the card, never a fact."""

    LAB_REPORT = "lab_report"
    MEDICINE_LABEL = "medicine_label"
    DISCHARGE_LETTER = "discharge_letter"
    CLINIC_SLIP = "clinic_slip"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Span:
    """Where on the page a field was read: a box in fractions of the image, top-left origin."""

    x0: float
    y0: float
    x1: float
    y1: float

    def as_json(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
"""A subject or attribute is a short code, the way facts name things ("lipid_panel", "ldl")."""

VALUE_LENGTH = 200
"""The most a proposed value may hold, as canonical JSON. A value is a number, a date, a name
or a short structure — never the page. The page is the artefact."""


class NotAFieldCode(Refusal):
    """A subject or attribute is a short lower-case code. This was not one."""


class NotAValue(Refusal):
    """A proposed value is a short JSON value. This was not JSON, or was long enough to be
    the document."""


class NotAConfidence(Refusal):
    """Confidence is a number from nought to one."""


def check_code(code: str) -> str:
    if not isinstance(code, str) or not CODE.match(code):
        raise NotAFieldCode("a subject or attribute is a short lower-case code")
    return code


def check_value(value: Any) -> Any:
    try:
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as not_json:
        raise NotAValue("a proposed value is a JSON value") from not_json
    if value is None or len(canonical) > VALUE_LENGTH:
        raise NotAValue(f"a proposed value is at most {VALUE_LENGTH} characters of JSON")
    return value


def check_confidence(confidence: float) -> float:
    if not isinstance(confidence, int | float) or not 0.0 <= confidence <= 1.0:
        raise NotAConfidence("confidence is a number from nought to one")
    return float(confidence)


@dataclass(frozen=True, slots=True)
class ExtractedField:
    """One proposed statement, and how sure the extractor is of it."""

    subject: str
    attribute: str
    value: Any
    unit: str | None
    confidence: float
    span: Span | None = None

    def checked(self) -> ExtractedField:
        """The same field, or a refusal: the codes are codes, the value short, the
        confidence a confidence. Run on every field before it reaches a card."""
        return ExtractedField(
            subject=check_code(self.subject),
            attribute=check_code(self.attribute),
            value=check_value(self.value),
            unit=None if self.unit is None else str(self.unit)[:32],
            confidence=check_confidence(self.confidence),
            span=self.span,
        )


@dataclass(frozen=True, slots=True)
class Extraction:
    """What one photo was read as: the kind of paper, its date, and the fields."""

    document_kind: DocumentKind
    fields: tuple[ExtractedField, ...]
    document_date: date | None = None

    @classmethod
    def nothing(cls) -> Extraction:
        """The honest answer for a page that could not be read."""
        return cls(document_kind=DocumentKind.UNKNOWN, fields=())


@dataclass(frozen=True, slots=True)
class Hints:
    """What the extractor may be told about the page: the profile's language and region,
    so a Malay label and a Singapore lab format are expected rather than guessed at."""

    language: str
    region: Region


class Extractor(Protocol):
    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction: ...


class NotAFixture(Refusal):
    """A paper fixture is a JSON file of one shape. This one was not."""


def _field_from(entry: Mapping[str, Any]) -> ExtractedField:
    span = entry.get("span")
    return ExtractedField(
        subject=entry["subject"],
        attribute=entry["attribute"],
        value=entry["value"],
        unit=entry.get("unit"),
        confidence=entry["confidence"],
        span=None if span is None else Span(span["x0"], span["y0"], span["x1"], span["y1"]),
    ).checked()


def extraction_from_fixture(fixture: Mapping[str, Any]) -> Extraction:
    """The extraction a fixture file describes. Keys the shape does not name — the note about
    the redaction, what the paper actually says beside a deliberate misread — are ignored: a
    fixture documents itself, and only the fields reach the card."""
    try:
        kind = DocumentKind(fixture["document_kind"])
        when = fixture.get("document_date")
        fields = tuple(_field_from(entry) for entry in fixture["fields"])
    except (KeyError, TypeError, ValueError) as misshapen:
        raise NotAFixture(f"a paper fixture names document_kind and fields: {misshapen}") from None
    return Extraction(
        document_kind=kind,
        fields=fields,
        document_date=None if when is None else date.fromisoformat(when),
    )


class FixtureExtractor:
    """Answers from `tests/fixtures/paper/*.json`, by the sha256 of the bytes it is shown.

    Every fixture names the digest of the placeholder bytes that stand in for the redacted
    photo (`tests/paper.py` makes them; nothing binary is committed). A digest no fixture
    names is a page this extractor cannot read: `Extraction.nothing()`.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        self._by_digest: dict[str, Path] | None = None

    def _index(self) -> dict[str, Path]:
        if self._by_digest is None:
            found: dict[str, Path] = {}
            for path in sorted(self._directory.glob("*.json")):
                digest = json.loads(path.read_text()).get("sha256")
                if isinstance(digest, str):
                    found[digest.lower()] = path
            self._by_digest = found
        return self._by_digest

    def fixtures(self) -> Sequence[Path]:
        return tuple(self._index().values())

    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction:
        path = self._index().get(sha256_of(data))
        if path is None:
            return Extraction.nothing()
        return extraction_from_fixture(json.loads(path.read_text()))
