"""Save and read back the Health Analyst's report (migration 0049): the glue between an
`Analyst`'s `Report` (`app.reasoning.analyst.port`) and the `InsightReport` row
(`app.reasoning.analyst.models`) `POST /profiles/{id}/insights/stream` saves the moment it
finishes streaming, the weekly job saves every Monday, and the two `GET` routes read back.

`InsightReport` is not `RowScoped`, and it is written under `Scope.PROFILE`, which every key
holds: the row itself is one JSON blob, the whole report as *whoever generated it* could read
— a chief's own report can hold a READINGS trend a caregiver's key never could. So a `GET`
by a narrower key must never simply hand that row back whole: `_narrowed_for` filters it down
to what *this* context's own scopes cover, section by section (`SECTION_SCOPE`), and
`questions_for_the_doctor` down to the insights whose own kind sits under a scope this context
holds (`_KIND_SCOPE`) — the same door `RuleAnalyst` would have closed at generation time, had
this context been the one generating it (`tests/test_row_scope.py`, the row-scope conformance
suite, is what caught the leak this filtering closes). What that narrowing cut is never left
unsaid either: `_narrowed_for` also hands back the key of every section a narrower context
could not see, and `InsightReportOut.withheld` carries it — a caregiver's `GET` on a chief's
own report says "screenings due was left out", never nothing at all where a section used to
be (the UI already renders a withheld section once the field is there, #271)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read, audited_write
from app.errors import Refusal
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.analyst.models import InsightReport
from app.reasoning.analyst.port import SECTION_SCOPE, InsightKind, Report

_KIND_SCOPE: dict[str, Scope] = {
    InsightKind.TREND.value: SECTION_SCOPE["what_changed"],
    InsightKind.COVERAGE.value: SECTION_SCOPE["worth_a_look"],
    InsightKind.GAP.value: SECTION_SCOPE["worth_a_look"],
    InsightKind.MEDICINE.value: SECTION_SCOPE["medicines_and_supplements"],
    InsightKind.SUPPLEMENT.value: SECTION_SCOPE["medicines_and_supplements"],
    InsightKind.COST.value: SECTION_SCOPE["what_you_pay"],
    InsightKind.CHECK.value: SECTION_SCOPE["screenings_due"],
}
"""Which scope each `InsightKind` was found under — the rollup's own map back to
`SECTION_SCOPE`, since a saved `questions_for_the_doctor` insight no longer carries which
section it first stood in."""


class NoReportYet(Refusal):
    """No Health Analyst report has ever been saved for this profile."""


def _section_json(report: Report) -> list[dict[str, object]]:
    return [
        {
            "key": section.key,
            "title": section.title,
            "insights": [
                {
                    "insight_id": insight.insight_id,
                    "kind": insight.kind.value,
                    "text": insight.text,
                    "ask_who": insight.ask_who.value,
                    "evidence": [
                        {
                            "id": evidence.id,
                            "kind": evidence.kind,
                            "label": evidence.label,
                        }
                        for evidence in insight.evidence
                    ],
                    "why_plain": insight.why_plain,
                    "confidence": insight.confidence.value,
                }
                for insight in section.insights
            ],
        }
        for section in report.sections
    ]


async def save_report(
    session: AsyncSession, *, context: KeyContext, report: Report
) -> InsightReport:
    """Write one row for a finished `Report` — what `POST …/insights/stream` does the moment
    it finishes streaming, and what the weekly job does once per profile."""
    return await audited_write(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        id=uuid.UUID(report.report_id),
        generated_at=report.generated_at,
        week_of=report.week_of,
        language=report.language,
        source=report.source,
        boundary=list(report.boundary),
        sections=_section_json(report),
    )


def _narrowed_for(
    context: KeyContext, sections: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """`sections`, exactly as saved, cut down to what `context`'s own scopes cover — never
    the scopes whoever generated and saved the row happened to hold — and, second, the key of
    every section this cut left out by name: a section a narrower key cannot see is named in
    `withheld`, never simply missing from the list with no reason given (`InsightReportOut`,
    `.claude/rules` — "a key without a scope gets that section withheld, named"). The rollup
    (`questions_for_the_doctor`) is never itself named in `withheld` — it carries no scope of
    its own (`SECTION_SCOPE`'s own docstring) and is only ever thinner, not absent, for a
    narrower key; a section with a real scope that this key holds but that simply has no
    insights in it is not withheld either — `withheld` names only a door this key could not
    open, never an empty room behind a door it could."""
    narrowed: list[dict[str, Any]] = []
    withheld: list[str] = []
    for section in sections:
        scope = SECTION_SCOPE.get(section["key"])
        if scope is not None:
            if context.allows(scope):
                narrowed.append(section)
            else:
                withheld.append(section["key"])
            continue
        # The rollup (`questions_for_the_doctor`): keep only the insights whose own kind
        # sits under a scope this context holds.
        kept = [
            insight
            for insight in section["insights"]
            if context.allows(_KIND_SCOPE.get(insight["kind"], Scope.PROFILE))
        ]
        if kept:
            narrowed.append({**section, "insights": kept})
    return narrowed, withheld


def _row_to_dict(row: InsightReport, *, context: KeyContext) -> dict[str, object]:
    sections, withheld = _narrowed_for(context, row.sections)
    return {
        "report_id": str(row.id),
        "generated_at": row.generated_at,
        "week_of": row.week_of,
        "language": row.language,
        "source": row.source,
        "boundary": list(row.boundary),
        "sections": sections,
        "withheld": withheld,
    }


async def latest_report(session: AsyncSession, *, context: KeyContext) -> dict[str, object]:
    """The newest saved report, tied on `(generated_at, id)` so a tie under a frozen clock
    never picks an arbitrary one (`.claude/rules` — "any latest query needs a tie-breaker"),
    narrowed to this context's own scopes (`_narrowed_for`)."""
    found = await audited_read(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        order_by=(desc(InsightReport.seq),),
        limit=1,
    )
    if not found:
        raise NoReportYet("no Health Analyst report has been saved for this profile yet")
    return _row_to_dict(found[0], context=context)


async def latest_report_or_none(
    session: AsyncSession, *, context: KeyContext
) -> dict[str, object] | None:
    """The same read as `latest_report`, but `None` rather than `NoReportYet` when nothing
    has been saved yet — `GET /profiles/{id}/insights` is read on every Health screen load,
    including a brand-new profile's very first one, where "nothing generated yet" is the
    ordinary case, not a refusal: a 404 there made the browser log a failed request on every
    such load (package 10's #2 defect). `latest_report` itself is kept, raise-and-all, for the
    callers that only ever call it once a report is known to exist."""
    found = await audited_read(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        order_by=(desc(InsightReport.seq),),
        limit=1,
    )
    if not found:
        return None
    return _row_to_dict(found[0], context=context)


async def list_reports(
    session: AsyncSession, *, context: KeyContext
) -> list[dict[str, object]]:
    """Every weekly/on-demand Health Analyst report saved for this profile, newest first — the
    quiet list "Health Analyst" opens under its current report. Never a paper-scoped insight
    (`artifact_id is not None`, checkpoint 3's own, separate feature, `app.reasoning.analyst.
    paper`): those are read back by `GET …/papers/{artifact_id}/insight`, not here. Summaries
    only — `report_id`, `generated_at`, `week_of` — never the sections themselves, which stay
    behind `GET …/insights/{report_id}` and its own narrowing."""
    found = await audited_read(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        where=(InsightReport.artifact_id.is_(None),),
        order_by=(desc(InsightReport.seq),),
    )
    return [
        {"report_id": str(row.id), "generated_at": row.generated_at, "week_of": row.week_of}
        for row in found
    ]


async def report_by_id(
    session: AsyncSession, *, context: KeyContext, report_id: uuid.UUID
) -> dict[str, object]:
    found = await audited_read(
        session,
        InsightReport,
        context,
        Scope.PROFILE,
        where=(InsightReport.id == report_id,),
    )
    if not found:
        raise NoReportYet("no Health Analyst report with that id on this profile")
    return _row_to_dict(found[0], context=context)


__all__ = [
    "NoReportYet",
    "latest_report",
    "latest_report_or_none",
    "list_reports",
    "report_by_id",
    "save_report",
]
