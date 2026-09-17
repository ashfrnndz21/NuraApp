"""The Claude-backed extractor (E02, `NURA_EXTRACTOR=claude`): a PDF, a label photo, a
refusal, a malformed answer, and a field whose confidence stays unconfirmed rather than
invented. No live call: every test hands `ClaudeExtractor` a fake that answers in memory, in
`client.messages.create`'s exact shape (`anthropic`), and asserts what was sent and what came
back — never a real API key, never a real request.

`extractor_for` (`app.ingestion.extract_provider`) is the other half: `NURA_EXTRACTOR=claude`
must refuse to build outside a declared demo (ADR 0008), because Anthropic's first-party API
does not process in SG or MY and a demo is the only deployment where every document is test
data by declaration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.claude_extract import ClaudeExtractor
from app.ingestion.extract import DocumentKind, Extraction, FixtureExtractor, Hints
from app.ingestion.extract_provider import (
    ClaudeExtractorOutsideDemo,
    NoExtractor,
    extractor_for,
)
from app.ingestion.models import CONFIDENCE_THRESHOLD
from app.regions import Region
from app.settings import MissingSetting, Settings

HINTS = Hints(language="en", region=Region.SG)


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[_TextBlock]
    stop_reason: str = "end_turn"


@dataclass
class _FakeMessages:
    """Records every call and answers from a queue, the way a test double for
    `client.messages.create` needs to for a call the code makes at most once per `extract`."""

    answers: list[_FakeMessage]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        return self.answers.pop(0)


@dataclass
class _FakeClient:
    messages: _FakeMessages


def _client_answering(*payloads: dict[str, Any] | str, stop_reason: str = "end_turn") -> _FakeClient:
    """A fake Anthropic client whose one call answers with `payloads[0]` as the structured
    output's JSON text (a dict is dumped; a str is used as-is, for a malformed answer)."""
    answers = [
        _FakeMessage(
            content=[_TextBlock(text=p if isinstance(p, str) else json.dumps(p))],
            stop_reason=stop_reason,
        )
        for p in payloads
    ]
    return _FakeClient(messages=_FakeMessages(answers=answers))


def _field(subject: str, attribute: str, value: Any, confidence: float, **rest: Any) -> dict[str, Any]:
    return {
        "subject": subject,
        "attribute": attribute,
        "value": value,
        "unit": rest.get("unit"),
        "confidence": confidence,
        "unreadable": rest.get("unreadable", False),
    }


async def test_a_pdf_lab_report_is_read_with_units_and_the_date_on_the_paper() -> None:
    client = _client_answering(
        {
            "document_kind": "lab_report",
            "document_date": "2026-09-01",
            "fields": [_field("lipid_panel", "ldl", 152, 0.97, unit="mg/dL")],
        }
    )
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4 not a real pdf", "application/pdf", HINTS)

    assert extraction.document_kind is DocumentKind.LAB_REPORT
    assert extraction.document_date is not None and extraction.document_date.isoformat() == "2026-09-01"
    assert len(extraction.fields) == 1
    got = extraction.fields[0]
    assert (got.subject, got.attribute, got.value, got.unit) == ("lipid_panel", "ldl", 152, "mg/dL")
    assert got.confidence == pytest.approx(0.97)

    # The document block goes before the text block (Claude API fact from the brief).
    sent = client.messages.calls[0]
    content = sent["messages"][0]["content"]
    assert content[0]["type"] == "document"
    assert content[0]["source"] == {
        "type": "base64",
        "media_type": "application/pdf",
        "data": content[0]["source"]["data"],
    }
    assert content[1]["type"] == "text"
    assert sent["model"] == "claude-opus-5"
    assert "output_format" not in sent
    assert sent["output_config"]["format"]["type"] == "json_schema"


async def test_a_medicine_label_photo_is_read_into_the_review_cards_shape() -> None:
    client = _client_answering(
        {
            "document_kind": "medicine_label",
            "fields": [
                _field("medicine", "name", "Warfarin", 0.95),
                _field("medicine", "strength", 5, 0.9, unit="mg"),
            ],
        }
    )
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"\xff\xd8\xff not a real jpeg", "image/jpeg", HINTS)

    assert extraction.document_kind is DocumentKind.MEDICINE_LABEL
    names = {(f.subject, f.attribute): f.value for f in extraction.fields}
    assert names[("medicine", "name")] == "Warfarin"
    assert names[("medicine", "strength")] == 5

    sent = client.messages.calls[0]
    block = sent["messages"][0]["content"][0]
    assert block == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": block["source"]["data"]},
    }


async def test_a_refusal_reads_as_the_honest_could_not_read_this_page_answer() -> None:
    client = _client_answering({"document_kind": "unknown", "fields": []}, stop_reason="refusal")
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4", "application/pdf", HINTS)

    assert extraction == Extraction.nothing()


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        "{}",  # missing document_kind and fields
        json.dumps({"document_kind": "not_a_real_kind", "fields": []}),
        json.dumps({"document_kind": "lab_report", "fields": "not a list"}),
    ],
)
async def test_a_malformed_answer_reads_as_could_not_read_this_page_not_a_crash(text: str) -> None:
    client = _client_answering(text)
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4", "application/pdf", HINTS)

    assert extraction == Extraction.nothing()


async def test_a_low_confidence_field_is_kept_and_stays_below_the_threshold() -> None:
    client = _client_answering(
        {
            "document_kind": "lab_report",
            "fields": [_field("lipid_panel", "triglycerides", 64, 0.4, unit="mg/dL")],
        }
    )
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4", "application/pdf", HINTS)

    assert len(extraction.fields) == 1
    got = extraction.fields[0]
    assert got.confidence == pytest.approx(0.4)
    assert got.confidence < CONFIDENCE_THRESHOLD
    assert got.value == 64  # kept, not dropped: a person confirms it, not the model


@pytest.mark.parametrize("bad_confidence", [None, "high", True, 1.4, -0.1])
async def test_a_field_the_model_cannot_be_trusted_on_stays_unconfirmed_not_invented(
    bad_confidence: Any,
) -> None:
    entry = _field("medicine", "dose", "1 tablet at night", 0.0)
    entry["confidence"] = bad_confidence
    client = _client_answering({"document_kind": "medicine_label", "fields": [entry]})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"\xff\xd8\xff", "image/jpeg", HINTS)

    assert len(extraction.fields) == 1
    got = extraction.fields[0]
    assert got.confidence == 0.0
    assert got.confidence < CONFIDENCE_THRESHOLD
    assert got.value == "1 tablet at night"  # the value is kept; only trust in it is not


async def test_an_unreadable_field_carries_no_value() -> None:
    client = _client_answering(
        {
            "document_kind": "handwritten_prescription",
            "fields": [_field("medicine", "frequency", None, 0.0, unreadable=True)],
        }
    )
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"\xff\xd8\xff", "image/jpeg", HINTS)

    assert len(extraction.fields) == 1
    assert extraction.fields[0].unreadable is True
    assert extraction.fields[0].value is None


async def test_a_content_type_the_adapter_does_not_handle_is_never_sent_to_the_model() -> None:
    client = _client_answering({"document_kind": "unknown", "fields": []})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"heic bytes", "image/heic", HINTS)

    assert extraction == Extraction.nothing()
    assert client.messages.calls == []  # no bytes were ever sent


# -- extractor_for: the residency refusal (ADR 0008) -------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "paper"


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"region": Region.SG, "database_url": "sqlite+aiosqlite://"}
    base.update(overrides)
    return Settings(**base)


def test_the_default_extractor_is_the_fixture_one() -> None:
    extractor = extractor_for(_settings(paper_fixtures=str(FIXTURES)))
    assert isinstance(extractor, FixtureExtractor)


def test_the_fixture_extractor_refuses_without_a_fixtures_directory() -> None:
    with pytest.raises(MissingSetting):
        extractor_for(_settings())


def test_claude_refuses_to_build_outside_a_declared_demo() -> None:
    with pytest.raises(ClaudeExtractorOutsideDemo):
        extractor_for(_settings(extractor="claude", anthropic_api_key="sk-test-not-real"))


def test_claude_refuses_to_build_on_a_plain_dev_run_too() -> None:
    """The residency rule is stricter than the fixtures' own: a dev run alone is not enough,
    only a declared demo is — a laptop's own test papers are not "test data by declaration"."""
    with pytest.raises(ClaudeExtractorOutsideDemo):
        extractor_for(
            _settings(extractor="claude", dev_code_sender=True, anthropic_api_key="sk-test-not-real")
        )


def test_claude_builds_on_a_declared_demo() -> None:
    extractor = extractor_for(
        _settings(
            extractor="claude",
            demo_mode=True,
            demo_login_code="123456",
            anthropic_api_key="sk-test-not-real",
        )
    )
    assert isinstance(extractor, ClaudeExtractor)


def test_claude_refuses_to_build_without_a_key_even_on_a_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingSetting):
        extractor_for(_settings(extractor="claude", demo_mode=True, demo_login_code="123456"))


def test_claude_builds_on_the_sdks_own_anthropic_api_key_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    extractor = extractor_for(
        _settings(extractor="claude", demo_mode=True, demo_login_code="123456")
    )
    assert isinstance(extractor, ClaudeExtractor)


def test_an_unknown_extractor_name_refuses_to_start() -> None:
    with pytest.raises(NoExtractor):
        extractor_for(_settings(extractor="ocr-3000"))
