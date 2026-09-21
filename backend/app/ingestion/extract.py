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
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from app.errors import Refusal
from app.fixtures import fixture
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
    """A snapshot of an insurance card, for the one field the emergency card keeps
    (`app.insurance.insurer`) — offered at onboarding, distinct from the fuller papers
    below."""
    INSURANCE_POLICY = "insurance_policy"
    """A policy document: insurer, policy number, plan, holder, dates and coverage lines
    (`app.insurance.policy`). Read into facts here, never into a policy row directly — the
    fuller record is always a person's own separate yes (`app.insurance.policy`'s module
    docstring)."""
    INSURANCE_CLAIM = "insurance_claim"
    """A claim letter or a claim's own paperwork: insurer, claim number, status, amount,
    date and what it was for (`app.insurance.claim`). Read into facts here, the same way."""
    DEVICE_SCREEN = "device_screen"
    """The screen of a blood pressure machine, a glucometer or a scale (E02-08)."""
    PILL_PHOTO = "pill_photo"
    """A loose pill or tablet, no label in view: what a person can actually see of it — the
    imprint, the colour, the shape, a score line — read as a `pill` field each, never a name.
    Routed to a proposal matched against the licensed registry (`app.drugs.registry`) and
    held at most at `app.ingestion.review.PILL_MAX_CONFIDENCE`, always below the confirmation
    threshold: a pill's identity is a guess from what it looks like, never a read, so it
    always needs the person's own look and the pharmacist's, not a silent assumption."""
    PHARMACY_RECEIPT = "pharmacy_receipt"
    """A pharmacy's own receipt: which pharmacy, the date, the currency, and each line bought
    — item, quantity, unit price, total (`app.ingestion.review`). A line naming a medicine or
    supplement already on his list becomes a cost entry the ledger sums; a line that matches
    nothing on his list is kept as a plain paper fact, same as any other kind's fallback."""
    OTHER = "other"
    """A health paper read as itself, and not one of the named kinds above — an X-ray
    report, a referral letter, a general clinical note. Its fields are kept as plain facts
    (`app.ingestion.review._write_paper`'s default), the same as any kind with no special
    routing of its own; distinct from NOT_HEALTH, which is for a page with nothing medical
    on it at all."""
    NOT_HEALTH = "not_health"
    """Read, and not a health paper at all: a receipt, a menu. Nothing is taken off it."""
    UNKNOWN = "unknown"
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    """The route accepted this kind of file, but this reader cannot open it at all — never
    looked, unlike UNKNOWN, which is the honest answer for a page that was looked at and
    could not be made out (E02-02)."""


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
        DocumentKind.INSURANCE_POLICY,
        DocumentKind.INSURANCE_CLAIM,
        DocumentKind.PILL_PHOTO,
        DocumentKind.PHARMACY_RECEIPT,
    }
)
"""What a person may say a photo of a page is. A device screen has its own route."""

DOCUMENT_HINTS = frozenset(
    {
        DocumentKind.LAB_REPORT,
        DocumentKind.DISCHARGE_LETTER,
        DocumentKind.INSURANCE_LETTER,
        DocumentKind.INSURANCE_POLICY,
        DocumentKind.INSURANCE_CLAIM,
    }
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

LABEL_ON_PAPER_LENGTH = 120
"""The most `label_on_paper` may hold: the words printed beside one line, never a paragraph."""

_RANGE_TWO_SIDED = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(-?\d+(?:\.\d+)?)")
_RANGE_UPPER = re.compile(
    r"^(?:<\s*|≤\s*|under\s+|up to\s+|below\s+)(-?\d+(?:\.\d+)?)", re.IGNORECASE
)
_RANGE_LOWER = re.compile(
    r"^(?:>\s*|≥\s*|over\s+|above\s+|at least\s+|or more\s+)(-?\d+(?:\.\d+)?)", re.IGNORECASE
)
_RANGE_UNIT_TAIL = re.compile(r"[ \t]*[A-Za-zµμ/%.]*")
"""What may follow a matched range and still count as the whole thing having been read: only
whitespace and a unit with no digit, bracket, colon, comma or dash in it. A trailing "mg/dL" or
"%" passes; a second range, a sex or age qualifier ("(M)", "F:"), a parenthetical threshold
("(desirable)") or an x10^9-style count does not — `fullmatch` on the text after the matched
range, so anything left over at all fails it unless it is exactly this shape."""


@dataclass(frozen=True, slots=True)
class PrintedRange:
    """A result's reference range, exactly as one row of a paper prints it (`text`), plus its
    lower and upper bound as numbers where the text is unambiguous (E02, defect #3: "a
    reference range arrives as a separate field instead of belonging to its result"). `low`/
    `high` are `None` where the text has no such bound ("<150" has no low; "Negative" has
    neither) or cannot be read as one — `text` itself is never touched, only ever the range
    exactly as printed. Distinct from `app.reasoning.ranges.Range`, the app's own guideline
    table looked up for the trend: this is only ever what the paper itself says."""

    low: float | None
    high: float | None
    text: str

    def as_json(self) -> dict[str, float | str | None]:
        return {"low": self.low, "high": self.high, "text": self.text}


def parse_printed_range(text: str) -> PrintedRange:
    """The range exactly as printed, with its bounds read off it only when the *whole* string
    is nothing but that one range and, at most, a plain unit after it: "<150" -> high 150;
    "> 1.0" -> low 1.0; "3.9 - 6.0" or "3.9-6.0" -> both; "Up to 40" -> high 40; "3.5 - 5.2
    mmol/L" -> both, the unit ignored. A low bound over the high one ("6.0 - 3.9", a range
    printed backwards or misread) is refused the same as anything else that cannot be trusted.

    Bounds are `None` — the text kept exactly as printed, nothing guessed — for anything this
    cannot read with confidence: an empty string; "Negative"; a compound, sex- or age-specific
    range ("13.0-17.0 (M) / 12.0-15.0 (F)", "M: 13-17 F: 12-15") — a wrong bound shown as a
    right one is the failure that matters here, never an unparsed range; a multi-threshold list
    ("5.2 (desirable) / 6.2 (high)"); a count with its unit still attached ("4.0-10.0
    x10^9/L", where the unit itself carries digits); a thousands separator ("1,000 - 2,000")
    or a comma decimal ("3,9 - 6,0") — neither is read as a number here, so the string simply
    does not match rather than being misread as one further left along it."""
    raw = text.strip()
    if not raw:
        return PrintedRange(low=None, high=None, text=raw)
    two_sided = _RANGE_TWO_SIDED.match(raw)
    if two_sided and _RANGE_UNIT_TAIL.fullmatch(raw[two_sided.end() :]):
        low, high = float(two_sided.group(1)), float(two_sided.group(2))
        if low <= high:
            return PrintedRange(low=low, high=high, text=raw)
        return PrintedRange(low=None, high=None, text=raw)
    upper = _RANGE_UPPER.match(raw)
    if upper and _RANGE_UNIT_TAIL.fullmatch(raw[upper.end() :]):
        return PrintedRange(low=None, high=float(upper.group(1)), text=raw)
    lower = _RANGE_LOWER.match(raw)
    if lower and _RANGE_UNIT_TAIL.fullmatch(raw[lower.end() :]):
        return PrintedRange(low=float(lower.group(1)), high=None, text=raw)
    return PrintedRange(low=None, high=None, text=raw)


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
    range: PrintedRange | None = None
    """The result's own printed reference range, when the row on the paper carries one
    (defect #3). Never present for a field that is not itself a result."""
    label_on_paper: str | None = None
    """The words printed on the paper for this line, exactly as they read — required by the
    extractor's prompt when `attribute` is `"other"` (outside the controlled vocabulary), and
    allowed on any field so the card can still show a person's own paper's wording as a last
    resort, ahead of a generic line name (`app.channels.strings`, `web/src/onboarding/review.ts
    fieldLabel`)."""

    def checked(self) -> ExtractedField:
        """The same field, or a refusal: the codes are codes, the value short — or, for an
        unreadable field, absent — the confidence a confidence, the page a page. Run on
        every field before it reaches a card."""
        if self.unreadable and self.value is not None:
            raise NotAValue("an unreadable field carries no value")
        if self.span is not None and self.span.page is not None and self.span.page < 1:
            raise NotAPage("a page number counts from one")
        label_on_paper = None if self.label_on_paper is None else str(self.label_on_paper).strip()
        return ExtractedField(
            subject=check_code(self.subject),
            attribute=check_code(self.attribute),
            value=None if self.unreadable else check_value(self.value),
            unit=None if self.unit is None else str(self.unit)[:32],
            confidence=check_confidence(self.confidence),
            span=self.span,
            unreadable=self.unreadable,
            range=self.range,
            label_on_paper=(label_on_paper[:LABEL_ON_PAPER_LENGTH] or None)
            if label_on_paper
            else None,
        )


_LEGACY_RANGE_SUFFIX = "_reference_range"
"""The shape every extractor wrote before a result carried its own `range`: a sibling field
named `<analyte>_reference_range` on the same subject (`app/llm/prompts/extract_document.txt`,
the version before defect #3's fix). Still what an older answer, and the fixtures already
written this way, carry — `fold_legacy_reference_ranges` is the server-side normaliser that
keeps them working without a rewrite."""


def fold_legacy_reference_ranges(fields: Sequence[ExtractedField]) -> tuple[ExtractedField, ...]:
    """Every legacy `<analyte>_reference_range` sibling folded onto the result it describes,
    and dropped from the list only once it actually is folded: once its text is on the
    result's own `range`, showing it again as a line of its own is exactly the defect this
    fixes (E02, "a reference range arrives as a separate field instead of belonging to its
    result"), not a second read of the same range. A result that already carries its own
    `range` — the shape a current extractor answer, or a fixture written the new way, already
    uses — is left alone, the legacy sibling never overwriting a range the result was given
    directly; a sibling with no result to fold onto at all, or whose value is not text, is
    left exactly as it is too. Either way nothing here silently discards a field that was
    never actually folded: the sibling stays, still its own line, rather than vanish.

    The merged field's confidence is the lower of the two: a clearly-read number beside a
    faintly-read range must not read as "Nura is sure" once the range is folded into it — the
    card's `needs_confirm` is computed from confidence (`app.ingestion.models.ReviewField.
    needs_confirm`), so this is what carries a low-confidence range to the person at all."""
    by_key = {(f.subject, f.attribute): f for f in fields}
    folded: dict[tuple[str, str], ExtractedField] = {}
    dropped: set[tuple[str, str]] = set()
    for legacy in fields:
        if not legacy.attribute.endswith(_LEGACY_RANGE_SUFFIX):
            continue
        base_attribute = legacy.attribute[: -len(_LEGACY_RANGE_SUFFIX)]
        if not base_attribute:
            continue
        base_key = (legacy.subject, base_attribute)
        base = by_key.get(base_key)
        if base is None or base.range is not None or not isinstance(legacy.value, str):
            # No result to fold onto, a result that already carries its own range (never
            # overwritten by the legacy sibling's text), or a value that is not text at all:
            # left exactly as it is, still its own field, rather than silently discarded.
            continue
        folded[base_key] = replace(
            base,
            range=parse_printed_range(legacy.value),
            confidence=min(base.confidence, legacy.confidence),
        )
        dropped.add((legacy.subject, legacy.attribute))
    return tuple(
        folded.get((f.subject, f.attribute), f)
        for f in fields
        if (f.subject, f.attribute) not in dropped
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

    @classmethod
    def unsupported_file_type(cls) -> Extraction:
        """The honest answer for a file this reader never looked at, because it is a kind
        the route accepted but this reader cannot open — distinct from `nothing()`, which
        is a page that was looked at and could not be made out."""
        return cls(document_kind=DocumentKind.UNSUPPORTED_FILE_TYPE, fields=())


@dataclass(frozen=True, slots=True)
class Hints:
    """What the extractor may be told about the page: the profile's language and region,
    so a Malay label and a Singapore lab format are expected rather than guessed at, and —
    where the person or the route says so — the kind of paper it is offered as."""

    language: str
    region: Region
    expected: DocumentKind | None = None


class Extractor(Protocol):
    external_processor: str | None
    """None for a reader that never leaves the region (a fixture, or a real in-region
    reader to come); a short name (e.g. "anthropic") for one whose bytes go to a
    third-party model processor outside it, so the caller that holds the audit trail
    (`app.ingestion.review.review_artifact`) can write that reach down without importing
    the adapter itself."""

    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction: ...


class NotAFixture(Refusal):
    """A paper fixture is a JSON file of one shape. This one was not."""


def _printed_range_of(entry: Mapping[str, Any]) -> PrintedRange | None:
    raw = entry.get("range")
    if not isinstance(raw, Mapping):
        return None
    low, high, text = raw.get("low"), raw.get("high"), raw.get("text")
    low = float(low) if isinstance(low, int | float) and not isinstance(low, bool) else None
    high = float(high) if isinstance(high, int | float) and not isinstance(high, bool) else None
    return PrintedRange(low=low, high=high, text=text if isinstance(text, str) else "")


def _field_from(entry: Mapping[str, Any]) -> ExtractedField:
    span = entry.get("span")
    label_on_paper = entry.get("label_on_paper")
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
        range=_printed_range_of(entry),
        label_on_paper=label_on_paper if isinstance(label_on_paper, str) else None,
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


@fixture
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

    external_processor: str | None = None
    """Answers from a file on disk; nothing ever leaves the region."""

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
