"""The ask bar's filters (spec §0, mockup v2): Records, Web, Providers, Videos.

Records is Ask (`POST /profiles/{id}/ask`, E03-05), unchanged. The other three are here:

- **Web** and **Videos** search the allowlisted sources only — the same allowlist a card is
  made from, in his region, through the same `Searcher` port — and each page found is said the
  way a learning card says it: compressed into his language, citing its passage, checked
  against the plain-words standard, ending on the boundary line. A page whose lines would
  change a treatment is not shown at all; a page from anywhere else is never returned.
  What is sent to the searcher is the words typed and the allowlisted domains — no name, no
  area, no fact of his, and the compressor is given none of his facts either. The words are
  not kept: the trail says a search was made and how many pages came back, not what for.
- **Providers** is his own directory (E03-03), narrowed to the names that match, read under
  the visits scope like the directory itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard
from app.audit.models import Action
from app.audit.trail import record
from app.db import as_utc
from app.delivery.feed.compress import changes_treatment
from app.delivery.feed.items import failures_in
from app.delivery.feed.search import Engine, on_its_source
from app.delivery.feed.sources import SourceNotAllowlisted, require_usable_source, usable_sources
from app.delivery.strings import YOUR_DOCTOR, language_for, learning_lines
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.memory.providers import directory

WHERE = ("web", "videos", "providers")
MOST = 8
"""The most pages one search answers with."""
FIND_TARGET = "find"


class NotAFilter(Refusal):
    """The ask bar searches his records, the web, his providers or videos."""


class NothingToFind(Refusal):
    """A search looks for at least one word."""


@dataclass(frozen=True, slots=True)
class Result:
    """One thing found: its title, who published it and where (or, for a provider, the
    provider), the lines it says in his language, and the boundary they end on."""

    title: str
    publisher: str | None = None
    url: str | None = None
    published_at: str | None = None
    lines: tuple[str, ...] = ()
    boundary: str | None = None
    media: str | None = None
    provider_id: str | None = None
    next_visit_at: str | None = None


@dataclass(frozen=True, slots=True)
class FindStep:
    """The one real stage `find_stream` streams before its results: the allowlisted search
    (`engine.searcher.find`, then each page's compression) is genuinely running. `providers`
    streams nothing — a directory read is over before there is anything to say is in
    progress, so `find_stream` goes straight to its results for that filter."""

    key: str = "searching"


async def find_stream(
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    words: str,
    where: str,
    language: str | None,
) -> AsyncIterator[FindStep | list[Result]]:
    """`find`, streamed: `FindStep` the instant the search is actually running, then the
    results — the last item. `find` (below) is this, drained, so the two can never drift
    apart."""
    if where not in WHERE:
        raise NotAFilter(f"{where!r} is not a filter of the ask bar")
    wanted = [word for word in words.lower().split() if word.strip()]
    if not wanted:
        raise NothingToFind("a search looks for at least one word")
    if where == "providers":
        found = [
            summary
            for summary in await directory(session, context=context)
            if all(word in summary.provider.name.lower() for word in wanted)
        ]
        yield [
            Result(
                title=summary.provider.name,
                provider_id=str(summary.provider.id),
                next_visit_at=None
                if summary.next_visit is None
                else as_utc(summary.next_visit.scheduled_at).isoformat(),
            )
            for summary in found
        ]
        return
    async with audited_guard(session, context, Action.READ, Scope.ASK, FIND_TARGET):
        context.require(Scope.ASK)
    yield FindStep()
    code = language_for(language)
    sources = await usable_sources(session, region=context.region)
    domains = [source.domain for source in sources]
    media = "video" if where == "videos" else None
    results: list[Result] = []
    for page in engine.searcher.find(wanted, domains, media=media):
        if len(results) >= MOST:
            break
        try:
            source = await require_usable_source(session, region=context.region, domain=page.domain)
        except SourceNotAllowlisted:
            continue
        if not on_its_source(page.url, source.domain):
            continue
        compressed = engine.compressor.compress(page.text, code, {})
        if compressed is None or not compressed.passage.strip():
            continue
        if changes_treatment([compressed.headline, *compressed.body]):
            continue
        lines = learning_lines(
            code,
            headline=compressed.headline,
            body=compressed.body,
            topic=compressed.why_topic,
            source_name=source.name,
            doctor=YOUR_DOCTOR[code],
        )
        if failures_in(lines):
            continue
        closing = len((lines.boundary or "").splitlines())
        results.append(
            Result(
                title=compressed.headline,
                publisher=source.name,
                url=page.url,
                published_at=page.published_at,
                lines=lines.body[: len(lines.body) - closing],
                boundary=lines.boundary,
                media=page.media,
            )
        )
    await record(
        session,
        context=context,
        action=Action.READ,
        scope=Scope.ASK,
        target=FIND_TARGET,
        rows=len(results),
    )
    yield results


async def find(
    session: AsyncSession,
    *,
    context: KeyContext,
    engine: Engine,
    words: str,
    where: str,
    language: str | None,
) -> list[Result]:
    """`find_stream`, drained: the results alone, for a caller that does not stream (the
    existing `POST /profiles/{id}/find` route, unchanged)."""
    result: list[Result] | None = None
    async for event in find_stream(
        session, context=context, engine=engine, words=words, where=where, language=language
    ):
        if isinstance(event, list):
            result = event
    assert result is not None
    return result
