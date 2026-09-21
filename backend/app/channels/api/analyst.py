"""The Health Analyst over HTTP.

    POST /profiles/{id}/insights/stream   a step per real read, then the finished report — saved
    GET  /profiles/{id}/insights          the latest saved report, or `null` when none exists yet
    GET  /profiles/{id}/insights/list     every past report, newest first, summaries only
    GET  /profiles/{id}/insights/{report_id}   one saved report by id
    POST /profiles/{id}/papers/{artifact_id}/insight/stream   checkpoint 3: one confirmed
        paper, beside the record — a step per real read, then the finished insight — saved
    POST /profiles/{id}/papers/{artifact_id}/insight/keep     file the offered questions on
        the next visit (or as a standing memo with none yet)

The stream opens its own session (`session_scope`), never `Depends(db)`, for the same reason
`app.channels.api.timeline.ask_stream` does: FastAPI closes a `yield` dependency's exit stack
the moment this function returns the `StreamingResponse` object, well before Starlette drives
the generator that actually reads with it.

`papers/{artifact_id}/insight/stream` opens `session_scope` twice, never once for the whole
request: once for every real read (`app.reasoning.analyst.paper.read_phase`), which closes and
commits before a model call is ever made, and — only if the deployment runs
`NURA_ANALYST=claude` — a second, fresh one for the rebuild and the save, opened only after
the model has already answered. No database transaction is open while that call is in flight
(`app.reasoning.analyst.paper`'s own module doc; the defect this avoids is `app.delivery.feed.
background`'s own docstring).

`GET …/insights` used to answer 404 (`NoReportYet`) for a profile with nothing generated yet —
correct as a refusal, but read on every single Health screen load, including a brand-new
profile's very first one, where "nothing generated yet" is the ordinary case. A browser logs
every failed fetch to its own console regardless of how the caller handles the rejection, so
that ordinary case printed a console error on every fresh Health load (package 10's #2 defect,
`web/src/screens/Health.tsx`). The route now answers `200` with a `null` body in that case —
`latest_report_or_none` — a normal, empty result; `GET …/insights/{report_id}` keeps its 404
for an id that genuinely does not exist, and `latest_report` (raise-and-all) is kept for the
callers that only ever call it once a report is already known to exist.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import record_share
from app.audit.models import Channel
from app.channels.about_him import reader_of
from app.channels.api.deps import Context, Db, providers_of, session_scope
from app.db import utcnow
from app.delivery import analyst_strings as analyst_words
from app.errors import Refusal
from app.identity.models import Profile, Stewardship
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.keys.context import KeyContext, as_the_system, resolve_key_context
from app.keys.scopes import Scope
from app.memory.spine import upcoming_appointments
from app.memory.timeline import language_for
from app.reasoning.analyst.port import Insight, Report, Section, Step
from app.reasoning.analyst.service import (
    latest_report_or_none,
    list_reports,
    report_by_id,
    save_report,
)
from app.reasoning.visits.guard import may_change_visits
from app.reasoning.visits.memos import current_memos, write_memo
from app.reasoning.visits.models import MemoKind, MemoSource
from app.reasoning.visits.questions import keep_paper_insight_questions
from app.settings import Settings
from app.state.service import StateView, current_state

# `app.reasoning.analyst.paper`/`paper_service`/`claude_adapter`/`provider` all reach,
# through `RuleAnalyst`'s own reads, back into `app.channels.api.deps` — this package's own
# `__init__` — which is still mid-import the first time this module loads as one of its
# routers (the same cycle `insights_stream` above already avoids). Imported lazily inside
# the functions that need them, below; `TYPE_CHECKING` only for the one annotation that
# names the module by its type.
if TYPE_CHECKING:
    from app.reasoning.analyst import paper as paper_analyst

router = APIRouter(prefix="/profiles", tags=["analyst"])


def _sse(payload: dict[str, object]) -> bytes:
    """One Server-Sent Event: a `data:` line of JSON, blank line after — the same shape
    `app.channels.api.timeline._sse` writes, kept as its own small copy here rather than a
    shared import, the way `app.channels.api.feed` already keeps its own."""
    return f"data: {json.dumps(payload, default=str)}\n\n".encode()


async def _refusal_event(request: Request, refusal: Refusal) -> bytes:
    # Deferred: `app.channels.api.refusals` imports modules that, transitively, import this
    # package's own `__init__` (the same cycle `app.channels.api.timeline` avoids by sitting
    # late in `__init__.py`'s router list); importing it lazily here keeps `analyst.py` safe
    # to import from anywhere, in any order.
    from app.channels.api.refusals import refused

    response = await refused(request, refusal)
    body = json.loads(bytes(response.body))
    return _sse({"type": "refusal", "status": response.status_code, **body})


class EvidenceOut(BaseModel):
    id: str
    kind: str
    label: str


class InsightOut(BaseModel):
    insight_id: str
    kind: str
    text: str
    ask_who: str
    evidence: list[EvidenceOut]
    why_plain: str
    confidence: str


class SectionOut(BaseModel):
    key: str
    title: str
    insights: list[InsightOut]


class InsightReportOut(BaseModel):
    report_id: str
    generated_at: datetime
    week_of: date
    boundary: list[str]
    sections: list[SectionOut]
    withheld: list[str] = []
    """The key of every section this key's own scopes could not cover — set by
    `app.reasoning.analyst.service._narrowed_for` on a saved report read back by a narrower
    key than generated it; always empty straight off the stream, since that key is the one
    that just generated the report and withheld nothing from itself (`RuleAnalyst` already
    leaves an unscoped section out of `sections` entirely at generation time)."""

    @classmethod
    def of_report(cls, report: Report) -> InsightReportOut:
        return cls(
            report_id=report.report_id,
            generated_at=report.generated_at,
            week_of=report.week_of,
            boundary=list(report.boundary),
            withheld=[],
            sections=[
                SectionOut(
                    key=section.key,
                    title=section.title,
                    insights=[
                        InsightOut(
                            insight_id=insight.insight_id,
                            kind=insight.kind.value,
                            text=insight.text,
                            ask_who=insight.ask_who.value,
                            evidence=[
                                EvidenceOut(id=e.id, kind=e.kind, label=e.label)
                                for e in insight.evidence
                            ],
                            why_plain=insight.why_plain,
                            confidence=insight.confidence.value,
                        )
                        for insight in section.insights
                    ],
                )
                for section in report.sections
            ],
        )

    @classmethod
    def of_row(cls, row: dict[str, object]) -> InsightReportOut:
        return cls(
            report_id=str(row["report_id"]),
            generated_at=cast(datetime, row["generated_at"]),
            week_of=cast(date, row["week_of"]),
            boundary=list(cast("list[str]", row["boundary"])),
            withheld=list(cast("list[str]", row.get("withheld", []))),
            sections=[
                SectionOut.model_validate(section)
                for section in cast("list[dict[str, object]]", row["sections"])
            ],
        )


@router.post("/{profile_id}/insights/stream")
async def insights_stream(request: Request, context: Context) -> StreamingResponse:
    """A `step` event the instant each real read finishes, then the finished `report` — saved
    to `insight_report` the moment it is ready, so `GET …/insights` can answer without a
    second run."""
    # Deferred: `app.reasoning.analyst.provider` reaches, through `RuleAnalyst`'s own reads
    # (`app.reasoning.patterns.series` -> `app.safety.not_feeling_well` -> `app.delivery.
    # triggers.deliver`), back into `app.channels.api.deps` — this package's own `__init__`
    # — which is still mid-import the first time this module loads as one of its routers.
    from app.reasoning.analyst.provider import analyst_for

    settings: Settings = request.app.state.settings
    registry = providers_of(request).drug_registry
    analyst = analyst_for(settings, registry=registry)

    async def events() -> AsyncIterator[bytes]:
        try:
            async with session_scope(request) as session:
                language = await language_for(session, context, None)
                reader = await reader_of(session, context, language)
                report: Report | None = None
                async for event in analyst.report_stream(session, context=context, language=language):
                    if isinstance(event, Step):
                        yield _sse(
                            {
                                "type": "step",
                                "key": event.key.value,
                                "label": reader.says(event.label),
                                # The bare noun (`STEP_NAME`, the same idea as Ask's own
                                # `ASK_STEP_NAMES`): what the Health Analyst screen collapses
                                # five real reads into, once, after the stream settles
                                # ("What Nura looked at: …"). Two of the five do speak to him
                                # ("what you have told Nura", "what you paid") and need
                                # `reader.says()` the same as `label` above — caught by a
                                # caregiver-voice e2e sweep the first time this shipped without
                                # it (package 10 review #1).
                                "name": reader.says(analyst_words.STEP_NAME[language][event.key.value]),
                            }
                        )
                    else:
                        report = event
                assert report is not None
                await save_report(session, context=context, report=report)
                out = reader.model(InsightReportOut.of_report(report))
                yield _sse({"type": "report", "report": out.model_dump(mode="json")})
        except Refusal as refusal:
            yield await _refusal_event(request, refusal)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/{profile_id}/insights")
async def insights_latest(context: Context, session: Db) -> InsightReportOut | None:
    """The newest saved report, or `null` when nothing has been generated for this profile
    yet — a normal, empty result, not a refusal (see the module doc)."""
    row = await latest_report_or_none(session, context=context)
    if row is None:
        return None
    reader = await reader_of(session, context, cast("str | None", row.get("language")))
    return reader.model(InsightReportOut.of_row(row))


class InsightReportSummaryOut(BaseModel):
    report_id: str
    generated_at: datetime
    week_of: date


@router.get("/{profile_id}/insights/list")
async def insights_list(context: Context, session: Db) -> list[InsightReportSummaryOut]:
    """Every past Health Analyst report for this profile, newest first — summaries only, no
    sections (`GET …/insights/{report_id}` reads one back in full). Registered ahead of
    `GET …/insights/{report_id}` below so the literal path `list` is never parsed as a
    `report_id`."""
    rows = await list_reports(session, context=context)
    return [
        InsightReportSummaryOut(
            report_id=cast(str, row["report_id"]),
            generated_at=cast(datetime, row["generated_at"]),
            week_of=cast(date, row["week_of"]),
        )
        for row in rows
    ]


@router.get("/{profile_id}/insights/{report_id}")
async def insights_by_id(
    report_id: uuid.UUID, context: Context, session: Db
) -> InsightReportOut:
    row = await report_by_id(session, context=context, report_id=report_id)
    reader = await reader_of(session, context, cast("str | None", row.get("language")))
    return reader.model(InsightReportOut.of_row(row))


# --- checkpoint 3: a paper-scoped insight ---------------------------------------------------


class LookedAtOut(BaseModel):
    kind: str
    id: str
    label: str


class PaperInsightOut(BaseModel):
    report_id: str
    generated_at: datetime
    boundary: list[str]
    headline: str
    looked_at: list[LookedAtOut]
    questions: list[InsightOut]
    withheld: list[str] = []

    @classmethod
    def of_insight(cls, insight: paper_analyst.PaperInsight) -> PaperInsightOut:
        return cls(
            report_id=insight.report_id,
            generated_at=insight.generated_at,
            boundary=list(insight.boundary),
            headline=insight.headline,
            looked_at=[
                LookedAtOut(kind=one.kind, id=one.id, label=one.label)
                for one in insight.looked_at
            ],
            questions=[
                InsightOut(
                    insight_id=q.insight_id,
                    kind=q.kind.value,
                    text=q.text,
                    ask_who=q.ask_who.value,
                    evidence=[EvidenceOut(id=e.id, kind=e.kind, label=e.label) for e in q.evidence],
                    why_plain=q.why_plain,
                    confidence=q.confidence.value,
                )
                for q in insight.questions
            ],
            withheld=list(insight.withheld),
        )


async def _paper_events(
    request: Request, context: KeyContext, artifact_id: uuid.UUID
) -> AsyncIterator[bytes]:
    # Deferred for the same reason `insights_stream` above defers `app.reasoning.analyst.
    # provider`: these reach back into this package's own `__init__`, still mid-import the
    # first time this module loads as one of its routers.
    from app.reasoning.analyst import paper as paper_analyst
    from app.reasoning.analyst.claude_adapter import ClaudeAnalyst, _parse_choices, _rebuild
    from app.reasoning.analyst.paper_service import save_paper_insight
    from app.reasoning.analyst.provider import analyst_for

    settings: Settings = request.app.state.settings
    registry = providers_of(request).drug_registry

    # Phase 1: every real read, in one short unit of work — closed and committed before a
    # model is ever called (see the module doc).
    read: paper_analyst.ReadResult | None = None
    language = "en"
    try:
        async with session_scope(request) as session:
            language = await language_for(session, context, None)
            reader = await reader_of(session, context, language)
            async for event in paper_analyst.read_phase(
                session, context=context, artifact_id=artifact_id, language=language, registry=registry
            ):
                if isinstance(event, paper_analyst.PaperStep):
                    yield _sse({"type": "step", "key": event.key.value, "label": reader.says(event.label)})
                else:
                    read = event
    except Refusal as refusal:
        yield await _refusal_event(request, refusal)
        return
    assert read is not None

    # Phase 2: the model call, if this deployment runs one — no session open at all.
    source = "rule"
    questions: Sequence[Insight] = read.questions
    moment = utcnow()
    temp_report = Report(
        report_id=str(uuid.uuid4()),
        generated_at=moment,
        week_of=moment.date(),
        language=language,
        source="rule",
        boundary=(),
        sections=(Section(paper_analyst.CANDIDATE_SECTION_KEY, "", tuple(read.questions)),),
    )
    claude_choices = None
    analyst = analyst_for(settings, registry=registry)
    attempted_external_call = False
    if isinstance(analyst, ClaudeAnalyst) and read.questions:
        attempted_external_call = True
        try:
            raw = await analyst._ask_claude(temp_report)
            claude_choices = None if raw is None else _parse_choices(raw)
        except Exception:  # noqa: BLE001 — any doubt at all falls back to the rule questions
            claude_choices = None

    # Phase 3: the rebuild (if any), the save and the audit line — a second, fresh session.
    async with session_scope(request) as session:
        # The context left the region the moment the call above was made, whatever it came
        # back with (or whether it came back at all) — the line is written once that is
        # known, never only when the rephrase also succeeded (CLAUDE.md: no unlogged path).
        if attempted_external_call:
            await record_share(
                session,
                context=context,
                scope=Scope.PROFILE,
                target="insight_report",
                channel=Channel.APP,
                shared_with_label=EXTERNAL_MODEL_PROCESSOR,
            )
        if claude_choices is not None:
            rebuilt = await _rebuild(
                temp_report, claude_choices, session=session, context=context, language=language
            )
            rebuilt_section = next(
                (s for s in rebuilt.sections if s.key == paper_analyst.CANDIDATE_SECTION_KEY), None
            )
            if rebuilt_section is not None and rebuilt_section.insights:
                questions = rebuilt_section.insights
                source = "claude"
        insight = paper_analyst.build_insight(
            language=language,
            source=source,
            questions=list(questions),
            looked_at=list(read.looked_at),
            withheld=list(read.withheld),
            now=utcnow(),
        )
        await save_paper_insight(session, context=context, artifact_id=artifact_id, insight=insight)
        reader = await reader_of(session, context, language)
        out = reader.model(PaperInsightOut.of_insight(insight))
        yield _sse({"type": "report", "report": out.model_dump(mode="json")})


@router.post("/{profile_id}/papers/{artifact_id}/insight/stream")
async def paper_insight_stream(
    artifact_id: uuid.UUID, request: Request, context: Context
) -> StreamingResponse:
    """Checkpoint 3, "What it means for you": the moment a paper is confirmed, run the Health
    Analyst over just this paper, beside the record — a `step` event per real read, then one
    `report` event, the same event contract `POST …/insights/stream` already promises. Saved
    the moment it finishes, so `POST …/insight/keep` can file it without a second run."""
    return StreamingResponse(_paper_events(request, context, artifact_id), media_type="text/event-stream")


async def _system_state(session: AsyncSession, *, context: KeyContext) -> StateView:
    """The current State, folded under this profile's own owner or steward reach — the same
    "acting as the system" standing `app.reasoning.analyst.weekly_job._acting_context`
    already uses for a profile's own unattended run — so a caregiver's key, which may not
    itself hold every scope a full recompute needs (`app.state.service.RECOMPUTE_SCOPES`;
    a caregiver preset lacks FAMILY and MONEY), can still file a standing memo without ever
    widening what that key itself may read: this read is never handed back to the caller,
    the same standing `app.safety.red_flags._system_read` already holds — only the memo's own
    fixed line, and the state id it is stamped with, ever leave."""
    profile = await session.get(Profile, context.profile_id)
    assert profile is not None  # a resolved KeyContext always names a profile that exists
    if profile.owner_person_id is not None:
        acting_id = profile.owner_person_id
    else:
        steward = await session.scalar(
            select(Stewardship).where(
                Stewardship.profile_id == profile.id, Stewardship.closed_at.is_(None)
            )
        )
        assert steward is not None  # a caregiver key implies an owner or an open stewardship
        acting_id = steward.steward_person_id
    acting = as_the_system(
        await resolve_key_context(
            session,
            region=context.region,
            person_id=acting_id,
            profile_id=profile.id,
            while_closing=True,
        )
    )
    return await current_state(session, context=acting)


class PaperInsightKeepOut(BaseModel):
    kept_count: int
    filed: str
    appointment_id: str | None = None


@router.post("/{profile_id}/papers/{artifact_id}/insight/keep", status_code=201)
async def keep_paper_insight(
    artifact_id: uuid.UUID, context: Context, session: Db
) -> PaperInsightKeepOut:
    """"Keep these for my visit": file the offered questions from the paper's saved insight
    on the next upcoming visit, through the existing visit-questions write path
    (`keep_paper_insight_questions`), idempotently. With no upcoming visit, keep a standing
    memo instead (`app.reasoning.visits.memos.write_memo`), the existing "unfiled" store this
    backend already has — also idempotent, by the same marker.

    Checked at the door, both branches alike: a viewer, a helper or a clinic key reads the
    visits and never changes them (`app.reasoning.visits.guard.may_change_visits`) — the same
    refusal `keep_paper_insight_questions` already raises for the "visit" branch on its own,
    made explicit here so the "unfiled" branch, which does not call it, is never the one path
    that door was missing from."""
    from app.reasoning.analyst.paper_service import latest_paper_insight, questions_of

    may_change_visits(context)
    row = await latest_paper_insight(session, context=context, artifact_id=artifact_id)
    questions = questions_of(row)
    upcoming = await upcoming_appointments(session, context=context)
    ordered = sorted(upcoming, key=lambda visit: (visit.scheduled_at, str(visit.id)))
    if ordered:
        visit = ordered[0]
        kept = await keep_paper_insight_questions(
            session,
            context=context,
            appointment_id=visit.id,
            artifact_id=artifact_id,
            insights=questions,
        )
        return PaperInsightKeepOut(
            kept_count=len(kept), filed="visit", appointment_id=str(visit.id)
        )
    marker_language = row.language
    standing = [
        memo
        for memo in await current_memos(session, context=context)
        if memo.key == "ask_from_paper" and memo.source_id == artifact_id
    ]
    filed_now = False
    if not standing and questions:
        from app.delivery.strings import YOUR_DOCTOR
        from app.reasoning.trends import doctor_to_ask

        doctor = await doctor_to_ask(session, context)
        await write_memo(
            session,
            context=context,
            kind=MemoKind.ASK,
            key="ask_from_paper",
            slots={"doctor": doctor or YOUR_DOCTOR[marker_language]},
            source=MemoSource.ANALYST,
            source_id=artifact_id,
            language=marker_language,
            state=await _system_state(session, context=context),
        )
        filed_now = True
    # `kept_count` counts what THIS call actually filed — 0 on a repeat call, the same
    # idempotency promise the "visit" branch above keeps.
    return PaperInsightKeepOut(kept_count=len(questions) if filed_now else 0, filed="unfiled")


__all__ = ["router"]
