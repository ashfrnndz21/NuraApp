"""The narrated trace (the owner's "Claude narrating the demo" story): `FixtureNarrator` is
today's behaviour, unchanged and the default; `ClaudeNarrator` may rephrase a step's catalogue
label livelier, never invent one, never speak to a caregiver as though she were the patient,
never say a word that fails `docs/plain-words.md`. No live call: every test hands
`ClaudeNarrator` a fake that answers in memory, in `client.messages.create`'s exact shape
(`anthropic`), and asserts what came back — never a real API key, never a real request.

`narrator_for` (`app.search.narrator_provider`) is the other half: `NURA_NARRATOR=claude` must
refuse to build outside a declared demo or a declared dev run (ADR 0017), mirroring
`extractor_for`'s own refusal.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx
import pytest

from app.channels.about_him import Reader
from app.llm import narrate as claude_narrate
from app.llm.narrate import ClaudeNarrator
from app.regions import Region
from app.search.narrate import (
    FixtureNarrator,
    NarratedLine,
    NarratedStep,
    Narrator,
    narrate_step_label,
)
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


# -- narrate_step_label: the background follow-up, never the step itself --------------------


@dataclass
class _RewordingNarrator:
    """A narrator that always has something different to say — the success case, standing in
    for a real `ClaudeNarrator` call that answered before its deadline."""

    external_processor: str | None = None

    async def narrate(
        self, steps: list[NarratedStep], *, language: str, reader: Reader
    ) -> Any:
        for step in steps:
            yield NarratedLine(key=step.key, text=f"{step.label} (said livelier)")


@dataclass
class _EchoingNarrator:
    """A narrator that always falls back to the very label it was given — standing in for
    every one of `ClaudeNarrator`'s own fallbacks (a timeout, a refusal, a truncated answer,
    an answer that failed a safety check): there is nothing new to say, whichever it was."""

    external_processor: str | None = None

    async def narrate(
        self, steps: list[NarratedStep], *, language: str, reader: Reader
    ) -> Any:
        for step in steps:
            yield NarratedLine(key=step.key, text=step.label)


async def test_narrate_step_label_returns_the_rephrasing_when_it_differs() -> None:
    steps = [NarratedStep(key="medicines", label="Checking your medicines.", count=2)]
    new_label = await narrate_step_label(
        _RewordingNarrator(), steps, "medicines", "Checking your medicines.", language="en", reader=HIS
    )
    assert new_label == "Checking your medicines. (said livelier)"


async def test_narrate_step_label_sends_nothing_when_the_narrator_falls_back() -> None:
    """The fallback case, whatever caused it (a timeout among them): the narrator resolved to
    the very label already sent, so there is nothing to send again."""
    steps = [NarratedStep(key="medicines", label="Checking your medicines.", count=2)]
    new_label = await narrate_step_label(
        _EchoingNarrator(), steps, "medicines", "Checking your medicines.", language="en", reader=HIS
    )
    assert new_label is None


async def test_narrate_step_label_ignores_a_line_for_a_different_step() -> None:
    narrator: Narrator = _RewordingNarrator()
    steps = [NarratedStep(key="visits", label="Checking your visits.", count=1)]
    new_label = await narrate_step_label(
        narrator, steps, "medicines", "Checking your medicines.", language="en", reader=HIS
    )
    assert new_label is None


# -- ClaudeNarrator: rephrases, never invents, always safe ----------------------------------


async def test_a_rephrased_line_is_used_when_it_is_safe() -> None:
    """A bare pronoun is not enough for a caregiver's voice: this candidate never names her
    ("Pa"), only says "his", so it now falls back to the catalogue label; the request itself
    is still shaped the way it should be."""
    client = _client_answering({"lines": [{"step": "medicines", "text": "Now checking his medicines."}]})
    steps = [NarratedStep(key="medicines", label="Checking his medicines.", count=4)]

    lines = await _narrated(client, steps, reader=HERS)

    assert lines == [NarratedLine(key="medicines", text="Checking his medicines.")]
    sent = client.messages.calls[0]
    # Haiku 4.5, not Opus: rephrasing a step that already happened, not deciding anything
    # (`app.llm.models.DEFAULT_MODELS[Task.NARRATE]`).
    assert sent["model"] == "claude-haiku-4-5-20251001"
    assert "output_format" not in sent
    assert sent["output_config"]["format"]["type"] == "json_schema"


async def test_an_honest_rephrase_that_names_her_and_keeps_the_count_is_used() -> None:
    """The positive twin of the test above: a rephrase that names the patient and keeps the
    step's own noun and count is the "safe" case the port exists to allow."""
    client = _client_answering(
        {"lines": [{"step": "medicines", "text": "Now checking Pa's medicines — 4 in all."}]}
    )
    steps = [NarratedStep(key="medicines", label="Checking his medicines.", count=4)]

    lines = await _narrated(client, steps, reader=HERS)

    assert lines == [NarratedLine(key="medicines", text="Now checking Pa's medicines — 4 in all.")]


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
    # "his" is a bare pronoun, not her name ("Pa") — falls back to the catalogue label.
    assert lines[0].text == "Checking his medicines."


async def test_a_line_that_fails_plain_words_falls_back_to_the_catalogue_label() -> None:
    client = _client_answering(
        {"lines": [{"step": "records", "text": "Recheck flagged docs re: non-compliant meds"}]}
    )
    steps = [NarratedStep(key="records", label="Looking at your papers.", count=2)]

    lines = await _narrated(client, steps)

    assert lines[0].text == "Looking at your papers."


@pytest.mark.parametrize("text", ["His pressure looks high.", "He should see a doctor."])
async def test_a_line_that_states_a_finding_or_advice_falls_back(text: str) -> None:
    """"Reads only" is enforced in code, not only asked for in the prompt: neither line names
    what the step actually opened ("medicines"), and each also trips the conclusion/advice
    blocklist, so both fall back to the catalogue label whatever the model said."""
    client = _client_answering({"lines": [{"step": "medicines", "text": text}]})
    steps = [NarratedStep(key="medicines", label="Checking your medicines.", count=4)]

    lines = await _narrated(client, steps)

    assert lines[0].text == "Checking your medicines."


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


async def test_a_timeout_falls_back_and_the_stream_continues() -> None:
    """The call itself failing must never hold back a real step or kill the stream: every
    step given still gets its line, from the catalogue, the same as a refusal already does."""

    class _FailingMessages:
        async def create(self, **kwargs: Any) -> _FakeMessage:
            raise anthropic.APITimeoutError(
                httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )

    client = _FakeClient(messages=_FailingMessages())  # type: ignore[arg-type]
    steps = [
        NarratedStep(key="visits", label="Checking your visits.", count=1),
        NarratedStep(key="medicines", label="Checking your medicines.", count=2),
    ]

    lines = await _narrated(client, steps)

    assert [(line.key, line.text) for line in lines] == [
        ("visits", "Checking your visits."),
        ("medicines", "Checking your medicines."),
    ]


async def test_a_slow_call_falls_back_within_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """A call slower than `NARRATE_DEADLINE_S` must never hold the real step back. The
    deadline itself is mocked short here so the test stays fast rather than actually waiting
    it out."""
    monkeypatch.setattr(claude_narrate, "NARRATE_DEADLINE_S", 0.05)

    class _SlowMessages:
        async def create(self, **kwargs: Any) -> _FakeMessage:
            await asyncio.sleep(5)
            raise AssertionError("should have been cancelled at the deadline")

    client = _FakeClient(messages=_SlowMessages())  # type: ignore[arg-type]
    steps = [NarratedStep(key="medicines", label="Checking your medicines.", count=1)]

    started = time.monotonic()
    lines = await _narrated(client, steps)
    elapsed = time.monotonic() - started

    assert lines[0].text == "Checking your medicines."
    assert elapsed < 1.0


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


def test_claude_refuses_to_build_outside_a_declared_demo_and_dev_run() -> None:
    with pytest.raises(ClaudeNarratorOutsideDemo):
        narrator_for(_settings(narrator="claude", anthropic_api_key="sk-test-not-real"))


def test_claude_builds_on_a_declared_dev_run() -> None:
    """The owner's own laptop, his own key: a declared dev run alone is enough, without also
    being a declared demo (ADR 0017 addendum)."""
    narrator = narrator_for(
        _settings(narrator="claude", dev_code_sender=True, anthropic_api_key="sk-test-not-real")
    )
    assert isinstance(narrator, ClaudeNarrator)


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


def _every_schema(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _every_schema(value)
    elif isinstance(node, list):
        for value in node:
            yield from _every_schema(value)


def test_the_structured_output_schema_is_one_the_api_accepts() -> None:
    """The same lint every Claude-backed structured-output adapter carries
    (`tests/test_claude_extractor.py`, `tests/test_claude_feed_adapters.py`,
    `tests/test_clipmaker.py`): a property without a `type`, and `minimum`/`maximum` on a
    number, are both refused by the API's structured output (hit live on the owner's key,
    2026-09-18, for the extractor and the feed adapters). Every property carries a type; no
    numeric bounds ride in this schema."""
    from app.llm.narrate import _SCHEMA

    for node in _every_schema(_SCHEMA):
        if not (isinstance(node, dict) and "properties" in node):
            continue
        for name, prop in node["properties"].items():
            assert "type" in prop, name
            assert "minimum" not in prop and "maximum" not in prop, name
