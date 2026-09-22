"""The one event vocabulary (ADR 0019 point 4; `docs/design/NURA-BUILD-MASTER-SPEC.md` §5).

Six mutually incompatible shapes used to carry a run to the wire — one per route
(`_sse` copy-pasted at `app/channels/api/timeline.py`, `capture.py`, `analyst.py`,
`feed.py`, `safety.py`), four terminal event names for one concept (`answer`, `results`,
`report`, `card`), and no structured tool call anywhere (audit `docs/design/
audit-2026-09-22.md` §7.1). This module is the replacement: one closed set of event types,
named exactly as `ag-ui-protocol/ag-ui` (`sdks/typescript/packages/core/src/generated/
types.ts`, read 23 September 2026) names them, plus one `CUSTOM` escape so an existing
route's `step`/`card`/`clarify`/`answer` payload can ride inside the new envelope unchanged
while its screen is migrated — never a second, competing vocabulary.

Every event carries `run_id`, `intent` and a monotonic `seq` (this module's own addition,
not AG-UI's): the three things a client needs to place one event in one run's own order,
across however many `TEXT_MESSAGE_*` or `TOOL_CALL_*` sequences a run interleaves.

What this module is not: an AI decision. No event here is emitted because a model decided
something — consent, ownership, confirmation, a safety gate, escalation and what State
holds are exactly the deterministic system's, named in `run.py`'s own module doc and in
ADR 0019 point 6 / master-spec §6. An event reports a decision already made; it never makes
one.
"""

from __future__ import annotations

import itertools
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """The wire's own discriminator. Names taken verbatim from the AG-UI spec (`EventType` in
    `sdks/typescript/packages/core/src/generated/types.ts`); `CUSTOM` is AG-UI's own escape
    hatch, used here for a migrating route's existing payload shape."""

    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"

    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"

    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"

    CUSTOM = "CUSTOM"


class SeqCounter:
    """One run's monotonic sequence. A plain `itertools.count` wrapped in a class so a run
    function can hold one without a module-level counter leaking across requests — the bug a
    bare global counter would be under two runs in flight at once."""

    __slots__ = ("_it",)

    def __init__(self) -> None:
        self._it = itertools.count(1)

    def __call__(self) -> int:
        return next(self._it)


@dataclass(frozen=True, slots=True)
class Envelope:
    """The fields every event carries, whatever its type: which run, which intent, and this
    event's place in that run's own order. Never the profile id, the person or anything of
    his record — a client already holds those from the request it made; the envelope is
    routing information, not a second copy of anything scoped."""

    run_id: str
    intent: str
    seq: int
    type: EventType


@dataclass(frozen=True, slots=True)
class Event:
    """One event: the envelope, plus whatever that type carries. `data` is a plain, already
    JSON-safe mapping — built by this module's own constructors below, never handed a Fact,
    a row or free text lifted from an extractor (`run.py`'s own rule: a tool result is a
    short, closed summary, never the record itself)."""

    envelope: Envelope
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.envelope.type.value,
            "run_id": self.envelope.run_id,
            "intent": self.envelope.intent,
            "seq": self.envelope.seq,
        }
        payload.update(self.data)
        return payload


def to_sse(event: Event) -> bytes:
    """The one serialiser (ADR 0019 point 4): a `data:` line of JSON, blank line after — the
    same wire shape the five copy-pasted `_sse` functions already write, so an existing
    client that only reads `data:` lines keeps working unchanged while it migrates to the
    typed envelope."""
    return f"data: {json.dumps(event.to_json(), default=str)}\n\n".encode()


class EventBuilder:
    """One run's own event factory: closes over `run_id`, `intent` and a `SeqCounter`, so
    call sites in `run.py` never thread `seq=` by hand and can never get two events the same
    sequence number by mistake."""

    __slots__ = ("_seq", "intent", "run_id")

    def __init__(self, *, run_id: uuid.UUID | str | None = None, intent: str) -> None:
        self.run_id = str(run_id) if run_id is not None else str(uuid.uuid4())
        self.intent = intent
        self._seq = SeqCounter()

    def _event(self, type_: EventType, data: Mapping[str, Any]) -> Event:
        return Event(
            envelope=Envelope(run_id=self.run_id, intent=self.intent, seq=self._seq(), type=type_),
            data=data,
        )

    # --- lifecycle --------------------------------------------------------------------------

    def run_started(self, *, subject: str | None = None) -> Event:
        data: dict[str, Any] = {}
        if subject is not None:
            data["subject"] = subject
        return self._event(EventType.RUN_STARTED, data)

    def run_finished(self, *, result: Mapping[str, Any] | None = None) -> Event:
        return self._event(EventType.RUN_FINISHED, {"result": result} if result is not None else {})

    def run_error(self, *, message: str, code: str | None = None) -> Event:
        """`message` is calm, patient-facing copy (master-spec §29: never a technical or HTTP
        string) — the same discipline `app.channels.api.refusals.refused` already holds the
        plain routes to. `code` is a closed machine name for a client that wants to branch,
        never shown."""
        data: dict[str, Any] = {"message": message}
        if code is not None:
            data["code"] = code
        return self._event(EventType.RUN_ERROR, data)

    # --- text ---------------------------------------------------------------------------------

    def text_message_start(self, *, message_id: str, role: str = "assistant") -> Event:
        return self._event(EventType.TEXT_MESSAGE_START, {"message_id": message_id, "role": role})

    def text_message_content(self, *, message_id: str, delta: str) -> Event:
        return self._event(EventType.TEXT_MESSAGE_CONTENT, {"message_id": message_id, "delta": delta})

    def text_message_end(self, *, message_id: str) -> Event:
        return self._event(EventType.TEXT_MESSAGE_END, {"message_id": message_id})

    # --- tool calls -----------------------------------------------------------------------------

    def tool_call_start(
        self, *, tool_call_id: str, tool_call_name: str, stage: str | None = None
    ) -> Event:
        """`stage` is the patient-words line a loading state shows while the call is in
        flight (master-spec §29: "Looking through your recent results…", never the bare tool
        name) — optional, because not every intent's tool has one yet."""
        data: dict[str, Any] = {"tool_call_id": tool_call_id, "tool_call_name": tool_call_name}
        if stage is not None:
            data["stage"] = stage
        return self._event(EventType.TOOL_CALL_START, data)

    def tool_call_args(self, *, tool_call_id: str, delta: str) -> Event:
        return self._event(EventType.TOOL_CALL_ARGS, {"tool_call_id": tool_call_id, "delta": delta})

    def tool_call_end(self, *, tool_call_id: str) -> Event:
        return self._event(EventType.TOOL_CALL_END, {"tool_call_id": tool_call_id})

    def tool_call_result(
        self, *, tool_call_id: str, content: Mapping[str, Any] | Sequence[Any] | int | str
    ) -> Event:
        """`content` is a short, closed summary — a count, a key, a list of ids — never a row
        and never free text off an extractor or a paper (the rule `run.py` names for every
        intent it wraps). Callers that need a stronger guarantee than "please don't" should
        build `content` from a dataclass field already typed as an id or a count, never from
        a string field that could hold prose."""
        return self._event(
            EventType.TOOL_CALL_RESULT, {"tool_call_id": tool_call_id, "content": content}
        )

    # --- state ------------------------------------------------------------------------------

    def state_snapshot(self, *, snapshot: Mapping[str, Any]) -> Event:
        return self._event(EventType.STATE_SNAPSHOT, {"snapshot": snapshot})

    def state_delta(self, *, patch: Sequence[Mapping[str, Any]]) -> Event:
        """`patch` is an RFC 6902 JSON Patch against the last `STATE_SNAPSHOT` a client holds
        — the same representation AG-UI's own `STATE_DELTA` carries, built here from
        `app.state.service.StateView` before/after a run by `run.diff_state`."""
        return self._event(EventType.STATE_DELTA, {"patch": list(patch)})

    # --- migration escape -----------------------------------------------------------------------

    def custom(self, *, name: str, value: Mapping[str, Any]) -> Event:
        """The existing route's own payload, unchanged, riding inside the new envelope: a
        `step`, a `card`, a `report`, an `answer`, a `results` or a `refusal` event exactly as
        `app.channels.api.timeline._sse` (and its four siblings) already send it — so a
        client mid-migration reads the old shape from `data` while a new client reads the
        typed events around it. Retired once every screen reads the typed vocabulary and
        nothing else."""
        return self._event(EventType.CUSTOM, {"name": name, "value": value})


__all__ = [
    "Envelope",
    "Event",
    "EventBuilder",
    "EventType",
    "SeqCounter",
    "to_sse",
]
