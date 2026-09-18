"""A generic SSE fan-in, for a stream that has more than one source of events in flight at
once — the steps a tool-use loop or a search yields, in order, and a narrator's own follow-up
rephrasing, which may resolve well after the step it narrates (`app.search.narrate.
narrate_step_label`). A step, a tool call and the final answer must never wait on a narrator,
however long it takes (docs/design-direction.md "Conversation, waiting and thinking"; the
narrator redesign followed Opus 5 routinely missing the old, synchronous 1.5s deadline, which
meant it was in practice never heard) — so the narrator's call runs as its own background
task, and whatever it resolves to reaches the wire as its own event, whenever it is ready,
never held for or blocking anything else already streaming.

Used by `app.channels.api.timeline.ask_stream` and `app.channels.api.feed.find_pages_stream`.
Kept here, not in either router, so neither has to import the other's (a route's own module
docstring already says it does not)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable

_DONE: object = object()
"""Put on the queue exactly once, by `_run` below, when `pump` returns (however it returns) —
never itself sent as an event; `stream_with_background_pump` stops draining the moment it is
seen."""


async def stream_with_background_pump(
    pump: Callable[[asyncio.Queue[bytes | object]], Awaitable[None]],
) -> AsyncIterator[bytes]:
    """Runs `pump(queue)` as its own task. `pump` puts every event it produces — in whatever
    order each actually becomes ready, from however many sources it starts — onto `queue`;
    this drains the queue onto the wire the instant each item arrives, never waiting for
    `pump` itself to finish before the first byte goes out.

    If the caller stops reading early (a client disconnect closes this generator), the pump
    task is cancelled rather than left running unread, the same way a lone `async with
    session_scope(...)` inside a route's own generator was already cancelled on disconnect
    before this existed."""
    queue: asyncio.Queue[bytes | object] = asyncio.Queue()

    async def _run() -> None:
        try:
            await pump(queue)
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(_run())
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                break
            yield item  # type: ignore[misc]
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
