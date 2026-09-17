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
declared demo (`NURA_DEMO_MODE=1`) — there is no in-region provider yet, so a real deployment's
data must not leave the region for this — and refuse without the key. Nothing here logs the
key or writes it anywhere; it is held in memory only, for the one client it constructs.

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

from app.delivery.feed.compress import (
    Compressed,
    Compressor,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    Searcher,
)
from app.settings import MissingSetting, Settings

log = logging.getLogger("nura.delivery.feed.claude")

MODEL = "claude-opus-5"
WEB_SEARCH_TOOL = "web_search_20260209"
WEB_FETCH_TOOL = "web_fetch_20260209"

_VIDEO_HOSTS = ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com")


class ClaudeAdapterNotAvailable(RuntimeError):
    """No Claude searcher or compressor outside a declared demo, or without an API key: data
    residency means no in-region provider exists yet, so this adapter refuses to construct."""


class NoSearcher(RuntimeError):
    """NURA_SEARCHER names an adapter this build does not have."""


class NoCompressor(RuntimeError):
    """NURA_COMPRESSOR names an adapter this build does not have."""


def _checked_key(*, api_key: str | None, demo_mode: bool, what: str) -> str:
    """The one gate both adapters share: a declared demo, and a key. Never a default, never
    inferred — the way a cross-region provider is refused everywhere else in this file."""
    if not demo_mode:
        raise ClaudeAdapterNotAvailable(
            f"the Claude {what} runs only on a declared demo (NURA_DEMO_MODE=1): no in-region "
            "provider exists yet"
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
    "name": "feed_search_results",
    "schema": {
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
    },
    "strict": True,
}

COMPRESS_SCHEMA: dict[str, Any] = {
    "name": "feed_compressed_card",
    "schema": {
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
    },
    "strict": True,
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


def _found_from_entry(entry: Mapping[str, Any], allowed: Sequence[str]) -> Found | None:
    url = str(entry.get("url") or "").strip()
    domain = _on_allowlist(url, allowed)
    title = str(entry.get("title") or "").strip()
    text = str(entry.get("text") or "").strip()
    if domain is None or not title or not text:
        return None
    media = "video" if entry.get("media") == "video" or _looks_like_video(url) else None
    licence = entry.get("licence")
    return Found(
        domain=domain,
        url=url,
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
    every result's own URL (`_on_allowlist`) — because a model asked to stay on a list is not
    the same guarantee as a caller that never returns a page off it."""

    def __init__(self, *, api_key: str | None, demo_mode: bool, client: Any | None = None) -> None:
        key = _checked_key(api_key=api_key, demo_mode=demo_mode, what="searcher")
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
                output_config={"format": {"type": "json_schema", "json_schema": SEARCH_SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:  # noqa: BLE001 — a call that fails answers nothing, never a guess
            log.warning("claude searcher call failed for %r", query)
            return []
        payload = _structured_json(response)
        if payload is None:
            return []
        results: list[Found] = []
        for entry in payload.get("results", []) or []:
            if not isinstance(entry, Mapping):
                continue
            one = _found_from_entry(entry, allowed)
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

    def __init__(self, *, api_key: str | None, demo_mode: bool, client: Any | None = None) -> None:
        key = _checked_key(api_key=api_key, demo_mode=demo_mode, what="compressor")
        self._client = client if client is not None else _client(key)

    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        if not text.strip():
            return None
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=4096,
                output_config={"format": {"type": "json_schema", "json_schema": COMPRESS_SCHEMA}},
                messages=[{"role": "user", "content": _compress_prompt(text, language, facts)}],
            )
        except Exception:  # noqa: BLE001 — a call that fails compresses nothing, never a guess
            log.warning("claude compressor call failed")
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
        return ClaudeSearcher(api_key=settings.anthropic_api_key, demo_mode=settings.demo_mode)
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
        return ClaudeCompressor(api_key=settings.anthropic_api_key, demo_mode=settings.demo_mode)
    if settings.compressor == "fixture":
        if settings.feed_fixtures is None:
            raise MissingSetting(
                "NURA_FEED_FIXTURES is not set and there is no other compressor yet"
            )
        return FixtureCompressor(Path(settings.feed_fixtures))
    raise NoCompressor(
        f"no compressor named {settings.compressor!r} is built; set NURA_COMPRESSOR=fixture or claude"
    )
