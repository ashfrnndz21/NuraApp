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

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.channels.api.deps import Context, providers_of, session_scope, settings_of
from app.channels.api.sse_pump import stream_with_background_pump
from app.runtime.events import EventBuilder, to_sse
from app.runtime.run import Engine, RunSubject, _calm_error_message, run_nura

log = logging.getLogger("nura.channels.api.runs")

router = APIRouter(prefix="/profiles", tags=["runtime"])


class RunIn(BaseModel):
    """A Nura Run's own request: which intent, and that intent's own payload — parsed against
    the existing Pydantic model for the route it wraps (`PhotoIn`, `AskIn`, `SaidIn`, …)
    inside `app.runtime.run`'s own per-intent function, never trusted unparsed past it.

    `intent` is a plain `str`, not the `Intent` enum, on purpose: a `RunIn.intent: Intent`
    field makes FastAPI's own request-body validation reject an unknown intent before this
    route ever runs, with a raw 422 body — a run that never even reaches `RUN_STARTED`,
    breaking the promise every other bad input on this route keeps (independent review of
    #331, follow-up 3). An unrecognised value here still becomes a well-formed run instead:
    `run_nura` raises `UnknownIntent` (a `Refusal`) the moment it is asked to dispatch it,
    caught by `start_run`'s own `pump` exactly like any other exception."""

    intent: str
    payload: dict[str, Any] = Field(default_factory=dict)


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

    A run always terminates (§4; independent review of #331, B1, B1-R1): exactly one
    `EventBuilder` is built here, passed into `run_nura` (which threads it into whichever
    handler runs), and kept by `pump` for its own last-resort catch too — never a second
    builder built partway through a run, which used to mean anything escaping a handler
    surfaced under a fresh `run_id` with `seq` restarted at 1 (`app.runtime.run`'s own module
    doc). `run_nura` already turns every exception a wrapped call raises into `RUN_ERROR`
    before it ever reaches here; `pump`'s own `except` is the outer net for the one thing that
    can still happen entirely outside `run_nura`'s own generator — `session_scope`'s commit,
    on the way out of the `async with` below, failing after `run_nura` already yielded
    `RUN_FINISHED`. `EventBuilder.run_error` itself refuses to build a second terminal event
    (`events.py`'s own doc), so even that case ends in exactly one `RUN_ERROR`, never a second
    one chasing the `RUN_FINISHED` that already reached the wire.

    Opens its own session (`session_scope`), never `Depends(db)`, for the reason
    `app.channels.api.timeline.ask_stream` gives: a `StreamingResponse` is handed back, and so
    a `yield` dependency closed, well before Starlette actually drives the pump."""
    engine = Engine(providers=providers_of(request), settings=settings_of(request))
    subject = RunSubject(profile_id=profile_id, payload=body.payload)
    builder = EventBuilder(intent=body.intent)

    async def pump(queue: Any) -> None:
        session = None  # bound even if session_scope's own __aenter__ never completes
        try:
            async with session_scope(request) as session:
                # `body.intent` is a plain `str` by design (its own docstring); `Intent` is a
                # `StrEnum`, so `_INTENTS.get(intent)` inside `run_nura` matches it by value
                # exactly as it would a real `Intent` member, and any string that is not one
                # of the six raises `UnknownIntent` the same way — never a type error at
                # runtime, only at the type-checker, which this line tells so on purpose.
                async for event in run_nura(
                    body.intent,  # type: ignore[arg-type]
                    subject,
                    context,
                    session,
                    engine,
                    builder=builder,
                ):
                    await queue.put(to_sse(event))
            # A commit failure here (session_scope's own __aexit__) is caught below, using the
            # SAME builder `run_nura` already used — see this function's own docstring.
        except Exception as exc:
            log.exception("nura run %s: an event never reached the wire", body.intent)
            # `_calm_error_message` falls back to English on its own if `session` cannot
            # actually answer a language query (including `session is None`, when
            # `session_scope`'s own `__aenter__` never completed) — see its own doc.
            message, code = await _calm_error_message(session, context, exc)
            error = builder.run_error(message=message, code=code)
            if error is not None:
                await queue.put(to_sse(error))

    return StreamingResponse(stream_with_background_pump(pump), media_type="text/event-stream")


__all__ = ["router"]
