"""The Health Analyst over HTTP.

    POST /profiles/{id}/insights/stream   a step per real read, then the finished report — saved
    GET  /profiles/{id}/insights          the latest saved report, or 404 `NoReportYet`
    GET  /profiles/{id}/insights/{report_id}   one saved report by id

The stream opens its own session (`session_scope`), never `Depends(db)`, for the same reason
`app.channels.api.timeline.ask_stream` does: FastAPI closes a `yield` dependency's exit stack
the moment this function returns the `StreamingResponse` object, well before Starlette drives
the generator that actually reads with it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.channels.about_him import reader_of
from app.channels.api.deps import Context, Db, providers_of, session_scope
from app.errors import Refusal
from app.memory.timeline import language_for
from app.reasoning.analyst.port import Report, Step
from app.reasoning.analyst.service import latest_report, report_by_id, save_report
from app.settings import Settings

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
                            {"type": "step", "key": event.key.value, "label": reader.says(event.label)}
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
async def insights_latest(context: Context, session: Db) -> InsightReportOut:
    """The newest saved report, or `NoReportYet` (404)."""
    row = await latest_report(session, context=context)
    reader = await reader_of(session, context, cast("str | None", row.get("language")))
    return reader.model(InsightReportOut.of_row(row))


@router.get("/{profile_id}/insights/{report_id}")
async def insights_by_id(
    report_id: uuid.UUID, context: Context, session: Db
) -> InsightReportOut:
    row = await report_by_id(session, context=context, report_id=report_id)
    reader = await reader_of(session, context, cast("str | None", row.get("language")))
    return reader.model(InsightReportOut.of_row(row))


__all__ = ["router"]
