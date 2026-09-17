"""The narrated trace (the owner's "Claude narrating the demo" story): `FixtureNarrator` is
today's behaviour, unchanged and the default; `ClaudeNarrator` may rephrase a step's catalogue
label livelier, never invent one, never speak to a caregiver as though she were the patient,
never say a word that fails `docs/plain-words.md`. No live call: every test hands
`ClaudeNarrator` a fake that answers in memory, in `client.messages.create`'s exact shape
(`anthropic`), and asserts what came back — never a real API key, never a real request.

`narrator_for` (`app.search.narrator_provider`) is the other half: `NURA_NARRATOR=claude` must
refuse to build outside a declared demo (ADR 0017), mirroring `extractor_for`'s own refusal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.channels.about_him import Reader
from app.regions import Region
from app.search.claude_narrate import ClaudeNarrator
from app.search.narrate import FixtureNarrator, NarratedLine, NarratedStep
from app.search.narrator_provider import (
    ClaudeNarratorOutsideDemo,
    NoNarrator,
    narrator_for,
)
from app.settings import MissingSetting, Settings

HIS = Reader(his=True, language="en")
HERS = Reader(his=False, name="Pa", language="en")


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
    answers: list[_FakeMessage]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        return self.answers.pop(0)


@dataclass
class _FakeClient:
    messages: _FakeMessages


def _client_answering(*payloads: dict[str, Any] | str, stop_reason: str = "end_turn") -> _FakeClient:
    answers = [
        _FakeMessage(
            content=[_TextBlock(text=p if isinstance(p, str) else json.dumps(p))],
            stop_reason=stop_reason,
        )
        for p in payloads
    ]
    return _FakeClient(messages=_FakeMessages(answers=answers))


async def _narrated(client: _FakeClient, steps: list[NarratedStep], *, reader: Reader = HIS) -> list[Any]:
    narrator = ClaudeNarrator(client)  # type: ignore[arg-type]
    return [line async for line in narrator.narrate(steps, language="en", reader=reader)]


# -- FixtureNarrator: today's behaviour, unchanged, the default ----------------------------


async def test_the_fixture_narrator_returns_each_steps_own_catalogue_label() -> None:
    narrator = FixtureNarrator()
    steps = [
        NarratedStep(key="visits", label="Checking your visits.", count=1),
        NarratedStep(key="medicines", label="Checking your medicines.", count=2),
    ]
    lines = [line async for line in narrator.narrate(steps, language="en", reader=HIS)]
    assert [(line.key, line.text) for line in lines] == [
        ("visits", "Checking your visits."),
        ("medicines", "Checking your medicines."),
    ]
    assert narrator.external_processor is None


async def test_the_fixture_narrator_on_no_steps_yields_nothing() -> None:
    narrator = FixtureNarrator()
    lines = [line async for line in narrator.narrate([], language="en", reader=HIS)]
    assert lines == []


# -- ClaudeNarrator: rephrases, never invents, always safe ----------------------------------


async def test_a_rephrased_line_is_used_when_it_is_safe() -> None:
    client = _client_answering({"lines": [{"step": "medicines", "text": "Now checking his medicines."}]})
    steps = [NarratedStep(key="medicines", label="Checking his medicines.", count=4)]

    lines = await _narrated(client, steps, reader=HERS)

    assert lines == [NarratedLine(key="medicines", text="Now checking his medicines.")]
    sent = client.messages.calls[0]
    assert sent["model"] == "claude-opus-5"
    assert "output_format" not in sent
    assert sent["output_config"]["format"]["type"] == "json_schema"


async def test_a_line_for_a_step_id_not_given_is_dropped() -> None:
    """The model may only rephrase the steps it is given; a line for a step id it invents is
    dropped, never shown — the given step keeps its own catalogue label instead."""
    client = _client_answering(
        {
            "lines": [
                {"step": "medicines", "text": "Now checking his medicines."},
                {"step": "readings", "text": "Also checking his blood pressure."},
            ]
        }
    )
    steps = [NarratedStep(key="medicines", label="Checking his medicines.", count=4)]

    lines = await _narrated(client, steps, reader=HERS)

    assert [line.key for line in lines] == ["medicines"]
    assert lines[0].text == "Now checking his medicines."


async def test_a_line_that_fails_plain_words_falls_back_to_the_catalogue_label() -> None:
    client = _client_answering(
        {"lines": [{"step": "records", "text": "Recheck flagged docs re: non-compliant meds"}]}
    )
    steps = [NarratedStep(key="records", label="Looking at your papers.", count=2)]

    lines = await _narrated(client, steps)

    assert lines[0].text == "Looking at your papers."


async def test_a_caregivers_line_that_speaks_to_him_directly_falls_back() -> None:
    """A rephrasing meant for a caregiver's voice must never say "you" or "your" to her about
    him — the same "speaks to him" check the about-him twin test uses
    (`app.channels.about_him.Reader.speaks_to_him`)."""
    client = _client_answering({"lines": [{"step": "medicines", "text": "Checking your medicines now."}]})
    steps = [NarratedStep(key="medicines", label="Checking his medicines.", count=1)]

    lines = await _narrated(client, steps, reader=HERS)

    assert lines[0].text == "Checking his medicines."  # the catalogue label, not the model's


async def test_a_line_that_speaks_to_him_is_fine_on_his_own_key() -> None:
    client = _client_answering({"lines": [{"step": "medicines", "text": "Checking your medicines now."}]})
    steps = [NarratedStep(key="medicines", label="Checking your medicines.", count=1)]

    lines = await _narrated(client, steps, reader=HIS)

    assert lines[0].text == "Checking your medicines now."


async def test_a_refusal_falls_back_to_every_steps_catalogue_label() -> None:
    client = _client_answering({"lines": []}, stop_reason="refusal")
    steps = [
        NarratedStep(key="visits", label="Checking your visits.", count=1),
        NarratedStep(key="medicines", label="Checking your medicines.", count=2),
    ]

    lines = await _narrated(client, steps)

    assert [(line.key, line.text) for line in lines] == [
        ("visits", "Checking your visits."),
        ("medicines", "Checking your medicines."),
    ]


async def test_a_truncated_answer_at_max_tokens_falls_back_too() -> None:
    client = _client_answering({"lines": []}, stop_reason="max_tokens")
    steps = [NarratedStep(key="records", label="Looking at your papers.", count=1)]

    lines = await _narrated(client, steps)

    assert lines[0].text == "Looking at your papers."


@pytest.mark.parametrize(
    "text",
    ["not json at all", "{}", json.dumps({"lines": "not a list"})],
)
async def test_a_malformed_answer_falls_back_not_a_crash(text: str) -> None:
    client = _client_answering(text)
    steps = [NarratedStep(key="readings", label="Looking at your blood pressure book.", count=1)]

    lines = await _narrated(client, steps)

    assert lines[0].text == "Looking at your blood pressure book."


async def test_no_steps_makes_no_call_at_all() -> None:
    client = _client_answering({"lines": []})
    lines = await _narrated(client, [])
    assert lines == []
    assert client.messages.calls == []


# -- narrator_for: the residency refusal (ADR 0017) ------------------------------------------


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"region": Region.SG, "database_url": "sqlite+aiosqlite://"}
    base.update(overrides)
    return Settings(**base)


def test_the_default_narrator_is_the_fixture_one() -> None:
    narrator = narrator_for(_settings())
    assert isinstance(narrator, FixtureNarrator)


def test_claude_refuses_to_build_outside_a_declared_demo() -> None:
    with pytest.raises(ClaudeNarratorOutsideDemo):
        narrator_for(_settings(narrator="claude", anthropic_api_key="sk-test-not-real"))


def test_claude_refuses_to_build_on_a_plain_dev_run_too() -> None:
    with pytest.raises(ClaudeNarratorOutsideDemo):
        narrator_for(
            _settings(narrator="claude", dev_code_sender=True, anthropic_api_key="sk-test-not-real")
        )


def test_claude_builds_on_a_declared_demo() -> None:
    narrator = narrator_for(
        _settings(
            narrator="claude",
            demo_mode=True,
            demo_login_code="123456",
            anthropic_api_key="sk-test-not-real",
        )
    )
    assert isinstance(narrator, ClaudeNarrator)


def test_claude_refuses_to_build_without_a_key_even_on_a_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingSetting):
        narrator_for(_settings(narrator="claude", demo_mode=True, demo_login_code="123456"))


def test_an_unknown_narrator_name_refuses_to_start() -> None:
    with pytest.raises(NoNarrator):
        narrator_for(_settings(narrator="chatty-3000"))
