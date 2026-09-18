"""The Claude-backed extractor (E02, `NURA_EXTRACTOR=claude`): a PDF, a label photo, a
refusal, a malformed answer, and a field whose confidence stays unconfirmed rather than
invented. No live call: every test hands `ClaudeExtractor` a fake that answers in memory, in
`client.messages.create`'s exact shape (`anthropic`), and asserts what was sent and what came
back — never a real API key, never a real request.

`extractor_for` (`app.ingestion.extract_provider`) is the other half: `NURA_EXTRACTOR=claude`
must refuse to build outside a declared demo or a declared dev run (ADR 0017), because
Anthropic's first-party API does not process in SG or MY, and only a demo (every document is
demo or test data) or a dev run on the owner's own laptop (he is the one choosing to show it
his own documents) admits the exception.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.identity.service import create_own_profile, register_person
from app.ingestion.claude_extract import ClaudeExtractor
from app.ingestion.extract import DocumentKind, Extraction, FixtureExtractor, Hints
from app.ingestion.extract_provider import (
    ClaudeExtractorOutsideDemo,
    NoExtractor,
    extractor_for,
)
from app.ingestion.models import CONFIDENCE_THRESHOLD
from app.ingestion.objects import LocalObjectStore
from app.ingestion.photos import store_photo
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR, Notice, notice_of, review_artifact
from app.keys.context import resolve_key_context
from app.memory.models import SourceChannel
from app.regions import Region
from app.settings import MissingSetting, Settings
from tests.support import OPENING_CONSENT

HINTS = Hints(language="en", region=Region.SG)
SG = Region.SG


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


def _client_answering(
    *payloads: dict[str, Any] | str, stop_reason: str = "end_turn"
) -> _FakeClient:
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


def _field(
    subject: str, attribute: str, value: Any, confidence: float, **rest: Any
) -> dict[str, Any]:
    return {
        "subject": subject,
        "attribute": attribute,
        "value": value,
        "unit": rest.get("unit"),
        "confidence": confidence,
        "unreadable": rest.get("unreadable", False),
        "page": rest.get("page", 1),
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
    assert extraction.document_date is not None
    assert extraction.document_date.isoformat() == "2026-09-01"
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


async def test_a_kind_the_route_accepts_but_this_reader_cannot_open_is_never_sent() -> None:
    """HEIC is accepted by the photo route (`app.ingestion.photos.PHOTO_CONTENT_TYPES`) but
    this reader cannot open it: the honest answer is "never looked"
    (`Extraction.unsupported_file_type()`), not `Extraction.nothing()` — which is the answer
    for a page that was looked at and not made out, and would tell the person to retake a
    photo that will fail again the same way."""
    client = _client_answering({"document_kind": "unknown", "fields": []})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"heic bytes", "image/heic", HINTS)

    assert extraction == Extraction.unsupported_file_type()
    assert extraction.document_kind is DocumentKind.UNSUPPORTED_FILE_TYPE
    assert client.messages.calls == []  # no bytes were ever sent


async def test_a_content_type_this_build_has_never_heard_of_is_never_sent_either() -> None:
    client = _client_answering({"document_kind": "unknown", "fields": []})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"???", "application/octet-stream", HINTS)

    assert extraction == Extraction.nothing()
    assert client.messages.calls == []


async def test_webp_is_sent_to_the_model_like_any_other_photo() -> None:
    client = _client_answering({"document_kind": "medicine_label", "fields": []})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"RIFF....WEBP", "image/webp", HINTS)

    assert extraction.document_kind is DocumentKind.MEDICINE_LABEL
    block = client.messages.calls[0]["messages"][0]["content"][0]
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/webp"


async def test_the_page_a_field_was_read_on_becomes_its_span() -> None:
    client = _client_answering(
        {
            "document_kind": "discharge_letter",
            "fields": [
                _field("discharge", "reason", "pneumonia", 0.9, page=1),
                _field("discharge", "follow_up_doctor", "Dr Lee", 0.5, page=2),
            ],
        }
    )
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4", "application/pdf", HINTS)

    by_attribute = {f.attribute: f for f in extraction.fields}
    assert by_attribute["reason"].span is not None and by_attribute["reason"].span.page == 1
    assert (
        by_attribute["follow_up_doctor"].span is not None
        and by_attribute["follow_up_doctor"].span.page == 2
    )


async def test_a_field_with_no_trustworthy_page_still_reaches_the_card() -> None:
    entry = _field("discharge", "reason", "pneumonia", 0.9)
    entry["page"] = "two"  # not an int: cannot be trusted as a page
    client = _client_answering({"document_kind": "discharge_letter", "fields": [entry]})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4", "application/pdf", HINTS)

    assert len(extraction.fields) == 1
    assert extraction.fields[0].span is None
    assert extraction.fields[0].value == "pneumonia"  # kept, not dropped


async def test_an_overlong_value_keeps_the_field_as_unreadable_not_dropped() -> None:
    """`checked()` refuses a value over `VALUE_LENGTH` characters of JSON (`NotAValue`); the
    field must still reach the card — dotted, asking to be typed in — not vanish, or the
    page looks emptier than it is (E02-02)."""
    entry = _field("medicine", "dose", "x" * 500, 0.9)
    client = _client_answering({"document_kind": "medicine_label", "fields": [entry]})
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"\xff\xd8\xff", "image/jpeg", HINTS)

    assert len(extraction.fields) == 1
    got = extraction.fields[0]
    assert got.subject == "medicine" and got.attribute == "dose"
    assert got.unreadable is True
    assert got.value is None
    assert got.confidence == 0.0


async def test_a_truncated_answer_at_max_tokens_reads_as_could_not_read_not_a_crash() -> None:
    client = _client_answering(
        {"document_kind": "lab_report", "fields": []}, stop_reason="max_tokens"
    )
    extractor = ClaudeExtractor(client)  # type: ignore[arg-type]

    extraction = await extractor.extract(b"%PDF-1.4", "application/pdf", HINTS)

    assert extraction == Extraction.nothing()


# -- review_artifact: the reach outside the region is on the trail, distinct from a fixture
# read, and a card of an unsupported kind carries the honest notice (ADR 0017) -------------


async def _owner(session: AsyncSession, phone: str = "+6591190001") -> Any:
    pa = await register_person(session, region=SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(session, region=SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(session, region=SG, person_id=pa.id, profile_id=profile.id)


async def test_a_claude_read_audits_the_reach_outside_the_region_a_fixture_read_never_writes(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await _owner(sg)
    store = LocalObjectStore(tmp_path, SG)
    artifact = await store_photo(
        sg,
        context=context,
        store=store,
        data=b"\xff\xd8\xff not a real jpeg",
        content_type="image/jpeg",
        captured_at=datetime(2026, 9, 1, tzinfo=UTC),
        source_channel=SourceChannel.APP,
    )
    client = _client_answering({"document_kind": "medicine_label", "fields": []})
    claude = ClaudeExtractor(client)  # type: ignore[arg-type]

    await review_artifact(
        sg,
        context=context,
        artifact_id=artifact.id,
        store=store,
        extractor=claude,
        language="en",
    )

    where = AuditEntry.target == EXTERNAL_MODEL_PROCESSOR
    trail = (await sg.execute(select(AuditEntry).where(where))).scalars().all()
    assert len(trail) == 1
    entry = trail[0]
    assert entry.action is Action.SHARE
    assert entry.outcome is Outcome.ALLOWED
    assert entry.target_id == artifact.id
    assert entry.shared_with_label == "anthropic"

    # A fixture read of another photo writes no such line at all.
    fixture_artifact = await store_photo(
        sg,
        context=context,
        store=store,
        data=b"\xff\xd8\xff another one",
        content_type="image/jpeg",
        captured_at=datetime(2026, 9, 1, tzinfo=UTC),
        source_channel=SourceChannel.APP,
    )
    await review_artifact(
        sg,
        context=context,
        artifact_id=fixture_artifact.id,
        store=store,
        extractor=FixtureExtractor(Path(__file__).resolve().parent / "fixtures" / "paper"),
        language="en",
    )
    still_one = (
        (await sg.execute(select(AuditEntry).where(AuditEntry.target == EXTERNAL_MODEL_PROCESSOR)))
        .scalars()
        .all()
    )
    assert len(still_one) == 1  # the fixture read added nothing


async def test_a_kind_this_reader_never_opened_carries_the_honest_notice_not_a_lie() -> None:
    """`notice_of` (`app.ingestion.review`): a card of `UNSUPPORTED_FILE_TYPE` says so —
    distinct from `NOT_A_HEALTH_PAPER` — so the surface never tells the person to retake a
    photo of a kind that will fail again the same way."""
    from app.ingestion.models import ReviewCard

    card = ReviewCard(document_kind=DocumentKind.UNSUPPORTED_FILE_TYPE)
    assert notice_of(card) is Notice.PHOTO_KIND_NOT_READ


# -- extractor_for: the residency refusal (ADR 0017) -------------------------------------

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


def test_claude_refuses_to_build_outside_a_declared_demo_and_dev_run() -> None:
    with pytest.raises(ClaudeExtractorOutsideDemo):
        extractor_for(_settings(extractor="claude", anthropic_api_key="sk-test-not-real"))


def test_claude_builds_on_a_declared_dev_run() -> None:
    """The owner's own laptop, his own documents, his own key: a declared dev run is now
    enough on its own, without also being a declared demo (ADR 0017 addendum)."""
    extractor = extractor_for(
        _settings(
            extractor="claude", dev_code_sender=True, anthropic_api_key="sk-test-not-real"
        )
    )
    assert isinstance(extractor, ClaudeExtractor)


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


def test_claude_refuses_to_build_without_a_key_even_on_a_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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



def _every_schema(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _every_schema(value)
    elif isinstance(node, list):
        for value in node:
            yield from _every_schema(value)


def test_the_structured_output_schema_is_one_the_api_accepts() -> None:
    """Hit live on the owner's key (2026-09-18): a property without a `type`, and `minimum`/
    `maximum` on a number, are both refused by the API's structured output — every upload was
    a 500. Every property carries a type; no numeric bounds ride in the schema."""
    from app.ingestion.claude_extract import _SCHEMA

    for props in (node["properties"] for node in _every_schema(_SCHEMA) if isinstance(node, dict) and "properties" in node):
        for name, prop in props.items():
            assert "type" in prop, name
            assert "minimum" not in prop and "maximum" not in prop, name
