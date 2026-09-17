"""The Claude-backed extractor (`NURA_EXTRACTOR=claude`): a vision and document model reads
a photo or a PDF into the same shape the fixture answers with — a document kind, a date, and
fields with confidence — behind the same port (`app.ingestion.extract.Extractor`). Nothing
above this file, or `FixtureExtractor` beside it, changes.

Residency (ADR 0008). Anthropic's first-party API processes in the US or globally, never in
SG or MY. This adapter may only run where every byte it is shown is test data by declaration:
a demo (`NURA_DEMO_MODE=1`). `extractor_for` (`app.ingestion.extract_provider`) refuses to
build it otherwise, and that refusal is the whole of this adapter's residency story — an
in-region provider is a later adapter behind the same port, and this file does not need to
change for it to arrive.

What the model is asked for is exactly `ExtractedField`'s shape, as a JSON schema
(`output_config`, not the deprecated `output_format`): a document kind, an optional date on
the paper, and a list of fields, each a subject, an attribute, a value, a unit, a confidence
from nought to one, and whether it was seen but could not be read. `stop_reason` is checked
before any content is read — `"refusal"` reads as the honest "could not read this page" every
other adapter gives, `Extraction.nothing()`, the same answer for a response that does not
parse as the schema asks. A field whose confidence the model cannot be trusted on — missing,
out of range, or of the wrong type — is kept at confidence 0.0 rather than invented: below
`CONFIDENCE_THRESHOLD` it is held for the person's confirmation exactly as a genuinely unsure
read would be, never silently promoted.

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
)

log = logging.getLogger("nura.ingestion.claude_extract")

MODEL: Final = "claude-opus-5"
MAX_TOKENS: Final = 4096

_PDF_TYPE = "application/pdf"
_IMAGE_TYPES = frozenset({"image/jpeg", "image/png"})

_FIELD_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "attribute", "value", "unit", "confidence", "unreadable"],
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

_SYSTEM_PROMPT = """You read one page of a family's health paperwork: a lab report, a \
medicine label, a hospital discharge letter, a clinic slip, a handwritten prescription, an \
insurance letter, or something that turns out not to be a health paper at all.

Answer only with what the page itself says. Never infer, round, average or complete a value \
you cannot actually read; a field you can see but cannot make out is `unreadable` with no \
value, not a guess. Never give clinical advice, a diagnosis, or an instruction to start, \
stop or change a medicine — you are reading a page, not treating anyone; that boundary is \
enforced elsewhere and is not your concern here.

Use short lower_snake_case codes for `subject` and `attribute` (English, even when the page \
is in Malay or Chinese), the way a structured record would: a medicine's fields are subject \
"medicine", attribute one of "name", "strength", "dose", "quantity", "dispensed_at", \
"prescriber"; a lab panel's fields are subject the panel's name (e.g. "lipid_panel", \
"full_blood_count"), attribute the analyte (e.g. "ldl", "hdl", "hba1c"). Keep a value short — \
a number, a short string, an ISO date, or a small structure — never a paragraph.

Give every field its own honest confidence from 0 to 1. A number you read clearly on a \
printed line is high confidence; a handwritten or smudged value, an inference from context, \
or anything you are not sure of is low confidence — never invent a high number to seem \
useful. When you are not sure what confidence to give a field, give it a low one."""


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
            span=None,
            unreadable=unreadable,
        ).checked()
    except (NotAFieldCode, NotAValue, NotAConfidence, NotAPage):
        return None


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

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def extract(self, data: bytes, content_type: str, hints: Hints) -> Extraction:
        block = _content_block(data, content_type.strip().lower())
        if block is None:
            # The honest answer a real recogniser gives for a kind of file it does not
            # handle at all — the same answer FixtureExtractor gives for bytes it does not
            # know.
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
        ):
            log.warning("claude extractor: the model's answer did not match the schema asked")
            return Extraction.nothing()
