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
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Any

log = logging.getLogger("nura.runtime.events")


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


class ErrorCode(StrEnum):
    """`RUN_ERROR.code`'s own closed set (independent review of #331, round 3, fix 2): before
    this, `code` was an open Python exception class name (`"KeyError"`, `"NoSuchAppointment"`,
    `"UnknownIntent"`, …) — unbounded, and a client branching on it would be branching on this
    codebase's own internals. Five buckets, deterministic, never a class name:
    `app.runtime.run._error_code` is the one function that maps an exception to one of these."""

    REFUSED = "refused"
    """Consent, a scope, a role or a confirmation stood in the way."""
    NOT_FOUND = "not_found"
    """The thing asked about does not exist, or nothing has been computed yet."""
    UNKNOWN_INTENT = "unknown_intent"
    BAD_REQUEST = "bad_request"
    """The payload itself was malformed or incomplete."""
    INTERNAL = "internal"
    """Anything else — including a bug. Never shown as such; `RUN_ERROR.message` stays the
    one calm, generic line for this bucket."""


@lru_cache(maxsize=1)
def _closed_tool_keys() -> frozenset[str]:
    """Every closed `key` a `TOOL_CALL_START`/`TOOL_CALL_RESULT`/`CUSTOM("step", …)` may
    legitimately name (F3, round 3 fix 3): `app.search.ask.AskStep.key` and the two extra
    keys only `ClaudeAsker` yields, `app.reasoning.analyst.port.StepKey`,
    `app.ingestion.review.ImportStepKey`, `app.safety.not_feeling_well.NfwStepKey`, and
    `run.py`'s own two plain-run tool names — read from the real catalogues and enums
    themselves (never hand-copied) so this set can never quietly drift from what `run.py`
    actually emits. Imported lazily so `app.runtime.events` never has to import `app.search`,
    `app.reasoning`, `app.ingestion` or `app.safety` at module load."""
    from app.delivery.timeline_strings import ASK_STEPS, RUN_STAGE_WORDS
    from app.ingestion.review import ImportStepKey
    from app.reasoning.analyst.port import StepKey
    from app.safety.not_feeling_well import NfwStepKey

    return frozenset(
        set(ASK_STEPS["en"])
        | set(RUN_STAGE_WORDS["en"])
        | {member.value for member in ImportStepKey}
        | {member.value for member in StepKey}
        | {member.value for member in NfwStepKey}
    )


@lru_cache(maxsize=1)
def _closed_document_kinds() -> frozenset[str]:
    from app.ingestion.extract import DocumentKind

    return frozenset(member.value for member in DocumentKind)


@lru_cache(maxsize=1)
def _closed_notices() -> frozenset[str]:
    from app.ingestion.review import Notice

    return frozenset(member.value for member in Notice)


_CLOSED_LANGUAGES = frozenset({"en", "ms", "zh"})
_CLOSED_LINKED_KINDS = frozenset({"medicine", "visit"})


def _closed_json(value: object) -> dict[str, Any]:
    """A closed, frozen dataclass's own fields as JSON, `None` ones dropped. The one place
    this module turns a typed payload into wire JSON — never a caller's own dict, which is
    exactly the seam F3 closed: before this, `tool_call_result`/`custom` accepted any
    `Mapping[str, Any]` or a bare `str`, and nothing stopped a caller from putting a model's
    or an extractor's own sentence there."""
    return {key: val for key, val in asdict(value).items() if val is not None}  # type: ignore[call-overload]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The closed shape a `TOOL_CALL_RESULT`'s content may take (F3, independent review of
    #331): every field is an id, a key from a closed enum, a count or a boolean — never a
    string a model or an extractor wrote. A caller with prose to report uses
    `TEXT_MESSAGE_CONTENT`, which is what those events are for; a caller that needs a field
    not listed here is telling this vocabulary it is missing a case, not that this dataclass
    should grow a free-text one."""

    key: str | None = None
    """Which read this was: `app.search.ask.AskStep.key`, `app.reasoning.analyst.port.
    StepKey.value`, `app.ingestion.review.ImportStepKey.value` or `app.safety.
    not_feeling_well.NfwStepKey.value` — always a closed enum's own value, never free text.
    Validated against the real, closed union of those (`_closed_tool_keys`), not merely typed
    as `str`: round 3 of the independent review found `ToolResult(key="LDL 3.8 mmol/L,
    borderline high — consider a statin")` was accepted before this."""
    count: int | None = None
    document_kind: str | None = None
    linked_kind: str | None = None
    looking: bool | None = None
    lines: int | None = None
    sections: int | None = None
    red_flag: bool | None = None

    def __post_init__(self) -> None:
        if self.key is not None and self.key not in _closed_tool_keys():
            raise ValueError(f"ToolResult.key must be one of the closed step keys, not {self.key!r}")
        if self.document_kind is not None and self.document_kind not in _closed_document_kinds():
            raise ValueError(f"ToolResult.document_kind must be a closed DocumentKind, not {self.document_kind!r}")
        if self.linked_kind is not None and self.linked_kind not in _CLOSED_LINKED_KINDS:
            raise ValueError(f"ToolResult.linked_kind must be 'medicine' or 'visit', not {self.linked_kind!r}")


@dataclass(frozen=True, slots=True)
class StepCustom:
    """`CUSTOM("step", …)`: the existing routes' own `{"type": "step", "key": …}` shape,
    unchanged, riding inside the new envelope. `key` is validated the same closed way
    `ToolResult.key` is."""

    key: str

    def __post_init__(self) -> None:
        if self.key not in _closed_tool_keys():
            raise ValueError(f"StepCustom.key must be one of the closed step keys, not {self.key!r}")


@dataclass(frozen=True, slots=True)
class CardCustom:
    """`CUSTOM("card", …)`: a review card or a not-feeling-well card's own closed summary —
    never the card's own fields, which a client already holds from the plain route's own
    response shape, or will read from `GET /review-cards/{id}` by the id here. `notice` is
    validated against the closed `app.ingestion.review.Notice` enum."""

    card_id: str | None = None
    notice: str | None = None
    red_flag: bool | None = None

    def __post_init__(self) -> None:
        if self.notice is not None and self.notice not in _closed_notices():
            raise ValueError(f"CardCustom.notice must be a closed Notice, not {self.notice!r}")


@dataclass(frozen=True, slots=True)
class ReportCustom:
    """`CUSTOM("report", …)`: the weekly Health Analyst report's own closed summary — never
    a section's own text, which a client reads from `GET /insights/{id}`. `language` is
    validated against the closed `("en", "ms", "zh")` set."""

    sections: int
    language: str

    def __post_init__(self) -> None:
        if self.language not in _CLOSED_LANGUAGES:
            raise ValueError(f"ReportCustom.language must be one of en/ms/zh, not {self.language!r}")


CustomPayload = StepCustom | CardCustom | ReportCustom


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
    sequence number by mistake.

    **One builder per run, always (independent review of #331, round 3, B1-R1).** Before
    this, `app.channels.api.runs.start_run`'s own `pump` built one `EventBuilder` for its
    last-resort catch and every `run.py` handler built a second, separate one — so anything
    that escaped a handler (a bug reading State before its own `try`, a commit failure after
    `RUN_FINISHED` had already gone out on `session_scope`'s own exit) surfaced as `RUN_ERROR`
    under a **different** `run_id`, with `seq` restarted at 1. Now exactly one `EventBuilder`
    is created in `start_run`'s `pump` and threaded through `run_nura` into every handler
    (`run.py`'s own module doc); this class enforces the other half of that promise itself:
    `run_finished`/`run_error` refuse to build a second terminal event. The first one to call
    either wins; every call after it is logged and returns `None` — never a second `RUN_ERROR`
    chasing a `RUN_FINISHED` that already reached the wire, and never a caller that has to
    remember to check `self.terminated` itself before deciding whether to yield."""

    __slots__ = ("_seq", "_terminated", "intent", "run_id")

    def __init__(self, *, run_id: uuid.UUID | str | None = None, intent: str) -> None:
        self.run_id = str(run_id) if run_id is not None else str(uuid.uuid4())
        self.intent = intent
        self._seq = SeqCounter()
        self._terminated = False

    @property
    def terminated(self) -> bool:
        """Whether `run_finished` or `run_error` has already built this run's one terminal
        event. A caller may check this before doing further work, but does not have to: both
        methods are themselves safe to call more than once."""
        return self._terminated

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

    def run_finished(self, *, result: Mapping[str, Any] | None = None) -> Event | None:
        """`None`, logged, if this run already has a terminal event — see the class doc."""
        if self._terminated:
            log.warning("nura run %s: RUN_FINISHED dropped, already terminated", self.run_id)
            return None
        self._terminated = True
        return self._event(EventType.RUN_FINISHED, {"result": result} if result is not None else {})

    def run_error(self, *, message: str, code: ErrorCode) -> Event | None:
        """`message` is calm, patient-facing copy (master-spec §29: never a technical or HTTP
        string) — the same discipline `app.channels.api.refusals.refused` already holds the
        plain routes to. `code` is one of the closed `ErrorCode` values, checked at runtime —
        never a Python exception's class name, which used to reach the wire here (round 3,
        fix 2). `None`, logged, if this run already has a terminal event — see the class doc."""
        if not isinstance(code, ErrorCode):
            raise TypeError(f"RUN_ERROR.code must be an ErrorCode, not {type(code).__name__}")
        if self._terminated:
            log.warning("nura run %s: RUN_ERROR dropped, already terminated (code=%s)", self.run_id, code)
            return None
        self._terminated = True
        return self._event(EventType.RUN_ERROR, {"message": message, "code": code.value})

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

    def tool_call_end(self, *, tool_call_id: str, error: bool = False) -> Event:
        """`error=True` closes a call that broke before it produced a `TOOL_CALL_RESULT`
        (round 3, fix 1): every handler now closes whichever call is open, this way, before
        its own `RUN_ERROR` — never a `TOOL_CALL_START` left with no matching `END` at all."""
        data: dict[str, Any] = {"tool_call_id": tool_call_id}
        if error:
            data["error"] = True
        return self._event(EventType.TOOL_CALL_END, data)

    def tool_call_result(self, *, tool_call_id: str, content: ToolResult) -> Event:
        """`content` is a `ToolResult` — a short, closed summary, never a row and never free
        text off an extractor, a paper or a model (F3: `content` used to accept any mapping
        or a bare string; nothing stopped a caller from putting prose there). Checked at
        runtime, not only by the type hint: a caller that passes anything else is refused
        with `TypeError` before it ever reaches the wire."""
        if not isinstance(content, ToolResult):
            raise TypeError(
                f"a TOOL_CALL_RESULT's content must be a ToolResult, not {type(content).__name__}"
            )
        return self._event(
            EventType.TOOL_CALL_RESULT, {"tool_call_id": tool_call_id, "content": _closed_json(content)}
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

    def custom(self, *, name: str, value: CustomPayload) -> Event:
        """The existing route's own payload, closed to one of `CustomPayload`'s three shapes
        (F3) — never an arbitrary mapping a caller could put a model's or an extractor's own
        sentence into. Riding inside the new envelope so a client mid-migration reads the old
        shape from `data` while a new client reads the typed events around it; retired once
        every screen reads the typed vocabulary and nothing else. Checked at runtime: a
        caller that passes anything else is refused with `TypeError`."""
        if not isinstance(value, StepCustom | CardCustom | ReportCustom):
            raise TypeError(f"a CUSTOM value must be one of CustomPayload, not {type(value).__name__}")
        return self._event(EventType.CUSTOM, {"name": name, "value": _closed_json(value)})


__all__ = [
    "CardCustom",
    "CustomPayload",
    "Envelope",
    "ErrorCode",
    "Event",
    "EventBuilder",
    "EventType",
    "ReportCustom",
    "SeqCounter",
    "StepCustom",
    "ToolResult",
    "to_sse",
]
