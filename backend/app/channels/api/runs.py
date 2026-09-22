"""`POST /profiles/{id}/runs` (ADR 0019 point 5; `docs/design/NURA-BUILD-MASTER-SPEC.md` §5):
the one route that streams `app.runtime.run.run_nura`'s typed event vocabulary
(`app.runtime.events`), over exactly the same guarded, existing logic every other streamed
route here already calls — never a second implementation of understanding a paper, answering
a question, building the weekly report, checking today's self-searches, triaging a red flag or
preparing a visit.

Every existing route this wraps keeps working unchanged, for the current web app and for
every other caller: this is a new, additive surface, not a replacement (module doc,
`app.channels.api.timeline` and its four siblings). The row-scope Walk in
`backend/tests/test_row_scope.py` covers this route the same way it covers `POST …/ask/stream`
— it exercises `answer_question`, which carries the same `Scope.ASK` guard `POST …/ask/stream`
does, because `key_context` (this route's own `Context` dependency, below) is the one door
every profile route already goes through and this route adds no other."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.channels.api.deps import Context, providers_of, session_scope, settings_of
from app.channels.api.refusals import refused
from app.channels.api.sse_pump import stream_with_background_pump
from app.errors import Refusal
from app.runtime.events import EventBuilder, to_sse
from app.runtime.run import Engine, Intent, RunSubject, run_nura

log = logging.getLogger("nura.channels.api.runs")

router = APIRouter(prefix="/profiles", tags=["runtime"])


class RunIn(BaseModel):
    """A Nura Run's own request: which intent, and that intent's own payload — parsed against
    the existing Pydantic model for the route it wraps (`PhotoIn`, `AskIn`, `SaidIn`, …)
    inside `app.runtime.run`'s own per-intent function, never trusted unparsed past it."""

    intent: Intent
    payload: dict[str, Any] = Field(default_factory=dict)


async def _refusal_events(request: Request, intent_value: str, refusal: Refusal) -> AsyncIterator[bytes]:
    """A refusal before or during a run, as a well-formed run: `RUN_STARTED` (so a client
    always sees a start for a run it started), then `RUN_ERROR` with the refusal's own calm
    message — never the HTTP body `app.channels.api.refusals.refused` would otherwise answer
    with, and never a status code in the text (master-spec §29)."""
    builder = EventBuilder(intent=intent_value)
    yield to_sse(builder.run_started())
    response = await refused(request, refusal)
    body = json.loads(bytes(response.body))
    message = str(body.get("message") or refusal) or "Nura could not finish that just now."
    yield to_sse(builder.run_error(message=message, code=type(refusal).__name__))


@router.post("/{profile_id}/runs")
async def start_run(
    profile_id: uuid.UUID, body: RunIn, request: Request, context: Context
) -> StreamingResponse:
    """One Nura Run, streamed as the typed event vocabulary. `context` is the same
    `key_context` dependency every route under `/profiles/{id}` takes (`app.channels.api.deps`)
    — there is no separate guard for this route: `answer_question` is refused exactly where
    `POST …/ask/stream` would refuse it (missing `Scope.ASK`), `understand_paper` exactly
    where `POST …/photos/stream` would, and so on for every intent, because each one calls the
    identical guarded function the existing route calls (`app.runtime.run`'s own module doc).

    Opens its own session (`session_scope`), never `Depends(db)`, for the reason
    `app.channels.api.timeline.ask_stream` gives: a `StreamingResponse` is handed back, and so
    a `yield` dependency closed, well before Starlette actually drives the pump."""
    engine = Engine(providers=providers_of(request), settings=settings_of(request))
    subject = RunSubject(profile_id=profile_id, payload=body.payload)

    async def pump(queue: Any) -> None:
        try:
            async with session_scope(request) as session:
                async for event in run_nura(body.intent, subject, context, session, engine):
                    await queue.put(to_sse(event))
        except Refusal as refusal:
            async for chunk in _refusal_events(request, body.intent.value, refusal):
                await queue.put(chunk)

    return StreamingResponse(stream_with_background_pump(pump), media_type="text/event-stream")


__all__ = ["router"]
