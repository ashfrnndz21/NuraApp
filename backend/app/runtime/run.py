"""Nura Run (ADR 0019 point 5; `docs/design/NURA-BUILD-MASTER-SPEC.md` §5): one runtime, not
six AI systems. `run_nura(intent, subject, context, session, engine)` wraps an EXISTING
streamed (or plain) route's own logic — `app.ingestion.review.review_artifact_stream`,
`app.search.asker.Asker.ask_stream`, `app.reasoning.analyst.port.report_stream`,
`app.delivery.feed.search.jobs_looking_today`, `app.safety.not_feeling_well.
not_feeling_well_stream`, `app.reasoning.visits.brief.brief_for` — and re-emits what each one
already yields as the one typed event vocabulary (`app.runtime.events`), never a second
implementation of any of them.

**Deterministic decides; AI interprets (ADR 0019 point 6; master-spec §6).** Nothing in this
module decides consent, a scope, identity matching, paper ownership, confirmation, a
confidence threshold, source validity, a medicine safety gate, an escalation or an audit
line — every one of those is decided, exactly as today, inside the wrapped call, before this
module ever sees the result. This module only reports what already happened, as events.

**One `EventBuilder` per run, always (§4; independent review of #331, round 3, B1-R1).**
`run_nura` is given its builder by its caller (`app.channels.api.runs.start_run`'s own
`pump`, which creates exactly one and keeps it for its own last-resort catch too) and threads
the same instance into every handler — never a second one built partway through. `RUN_STARTED`
is the first event this function yields; everything else, including looking up the handler
and reading State before any wrapped call runs, happens inside one `try` so that nothing
between `RUN_STARTED` and the handler's own work can escape uncaught with a fresh `run_id` and
`seq` restarted at 1 (round 3's own proof: a `RuntimeError` reading State used to do exactly
that, four handlers out of six). `EventBuilder.run_finished`/`run_error` refuse to build a
second terminal event on their own (`events.py`'s own doc) — belt and braces on top of this
module only ever calling one of them once per run.

**A handler closes what it opened before it lets an exception through (round 3, fix 1).** A
`TOOL_CALL_START` a handler yielded is always followed by a `TOOL_CALL_END` — `error=True` if
the call itself never finished — before the exception reaches `run_nura`'s own catch; a
`TEXT_MESSAGE_START` is closed the same way. A handler never yields `RUN_ERROR` itself: it
raises, and `run_nura` is the one place that turns any exception into the run's one terminal
event.

**Patient words, not engine language (§29; B2, B2-R1).** `TOOL_CALL_START.stage` reads the
`@patient`-tagged catalogues in `app.delivery.timeline_strings`, in the profile's language.
`RUN_ERROR.message` reads `RUN_ERROR_WORDS` — also `@patient`-tagged, also in
`app.delivery.timeline_strings`, not here (round 3: a catalogue kept in `app/runtime/**`, off
every path `.claude/rules/patient-strings.md` and `make plain-words` check, is not actually
checked) — keyed by the closed `app.runtime.events.ErrorCode` this module maps every
exception to (`_error_code`), never a Python exception's class name and never a `Refusal`'s
own constructor text, which is written for a log, not a person (`app.channels.api.refusals`
module doc).

**Fixture and live parity (ADR 0019 point 12; master-spec §42).** Every intent below is
wired against a *port* (`app.search.asker.Asker`, `app.reasoning.analyst.port.Analyst` — see
each module's own doc), never against a specific adapter, so the event sequence a fixture
adapter produces and the one a live model adapter produces are the same shape: neither this
module nor a client reading its stream can tell which one is running
(`tests/test_runtime_events.py::test_fixture_and_live_askers_produce_the_same_event_type_sequence`,
`test_rule_and_claude_analysts_produce_the_same_event_type_sequence`, both driven through
`run_nura` itself, not the adapters alone).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.api.deps import Providers
from app.errors import Refusal
from app.keys.context import KeyContext
from app.runtime.events import (
    CardCustom,
    ErrorCode,
    Event,
    EventBuilder,
    ReportCustom,
    StepCustom,
    ToolResult,
)
from app.settings import Settings
from app.state.models import Dimension
from app.state.service import StateView, current_state

log = logging.getLogger("nura.runtime")


@dataclass(frozen=True, slots=True)
class Engine:
    """What a run is given to do its work with: the deployment's existing `Providers` (the
    adapters behind every port — the asker, the extractor, the analyst's registry, …) plus
    the `Settings` a couple of intents need to choose an adapter the way their plain routes
    already do (`app.reasoning.analyst.provider.analyst_for`). Never a second provider
    registry: attribute access falls through to `providers` unchanged, so a call site reads
    `engine.asker` or `engine.object_store` exactly as a route reads `providers_of(request)
    .asker` today."""

    providers: Providers
    settings: Settings

    def __getattr__(self, name: str) -> Any:
        return getattr(self.providers, name)


class Intent(StrEnum):
    """`runNura(intent, subject, context)` (ADR 0019 point 5; master-spec §5). One value per
    existing streamed or on-demand route this runtime wraps."""

    UNDERSTAND_PAPER = "understand_paper"
    ANSWER_QUESTION = "answer_question"
    GENERATE_ANALYSIS = "generate_analysis"
    GENERATE_RECOMMENDATIONS = "generate_recommendations"
    TRIAGE_RED_FLAG = "triage_red_flag"
    PREPARE_VISIT = "prepare_visit"


@dataclass(frozen=True, slots=True)
class RunSubject:
    """What a run is about: the profile, and the intent's own payload — already validated by
    that intent's existing Pydantic model (`PhotoIn`, `AskIn`, `SaidIn`, …), never a raw dict
    trusted past this module's own parsing in `run.py`'s per-intent functions."""

    profile_id: uuid.UUID
    payload: Mapping[str, Any]


class UnknownIntent(Refusal):
    """`POST /profiles/{id}/runs` was asked for an intent this runtime does not know."""


# --- exception -> closed ErrorCode, exception -> patient words (§29; B2, B2-R1) -------------

_REFUSAL_ERROR_CODE: dict[str, ErrorCode] = {
    "OutOfScope": ErrorCode.REFUSED,
    "NoKey": ErrorCode.REFUSED,
    "AlreadyConfirmed": ErrorCode.REFUSED,
    "NoState": ErrorCode.NOT_FOUND,
    "StaleState": ErrorCode.NOT_FOUND,
    "SnapshotBehindTheCard": ErrorCode.NOT_FOUND,
    "NoBriefYet": ErrorCode.NOT_FOUND,
    "NotAQuestion": ErrorCode.BAD_REQUEST,
    "NotEveryFieldDecided": ErrorCode.BAD_REQUEST,
    "UnreadableField": ErrorCode.BAD_REQUEST,
    "UnknownIntent": ErrorCode.UNKNOWN_INTENT,
}
"""Every `Refusal` this runtime's own wrapped calls are known to raise, mapped to one of
`ErrorCode`'s five buckets (round 3, fix 2) — never a class name reaching `RUN_ERROR.code`,
which used to be exactly that (`'KeyError'`, `'NoSuchAppointment'`, `'UnknownIntent'`, an open
set with no end to it). A `Refusal` not listed here gets `ErrorCode.REFUSED`, the safest
default for a kind this runtime has not seen yet."""


def _error_code(exc: BaseException) -> ErrorCode:
    if isinstance(exc, Refusal):
        return _REFUSAL_ERROR_CODE.get(type(exc).__name__, ErrorCode.REFUSED)
    if isinstance(exc, KeyError | ValueError):
        # pydantic's ValidationError is a ValueError subclass; a bad or missing payload field
        # (KeyError: `prepare_visit` with no `appointment_id`) is the same bucket.
        return ErrorCode.BAD_REQUEST
    return ErrorCode.INTERNAL


async def _calm_error_message(
    session: AsyncSession | None, context: KeyContext, exc: BaseException
) -> tuple[str, ErrorCode]:
    """Patient words only (§29; B1/B2/B2-R1) — never the exception's own text, whether it is a
    `Refusal`'s constructor message or a bug's own `str()`. Reads `RUN_ERROR_WORDS` (`app.
    delivery.timeline_strings`, `@patient`-tagged, checked by `make plain-words`) in the
    profile's own language where that can still be read; falls back to English on the code's
    own generic line if even that fails (`session` may be `None` — `app.channels.api.runs.
    start_run`'s own `pump` passes it through unconditionally, if `session_scope` itself never
    opened one — rather than let a second exception hide the first."""
    from app.delivery.timeline_strings import RUN_ERROR_WORDS

    code = _error_code(exc)
    try:
        from app.memory.timeline import language_for

        if session is None:
            raise RuntimeError("no session to read a language from")
        language = await language_for(session, context, None)
    except Exception:
        log.exception("nura run: could not read the profile's language for a calm RUN_ERROR")
        language = "en"
    words = RUN_ERROR_WORDS.get(language, RUN_ERROR_WORDS["en"])
    return words.get(code.value, RUN_ERROR_WORDS["en"][code.value]), code


def _dimensions_json(view: StateView) -> dict[str, Any]:
    return {dimension.value: held for dimension, held in view.dimensions.items()}


def _state_snapshot_payload(view: StateView) -> dict[str, Any]:
    return {
        "state_id": str(view.id),
        "sequence": view.sequence,
        "posture": view.posture.value,
        "computed_at": view.computed_at.isoformat(),
        "dimensions": _dimensions_json(view),
        "withheld": sorted(dimension.value for dimension in view.withheld),
        "withheld_scopes": sorted(scope.value for scope in view.withheld_scopes),
        "stale": view.stale,
    }


def _state_patch(before: StateView | None, after: StateView) -> list[dict[str, Any]] | None:
    """An RFC 6902 patch from `before` to `after`, or `None` when nothing a run can act on
    moved. `None` on the very first read of a run (`before is None`) deliberately: a run that
    never had a prior snapshot to diff against emits `STATE_SNAPSHOT` instead (see the
    per-intent functions below), not a patch with nothing to compare to."""
    if before is None or before.id == after.id:
        return None
    ops: list[dict[str, Any]] = []
    if before.sequence != after.sequence:
        ops.append({"op": "replace", "path": "/sequence", "value": after.sequence})
    if before.posture is not after.posture:
        ops.append({"op": "replace", "path": "/posture", "value": after.posture.value})
    if before.stale != after.stale:
        ops.append({"op": "replace", "path": "/stale", "value": after.stale})
    for dimension in Dimension:
        was = before.dimensions.get(dimension)
        now = after.dimensions.get(dimension)
        if was != now:
            ops.append({"op": "replace", "path": f"/dimensions/{dimension.value}", "value": now})
    return ops or None


async def _maybe_state_event(
    builder: EventBuilder, session: AsyncSession, *, context: KeyContext, before: StateView | None
) -> Event | None:
    """`STATE_DELTA` when the record moved during this run, `STATE_SNAPSHOT` the first time a
    run can read State at all (`before is None`), or nothing when neither applies — never
    emitted for a key too narrow to recompute (`current_state` itself tells that apart; this
    function only reacts to what it returns, it does not loosen the door)."""
    try:
        after = await current_state(session, context=context)
    except Refusal:
        return None
    if before is None:
        return builder.state_snapshot(snapshot=_state_snapshot_payload(after))
    patch = _state_patch(before, after)
    if patch is None:
        return None
    return builder.state_delta(patch=patch)


async def _state_before(session: AsyncSession, *, context: KeyContext) -> StateView | None:
    try:
        return await current_state(session, context=context)
    except Refusal:
        return None


# --- understand_paper -------------------------------------------------------------------------


async def _understand_paper(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine, builder: EventBuilder
) -> AsyncIterator[Event]:
    from app.audit.access import audited_profile_read
    from app.channels.about_him import Reader, reader_of
    from app.channels.api.schemas import ImportIn, PhotoIn
    from app.delivery.timeline_strings import DOCUMENT_KIND_WORD, IMPORT_STEPS
    from app.ingestion.documents import store_pdf
    from app.ingestion.photos import store_photo
    from app.ingestion.review import (
        ImportStep,
        ImportStepKey,
        ReviewCard,
        notice_of,
        review_artifact_stream,
    )

    def _stage(reader: Reader, lang: str, step: ImportStep) -> str:
        catalogue = IMPORT_STEPS[lang]
        if step.key is ImportStepKey.FOUND:
            kind = DOCUMENT_KIND_WORD[lang].get(step.document_kind or "", DOCUMENT_KIND_WORD[lang]["other"])
            text = (
                catalogue["found_at"].format(kind=kind, facility=step.facility)
                if step.facility
                else catalogue["found"].format(kind=kind)
            )
        elif step.key is ImportStepKey.LINKED and step.linked_kind == "medicine":
            text = catalogue["linked_medicine"].format(medicine=step.linked_label or "")
        elif step.key is ImportStepKey.LINKED:
            text = catalogue["linked_visit"]
        else:
            text = catalogue[step.key.value]
        return reader.says(text)

    open_tool_call_id: str | None = None
    try:
        before = await _state_before(session, context=context)
        language = (await audited_profile_read(session, context)).language
        reader = await reader_of(session, context, None)
        kind = str(subject.payload.get("kind", "photo"))
        body: ImportIn | PhotoIn
        if kind == "pdf":
            body = ImportIn.model_validate(subject.payload)
            artifact = await store_pdf(
                session,
                context=context,
                store=engine.object_store,
                data=body.as_bytes(),
                content_type=body.content_type,
                captured_at=body.captured_at,
            )
            source = body.source
        else:
            from app.memory.models import SourceChannel

            body = PhotoIn.model_validate(subject.payload)
            artifact = await store_photo(
                session,
                context=context,
                store=engine.object_store,
                data=body.as_bytes(),
                content_type=body.content_type,
                captured_at=body.captured_at,
                source_channel=SourceChannel.APP,
            )
            source = None

        card: ReviewCard | None = None
        async for event in review_artifact_stream(
            session,
            context=context,
            artifact_id=artifact.id,
            store=engine.object_store,
            extractor=engine.extractor,
            language=language,
            asked_as=body.document_kind,
            source=source,
            registry=engine.drug_registry,
        ):
            if isinstance(event, ImportStep):
                tool_call_id = f"{builder.run_id}:{event.key.value}"
                # `open_tool_call_id` is set only once `tool_call_start` has actually been
                # yielded (round 3 review nit): `stage=_stage(...)` is evaluated as part of
                # building that call's own arguments, before the `yield` — a failure there
                # (a missing catalogue key, say) never opened a call at all, so the `except`
                # below must not close one either.
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key.value,
                    stage=_stage(reader, language, event),
                )
                open_tool_call_id = tool_call_id
                yield builder.tool_call_end(tool_call_id=tool_call_id)
                open_tool_call_id = None
                yield builder.tool_call_result(
                    tool_call_id=tool_call_id,
                    content=ToolResult(
                        key=event.key.value,
                        document_kind=event.document_kind,
                        linked_kind=event.linked_kind,
                    ),
                )
                yield builder.custom(name="step", value=StepCustom(key=event.key.value))
            else:
                card = event
        assert card is not None
        notice = notice_of(card)
        yield builder.custom(
            name="card",
            value=CardCustom(card_id=str(card.id), notice=notice.value if notice else None),
        )
        state_event = await _maybe_state_event(builder, session, context=context, before=before)
        if state_event is not None:
            yield state_event
        finished = builder.run_finished(result={"card_id": str(card.id)})
        if finished is not None:
            yield finished
    except Exception:
        if open_tool_call_id is not None:
            yield builder.tool_call_end(tool_call_id=open_tool_call_id, error=True)
        raise


# --- answer_question ---------------------------------------------------------------------------


async def _answer_question(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine, builder: EventBuilder
) -> AsyncIterator[Event]:
    from app.channels.about_him import reader_of
    from app.channels.api.timeline_schemas import AskIn
    from app.delivery.timeline_strings import ASK_STEPS
    from app.memory.timeline import language_for
    from app.search.ask import AskStep
    from app.search.asker import AnswerDelta

    message_id = f"{builder.run_id}:answer"
    started_text = False
    open_tool_call_id: str | None = None
    try:
        before = await _state_before(session, context=context)
        body = AskIn.model_validate(subject.payload)
        language = await language_for(session, context, body.language)
        reader = await reader_of(session, context, body.language)
        final: Any = None
        async for event in engine.asker.ask_stream(
            session,
            context=context,
            question=body.question,
            mode=body.mode,
            retriever=engine.retriever,
            store=engine.object_store,
            registry=engine.drug_registry,
            language=body.language,
            history=None,
        ):
            if isinstance(event, AskStep):
                # One real read of his own record (`app.search.asker.Asker`'s own contract):
                # a zero-argument tool, so START/END carry no ARGS event, and RESULT is the
                # step's own already-safe count — never the record itself (module doc; this
                # is the fixture/live parity point the audit named at ask_agent.py:1316).
                tool_call_id = f"{builder.run_id}:{event.key}:{event.count}"
                # See `_understand_paper`'s own comment: `open_tool_call_id` is set only once
                # `tool_call_start` — including its `stage=` argument — has actually run.
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key,
                    stage=reader.says(ASK_STEPS[language][event.key]),
                )
                open_tool_call_id = tool_call_id
                yield builder.tool_call_end(tool_call_id=tool_call_id)
                open_tool_call_id = None
                yield builder.tool_call_result(
                    tool_call_id=tool_call_id, content=ToolResult(key=event.key, count=event.count)
                )
            elif isinstance(event, AnswerDelta):
                if not started_text:
                    yield builder.text_message_start(message_id=message_id)
                    started_text = True
                yield builder.text_message_content(message_id=message_id, delta=event.text)
            else:
                final = event
        if started_text:
            yield builder.text_message_end(message_id=message_id)
            started_text = False
        assert final is not None
        state_event = await _maybe_state_event(builder, session, context=context, before=before)
        if state_event is not None:
            yield state_event
        finished = builder.run_finished(result={"lines": len(final.lines)})
        if finished is not None:
            yield finished
    except Exception:
        if open_tool_call_id is not None:
            yield builder.tool_call_end(tool_call_id=open_tool_call_id, error=True)
        if started_text:
            yield builder.text_message_end(message_id=message_id)
        raise


# --- generate_analysis -------------------------------------------------------------------------


async def _generate_analysis(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine, builder: EventBuilder
) -> AsyncIterator[Event]:
    from app.channels.about_him import reader_of
    from app.memory.timeline import language_for
    from app.reasoning.analyst.port import Report, Step
    from app.reasoning.analyst.provider import analyst_for
    from app.reasoning.analyst.service import save_report

    open_tool_call_id: str | None = None
    try:
        before = await _state_before(session, context=context)
        asked_language = subject.payload.get("language")
        language = await language_for(
            session, context, str(asked_language) if asked_language else None
        )
        reader = await reader_of(session, context, language)
        analyst = analyst_for(engine.settings, registry=engine.drug_registry)
        report: Report | None = None
        async for event in analyst.report_stream(session, context=context, language=language):
            if isinstance(event, Step):
                tool_call_id = f"{builder.run_id}:{event.key.value}"
                # See `_understand_paper`'s own comment: `open_tool_call_id` is set only once
                # `tool_call_start` — including its `stage=` argument — has actually run.
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key.value,
                    stage=reader.says(event.label),
                )
                open_tool_call_id = tool_call_id
                yield builder.tool_call_end(tool_call_id=tool_call_id)
                open_tool_call_id = None
                yield builder.tool_call_result(
                    tool_call_id=tool_call_id, content=ToolResult(key=event.key.value)
                )
            else:
                report = event
        assert report is not None
        await save_report(session, context=context, report=report)
        yield builder.custom(
            name="report", value=ReportCustom(sections=len(report.sections), language=report.language)
        )
        state_event = await _maybe_state_event(builder, session, context=context, before=before)
        if state_event is not None:
            yield state_event
        finished = builder.run_finished(result={"sections": len(report.sections)})
        if finished is not None:
            yield finished
    except Exception:
        if open_tool_call_id is not None:
            yield builder.tool_call_end(tool_call_id=open_tool_call_id, error=True)
        raise


# --- generate_recommendations -------------------------------------------------------------------


async def _generate_recommendations(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine, builder: EventBuilder
) -> AsyncIterator[Event]:
    """The feed's self-searches have no stream of their own today (`GET …/feed/jobs/status`
    is a plain read of work that already ran or is still due) — so, like `prepare_visit`
    below, this is a plain run: one `TOOL_CALL_*` for the one real read it makes,
    `RUN_FINISHED`. Nothing here starts a search job itself (`POST …/search-jobs` already
    exists and is unchanged); this intent only reports whether today's are done."""
    from app.channels.about_him import reader_of
    from app.delivery.feed.days import today_for
    from app.delivery.feed.search import jobs_looking_today
    from app.delivery.timeline_strings import RUN_STAGE_WORDS
    from app.memory.timeline import language_for

    open_tool_call_id: str | None = None
    try:
        language = await language_for(session, context, None)
        reader = await reader_of(session, context, None)
        tool_call_id = f"{builder.run_id}:jobs_looking_today"
        # `open_tool_call_id` is set only once `tool_call_start` — including its `stage=`
        # argument — has actually run (round 3 review nit; see `_understand_paper`'s comment).
        yield builder.tool_call_start(
            tool_call_id=tool_call_id,
            tool_call_name="jobs_looking_today",
            stage=reader.says(RUN_STAGE_WORDS[language]["jobs_looking_today"]),
        )
        open_tool_call_id = tool_call_id
        # round 3, fix 1: the real work (`await`) happens between START and END here — unlike
        # the streamed intents above, where a step is only ever reported once the read behind
        # it has already finished. A failure here left `TOOL_CALL_START` with no matching
        # `END` before this fix; `open_tool_call_id` is what the `except` below closes.
        looking = await jobs_looking_today(session, context=context, day=today_for(context))
        yield builder.tool_call_end(tool_call_id=tool_call_id)
        open_tool_call_id = None
        yield builder.tool_call_result(tool_call_id=tool_call_id, content=ToolResult(looking=looking))
        finished = builder.run_finished(result={"looking": looking})
        if finished is not None:
            yield finished
    except Exception:
        if open_tool_call_id is not None:
            yield builder.tool_call_end(tool_call_id=open_tool_call_id, error=True)
        raise


# --- triage_red_flag ----------------------------------------------------------------------------


async def _triage_red_flag(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine, builder: EventBuilder
) -> AsyncIterator[Event]:
    from app.channels.about_him import reader_of
    from app.channels.api.safety_schemas import SaidIn
    from app.delivery.timeline_strings import NFW_STEPS
    from app.delivery.triggers.deliver import Via
    from app.memory.timeline import language_for
    from app.safety.not_feeling_well import NfwStep, not_feeling_well_stream

    open_tool_call_id: str | None = None
    try:
        before = await _state_before(session, context=context)
        body = SaidIn.model_validate(subject.payload)
        # `not_feeling_well_stream` resolves the card's own language internally (voice
        # transcription may differ from what was asked); this is only the best available
        # guess for the *stage* line while it is still running — never shown as the card's
        # own answer, which always uses `done.language` (module doc of the plain route,
        # `app.channels.api.safety.button_stream`).
        language = await language_for(session, context, body.language)
        reader = await reader_of(session, context, body.language)
        done: Any = None
        async for event in not_feeling_well_stream(
            session,
            context=context,
            store=engine.object_store,
            transcriber=engine.transcriber,
            registry=engine.drug_registry,
            via=Via.of(engine.settings, engine.providers),
            words=body.words,
            audio=body.audio_bytes(),
            content_type=body.content_type,
            language=body.language,
        ):
            if isinstance(event, NfwStep):
                tool_call_id = f"{builder.run_id}:{event.key.value}"
                stage_words = NFW_STEPS.get(language, NFW_STEPS["en"])
                # `open_tool_call_id` is set only once `tool_call_start` — including its
                # `stage=` argument — has actually run (see `_understand_paper`'s comment).
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key.value,
                    stage=reader.says(stage_words[event.key.value]),
                )
                open_tool_call_id = tool_call_id
                yield builder.tool_call_end(tool_call_id=tool_call_id)
                open_tool_call_id = None
                yield builder.tool_call_result(
                    tool_call_id=tool_call_id, content=ToolResult(key=event.key.value)
                )
            else:
                done = event
        assert done is not None
        has_red_flag = bool(done.red_flags)
        yield builder.custom(name="card", value=CardCustom(red_flag=has_red_flag))
        state_event = await _maybe_state_event(builder, session, context=context, before=before)
        if state_event is not None:
            yield state_event
        finished = builder.run_finished(result={"red_flag": has_red_flag})
        if finished is not None:
            yield finished
    except Exception:
        if open_tool_call_id is not None:
            yield builder.tool_call_end(tool_call_id=open_tool_call_id, error=True)
        raise


# --- prepare_visit -------------------------------------------------------------------------------


async def _prepare_visit(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine, builder: EventBuilder
) -> AsyncIterator[Event]:
    """Visit prep has no stream of its own today (`GET …/appointments/{id}/brief` is a plain
    read) — a plain run, per the operator's own correction: one `TOOL_CALL_*` for the one
    real read (`app.reasoning.visits.brief.brief_for`, unchanged), `STATE_SNAPSHOT` (a visit
    brief is rendered from State — `brief_for` reads `current_state` itself — so a snapshot is
    always meaningful here, never only a delta), `RUN_FINISHED`."""
    from app.channels.about_him import reader_of
    from app.delivery.timeline_strings import RUN_STAGE_WORDS
    from app.memory.timeline import language_for
    from app.reasoning.visits.brief import brief_for

    open_tool_call_id: str | None = None
    try:
        raw_appointment_id = subject.payload["appointment_id"]
        appointment_id = uuid.UUID(str(raw_appointment_id))
        language = await language_for(session, context, None)
        reader = await reader_of(session, context, None)
        tool_call_id = f"{builder.run_id}:brief_for"
        # `open_tool_call_id` is set only once `tool_call_start` — including its `stage=`
        # argument — has actually run (round 3 review nit; see `_understand_paper`'s comment).
        yield builder.tool_call_start(
            tool_call_id=tool_call_id,
            tool_call_name="brief_for",
            stage=reader.says(RUN_STAGE_WORDS[language]["brief_for"]),
        )
        open_tool_call_id = tool_call_id
        # round 3, fix 1: same gap as `generate_recommendations` above — the real work is
        # between START and END, so a failure in `brief_for` used to leave START unmatched.
        brief = await brief_for(
            session, context=context, appointment_id=appointment_id, registry=engine.drug_registry
        )
        yield builder.tool_call_end(tool_call_id=tool_call_id)
        open_tool_call_id = None
        yield builder.tool_call_result(tool_call_id=tool_call_id, content=ToolResult(lines=len(brief.lines)))
        after = await _state_before(session, context=context)
        if after is not None:
            yield builder.state_snapshot(snapshot=_state_snapshot_payload(after))
        finished = builder.run_finished(result={"appointment_id": str(appointment_id)})
        if finished is not None:
            yield finished
    except Exception:
        if open_tool_call_id is not None:
            yield builder.tool_call_end(tool_call_id=open_tool_call_id, error=True)
        raise


_INTENTS: dict[Intent, Any] = {
    Intent.UNDERSTAND_PAPER: _understand_paper,
    Intent.ANSWER_QUESTION: _answer_question,
    Intent.GENERATE_ANALYSIS: _generate_analysis,
    Intent.GENERATE_RECOMMENDATIONS: _generate_recommendations,
    Intent.TRIAGE_RED_FLAG: _triage_red_flag,
    Intent.PREPARE_VISIT: _prepare_visit,
}


async def run_nura(
    intent: Intent,
    subject: RunSubject,
    context: KeyContext,
    session: AsyncSession,
    engine: Engine,
    *,
    builder: EventBuilder | None = None,
) -> AsyncIterator[Event]:
    """`runNura(intent, subject, context)` (ADR 0019 point 5; master-spec §5), over the
    existing engine (`Providers`, `app.channels.api.deps`) and the existing session — never a
    second database connection, never a second copy of any wrapped route's own logic.

    `builder` is normally supplied by the caller (`app.channels.api.runs.start_run`'s `pump`,
    which keeps the same instance for its own last-resort catch — round 3, B1-R1): passing it
    in, rather than this function creating its own, is what keeps `run_id` and `seq` the same
    across everything a run ever emits, including an error that comes from outside this
    function's own `try` (a `session_scope` commit failing on the way out, after
    `RUN_FINISHED` already reached the wire). A caller that does not supply one — every direct
    test in this repo — gets a fresh one built here; the one-builder-per-*run* promise still
    holds, because each call to `run_nura` is exactly one run.

    `RUN_STARTED` is the first event yielded. Every outcome after it — the wrapped call
    succeeding, a `Refusal`, an unknown intent, or any other exception — ends the run in
    exactly one terminal event, `RUN_FINISHED` or `RUN_ERROR`; never an exception past this
    function (§4; B1, B1-R1)."""
    # `str(intent)`, not `intent.value`: a `StrEnum` member's `str()` is its own value, and a
    # caller that (like `app.channels.api.runs.start_run`, and this module's own tests) hands
    # in a plain string for an intent this runtime does not know needs that string to reach
    # `UnknownIntent` below, not an `AttributeError` from `.value` on a bare `str`.
    builder = builder or EventBuilder(intent=str(intent))
    yield builder.run_started(subject=str(subject.profile_id))
    try:
        handler = _INTENTS.get(intent)
        if handler is None:
            raise UnknownIntent(f"no such intent: {intent!r}")
        async for event in handler(subject, context, session, engine, builder):
            yield event
    except Exception as exc:
        log.exception("nura run %s (%s)", builder.run_id, builder.intent)
        message, code = await _calm_error_message(session, context, exc)
        error = builder.run_error(message=message, code=code)
        if error is not None:
            yield error


__all__ = ["Engine", "Intent", "RunSubject", "UnknownIntent", "run_nura"]
