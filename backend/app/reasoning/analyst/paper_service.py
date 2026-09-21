"""Save and read back a paper-scoped insight (checkpoint 3, "What it means for you",
migration 0053): a sibling of `app.reasoning.analyst.service.save_report` that reuses the
same `insight_report` table and the same discipline — one row per run, `Scope.PROFILE`,
never a row a narrower key could not have read had it generated the report itself — rather
than a second table for what is still one Health Analyst report, just scoped to one paper
instead of the whole week.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.db import as_utc
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.analyst.models import InsightReport
from app.reasoning.analyst.paper import REPORT_KEY, PaperInsight
from app.reasoning.analyst.port import (
    SECTION_TITLES,
    AskWho,
    Confidence,
    Evidence,
    Insight,
    InsightKind,
)
from app.regions import REGION_TZ


class NoPaperInsightYet(Refusal):
    """No paper-scoped insight has been generated for this artifact yet: call
    `POST /profiles/{id}/papers/{artifact_id}/insight/stream` first."""


def _section_json(insight: PaperInsight) -> list[dict[str, object]]:
    return [
        {
            "key": REPORT_KEY,
            "title": SECTION_TITLES[insight.language][REPORT_KEY],
            "insights": [
                {
                    "insight_id": question.insight_id,
                    "kind": question.kind.value,
                    "text": question.text,
                    "ask_who": question.ask_who.value,
                    "evidence": [
                        {"id": e.id, "kind": e.kind, "label": e.label}
                        for e in question.evidence
                    ],
                    "why_plain": question.why_plain,
                    "confidence": question.confidence.value,
                }
                for question in insight.questions
            ],
        }
    ]


def _week_of(context: KeyContext, insight: PaperInsight) -> object:
    """The Monday of the week the insight was generated, on the region's own clock — the same
    computation `app.reasoning.analyst.rule._week_of` makes for the weekly report, held to
    the one promise every `insight_report` row keeps regardless of which kind it is."""
    local = as_utc(insight.generated_at).astimezone(REGION_TZ[context.region]).date()  # type: ignore[index]
    return local - timedelta(days=local.weekday())


async def save_paper_insight(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    insight: PaperInsight,
) -> InsightReport:
    """Write one row for a finished `PaperInsight` — what the paper-scoped stream does the
    moment it finishes, the same moment `save_report` writes for the weekly one."""
    return await audited_write(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        id=uuid.UUID(insight.report_id),
        generated_at=insight.generated_at,
        week_of=_week_of(context, insight),
        language=insight.language,
        source=insight.source,
        boundary=list(insight.boundary),
        sections=_section_json(insight),
        artifact_id=artifact_id,
        headline=insight.headline,
        looked_at=[
            {"kind": one.kind, "id": one.id, "label": one.label} for one in insight.looked_at
        ],
    )


async def latest_paper_insight(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID
) -> InsightReport:
    """The newest saved paper-scoped insight for this artifact, tied on `(seq, id)` so a tie
    under a frozen clock never picks an arbitrary one — the same tie-breaker
    `app.reasoning.analyst.service.latest_report` already holds to."""
    found = await audited_read(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        where=(InsightReport.artifact_id == artifact_id,),
        order_by=(desc(InsightReport.seq),),
        limit=1,
    )
    if not found:
        raise NoPaperInsightYet(
            f"no paper insight saved for artifact {artifact_id} on profile {context.profile_id}"
        )
    return found[0]


def questions_of(row: InsightReport) -> list[Insight]:
    """The saved row's own questions, rebuilt as `Insight`s — the same shape
    `keep_paper_insight_questions` (`app.reasoning.visits.questions`) needs, read back from
    exactly what was shown, never recomputed."""
    section = next((s for s in row.sections if s["key"] == REPORT_KEY), None)
    if section is None:
        return []
    insights = cast("list[dict[str, Any]]", section["insights"])
    return [
        Insight(
            insight_id=cast(str, one["insight_id"]),
            kind=InsightKind(one["kind"]),
            text=cast(str, one["text"]),
            ask_who=AskWho(one["ask_who"]),
            evidence=tuple(
                Evidence(id=e["id"], kind=e["kind"], label=e["label"])
                for e in cast("list[dict[str, str]]", one["evidence"])
            ),
            why_plain=cast(str, one["why_plain"]),
            confidence=Confidence(one["confidence"]),
        )
        for one in insights
    ]


__all__ = [
    "NoPaperInsightYet",
    "latest_paper_insight",
    "questions_of",
    "save_paper_insight",
]
