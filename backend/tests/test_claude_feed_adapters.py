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
class FakeWebSearchResult:
    """One entry of a `web_search_tool_result` block's own `content` — the tool's own URL,
    never the model's."""

    url: str
    title: str = ""
    type: str = "web_search_result"


@dataclass
class FakeWebSearchToolResult:
    content: Sequence[FakeWebSearchResult]
    type: str = "web_search_tool_result"


@dataclass
class FakeFetchSource:
    data: str
    type: str = "text"


@dataclass
class FakeFetchDocument:
    source: FakeFetchSource
    type: str = "document"


@dataclass
class FakeFetchResult:
    """A `web_fetch_tool_result` block's own `content`: the *resolved* URL the fetch actually
    landed on (which a redirect can make different from the URL that was asked for) and the
    document it fetched."""

    url: str
    content: FakeFetchDocument
    type: str = "web_fetch_result"


@dataclass
class FakeWebFetchToolResult:
    content: FakeFetchResult
    type: str = "web_fetch_tool_result"


@dataclass
class FakeResponse:
    content: Sequence[Any]
    stop_reason: str = "end_turn"


def _search_result_block(urls: Sequence[str]) -> FakeWebSearchToolResult:
    """A `web_search_tool_result` block naming exactly these URLs, as the tool itself found
    them."""
    return FakeWebSearchToolResult(content=[FakeWebSearchResult(url=url) for url in urls])


def _fetch_result_block(url: str, text: str, *, resolved: str | None = None) -> FakeWebFetchToolResult:
    """A `web_fetch_tool_result` block: `url` is what was asked for, `resolved` is the URL the
    fetch actually landed on (a redirect can make it a different site) and defaults to `url`
    when there was no redirect. `text` is the document's own body."""
    return FakeWebFetchToolResult(
        content=FakeFetchResult(
            url=resolved if resolved is not None else url,
            content=FakeFetchDocument(source=FakeFetchSource(data=text)),
        )
    )


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


def _search_response(
    results: list[dict[str, Any]],
    *,
    tool_blocks: Sequence[Any] = (),
    stop_reason: str = "end_turn",
) -> FakeResponse:
    content: list[Any] = [*tool_blocks, FakeBlock(json.dumps({"results": results}))]
    return FakeResponse(content=content, stop_reason=stop_reason)


def _compress_response(payload: dict[str, Any] | None, *, stop_reason: str = "end_turn") -> FakeResponse:
    content = [] if payload is None else [FakeBlock(json.dumps(payload))]
    return FakeResponse(content=content, stop_reason=stop_reason)


# ---------------------------------------------------------------------------
# Refusal without a declared demo and a declared dev run, or without a key: no in-region
# provider yet (ADR 0017, and its dev-run addendum).
# ---------------------------------------------------------------------------


def test_claude_searcher_refuses_without_demo_mode_or_dev_run() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="declared demo"):
        ClaudeSearcher(api_key="sk-test", demo_mode=False, dev_run=False)


def test_claude_searcher_builds_on_a_declared_dev_run_without_demo_mode() -> None:
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=False, dev_run=True, client=object())
    assert isinstance(searcher, ClaudeSearcher)


def test_claude_searcher_refuses_without_an_api_key() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeSearcher(api_key=None, demo_mode=True)
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeSearcher(api_key="", demo_mode=True)


def test_claude_compressor_refuses_without_demo_mode_or_dev_run() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="declared demo"):
        ClaudeCompressor(api_key="sk-test", demo_mode=False, dev_run=False)


def test_claude_compressor_builds_on_a_declared_dev_run_without_demo_mode() -> None:
    compressor = ClaudeCompressor(
        api_key="sk-test", demo_mode=False, dev_run=True, client=object()
    )
    assert isinstance(compressor, ClaudeCompressor)


def test_claude_compressor_refuses_without_an_api_key() -> None:
    with pytest.raises(ClaudeAdapterNotAvailable, match="ANTHROPIC_API_KEY"):
        ClaudeCompressor(api_key=None, demo_mode=True)


# ---------------------------------------------------------------------------
# ClaudeSearcher: shape, the allowlist filter, and video tagging.
# ---------------------------------------------------------------------------


def test_claude_searcher_returns_the_ports_found_shape() -> None:
    url = "https://healthhub.sg/live-healthy/bp"
    text = "Checking your blood pressure regularly helps you and your doctor."
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Managing high blood pressure",
                        "url": url,
                        "publisher": "HealthHub",
                        "text": text,
                        "published_at": "2026-01-01",
                        "media": "article",
                    }
                ],
                tool_blocks=[_search_result_block([url]), _fetch_result_block(url, text)],
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
    on_list_url = "https://healthhub.sg/a"
    off_list_url = "https://not-allowlisted.example/a"
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "On the list",
                        "url": on_list_url,
                        "publisher": "HealthHub",
                        "text": "This page is on the allowlist.",
                        "media": "article",
                    },
                    {
                        "title": "Not on the list",
                        "url": off_list_url,
                        "publisher": "Some Blog",
                        "text": "This page is not on the allowlist.",
                        "media": "article",
                    },
                ],
                tool_blocks=[
                    _search_result_block([on_list_url, off_list_url]),
                    _fetch_result_block(on_list_url, "This page is on the allowlist."),
                    _fetch_result_block(off_list_url, "This page is not on the allowlist."),
                ],
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    found = searcher.search("explainer", ["diabetes"], ALLOWLIST)
    assert [one.url for one in found] == ["https://healthhub.sg/a"]


def test_claude_searcher_only_returns_https_pages_on_the_named_domain() -> None:
    wrong_scheme = "http://healthhub.sg/a"
    lookalike = "https://healthhub.sg.evil.example/a"
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Wrong scheme",
                        "url": wrong_scheme,
                        "publisher": "HealthHub",
                        "text": "Not https.",
                        "media": "article",
                    },
                    {
                        "title": "Lookalike host",
                        "url": lookalike,
                        "publisher": "HealthHub",
                        "text": "Not really healthhub.sg.",
                        "media": "article",
                    },
                ],
                tool_blocks=[
                    _search_result_block([wrong_scheme, lookalike]),
                    _fetch_result_block(wrong_scheme, "Not https."),
                    _fetch_result_block(lookalike, "Not really healthhub.sg."),
                ],
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    assert searcher.search("explainer", ["x"], ALLOWLIST) == []


def test_claude_searcher_tags_video_results() -> None:
    url = "https://healthhub.sg/videos/bp-check"
    text = "A short video on checking your blood pressure at home."
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "How to check your blood pressure",
                        "url": url,
                        "publisher": "HealthHub",
                        "text": text,
                        "media": "video",
                        "licence": "permission",
                    }
                ],
                tool_blocks=[_search_result_block([url]), _fetch_result_block(url, text)],
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    found = searcher.find(["blood", "pressure"], ALLOWLIST, media="video")
    assert len(found) == 1
    assert found[0].media == "video"
    assert found[0].licence == "permission"


def test_claude_searcher_find_media_filter_excludes_articles() -> None:
    url = "https://healthhub.sg/a"
    text = "Plain text about diabetes."
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "An article, not a video",
                        "url": url,
                        "publisher": "HealthHub",
                        "text": text,
                        "media": "article",
                    }
                ],
                tool_blocks=[_search_result_block([url]), _fetch_result_block(url, text)],
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
# ClaudeSearcher: the allowlist is checked against what the tools themselves returned, never
# against the URL string the model writes into its final JSON (the safety-review fix).
# ---------------------------------------------------------------------------


def test_claude_searcher_drops_a_model_claimed_url_absent_from_the_tool_results() -> None:
    """A fetched page could make the model write an allowlisted URL into its JSON while the
    text it gives came from somewhere else entirely. If no `web_search_tool_result` or
    `web_fetch_tool_result` block ever named that URL, the model's own say-so is not enough —
    the item is dropped."""
    claimed_url = "https://healthhub.sg/live-healthy/bp"
    other_url = "https://healthhub.sg/some-other-page"
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Managing high blood pressure",
                        "url": claimed_url,
                        "publisher": "HealthHub",
                        "text": "Checking your blood pressure regularly helps you and your doctor.",
                        "media": "article",
                    }
                ],
                # The tools only ever named a different page — never `claimed_url`.
                tool_blocks=[
                    _search_result_block([other_url]),
                    _fetch_result_block(other_url, "Some other page entirely."),
                ],
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    assert searcher.search("explainer", ["blood pressure"], ALLOWLIST) == []


def test_claude_searcher_drops_a_fetch_whose_resolved_url_is_off_list() -> None:
    """The model asks for an allowlisted page, but the fetch tool's own resolved URL (after a
    redirect) lands off the allowlist. The model then honestly reports the resolved URL — so
    it matches a tool result — but that tool's own URL is not on the allowlist, and the item
    is still dropped."""
    resolved_off_list = "https://off-list-redirect.example/landed-here"
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Redirected away from the allowlist",
                        "url": resolved_off_list,
                        "publisher": "HealthHub",
                        "text": "This is what the redirect actually served.",
                        "media": "article",
                    }
                ],
                tool_blocks=[
                    _fetch_result_block(
                        "https://healthhub.sg/live-healthy/bp",
                        "This is what the redirect actually served.",
                        resolved=resolved_off_list,
                    )
                ],
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    assert searcher.search("explainer", ["blood pressure"], ALLOWLIST) == []


def test_claude_searcher_keeps_a_matching_allowlisted_fetch_with_its_fetched_text() -> None:
    """The good path: the model's claimed URL matches a `web_fetch_tool_result` whose own
    resolved URL is on the allowlist. The card's text is the tool's own fetched document text
    — not whatever the model restated in its `text` field."""
    url = "https://healthhub.sg/live-healthy/bp"
    fetched_text = "The tool's own fetched document body, verbatim, word for word."
    model_restated_text = "A shorter summary the model wrote in its own words."
    client = FakeClient(
        [
            _search_response(
                [
                    {
                        "title": "Managing high blood pressure",
                        "url": url,
                        "publisher": "HealthHub",
                        "text": model_restated_text,
                        "media": "article",
                    }
                ],
                tool_blocks=[
                    _search_result_block([url]),
                    _fetch_result_block(url, fetched_text),
                ],
            )
        ]
    )
    searcher = ClaudeSearcher(api_key="sk-test", demo_mode=True, client=client)
    found = searcher.search("explainer", ["blood pressure"], ALLOWLIST)
    assert len(found) == 1
    assert found[0].url == url
    assert found[0].domain == "healthhub.sg"
    assert found[0].text == fetched_text
    assert found[0].text != model_restated_text


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


def test_searcher_for_claude_without_demo_mode_or_dev_run_refuses() -> None:
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


def test_searcher_for_claude_on_a_declared_dev_run_constructs() -> None:
    """The owner's own laptop, his own key: a declared dev run alone is enough, without also
    being a declared demo (ADR 0017 addendum)."""
    settings = _settings(searcher="claude", dev_code_sender=True, anthropic_api_key="sk-test")
    assert isinstance(searcher_for(settings), ClaudeSearcher)


def test_compressor_for_claude_on_a_declared_dev_run_constructs() -> None:
    settings = _settings(compressor="claude", dev_code_sender=True, anthropic_api_key="sk-test")
    assert isinstance(compressor_for(settings), ClaudeCompressor)


def test_searcher_for_an_unknown_name_refuses() -> None:
    with pytest.raises(NoSearcher, match="madeup"):
        searcher_for(_settings(searcher="madeup"))


def test_compressor_for_an_unknown_name_refuses() -> None:
    with pytest.raises(NoCompressor, match="madeup"):
        compressor_for(_settings(compressor="madeup"))
