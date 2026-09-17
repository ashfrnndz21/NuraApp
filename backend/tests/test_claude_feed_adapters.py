"""The Claude-backed adapters behind the feed's two ports (real article and video feeds):
`ClaudeSearcher`/`ClaudeCompressor` (`app.delivery.feed.claude_adapters`), and their selection
by `NURA_SEARCHER`/`NURA_COMPRESSOR` at startup (`searcher_for`/`compressor_for`).

Every test here mocks the `anthropic` client. Nothing here calls a live service — the same
rule `docs/checkpoints.md` holds every other adapter to: deterministic inputs, no network.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from app.delivery.feed.claude_adapters import (
    ClaudeAdapterNotAvailable,
    ClaudeCompressor,
    ClaudeSearcher,
    NoCompressor,
    NoSearcher,
    compressor_for,
    searcher_for,
)
from app.delivery.feed.compress import (
    Compressed,
    Compressor,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    Searcher,
    changes_treatment,
)
from app.regions import Region
from app.settings import MissingSetting, Settings

ALLOWLIST = ["healthhub.sg", "moh.gov.sg"]


@dataclass
class FakeBlock:
    text: str


@dataclass
class FakeResponse:
    content: Sequence[Any]
    stop_reason: str = "end_turn"


class FakeMessages:
    """Stands in for `client.messages`: `create()` returns whatever was queued, in order, and
    remembers every call so a test can check the request shape (the prompt, the tools, the
    model) without a real client."""

    def __init__(self, responses: Sequence[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessages.create called more times than responses queued")
        return self._responses.pop(0)


class FakeClient:
    def __init__(self, responses: Sequence[FakeResponse]) -> None:
        self.messages = FakeMessages(responses)


def _search_response(results: list[dict[str, Any]], *, stop_reason: str = "end_turn") -> FakeResponse:
    return FakeResponse(
        content=[FakeBlock(json.dumps({"results": results}))], stop_reason=stop_reason
    )


def _compress_response(payload: dict[str, Any] | None, *, stop_reason: str = "end_turn") -> FakeResponse:
    content = [] if payload is None else [FakeBlock(json.dumps(payload))]
    return FakeResponse(content=content, stop_reason=stop_reason)


# ---------------------------------------------------------------------------
# Refusal without a declared demo, or without a key: no in-region provider yet.
# ---------------------------------------------------------------------------


def test_claude_searcher_refuses_without_demo_mode() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="declared demo"):
        ClaudeSearcher(api_key="sk-test", demo_mode=False)


def test_claude_searcher_refuses_without_an_api_key() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeSearcher(api_key=None, demo_mode=True)
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeSearcher(api_key="", demo_mode=True)


def test_claude_compressor_refuses_without_demo_mode() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="declared demo"):
        ClaudeCompressor(api_key="sk-test", demo_mode=False)


def test_claude_compressor_refuses_without_an_api_key() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeCompressor(api_key=None, demo_mode=True)


# ---------------------------------------------------------------------------
# ClaudeSearcher: shape, the allowlist filter, and video tagging.
# ---------------------------------------------------------------------------


def test_claude_searcher_returns_the_ports_found_shape() -> None:
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Managing high blood pressure",
                        "url": "https://healthhub.sg/live-healthy/bp",
                        "publisher": "HealthHub",
                        "text": "Checking your blood pressure regularly helps you and your doctor.",
                        "published_at": "2026-01-01",
                        "media": "article",
                    }
                ]
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    found = searcher.search("explainer", ["blood pressure"], ALLOWLIST)
    assert len(found) == 1
    one = found[0]
    assert isinstance(one, Found)
    assert one.domain == "healthhub.sg"
    assert one.url == "https://healthhub.sg/live-healthy/bp"
    assert one.title == "Managing high blood pressure"
    assert one.media is None
    assert "blood pressure" in one.text.lower()
    # The model, and every tool it was given, are named as the brief pins them.
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    tool_types = {tool["type"] for tool in call["tools"]}
    assert tool_types == {"web_search_20260209", "web_fetch_20260209"}
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_claude_searcher_drops_a_result_off_the_allowlist() -> None:
    """The allowlist is enforced here too, not only by the prompt: a page the model returns
    from a site it was not asked for is dropped, never smuggled onto a card (the same
    guarantee `FixtureSearcher.search` gives by construction)."""
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "On the list",
                        "url": "https://healthhub.sg/a",
                        "publisher": "HealthHub",
                        "text": "This page is on the allowlist.",
                        "media": "article",
                    },
                    {
                        "title": "Not on the list",
                        "url": "https://not-allowlisted.example/a",
                        "publisher": "Some Blog",
                        "text": "This page is not on the allowlist.",
                        "media": "article",
                    },
                ]
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    found = searcher.search("explainer", ["diabetes"], ALLOWLIST)
    assert [one.url for one in found] == ["https://healthhub.sg/a"]


def test_claude_searcher_only_returns_https_pages_on_the_named_domain() -> None:
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Wrong scheme",
                        "url": "http://healthhub.sg/a",
                        "publisher": "HealthHub",
                        "text": "Not https.",
                        "media": "article",
                    },
                    {
                        "title": "Lookalike host",
                        "url": "https://healthhub.sg.evil.example/a",
                        "publisher": "HealthHub",
                        "text": "Not really healthhub.sg.",
                        "media": "article",
                    },
                ]
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    assert searcher.search("explainer", ["x"], ALLOWLIST) == []


def test_claude_searcher_tags_video_results() -> None:
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "How to check your blood pressure",
                        "url": "https://healthhub.sg/videos/bp-check",
                        "publisher": "HealthHub",
                        "text": "A short video on checking your blood pressure at home.",
                        "media": "video",
                        "licence": "permission",
                    }
                ]
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    found = searcher.find(["blood", "pressure"], ALLOWLIST, media="video")
    assert len(found) == 1
    assert found[0].media == "video"
    assert found[0].licence == "permission"


def test_claude_searcher_find_media_filter_excludes_articles() -> None:
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "An article, not a video",
                        "url": "https://healthhub.sg/a",
                        "publisher": "HealthHub",
                        "text": "Plain text about diabetes.",
                        "media": "article",
                    }
                ]
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    assert searcher.find(["diabetes"], ALLOWLIST, media="video") == []


def test_claude_searcher_answers_nothing_on_a_refusal_or_a_bad_call() -> None:
    refused = FakeClient([_search_response([], stop_reason="refusal")])
    assert ClaudeSearcher(api_key="k", demo_mode=True, client=refused).search(
        "explainer", ["x"], ALLOWLIST
    ) == []

    class Explodes:
        class messages:
            @staticmethod
            def create(**_: Any) -> Any:
                raise RuntimeError("network is down")

    assert ClaudeSearcher(api_key="k", demo_mode=True, client=Explodes()).search(
        "explainer", ["x"], ALLOWLIST
    ) == []


def test_claude_searcher_with_no_domains_or_no_terms_calls_nothing() -> None:
    client = FakeClient([])
    searcher = ClaudeSearcher(api_key="k", demo_mode=True, client=client)
    assert searcher.search("explainer", ["x"], []) == []
    assert searcher.search("explainer", [], ALLOWLIST) == []
    assert client.messages.calls == []


# ---------------------------------------------------------------------------
# ClaudeCompressor: shape, and the stop_reason refusal.
# ---------------------------------------------------------------------------


def test_claude_compressor_returns_the_ports_compressed_shape() -> None:
    client = FakeClient(
        [
            _compress_response(
                {
                    "headline": "Your blood pressure, in plain words",
                    "body": ["Checking it often helps your doctor see the pattern."],
                    "why_topic": "your blood pressure",
                    "passage": "Checking your blood pressure regularly helps you and your doctor.",
                    "start_sec": None,
                    "end_sec": None,
                }
            )
        ]
    )
    compressor = ClaudeCompressor(api_key="k", demo_mode=True, client=client)
    out = compressor.compress(
        "Checking your blood pressure regularly helps you and your doctor.", "en", {}
    )
    assert isinstance(out, Compressed)
    assert out.headline == "Your blood pressure, in plain words"
    assert out.body == ("Checking it often helps your doctor see the pattern.",)
    assert out.why_topic == "your blood pressure"
    assert out.passage.strip() != ""
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_claude_compressor_refuses_cleanly_on_stop_reason_refusal() -> None:
    client = FakeClient([_compress_response(None, stop_reason="refusal")])
    compressor = ClaudeCompressor(api_key="k", demo_mode=True, client=client)
    assert compressor.compress("some page text", "en", {}) is None


def test_claude_compressor_answers_nothing_on_a_bad_call_or_bad_json() -> None:
    class Explodes:
        class messages:
            @staticmethod
            def create(**_: Any) -> Any:
                raise RuntimeError("network is down")

    assert ClaudeCompressor(api_key="k", demo_mode=True, client=Explodes()).compress(
        "text", "en", {}
    ) is None

    not_json = FakeClient([FakeResponse(content=[FakeBlock("not json at all")])])
    assert ClaudeCompressor(api_key="k", demo_mode=True, client=not_json).compress(
        "text", "en", {}
    ) is None


def test_claude_compressor_treats_an_empty_text_as_nothing_for_him() -> None:
    client = FakeClient([])
    compressor = ClaudeCompressor(api_key="k", demo_mode=True, client=client)
    assert compressor.compress("   ", "en", {}) is None
    assert client.messages.calls == []


def test_claude_compressor_output_still_meets_the_treatment_change_guard() -> None:
    """`Do not bypass the downstream checks`: whatever Claude writes, the same
    `changes_treatment` regex `search.run_job` runs against every compressor's lines still
    catches a line that would start, stop or change a medicine."""
    client = FakeClient(
        [
            _compress_response(
                {
                    "headline": "Stop taking your warfarin tablets",
                    "body": ["Stop taking your warfarin tablets today."],
                    "why_topic": "your warfarin",
                    "passage": "Some cited passage.",
                }
            )
        ]
    )
    compressor = ClaudeCompressor(api_key="k", demo_mode=True, client=client)
    out = compressor.compress("some page text", "en", {})
    assert out is not None
    assert changes_treatment([out.headline, *out.body])


# ---------------------------------------------------------------------------
# Conformance: both adapters answer the same shape as the fixtures do, behind the same ports.
# ---------------------------------------------------------------------------


def assert_searcher_conforms(searcher: Searcher, domains: Sequence[str]) -> None:
    found = searcher.search("explainer", ["anything"], domains)
    assert isinstance(found, Sequence)
    for one in found:
        assert isinstance(one, Found)
        assert one.domain in set(domains)
    also = searcher.find(["anything"], domains)
    assert isinstance(also, Sequence)


def assert_compressor_conforms(compressor: Compressor) -> None:
    out = compressor.compress("any text", "en", {})
    assert out is None or isinstance(out, Compressed)


def test_the_claude_searcher_conforms_to_the_port() -> None:
    client = FakeClient([_search_response([]), _search_response([])])
    assert_searcher_conforms(ClaudeSearcher(api_key="k", demo_mode=True, client=client), ALLOWLIST)


def test_the_claude_compressor_conforms_to_the_port() -> None:
    client = FakeClient([_compress_response(None, stop_reason="refusal")])
    assert_compressor_conforms(ClaudeCompressor(api_key="k", demo_mode=True, client=client))


def test_the_fixture_searcher_and_compressor_still_conform() -> None:
    # A guard against the selection wiring changing the fixtures' own shape: same conformance
    # helper, the adapter this build already had before this change.
    from pathlib import Path

    fixtures = Path(__file__).resolve().parent / "fixtures" / "feed"
    assert_searcher_conforms(FixtureSearcher(fixtures), ALLOWLIST)
    assert_compressor_conforms(FixtureCompressor(fixtures))


# ---------------------------------------------------------------------------
# Selection: NURA_SEARCHER / NURA_COMPRESSOR, and the demo-mode gate, end to end.
# ---------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "region": Region.SG,
        "database_url": "sqlite+aiosqlite://",
        "feed_fixtures": "tests/fixtures/feed",
    }
    base.update(overrides)
    return Settings(**base)


def test_searcher_for_defaults_to_the_fixture() -> None:
    assert isinstance(searcher_for(_settings()), FixtureSearcher)


def test_compressor_for_defaults_to_the_fixture() -> None:
    assert isinstance(compressor_for(_settings()), FixtureCompressor)


def test_searcher_for_fixture_without_feed_fixtures_refuses() -> None:
    with pytest.raises(MissingSetting):
        searcher_for(_settings(feed_fixtures=None))


def test_searcher_for_claude_without_demo_mode_refuses() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="declared demo"):
        searcher_for(_settings(searcher="claude", anthropic_api_key="sk-test"))


def test_searcher_for_claude_without_api_key_refuses() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        searcher_for(_settings(searcher="claude", demo_mode=True))


def test_searcher_for_claude_with_demo_mode_and_key_constructs() -> None:
    settings = _settings(searcher="claude", demo_mode=True, anthropic_api_key="sk-test")
    assert isinstance(searcher_for(settings), ClaudeSearcher)


def test_compressor_for_claude_with_demo_mode_and_key_constructs() -> None:
    settings = _settings(compressor="claude", demo_mode=True, anthropic_api_key="sk-test")
    assert isinstance(compressor_for(settings), ClaudeCompressor)


def test_searcher_for_an_unknown_name_refuses() -> None:
    with pytest.raises(NoSearcher, match="madeup"):
        searcher_for(_settings(searcher="madeup"))


def test_compressor_for_an_unknown_name_refuses() -> None:
    with pytest.raises(NoCompressor, match="madeup"):
        compressor_for(_settings(compressor="madeup"))
