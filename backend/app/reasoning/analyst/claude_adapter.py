"""`ClaudeAnalyst`: the agent behind the `Analyst` port, gated the same way every other
Claude-backed adapter here is (`app.llm.residency.allow_external_model`, ADR 0017) — it may
only be built on a declared demo or a declared dev run, never the public deployment, and its
construction site is `app.reasoning.analyst.provider.analyst_for`, never this class itself.

It never reads the record on its own account: it wraps `RuleAnalyst`, which does every real,
audited read (`records`, `series`, `medicines`, `ledger`, `coverage` — the same tools
`app.llm.ask_agent.ClaudeAsker` calls, scoped the same way) and already turns them into a
finished, cited, verified `Report`. That report's own insights, one candidate list per
section, is the only material this adapter ever shows the model: it asks Claude to choose and
rephrase from that list alone — never to invent a new fact — and structured output means a
plain, typed shape back, not prose to parse loosely. Every insight the model returns must cite
only ids that already appear in the rule report's own evidence; one that cites an id the tools
never produced, or none at all, is dropped, the same "cites or it is not shown" floor
`app.reasoning.analyst.pipeline.finalize` already holds every rule insight to. On any doubt at
all — the API call fails, times out, returns something that does not parse, or every one of
its insights gets dropped for citing nothing real — the whole call falls back to the rule
report, unchanged, and nobody sees a half-built page.

One `EXTERNAL_MODEL_PROCESSOR` audit entry is written per run, the same line
`app.channels.api.timeline.ask_stream` writes for the agent asker's own reach outside the
region (ADR 0017, mirroring `app.ingestion.review.review_artifact`'s line for the extractor).
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import record_share
from app.audit.models import Channel
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.analyst.port import Insight, Report, ReportEvent, Section
from app.reasoning.analyst.rule import RuleAnalyst

log = logging.getLogger("nura.reasoning.analyst.claude")

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 2048

SYSTEM_PROMPT = (
    "You choose and lightly rephrase entries from a list of already-verified insights about "
    "a person's health record. You never invent a fact, a number, an id or a medicine name "
    "that is not already in the list you are given. For every insight you return, the "
    "`evidence` ids must be exactly a subset of the ids already on that candidate. Return "
    "JSON only, matching the schema you are given."
)


@dataclass(frozen=True, slots=True)
class _ModelChoice:
    """One insight the model chose to keep, by its candidate id and its own words — parsed,
    never trusted until every evidence id is checked against the candidate it named."""

    insight_id: str
    text: str
    why_plain: str


def _candidate_pool(report: Report) -> dict[str, Insight]:
    return {insight.insight_id: insight for section in report.sections for insight in section.insights}


def _parse_choices(raw: str) -> list[_ModelChoice] | None:
    try:
        data = json.loads(raw)
        items = data["insights"] if isinstance(data, dict) else data
        return [
            _ModelChoice(
                insight_id=str(item["insight_id"]),
                text=str(item["text"]),
                why_plain=str(item["why_plain"]),
            )
            for item in items
        ]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _rebuild(report: Report, choices: list[_ModelChoice]) -> Report:
    """The rule report, with each section's insights replaced by the model's own words where
    it kept that insight — never a new id, never new evidence: `pool[choice.insight_id]`
    already carries the cites and the ask_who a rule candidate earned, only `text` and
    `why_plain` change. A choice naming an id not in the pool is dropped outright."""
    pool = _candidate_pool(report)
    by_id = {choice.insight_id: choice for choice in choices if choice.insight_id in pool}
    sections: list[Section] = []
    for section in report.sections:
        rebuilt: list[Insight] = []
        for insight in section.insights:
            choice = by_id.get(insight.insight_id)
            if choice is None:
                continue
            rebuilt.append(
                Insight(
                    insight_id=insight.insight_id,
                    kind=insight.kind,
                    text=choice.text,
                    ask_who=insight.ask_who,
                    evidence=insight.evidence,
                    why_plain=choice.why_plain,
                    confidence=insight.confidence,
                )
            )
        if rebuilt:
            sections.append(Section(section.key, section.title, tuple(rebuilt)))
    if not sections:
        return report
    return Report(
        report_id=report.report_id,
        generated_at=report.generated_at,
        week_of=report.week_of,
        language=report.language,
        source="claude",
        boundary=report.boundary,
        sections=tuple(sections),
    )


class ClaudeAnalyst:
    """The agent `Analyst`. Every real read is `RuleAnalyst`'s; this class only asks Claude to
    choose and rephrase from what that read already produced, and falls back to it whole on
    any doubt."""

    def __init__(self, *, client: AsyncAnthropic, registry: object | None = None) -> None:
        self._client = client
        self._rule = RuleAnalyst(registry=registry)  # type: ignore[arg-type]

    async def _ask_claude(self, report: Report) -> str:
        """The one network call, isolated so a test can replace it without a live key."""
        pool = [
            {
                "insight_id": insight.insight_id,
                "kind": insight.kind.value,
                "text": insight.text,
                "why_plain": insight.why_plain,
                "evidence_ids": [e.id for e in insight.evidence],
            }
            for section in report.sections
            for insight in section.insights
        ]
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Candidates (JSON): " + json.dumps(pool) + "\n\n"
                        'Return {"insights": [{"insight_id": ..., "text": ..., '
                        '"why_plain": ...}]} for the ones worth keeping, in his own '
                        f"language ({report.language})."
                    ),
                }
            ],
        )
        return "".join(
            block.text for block in response.content if isinstance(block, TextBlock)
        )

    async def report_stream(
        self,
        session: AsyncSession,
        *,
        context: KeyContext,
        language: str,
        now: datetime | None = None,
    ) -> AsyncIterator[ReportEvent]:
        rule_report: Report | None = None
        async for event in self._rule.report_stream(session, context=context, language=language, now=now):
            if isinstance(event, Report):
                rule_report = event
            else:
                yield event
        assert rule_report is not None
        if not rule_report.sections:
            yield rule_report
            return
        try:
            raw = await self._ask_claude(rule_report)
            choices = _parse_choices(raw)
            if choices is None:
                raise ValueError("the model's reply did not parse")
            rebuilt = _rebuild(rule_report, choices)
        except Exception:
            log.warning("analyst: falling back to the rule report", exc_info=True)
            yield rule_report
            return
        await record_share(
            session,
            context=context,
            scope=Scope.PROFILE,
            target="insight_report",
            channel=Channel.APP,
            shared_with_label=EXTERNAL_MODEL_PROCESSOR,
        )
        yield rebuilt


__all__ = ["ClaudeAnalyst"]
