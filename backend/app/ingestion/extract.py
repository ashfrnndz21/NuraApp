"""Extraction: what a photo says, as fields with confidence, behind one interface.

An `Extractor` takes the bytes and answers with an `Extraction`: a guess at what kind of
document it is, the date on the document, and fields — each a proposed statement (subject,
attribute, value, unit) with how sure the extractor is and, where it can say, where on the
page it read it, and on which page of a document of several. Nothing here is a fact: a field
is a proposal for the review card, and only a person's yes turns it into one
(`app.ingestion.review`).

One port reads every kind of paper — a printed lab report, a PDF from a portal, a clinic slip
in a doctor's hand, the screen of a blood pressure machine (E02-02, E02-03, E02-08). What
differs is the hint (`Hints.expected`): the kind the person, or the route, says the page is,
so a real recogniser can choose how to read it. A hint is never an answer: the extraction
still says what the page looks like, and a page that is not what it was offered as is said
to be so. A field the recogniser saw but could not read is `unreadable` — no value, never
guessed — and the card asks a person to type it.

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
    HANDWRITTEN_PRESCRIPTION = "handwritten_prescription"
    """A prescription in a doctor's hand (E02-02): drug, dose and frequency, each asked."""
    INSURANCE_LETTER = "insurance_letter"
    DEVICE_SCREEN = "device_screen"
    """The screen of a blood pressure machine, a glucometer or a scale (E02-08)."""
    NOT_HEALTH = "not_health"
    """Read, and not a health paper at all: a receipt, a menu. Nothing is taken off it."""
    UNKNOWN = "unknown"


HANDWRITTEN = frozenset({DocumentKind.CLINIC_SLIP, DocumentKind.HANDWRITTEN_PRESCRIPTION})
"""The papers written by hand (E02-02): the ones where a field may be unreadable."""

PHOTO_HINTS = frozenset(
    {
        DocumentKind.LAB_REPORT,
        DocumentKind.MEDICINE_LABEL,
        DocumentKind.DISCHARGE_LETTER,
        DocumentKind.CLINIC_SLIP,
        DocumentKind.HANDWRITTEN_PRESCRIPTION,
        DocumentKind.INSURANCE_LETTER,
    }
)
"""What a person may say a photo of a page is. A device screen has its own route."""

DOCUMENT_HINTS = frozenset(
    {DocumentKind.LAB_REPORT, DocumentKind.DISCHARGE_LETTER, DocumentKind.INSURANCE_LETTER}
)
"""What a person may say an imported PDF is (E02-03)."""


@dataclass(frozen=True, slots=True)
class Span:
    """Where on the page a field was read: a box in fractions of the image, top-left origin,
    and — in a document of several pages — which page, counting from 1."""

    x0: float
    y0: float
    x1: float
    y1: float
    page: int | None = None

    def as_json(self) -> dict[str, float | int]:
        box: dict[str, float | int] = {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}
        if self.page is not None:
            box["page"] = self.page
        return box


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


class NotAPage(Refusal):
    """A page number counts from one."""


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
    """One proposed statement, and how sure the extractor is of it.

    `unreadable` is the honest answer for a field the recogniser found and could not read —
    the frequency scrawled on a clinic slip. It carries no value, never a guess; the card
    shows it as a line for a person to type (E02-02).
    """

    subject: str
    attribute: str
    value: Any
    unit: str | None
    confidence: float
    span: Span | None = None
    unreadable: bool = False

    def checked(self) -> ExtractedField:
        """The same field, or a refusal: the codes are codes, the value short — or, for an
        unreadable field, absent — the confidence a confidence, the page a page. Run on
        every field before it reaches a card."""
        if self.unreadable and self.value is not None:
            raise NotAValue("an unreadable field carries no value")
        if self.span is not None and self.span.page is not None and self.span.page < 1:
            raise NotAPage("a page number counts from one")
        return ExtractedField(
            subject=check_code(self.subject),
            attribute=check_code(self.attribute),
            value=None if self.unreadable else check_value(self.value),
            unit=None if self.unit is None else str(self.unit)[:32],
            confidence=check_confidence(self.confidence),
            span=self.span,
            unreadable=self.unreadable,
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
    so a Malay label and a Singapore lab format are expected rather than guessed at, and —
    where the person or the route says so — the kind of paper it is offered as."""

    language: str
    region: Region
    expected: DocumentKind | None = None


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
        span=None
        if span is None
        else Span(span["x0"], span["y0"], span["x1"], span["y1"], span.get("page")),
        unreadable=bool(entry.get("unreadable", False)),
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
    photo or PDF (`tests/paper.py` makes them; nothing binary is committed). A digest no
    fixture names is a page this extractor cannot read: `Extraction.nothing()`. The hint is
    taken and not needed — a fixture already knows what its page is — which is exactly the
    answer a real recogniser must also give: the page as it is, whatever it was offered as.
    The labelled answers beside the fixtures (`*.expected.json`) name no digest and are not
    read here; they are the accuracy harness's (`tests/paper_accuracy.py`).
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
