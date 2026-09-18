"""The real adapters behind the feed's two ports (`app.delivery.feed.compress`): a search that
reads the allowlist through Claude's own web-search and web-fetch tools, and a compressor that
turns a fetched page into the plain-words lines a card says, through Claude's structured
output. Both wrap the official `anthropic` Python SDK; neither is imported anywhere but here
and `app.main` — a caller only ever sees the two ports.

`searcher_for` and `compressor_for` are the selection a deployment makes at startup
(`app.main.providers_for`), the way `app.drugs.client.drug_registry_for` and
`app.channels.whatsapp.provider.whatsapp_provider_for` already choose their adapter:
NURA_SEARCHER and NURA_COMPRESSOR name one, `fixture` by default, and `claude` reads
ANTHROPIC_API_KEY from the environment. Both Claude adapters refuse to construct outside a
declared demo (`NURA_DEMO_MODE=1`) or a declared dev run (`NURA_DEV_CODE_SENDER=1`) on the
owner's own laptop — there is no in-region provider yet, so a real deployment's data must not
leave the region for this, and a dev run is the owner choosing for himself to run his own
documents through his own key (ADR 0017) — and refuse without the key either way. Nothing here
logs the key or writes it anywhere; it is held in memory only, for the one client it
constructs. `app.llm.residency.allow_external_model` is the one gate this and every other
Claude-backed adapter's construction site shares.

What a page becomes is still decided in `app.delivery.feed.search` and `app.delivery.feed.
compress`, not here: an empty or missing citation is rejected there (`uncited`), a line that
would start, stop or change a medicine is rerouted there (`changes_treatment`), and every card
still passes the plain-words verifier there (`NotPlainWords`). A Claude response that refuses,
errors, or cannot be parsed as the schema it was asked for answers with nothing — `[]` from a
search, `None` from a compression — the same clean "nothing for him" a fixture with no matching
file already answers with; it is never treated as a card in disguise.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from anthropic import APIStatusError

from app.delivery.feed.compress import (
    Compressed,
    Compressor,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    Searcher,
)
from app.llm.residency import allow_external_model
from app.settings import MissingSetting, Settings

log = logging.getLogger("nura.delivery.feed.claude")

MODEL = "claude-opus-5"
WEB_SEARCH_TOOL = "web_search_20260209"
WEB_FETCH_TOOL = "web_fetch_20260209"

_VIDEO_HOSTS = ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com")


class ClaudeAdapterNotAvailable(RuntimeError):
    """No Claude searcher or compressor outside a declared demo or a declared dev run, or
    without an API key: data residency means no in-region provider exists yet, so this
    adapter refuses to construct."""


class NoSearcher(RuntimeError):
    """NURA_SEARCHER names an adapter this build does not have."""


class NoCompressor(RuntimeError):
    """NURA_COMPRESSOR names an adapter this build does not have."""


def _checked_key(*, api_key: str | None, demo_mode: bool, dev_run: bool, what: str) -> str:
    """The one gate both adapters share: a declared demo or a declared dev run, and a key.
    Never a default, never inferred — the way a cross-region provider is refused everywhere
    else in this file."""
    allow_external_model(
        demo_mode=demo_mode,
        dev_run=dev_run,
        refusal=ClaudeAdapterNotAvailable,
        what=f"the Claude {what}",
    )
    if not api_key:
        raise ClaudeAdapterNotAvailable(
            f"the Claude {what} needs ANTHROPIC_API_KEY set in the environment"
        )
    return api_key


def _client(api_key: str) -> Any:
    import anthropic  # local import: only a deployment that runs the claude adapters needs it

    return anthropic.Anthropic(api_key=api_key)


SEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "publisher": {"type": "string"},
                    "text": {"type": "string"},
                    "published_at": {"type": "string"},
                    "media": {"type": "string", "enum": ["article", "video"]},
                    "licence": {"type": ["string", "null"]},
                },
                "required": ["title", "url", "publisher", "text", "media"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}
"""The raw JSON schema `output_config.format.schema` asks for — a flat schema, never the
`{"name", "schema", "strict"}` wrapper an OpenAI-shaped `response_format` uses: the Anthropic
SDK's `JSONOutputFormatParam` only recognises `type` and `schema`, so that wrapper's `schema`
key was silently invisible to the API and every property lacked a `type` from the API's own
point of view — every searcher and compressor call read as `output_config.format:
Unexpected key 'json_schema'` and was refused with a 400 before the model ever ran (caught
live 2026-09-18; see `test_the_structured_output_schema_is_one_the_api_accepts` below)."""

COMPRESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "body": {"type": "array", "items": {"type": "string"}},
        "why_topic": {"type": "string"},
        "passage": {"type": "string"},
        "start_sec": {"type": ["integer", "null"]},
        "end_sec": {"type": ["integer", "null"]},
    },
    "required": ["headline", "body", "why_topic", "passage"],
    "additionalProperties": False,
}


def _structured_json(response: Any) -> dict[str, Any] | None:
    """The parsed JSON body of a structured-output response, or None when Claude refused
    (`stop_reason == "refusal"`), said nothing usable, or answered something that is not the
    JSON it was asked for — never guessed at."""
    if getattr(response, "stop_reason", None) == "refusal":
        return None
    for block in getattr(response, "content", None) or []:
        text = block.get("text") if isinstance(block, Mapping) else getattr(block, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _on_allowlist(url: str, allowed: Sequence[str]) -> str | None:
    """The allowlisted domain this url is on its own site of (`https`, host or subdomain),
    or None. A search result on any other site — whatever Claude was asked for — is dropped
    here, the same way a fixture page from an unlisted domain never reaches `search.run_job`."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        return None
    host = (parsed.hostname or "").lower()
    for domain in allowed:
        site = domain.strip().lower()
        if site and (host == site or host.endswith("." + site)):
            return site
    return None


def _looks_like_video(url: str) -> bool:
    host = (urlparse(url.strip()).hostname or "").lower()
    return host in _VIDEO_HOSTS


def _normalize_url(url: str) -> str:
    """Light normalisation for matching the model's claimed URL to a tool result's own URL:
    scheme and host lower-cased, trailing slash and fragment dropped. This is only ever used
    to compare one string to another — the allowlist decision itself (`_on_allowlist`) always
    runs on a tool's own URL, never on this normalised form."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    normalized = f"{scheme}://{host}{port}{path}"
    return f"{normalized}?{parsed.query}" if parsed.query else normalized


def _block_type(block: Any) -> str | None:
    if isinstance(block, Mapping):
        return block.get("type")
    return getattr(block, "type", None)


def _block_field(block: Any, key: str) -> Any:
    if block is None:
        return None
    if isinstance(block, Mapping):
        return block.get(key)
    return getattr(block, key, None)


def _fetch_document_text(fetch_result: Any) -> str:
    """The plain text of a `web_fetch_tool_result`'s document, however its `source` carries
    it. Anything that is not plain text (an image, a PDF this port does not parse here)
    answers `''` — never falls back to the model's own restated text."""
    document = _block_field(fetch_result, "content")
    source = _block_field(document, "source")
    if source is None:
        return ""
    kind = _block_field(source, "type")
    data = _block_field(source, "data")
    if kind in (None, "text") and isinstance(data, str) and data.strip():
        return data
    return ""


def _tool_results(response: Any) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """What the server tools themselves returned — never the model's prose. `tool_urls` maps
    every URL a `web_search_tool_result` or `web_fetch_tool_result` block named (normalised)
    to that tool's own, un-normalised URL. `fetched` maps the same normalised key, for
    `web_fetch_tool_result` blocks only, to `(resolved_url, document_text)`: the one place a
    found item's text is allowed to come from. A page the model mentions but no tool result
    named is in neither map, and a page a tool named but never fetched has no entry in
    `fetched` — both are how `_found_from_entry` drops an item, never by trusting the model."""
    tool_urls: dict[str, str] = {}
    fetched: dict[str, tuple[str, str]] = {}
    for block in getattr(response, "content", None) or []:
        block_type = _block_type(block)
        if block_type == "web_search_tool_result":
            content = _block_field(block, "content") or []
            if not isinstance(content, Sequence) or isinstance(content, (str, bytes)):
                continue
            for result in content:
                url = str(_block_field(result, "url") or "").strip()
                if url:
                    tool_urls[_normalize_url(url)] = url
        elif block_type == "web_fetch_tool_result":
            fetch_result = _block_field(block, "content")
            url = str(_block_field(fetch_result, "url") or "").strip()
            if not url:
                continue
            key = _normalize_url(url)
            tool_urls[key] = url
            text = _fetch_document_text(fetch_result).strip()
            if text:
                fetched[key] = (url, text)
    return tool_urls, fetched


def _found_from_entry(
    entry: Mapping[str, Any],
    allowed: Sequence[str],
    tool_urls: Mapping[str, str],
    fetched: Mapping[str, tuple[str, str]],
) -> Found | None:
    """A card's page, built only from what the server tools themselves returned. A fetched
    page could make the model write an allowlisted URL into its JSON while the text it gives
    came from an off-list page or a redirect — so the model's own `url` and `text` are never
    trusted here. The model's claimed URL must match, after `_normalize_url`, a URL a tool
    result actually named; that tool's own URL (never the model's string) must be on the
    allowlist; and the text must be the matching `web_fetch_tool_result` document's own text.
    Short of all three, the item is dropped — never a fallback to the model's prose."""
    claimed_url = str(entry.get("url") or "").strip()
    if not claimed_url:
        return None
    key = _normalize_url(claimed_url)
    tool_url = tool_urls.get(key)
    if tool_url is None:
        return None
    domain = _on_allowlist(tool_url, allowed)
    if domain is None:
        return None
    fetch = fetched.get(key)
    if fetch is None:
        # A tool named this URL but never fetched it (or the fetch was not text): there is
        # nowhere else in the port's shape to get real text from, so the item is dropped
        # rather than compressing the model's restated version of it.
        return None
    _, text = fetch
    title = str(entry.get("title") or "").strip()
    if not title or not text:
        return None
    media = "video" if entry.get("media") == "video" or _looks_like_video(tool_url) else None
    licence = entry.get("licence")
    return Found(
        domain=domain,
        url=tool_url,
        title=title,
        published_at=str(entry.get("published_at") or ""),
        text=text,
        media=media,
        licence=str(licence).strip() if media == "video" and licence else None,
    )


class ClaudeSearcher:
    """The `Searcher` port, answered for real: Claude's own `web_search` and `web_fetch` server
    tools, asked for pages on the allowlisted publishers only, structured to the shape this
    port promises. The allowlist is enforced twice — once in the prompt, and again here on
    every URL a tool result itself returned (`_on_allowlist`, through `_tool_results` and
    `_found_from_entry`) — never on the URL string the model writes into its JSON, because a
    model asked to stay on a list is not the same guarantee as a caller that never returns a
    page off it, or a page whose text did not come from where its URL says it did."""

    def __init__(
        self,
        *,
        api_key: str | None,
        demo_mode: bool,
        dev_run: bool = False,
        client: Any | None = None,
    ) -> None:
        key = _checked_key(api_key=api_key, demo_mode=demo_mode, dev_run=dev_run, what="searcher")
        self._client = client if client is not None else _client(key)

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        found: list[Found] = []
        for term in terms:
            found.extend(self._ask(f"{kind}: {term}", domains))
        return found

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        results = self._ask(" ".join(words), domains, media=media)
        if media is None:
            return results
        return [one for one in results if one.media == media]

    def _ask(self, query: str, domains: Sequence[str], *, media: str | None = None) -> list[Found]:
        allowed = [domain.strip().lower() for domain in domains if domain.strip()]
        if not allowed or not query.strip():
            return []
        only = " Only pages whose video is on that publisher's own site." if media == "video" else ""
        prompt = (
            "Search only these publishers, no others: "
            + ", ".join(sorted(set(allowed)))
            + f". Find pages about: {query.strip()}." + only
            + " For each page, fetch it and give its full plain-text body, not a snippet."
            " A page is `media: \"video\"` only when what it shows is a video; otherwise"
            ' `media: "article"`.'
        )
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=8192,
                tools=[
                    {"type": WEB_SEARCH_TOOL, "name": "web_search"},
                    {"type": WEB_FETCH_TOOL, "name": "web_fetch"},
                ],
                output_config={"format": {"type": "json_schema", "schema": SEARCH_SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as failed:  # noqa: BLE001 — a call that fails answers nothing, never a guess
            # Never the query's own words past this line — only the exception's own class
            # and, for an API refusal, its status and message (never the request content),
            # so a schema the API rejects (a 400) is distinguishable in the log from a
            # timeout or a connection drop, instead of one identical silent line either way.
            log.warning(
                "claude searcher call failed (%s%s)",
                type(failed).__name__,
                f": {failed}" if isinstance(failed, APIStatusError) else "",
            )
            return []
        payload = _structured_json(response)
        if payload is None:
            return []
        tool_urls, fetched = _tool_results(response)
        if not tool_urls:
            # No web_search_tool_result or web_fetch_tool_result blocks at all: never fall
            # back to trusting the model's own URLs.
            return []
        results: list[Found] = []
        for entry in payload.get("results", []) or []:
            if not isinstance(entry, Mapping):
                continue
            one = _found_from_entry(entry, allowed, tool_urls, fetched)
            if one is not None:
                results.append(one)
        return results


def _compress_prompt(text: str, language: str, facts: Mapping[str, Any]) -> str:
    grounding = json.dumps(dict(facts), ensure_ascii=False) if facts else "{}"
    return (
        f"Write a short, plain-words learning card in language code {language!r} from the page "
        "text below, for a layperson managing a family member's health at home. Ground it only "
        "on what the page says and on these facts already on his record (JSON): "
        f"{grounding}. Quote, verbatim, the exact passage of the page the lines came from as "
        "`passage`; if nothing on the page is relevant to him, answer with an empty `passage` "
        "and empty `body`. Never write a line that would tell him to start, stop, double, "
        "reduce or otherwise change a medicine or its dose — that is a question for his doctor, "
        "not a card, so leave it out.\n\nPage text:\n" + text
    )


class ClaudeCompressor:
    """The `Compressor` port, answered for real: one call to Claude's structured output, asked
    to ground on the page and the facts already on his record, and to cite the passage its
    lines came from. `search.run_job` still rejects an empty citation, still reroutes a line
    that would change treatment, and still runs every line through the plain-words verifier —
    nothing here is trusted past those checks."""

    def __init__(
        self,
        *,
        api_key: str | None,
        demo_mode: bool,
        dev_run: bool = False,
        client: Any | None = None,
    ) -> None:
        key = _checked_key(
            api_key=api_key, demo_mode=demo_mode, dev_run=dev_run, what="compressor"
        )
        self._client = client if client is not None else _client(key)

    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        if not text.strip():
            return None
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=4096,
                output_config={"format": {"type": "json_schema", "schema": COMPRESS_SCHEMA}},
                messages=[{"role": "user", "content": _compress_prompt(text, language, facts)}],
            )
        except Exception as failed:  # noqa: BLE001 — a call that fails compresses nothing, never a guess
            # Same rule as the searcher above: the page text and the facts never reach the
            # log, only the exception's own class and, for an API refusal, its status and
            # message — so a rejected schema (a 400) reads as its own case, not a silent
            # line indistinguishable from a timeout.
            log.warning(
                "claude compressor call failed (%s%s)",
                type(failed).__name__,
                f": {failed}" if isinstance(failed, APIStatusError) else "",
            )
            return None
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            # A clean refusal, the same "nothing for him" a fixture with no matching file
            # already answers with — never coerced into a card.
            log.info("claude compressor refused")
            return None
        payload = _structured_json(response)
        if payload is None:
            return None
        headline = str(payload.get("headline") or "").strip()
        body = tuple(
            line.strip() for line in payload.get("body", []) or [] if str(line).strip()
        )
        why_topic = str(payload.get("why_topic") or "").strip()
        passage = str(payload.get("passage") or "").strip()
        if not headline or not body or not why_topic:
            return None
        start_sec = payload.get("start_sec")
        end_sec = payload.get("end_sec")
        return Compressed(
            headline=headline,
            body=body,
            why_topic=why_topic,
            passage=passage,
            start_sec=int(start_sec) if isinstance(start_sec, int) else None,
            end_sec=int(end_sec) if isinstance(end_sec, int) else None,
        )


def searcher_for(settings: Settings) -> Searcher:
    """The searcher this deployment runs on: `NURA_SEARCHER`, `fixture` by default."""
    if settings.searcher == "claude":
        return ClaudeSearcher(
            api_key=settings.anthropic_api_key,
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
        )
    if settings.searcher == "fixture":
        if settings.feed_fixtures is None:
            raise MissingSetting("NURA_FEED_FIXTURES is not set and there is no other searcher yet")
        return FixtureSearcher(Path(settings.feed_fixtures))
    raise NoSearcher(
        f"no searcher named {settings.searcher!r} is built; set NURA_SEARCHER=fixture or claude"
    )


def compressor_for(settings: Settings) -> Compressor:
    """The compressor this deployment runs on: `NURA_COMPRESSOR`, `fixture` by default."""
    if settings.compressor == "claude":
        return ClaudeCompressor(
            api_key=settings.anthropic_api_key,
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
        )
    if settings.compressor == "fixture":
        if settings.feed_fixtures is None:
            raise MissingSetting(
                "NURA_FEED_FIXTURES is not set and there is no other compressor yet"
            )
        return FixtureCompressor(Path(settings.feed_fixtures))
    raise NoCompressor(
        f"no compressor named {settings.compressor!r} is built; set NURA_COMPRESSOR=fixture or claude"
    )
