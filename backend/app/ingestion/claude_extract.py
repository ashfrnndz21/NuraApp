"""The Claude-backed extractor (`NURA_EXTRACTOR=claude`): a vision and document model reads
a photo or a PDF into the same shape the fixture answers with — a document kind, a date, and
fields with confidence — behind the same port (`app.ingestion.extract.Extractor`). Nothing
above this file, or `FixtureExtractor` beside it, changes.

Demo only (ADR 0017). Anthropic's first-party API processes in the US or globally, never in
SG or MY, and no in-region provider exists yet. This adapter is a runtime feature that may
only run where every byte it is shown is demo or test data: a declared demo
(`NURA_DEMO_MODE=1`). `extractor_for` (`app.ingestion.extract_provider`) refuses to build it
otherwise, and that refusal is the whole of this adapter's residency story — a real patient's
bytes never reach it. ADR 0008 (demo mode) is not this adapter's residency authority: it
authorises a deployment running on fixtures, and free text on it can still carry real
information (ADR 0008 "Consequences"); ADR 0017 is what actually admits a US-processing
adapter, and only for these Claude-backed runtime features, only under the demo declaration.
An in-region provider is a later adapter behind the same port, and this file does not need to
change for it to arrive.

What the model is asked for is exactly `ExtractedField`'s shape, as a JSON schema
(`output_config`, not the deprecated `output_format`): a document kind, an optional date on
the paper, and a list of fields, each a subject, an attribute, a value, a unit, a confidence
from nought to one, which page it was read on, and whether it was seen but could not be read.
`stop_reason` is checked before any content is read: `"refusal"` reads as the honest "could
not read this page" every other adapter gives, `Extraction.nothing()`; `"max_tokens"` is the
same answer, logged as its own case rather than falling through to the parse failure it would
otherwise masquerade as — a page that overran the budget was truncated mid-answer, not one
the model declined. A response that does not parse as the schema asks reads the same way. A
field whose confidence the model cannot be trusted on — missing, out of range, or of the
wrong type — is kept at confidence 0.0 rather than invented: below `CONFIDENCE_THRESHOLD` it
is held for the person's confirmation exactly as a genuinely unsure read would be, never
silently promoted.

A file of a kind this reader cannot open at all — today, `image/heic`, which the route
accepts but the model does not — is never sent, and is not `Extraction.nothing()`: that
answer is for a page that was looked at and not made out, and reusing it here would tell the
person to retake a photo that will fail again in exactly the same way. It is
`Extraction.unsupported_file_type()`, logged as its own case, so the card above can say what
is actually true.

Never logged: document bytes, the prompt, or the model's answer. A log line here says only
that a call happened, and how it ended.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Mapping
from datetime import date
from typing import Any, Final

from anthropic import AsyncAnthropic

from app.ingestion.extract import (
    DocumentKind,
    ExtractedField,
    Extraction,
    Hints,
    NotAConfidence,
    NotAFieldCode,
    NotAPage,
    NotAValue,
    Span,
)
from app.llm.prompts import load_prompt

log = logging.getLogger("nura.ingestion.claude_extract")

MODEL: Final = "claude-opus-5"
MAX_TOKENS: Final = 8192
"""Enough for a full multi-page discharge letter's fields as JSON; a page that still overruns
this is a truncated answer, handled as its own case (`stop_reason == "max_tokens"`), not a
schema failure."""

_PDF_TYPE = "application/pdf"
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
"""What this reader can open, of what the route accepts (`app.ingestion.photos.
PHOTO_CONTENT_TYPES`). `image/heic` is accepted by the route and not by this reader — see
the module docstring — and is refused, not silently sent nowhere and not misread as a page
that was looked at."""
_UNOPENABLE_TYPES = frozenset({"image/heic"})
"""Kinds the route accepts that this reader is never handed to the model at all."""

_FIELD_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "attribute", "value", "unit", "confidence", "unreadable", "page"],
    "properties": {
        "subject": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]{0,63}$",
            "description": "A short lower_snake_case code for what the field is about, e.g. "
            "'medicine', 'lipid_panel', 'blood_pressure'.",
        },
        "attribute": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]{0,63}$",
            "description": "A short lower_snake_case code for the property read, e.g. 'name', "
            "'strength', 'dose', 'ldl', 'systolic'.",
        },
        "value": {
            "description": "The value read, as a short JSON scalar or object — a number, a "
            "string, an ISO date, or a small structure. Null when unreadable is true.",
        },
        "unit": {"type": ["string", "null"], "description": "The unit the value is in, or null."},
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How sure you are this is what the page says, from 0 to 1. Only "
            "give a high number when the text is clearly legible and unambiguous; a guess, an "
            "inference, or a smudged or handwritten value is a low number.",
        },
        "unreadable": {
            "type": "boolean",
            "description": "True for a field you can see is on the page but cannot make out — "
            "value must then be null. Never guess a value to avoid this.",
        },
        "page": {
            "type": "integer",
            "minimum": 1,
            "description": "Which page of the document this field was read on, counting from "
            "1. A single photo is always 1.",
        },
    },
}

_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_kind", "fields"],
    "properties": {
        "document_kind": {
            "type": "string",
            "enum": [kind.value for kind in DocumentKind],
            "description": "What the page actually is, read as it is — not what it was "
            "offered as. 'not_health' for a paper with nothing medical on it (a receipt, a "
            "menu); 'unknown' only if the page truly cannot be made out at all.",
        },
        "document_date": {
            "type": ["string", "null"],
            "description": "The date on the document itself (ISO 8601, YYYY-MM-DD), or null "
            "if no date appears on the page.",
        },
        "fields": {"type": "array", "items": _FIELD_SCHEMA},
    },
}

_SYSTEM_PROMPT: Final = load_prompt("extract_document")
"""`app/llm/prompts/extract_document.txt` (`backend/CLAUDE.md`: prompts are files, not
strings in code)."""


def _user_prompt(hints: Hints) -> str:
    lines = [
        (
            f"The person uploading this is in {hints.region.value}; the page may be in "
            f"{hints.language} as well as English."
        ),
    ]
    if hints.expected is not None:
        lines.append(
            f"The uploader says this page is a {hints.expected.value}. That is only what "
            "they expect — read the page as it actually is and say so, even if it disagrees."
        )
    lines.append("Read the page and answer with the fields on it, following the schema given.")
    return "\n".join(lines)


def _content_block(data: bytes, content_type: str) -> dict[str, Any] | None:
    encoded = base64.b64encode(data).decode("ascii")
    if content_type == _PDF_TYPE:
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": _PDF_TYPE, "data": encoded},
        }
    if content_type in _IMAGE_TYPES:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": content_type, "data": encoded},
        }
    return None


def _confidence_of(entry: Mapping[str, Any]) -> float:
    """The field's confidence, or 0.0 — held for a person's confirmation — when the model's
    answer cannot be trusted as one: missing, the wrong type, or out of nought-to-one."""
    confidence = entry.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return 0.0
    if not 0.0 <= confidence <= 1.0:
        return 0.0
    return float(confidence)


def _span_of(entry: Mapping[str, Any]) -> Span | None:
    """The field's page, as a span (E02-03): no bounding box is asked of the model, only
    which page — so the box is the whole page, honestly, rather than a location nobody read
    off it. None when the model's `page` cannot be trusted as one (missing or not a positive
    integer): the field still reaches the card, without a locator, exactly as it did before
    this was asked."""
    page = entry.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        return None
    return Span(x0=0.0, y0=0.0, x1=1.0, y1=1.0, page=page)


def _field_from(entry: Mapping[str, Any]) -> ExtractedField | None:
    """One field of the model's answer, checked the way every extractor's fields are
    (`ExtractedField.checked`) — or None, when the model's answer for this one field cannot
    be trusted at all, so the rest of the page's fields are not thrown away for its sake."""
    subject, attribute = entry.get("subject"), entry.get("attribute")
    if not isinstance(subject, str) or not isinstance(attribute, str):
        return None
    unreadable = bool(entry.get("unreadable", False))
    value = None if unreadable else entry.get("value")
    unit = entry.get("unit")
    try:
        return ExtractedField(
            subject=subject,
            attribute=attribute,
            value=value,
            unit=None if unit is None else str(unit),
            confidence=_confidence_of(entry),
            span=_span_of(entry),
            unreadable=unreadable,
        ).checked()
    except NotAFieldCode:
        # No trustworthy code to label the field with at all: nothing to show a person.
        return None
    except (NotAValue, NotAConfidence, NotAPage):
        # `checked()` validates subject and attribute before value, confidence or page
        # (see its body), so reaching here means those two are already good codes — the
        # value, confidence or page is what could not be trusted. Kept as a field a person
        # can see and type in, not dropped: a misread page must not look emptier than it
        # is (`app.errors.Refusal` is a data problem here, not a reason to hide the line).
        log.warning(
            "claude extractor: a field's value, confidence or page did not check out; "
            "kept as unreadable rather than dropped"
        )
        return ExtractedField(
            subject=subject,
            attribute=attribute,
            value=None,
            unit=None,
            confidence=0.0,
            span=None,
            unreadable=True,
        ).checked()


def _extraction_from_payload(payload: Mapping[str, Any]) -> Extraction:
    kind = DocumentKind(payload["document_kind"])
    when = payload.get("document_date")
    document_date = None
    if isinstance(when, str) and when:
        try:
            document_date = date.fromisoformat(when)
        except ValueError:
            document_date = None
    raw_fields = payload["fields"]
    if not isinstance(raw_fields, list):
        raise TypeError("the model's answer did not give fields as a list")
    fields = tuple(
        field
        for field in (_field_from(entry) for entry in raw_fields if isinstance(entry, Mapping))
        if field is not None
    )
    return Extraction(document_kind=kind, fields=fields, document_date=document_date)


class ClaudeExtractor:
    """Reads a photo or a PDF with Claude. See the module docstring for the residency and
    confidence rules `extractor_for` and this class hold to."""

    external_processor: str | None = "anthropic"
    """Every call sends the page's bytes to Anthropic's first-party API (see the module
    docstring): `app.ingestion.review.review_artifact` reads this to write the audit line
    a fixture read never needs."""

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction:
        kind = content_type.strip().lower()
        if kind in _UNOPENABLE_TYPES:
            # Accepted by the route (`app.ingestion.photos.PHOTO_CONTENT_TYPES`), never sent
            # here: this reader cannot open it at all, so the honest answer is "never
            # looked", not "looked and could not read" (`Extraction.nothing()` would tell the
            # person to retake a photo that will fail again the same way).
            log.info("claude extractor: %s is accepted by the route, not by this reader", kind)
            return Extraction.unsupported_file_type()
        block = _content_block(data, kind)
        if block is None:
            log.info("claude extractor: %s is not a kind this reader was ever asked to open", kind)
            return Extraction.nothing()

        # The SDK's `MessageParam`/content-block TypedDicts are precise unions that plain
        # dicts built from `_content_block`'s `dict[str, Any]` cannot be checked against
        # structurally; the shapes here are exactly the ones the Claude API documents.
        message = await self._client.messages.create(  # type: ignore[call-overload]
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [block, {"type": "text", "text": _user_prompt(hints)}],
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )

        if message.stop_reason == "refusal":
            log.info("claude extractor: the model refused to read this page")
            return Extraction.nothing()
        if message.stop_reason == "max_tokens":
            # Truncated mid-answer, not declined: the honest answer is still "could not read
            # this page" (the page was looked at), but logged as its own case rather than
            # falling into the JSON-parse failure below, which it would only resemble.
            log.warning("claude extractor: the model's answer was cut off at max_tokens")
            return Extraction.nothing()

        try:
            text = message.content[0].text  # type: ignore[union-attr]
            payload = json.loads(text)
            if not isinstance(payload, Mapping):
                raise TypeError("the model's answer was not a JSON object")
            return _extraction_from_payload(payload)
        except (
            IndexError,
            AttributeError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as malformed:
            # Never the content, never the prompt — but the exception's own class and
            # message name what broke (a missing key, a bad enum value), so this case
            # stays distinguishable from a genuine bug in the ones above it in the log,
            # rather than every unexpected shape reading as the identical silent line.
            log.warning(
                "claude extractor: the model's answer did not match the schema asked (%s: %s)",
                type(malformed).__name__,
                malformed,
            )
            return Extraction.nothing()
