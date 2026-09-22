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

**A run always terminates (§4; independent review of #331, B1).** Every handler below is one
`try` whose `except Exception` — not only `except Refusal` — is the last thing that runs
before the generator returns: whatever goes wrong inside the wrapped call, on the model's own
side or on a bad payload, becomes one `RUN_ERROR` and the run ends there. Nothing here lets a
bug end a stream silently, mid-message, with the connection simply closing.

**Patient words, not engine language (§29; B2).** `TOOL_CALL_START.stage` and
`RUN_ERROR.message` are never a Python exception's own text, a bare enum value or a function
name — both come from `app.delivery.timeline_strings`' own `@patient`-tagged catalogues, in
the profile's language, the same words the plain routes this module wraps already say while
they work.

**Fixture and live parity (ADR 0019 point 12; master-spec §42).** Every intent below is
wired against a *port* (`app.search.asker.Asker`, `app.reasoning.analyst.port.Analyst` — see
each module's own doc), never against a specific adapter, so the event sequence a fixture
adapter produces and the one a live model adapter produces are the same shape: neither this
module nor a client reading its stream can tell which one is running
(`tests/test_runtime_events.py::test_fixture_and_live_askers_produce_the_same_event_type_sequence`,
`test_rule_and_claude_analysts_produce_the_same_event_type_sequence`).
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
from app.runtime.events import CardCustom, Event, EventBuilder, ReportCustom, StepCustom, ToolResult
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


# --- calm, patient-facing errors (§29; B2) -------------------------------------------------------

_REFUSAL_WORDS: dict[str, str] = {
    "OutOfScope": "The people looking after this cannot see that part yet.",
    "NoKey": "Nura does not recognise who is asking.",
    "NoState": "Nura does not have enough written down yet to answer that.",
    "StaleState": "Something just changed. Please try again in a moment.",
    "SnapshotBehindTheCard": "Something just changed. Please try again in a moment.",
    "NotAQuestion": "That does not look like a question Nura can answer.",
    "NoBriefYet": "Nura has not prepared anything for this visit yet.",
    "NotEveryFieldDecided": "A few things on this paper still need a yes or a no.",
    "AlreadyConfirmed": "This paper has already been checked.",
    "UnreadableField": "Nura could not read one of the fields on this paper.",
    "UnknownIntent": "Nura does not know how to do that yet.",
}
"""One calm sentence per `Refusal` this runtime's own wrapped calls are known to raise
(master-spec §29: never engine language, never "key does not cover records"). Never read
from a `Refusal`'s own constructor message — that message is written for a log
(`app.channels.api.refusals` module doc: "the sentence is the app's to write, not this
layer's") and may name an id, a role or a scope. A refusal not listed here, and any other
exception at all, gets `_GENERIC_ERROR_WORD`: an honest line, never a guess at one."""

_GENERIC_ERROR_WORD = "Nura could not finish that just now. Please try again."


def _calm_error_message(exc: BaseException) -> str:
    """Patient words only (§29; B1/B2) — never the exception's own text, whether it is a
    `Refusal`'s constructor message or a bug's own `str()`. This is the one seam a run's
    `RUN_ERROR.message` passes through; nothing else in this module writes error copy."""
    if isinstance(exc, Refusal):
        return _REFUSAL_WORDS.get(type(exc).__name__, _GENERIC_ERROR_WORD)
    return _GENERIC_ERROR_WORD


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
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine
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

    builder = EventBuilder(intent=Intent.UNDERSTAND_PAPER.value)
    yield builder.run_started(subject=str(subject.profile_id))
    before = await _state_before(session, context=context)
    try:
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
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key.value,
                    stage=_stage(reader, language, event),
                )
                yield builder.tool_call_end(tool_call_id=tool_call_id)
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
        yield builder.run_finished(result={"card_id": str(card.id)})
    except Exception as exc:
        log.exception("nura run %s: %s", builder.intent, builder.run_id)
        yield builder.run_error(message=_calm_error_message(exc), code=type(exc).__name__)


# --- answer_question ---------------------------------------------------------------------------


async def _answer_question(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine
) -> AsyncIterator[Event]:
    from app.channels.about_him import reader_of
    from app.channels.api.timeline_schemas import AskIn
    from app.delivery.timeline_strings import ASK_STEPS
    from app.memory.timeline import language_for
    from app.search.ask import AskStep
    from app.search.asker import AnswerDelta

    builder = EventBuilder(intent=Intent.ANSWER_QUESTION.value)
    yield builder.run_started(subject=str(subject.profile_id))
    before = await _state_before(session, context=context)
    message_id = f"{builder.run_id}:answer"
    started_text = False
    try:
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
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key,
                    stage=reader.says(ASK_STEPS[language][event.key]),
                )
                yield builder.tool_call_end(tool_call_id=tool_call_id)
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
        yield builder.run_finished(result={"lines": len(final.lines)})
    except Exception as exc:
        log.exception("nura run %s: %s", builder.intent, builder.run_id)
        if started_text:
            yield builder.text_message_end(message_id=message_id)
        yield builder.run_error(message=_calm_error_message(exc), code=type(exc).__name__)


# --- generate_analysis -------------------------------------------------------------------------


async def _generate_analysis(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine
) -> AsyncIterator[Event]:
    from app.channels.about_him import reader_of
    from app.memory.timeline import language_for
    from app.reasoning.analyst.port import Report, Step
    from app.reasoning.analyst.provider import analyst_for
    from app.reasoning.analyst.service import save_report

    builder = EventBuilder(intent=Intent.GENERATE_ANALYSIS.value)
    yield builder.run_started(subject=str(subject.profile_id))
    before = await _state_before(session, context=context)
    try:
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
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key.value,
                    stage=reader.says(event.label),
                )
                yield builder.tool_call_end(tool_call_id=tool_call_id)
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
        yield builder.run_finished(result={"sections": len(report.sections)})
    except Exception as exc:
        log.exception("nura run %s: %s", builder.intent, builder.run_id)
        yield builder.run_error(message=_calm_error_message(exc), code=type(exc).__name__)


# --- generate_recommendations -------------------------------------------------------------------


async def _generate_recommendations(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine
) -> AsyncIterator[Event]:
    """The feed's self-searches have no stream of their own today (`GET …/feed/jobs/status`
    is a plain read of work that already ran or is still due) — so, like `prepare_visit`
    below, this is a plain run: `RUN_STARTED`, one `TOOL_CALL_*` for the one real read it
    makes, `RUN_FINISHED`. Nothing here starts a search job itself (`POST …/search-jobs`
    already exists and is unchanged); this intent only reports whether today's are done."""
    from app.channels.about_him import reader_of
    from app.delivery.feed.days import today_for
    from app.delivery.feed.search import jobs_looking_today
    from app.delivery.timeline_strings import RUN_STAGE_WORDS
    from app.memory.timeline import language_for

    builder = EventBuilder(intent=Intent.GENERATE_RECOMMENDATIONS.value)
    yield builder.run_started(subject=str(subject.profile_id))
    try:
        language = await language_for(session, context, None)
        reader = await reader_of(session, context, None)
        tool_call_id = f"{builder.run_id}:jobs_looking_today"
        yield builder.tool_call_start(
            tool_call_id=tool_call_id,
            tool_call_name="jobs_looking_today",
            stage=reader.says(RUN_STAGE_WORDS[language]["jobs_looking_today"]),
        )
        looking = await jobs_looking_today(session, context=context, day=today_for(context))
        yield builder.tool_call_end(tool_call_id=tool_call_id)
        yield builder.tool_call_result(tool_call_id=tool_call_id, content=ToolResult(looking=looking))
        yield builder.run_finished(result={"looking": looking})
    except Exception as exc:
        log.exception("nura run %s: %s", builder.intent, builder.run_id)
        yield builder.run_error(message=_calm_error_message(exc), code=type(exc).__name__)


# --- triage_red_flag ----------------------------------------------------------------------------


async def _triage_red_flag(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine
) -> AsyncIterator[Event]:
    from app.channels.about_him import reader_of
    from app.channels.api.safety_schemas import SaidIn
    from app.delivery.timeline_strings import NFW_STEPS
    from app.delivery.triggers.deliver import Via
    from app.memory.timeline import language_for
    from app.safety.not_feeling_well import NfwStep, not_feeling_well_stream

    builder = EventBuilder(intent=Intent.TRIAGE_RED_FLAG.value)
    yield builder.run_started(subject=str(subject.profile_id))
    before = await _state_before(session, context=context)
    try:
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
                yield builder.tool_call_start(
                    tool_call_id=tool_call_id,
                    tool_call_name=event.key.value,
                    stage=reader.says(stage_words[event.key.value]),
                )
                yield builder.tool_call_end(tool_call_id=tool_call_id)
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
        yield builder.run_finished(result={"red_flag": has_red_flag})
    except Exception as exc:
        log.exception("nura run %s: %s", builder.intent, builder.run_id)
        yield builder.run_error(message=_calm_error_message(exc), code=type(exc).__name__)


# --- prepare_visit -------------------------------------------------------------------------------


async def _prepare_visit(
    subject: RunSubject, context: KeyContext, session: AsyncSession, engine: Engine
) -> AsyncIterator[Event]:
    """Visit prep has no stream of its own today (`GET …/appointments/{id}/brief` is a plain
    read) — a plain run, per the operator's own correction: `RUN_STARTED`, one `TOOL_CALL_*`
    for the one real read (`app.reasoning.visits.brief.brief_for`, unchanged), `STATE_SNAPSHOT`
    (a visit brief is rendered from State — `brief_for` reads `current_state` itself — so a
    snapshot is always meaningful here, never only a delta), `RUN_FINISHED`."""
    from app.channels.about_him import reader_of
    from app.delivery.timeline_strings import RUN_STAGE_WORDS
    from app.memory.timeline import language_for
    from app.reasoning.visits.brief import brief_for

    builder = EventBuilder(intent=Intent.PREPARE_VISIT.value)
    yield builder.run_started(subject=str(subject.profile_id))
    try:
        raw_appointment_id = subject.payload["appointment_id"]
        appointment_id = uuid.UUID(str(raw_appointment_id))
        language = await language_for(session, context, None)
        reader = await reader_of(session, context, None)
        tool_call_id = f"{builder.run_id}:brief_for"
        yield builder.tool_call_start(
            tool_call_id=tool_call_id,
            tool_call_name="brief_for",
            stage=reader.says(RUN_STAGE_WORDS[language]["brief_for"]),
        )
        brief = await brief_for(
            session, context=context, appointment_id=appointment_id, registry=engine.drug_registry
        )
        yield builder.tool_call_end(tool_call_id=tool_call_id)
        yield builder.tool_call_result(tool_call_id=tool_call_id, content=ToolResult(lines=len(brief.lines)))
        after = await _state_before(session, context=context)
        if after is not None:
            yield builder.state_snapshot(snapshot=_state_snapshot_payload(after))
        yield builder.run_finished(result={"appointment_id": str(appointment_id)})
    except Exception as exc:
        log.exception("nura run %s: %s", builder.intent, builder.run_id)
        yield builder.run_error(message=_calm_error_message(exc), code=type(exc).__name__)


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
) -> AsyncIterator[Event]:
    """`runNura(intent, subject, context)` (ADR 0019 point 5; master-spec §5), over the
    existing engine (`Providers`, `app.channels.api.deps`) and the existing session — never a
    second database connection, never a second copy of any wrapped route's own logic. Raises
    `UnknownIntent` for anything not in `Intent`, before any event is yielded; every other
    outcome, including a refusal or any other exception from the wrapped call, is reported as
    events — `RUN_STARTED` then `RUN_ERROR`, never an exception past this function (§4; B1)."""
    handler = _INTENTS.get(intent)
    if handler is None:
        raise UnknownIntent(f"no such intent: {intent!r}")
    async for event in handler(subject, context, session, engine):
        yield event


__all__ = ["Engine", "Intent", "RunSubject", "UnknownIntent", "run_nura"]
