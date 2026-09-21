"""`ClaudeAnalyst`: the agent behind the `Analyst` port, gated the same way every other
Claude-backed adapter here is (`app.llm.residency.allow_external_model`, ADR 0017) — it may
only be built on a declared demo or a declared dev run, never the public deployment, and its
construction site is `app.reasoning.analyst.provider.analyst_for`, never this class itself.

It never reads the record on its own account: it wraps `RuleAnalyst`, which does every real,
audited read (`records`, `series`, `medicines`, `ledger`, `coverage` — the same tools
`app.llm.ask_agent.ClaudeAsker` calls, scoped the same way) and already turns them into a
finished, cited, verified `Report`. That report's own insights, one candidate list per
section, is the only material this adapter ever shows the model: it asks Claude to choose and
rephrase from that list alone — never to invent a new fact — and structured output
(`output_config={"format": {"type": "json_schema", ...}}`, the same shape every other
Claude-backed adapter here uses) means a plain, typed shape back, not prose to parse loosely.

Every insight the model returns must cite only ids that already appear in the rule report's
own evidence — never a new id, never new evidence, only `text` and `why_plain` change — and,
unlike the first cut of this adapter, the model's own words are never trusted just because
they parsed: each rebuilt candidate is run back through the exact gate every rule candidate
already passed, `app.reasoning.analyst.pipeline.finalize` — plain words, the
conclusion-or-advice blocklist, a cite or it is not shown, and a medicine or supplement that
fails either rerouted as a real question for the doctor
(`app.reasoning.analyst.rule.ask_the_doctor`, #236), its own words never printed. Only the
rule the candidate failed is ever logged; the candidate's text itself is not. On any doubt at
all — the API call fails, times out, is refused, is cut off at `max_tokens`, returns something
that does not parse, or every one of its insights gets dropped or rerouted — the whole call
falls back to the rule report, unchanged, and nobody sees a half-built page.

One `EXTERNAL_MODEL_PROCESSOR` audit entry is written per run in which the model was actually
called — whatever its outcome, success, a refusal, a cut-off answer, a reply that does not
parse, or the call itself raising — never only on success: the person's context left the
region the moment the call was made, whether or not anything useful came back, so the line is
written once that is known to be true, before the outcome is even decided, the same line
`app.channels.api.timeline.ask_stream` writes for the agent asker's own reach outside the
region (ADR 0017, mirroring `app.ingestion.review.review_artifact`'s line for the extractor).
Never written when `rule_report.sections` was empty: the model is never called on nothing.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import record_share
from app.audit.models import Channel
from app.ingestion.review import EXTERNAL_MODEL_PROCESSOR
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.reasoning.analyst.pipeline import Candidate, finalize
from app.reasoning.analyst.port import AskWho, Insight, Report, ReportEvent, Section
from app.reasoning.analyst.rule import QUESTIONS_KEY, RuleAnalyst, ask_the_doctor

log = logging.getLogger("nura.reasoning.analyst.claude")

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 2048

CHOICES_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["insights"],
    "properties": {
        "insights": {
            "type": "array",
            "description": "The candidates worth keeping, in his own words — never a new "
            "id, never a new fact, never a number or a name not already on the candidate.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["insight_id", "text", "why_plain"],
                "properties": {
                    "insight_id": {
                        "type": "string",
                        "description": "Exactly one of the candidate ids given below.",
                    },
                    "text": {"type": "string"},
                    "why_plain": {"type": "string"},
                },
            },
        },
    },
}
"""The raw JSON schema `output_config.format.schema` asks for — a flat schema, every property
carrying a `type`, no `minimum`/`maximum` on any number: both are refused outright by the
API's structured output (`tests/test_claude_feed_adapters.py`, `tests/test_clipmaker.py`, hit
live on the owner's key, 2026-09-18)."""

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


def _block_text(block: Any) -> str:
    """A response content block's own text, whichever shape the SDK (or a test's fake) hands
    it back as — a `Mapping` or an object with a `.text` attribute, the same duck-typed read
    `app.delivery.feed.claude_adapters._structured_json` and `app.llm.ask_agent._structured_json`
    already use, never a strict `isinstance(block, TextBlock)` that a fake response would fail."""
    text = block.get("text") if isinstance(block, Mapping) else getattr(block, "text", None)
    return text or ""


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


async def _rebuild(
    report: Report,
    choices: list[_ModelChoice],
    *,
    session: AsyncSession,
    context: KeyContext,
    language: str,
) -> Report:
    """The rule report, with each real section's insights replaced by the model's own words
    where it kept that insight — never a new id, never new evidence: `pool[choice.insight_id]`
    already carries the cites and the ask_who a rule candidate earned, only `text` and
    `why_plain` change. A choice naming an id not in the pool is dropped outright.

    Every rebuilt candidate is run back through `app.reasoning.analyst.pipeline.finalize` —
    the same gate every rule candidate already passed once, now applied to the model's own
    words, which have never been checked: plain words, the conclusion-or-advice blocklist, a
    medicine or supplement that fails either rerouted as a real question for the doctor
    (`ask_the_doctor`, #236) and its own words never printed, any other kind that fails simply
    dropped. `questions_for_the_doctor` is never replayed itself — replaying it would run the
    same insight through the gate twice, and if it is a medicine or supplement (never true
    today, since only a doctor-bound kind rolls up here, but not a shape to depend on) could
    file the same doctor question twice — it is rebuilt fresh from what the five real sections
    kept, the exact rollup rule `RuleAnalyst.report_stream` itself holds to."""
    pool = _candidate_pool(report)
    by_id = {choice.insight_id: choice for choice in choices if choice.insight_id in pool}

    async def reroute(candidate: Candidate) -> Insight | None:
        return await ask_the_doctor(session, context, language, candidate)

    sections: list[Section] = []
    for section in report.sections:
        if section.key == QUESTIONS_KEY:
            continue
        rebuilt: list[Insight] = []
        for insight in section.insights:
            choice = by_id.get(insight.insight_id)
            if choice is None:
                continue
            candidate = Candidate(
                insight_id=insight.insight_id,
                kind=insight.kind,
                text=choice.text,
                ask_who=insight.ask_who,
                evidence=insight.evidence,
                why_plain=choice.why_plain,
                confidence=insight.confidence,
            )
            finalized = await finalize(candidate, language=language, reroute=reroute)
            if finalized is not None:
                rebuilt.append(finalized)
        if rebuilt:
            sections.append(Section(section.key, section.title, tuple(rebuilt)))

    if not sections:
        return report

    original_rollup = next((s for s in report.sections if s.key == QUESTIONS_KEY), None)
    if original_rollup is not None:
        by_key = {section.key: section for section in sections}
        doctor_insights: list[Insight] = []
        for key in (
            "what_changed",
            "worth_a_look",
            "medicines_and_supplements",
            "what_you_pay",
            "screenings_due",
        ):
            found = by_key.get(key)
            if found is None:
                continue
            doctor_insights.extend(one for one in found.insights if one.ask_who is AskWho.DOCTOR)
        sections.append(Section(QUESTIONS_KEY, original_rollup.title, tuple(doctor_insights)))

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

    async def _ask_claude(self, report: Report) -> str | None:
        """The one network call, isolated so a test can replace it without a live key.
        `None` on a refusal or a cut-off answer (`stop_reason` "refusal" or "max_tokens") —
        both checked before anything is parsed, the same two `report_stream` folds into its
        fallback along with a parse failure."""
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
            output_config={"format": {"type": "json_schema", "schema": CHOICES_SCHEMA}},
        )
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            log.info("analyst claude: the model refused; falling back to the rule report")
            return None
        if stop_reason == "max_tokens":
            log.warning("analyst claude: the model's answer was cut off at max_tokens")
            return None
        return "".join(_block_text(block) for block in response.content or [] if _block_text(block))

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
        # Reaching here means the model is about to be called (or the call itself is about
        # to raise) — the context is about to leave the region either way, so the share line
        # is written once that is decided, before the outcome is: on any doubt at all
        # (a refusal, a cut-off answer, a parse failure, the call itself raising), the
        # report falls back to the rule's own, but the audit line still stands — there is no
        # unlogged path (CLAUDE.md).
        rebuilt: Report | None = None
        try:
            raw = await self._ask_claude(rule_report)
            if raw is None:
                raise ValueError("the model's reply was refused or cut off")
            choices = _parse_choices(raw)
            if choices is None:
                raise ValueError("the model's reply did not parse")
            rebuilt = await _rebuild(rule_report, choices, session=session, context=context, language=language)
        except Exception:
            log.warning("analyst: falling back to the rule report", exc_info=True)
        await record_share(
            session,
            context=context,
            scope=Scope.PROFILE,
            target="insight_report",
            channel=Channel.APP,
            shared_with_label=EXTERNAL_MODEL_PROCESSOR,
        )
        yield rebuilt if rebuilt is not None else rule_report


__all__ = ["ClaudeAnalyst"]
