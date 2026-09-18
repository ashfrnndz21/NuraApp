"""Cost expectation before a visit or procedure (T3): a typical fee range from a public fee
benchmark, always cited and dated, and what his cover on file would likely pay, always as a
range and always labelled "typical, not a quote". Nura does not quote a price — a clinic sets
its own fee — and, the same as `app.insurance.relevance`, Nura does not decide coverage: the
insurer does. This module only ever shows a number a benchmark publisher already published, or
a number already on his own insurance record; never a number it invented.

**Two estimators, one shape.** `RuleEstimator` (the default) looks the visit or procedure up
by keyword in a small, hand-reviewed table of public benchmarks (`app.insurance.benchmarks`) —
Singapore's MOH fee-benchmark comparisons and hospital published bills, Malaysia's MOH fee
schedule. `ClaudeEstimator`, behind `NURA_ESTIMATOR=claude`, refines that same row's own
published page with a live fetch through Claude's `web_fetch` tool, gated by
`app.llm.residency.allow_external_model` the same way every other Claude-backed adapter is;
every property of its structured output is typed, and a number it wrote that is not, verbatim,
in the page it fetched is dropped, never guessed at — the same discipline `#239`'s searcher
already keeps for a result's own url (`app.delivery.feed.claude_adapters`). The fetched url is
checked against the allowlist (`app.delivery.feed.sources`) the same way, on the url the tool
itself returned, never the model's restated string.

**What his cover would pay is never invented.** A percentage Nura calculated from nothing he
told it would be exactly the kind of number this module exists to avoid. So the covered range
is the widest honest one his own record supports: with no active policy, zero to zero — the
insurer pays nothing that is not on file; with one, zero (the insurer may decline the claim) to
the benchmark's own high (the insurer may cover it in full) — never a made-up midpoint. The
note line beside it always says "may pay part of this" and points at the insurer, the same
"may apply, confirm with the insurer" framing `app.insurance.relevance` already uses.

**The scope split.** Reading the visit at all needs `Scope.VISITS`, the same door `app.memory.
attach.require_appointment` already keeps — a key that cannot see the visit is refused before
any figure is looked up. The covered range needs `Scope.MONEY` on top of that, the same door a
policy already stands behind (`app.insurance.policy`): a key without it still sees the typical
fee range and its source, but the covered range is withheld and named, not silently blank
(`cost.covered_needs_money_scope`) — never a number a caregiver could reverse-engineer his
finances from.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_guard, audited_profile_read
from app.audit.models import Action
from app.clock import now
from app.delivery.feed.sources import usable_sources
from app.insurance.benchmarks import find_benchmark
from app.insurance.policy import POLICY_SCOPE, PolicyStatus, current_policies
from app.insurance.strings import CURRENCY_BY_REGION, render, say_money
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.llm.residency import allow_external_model
from app.memory.attach import require_appointment
from app.memory.models import Appointment
from app.regions import Region
from app.settings import Settings

log = logging.getLogger("nura.insurance.cost_expectation")

__all__ = [
    "COST_SCOPE",
    "ClaudeEstimator",
    "CostEstimatorNotAvailable",
    "CostExpectation",
    "Estimator",
    "Line",
    "NoEstimator",
    "RuleEstimator",
    "Source",
    "estimator_for",
    "expect_cost",
]

COST_SCOPE = Scope.VISITS
"""The door for the typical fee range itself — the same one a visit's own brief and logistics
sit behind. `Scope.MONEY` gates only the covered range on top of it (module docstring)."""


class CostEstimatorNotAvailable(RuntimeError):
    """The Claude cost estimator runs only on a declared demo or a declared dev run, and needs
    ANTHROPIC_API_KEY — the same gate every Claude-backed adapter shares (ADR 0017)."""


class NoEstimator(RuntimeError):
    """NURA_ESTIMATOR names an adapter this build does not have."""


@dataclass(frozen=True, slots=True)
class Source:
    """Who published the benchmark, the page it came from, and the day it was read."""

    publisher: str
    url: str
    fetched_at: date


@dataclass(frozen=True, slots=True)
class Line:
    """One rendered, verified line, with the id of the template it came from."""

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class CostExpectation:
    """What `GET /profiles/{id}/visits/{appointment_id}/cost` answers with. `found=False`
    means `low_cents`, `high_cents` and `source` are all `None` — no benchmark matched, said
    plainly, never a guess. `covered_shown=False` means `covered_low_cents` and
    `covered_high_cents` are `None` too — the caller does not hold `Scope.MONEY`."""

    appointment_id: uuid.UUID
    found: bool
    low_cents: int | None
    high_cents: int | None
    low_said: str | None
    high_said: str | None
    currency: str
    source: Source | None
    covered_shown: bool
    covered_low_cents: int | None
    covered_high_cents: int | None
    covered_low_said: str | None
    covered_high_said: str | None
    note: tuple[Line, ...]


class Estimator(Protocol):
    """The one shape both estimators answer: a benchmark's low/high in minor units, its
    source, or `None` when nothing usable was found — never a partial guess."""

    async def estimate(
        self, session: AsyncSession, *, visit_or_procedure: str, region: Region
    ) -> _Estimate | None: ...


@dataclass(frozen=True, slots=True)
class _Estimate:
    low_cents: int | None
    high_cents: int | None
    source: Source


class RuleEstimator:
    """The default: a lookup in the small cached benchmark table
    (`app.insurance.benchmarks`), nothing fetched, nothing inferred."""

    async def estimate(
        self, session: AsyncSession, *, visit_or_procedure: str, region: Region
    ) -> _Estimate | None:
        entry = find_benchmark(visit_or_procedure, region)
        if entry is None:
            return None
        return _Estimate(
            low_cents=entry.low_cents,
            high_cents=entry.high_cents,
            source=Source(publisher=entry.publisher, url=entry.url, fetched_at=entry.fetched_at),
        )


ESTIMATE_SCHEMA: dict[str, Any] = {
    "name": "cost_estimate",
    "schema": {
        "type": "object",
        "properties": {
            "low": {"type": ["integer", "null"]},
            "high": {"type": ["integer", "null"]},
            "currency": {"type": "string"},
        },
        "required": ["low", "high", "currency"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _numeral_in(number: int, text: str) -> bool:
    """Whether this whole-unit amount appears, as digits, somewhere in the fetched page's own
    text — thousands separators and decimal cents stripped out first, so "S$1,250" and "1250"
    both match a claimed `1250`. Never true for a number the page never wrote."""
    stripped = re.sub(r"[,\s]", "", text)
    return str(number) in stripped


class ClaudeEstimator:
    """`NURA_ESTIMATOR=claude`: refines the rule table's own benchmark row with one live fetch
    of that row's own published page, through Claude's `web_fetch` tool and structured output.
    Never a free search — the url fetched is always the one the cached table already names for
    this region and this kind of visit, and that url is checked against the source allowlist
    (`app.delivery.feed.sources`) the same way `#239`'s searcher checks a result's own url:
    on the url the tool itself returned, never a string the model wrote. A `low` or `high` the
    model answers that does not appear, verbatim, in the fetched page's own text is dropped —
    each independently, so one honest number is never discarded because the other could not be
    verified."""

    def __init__(
        self, *, api_key: str | None, demo_mode: bool, dev_run: bool = False, client: Any | None = None
    ) -> None:
        allow_external_model(
            demo_mode=demo_mode,
            dev_run=dev_run,
            refusal=CostEstimatorNotAvailable,
            what="the Claude cost estimator",
        )
        if not api_key:
            raise CostEstimatorNotAvailable(
                "the Claude cost estimator needs ANTHROPIC_API_KEY set in the environment"
            )
        self._client = client if client is not None else self._build_client(api_key)

    @staticmethod
    def _build_client(api_key: str) -> Any:
        import anthropic  # local import: only a deployment running this adapter needs it

        return anthropic.Anthropic(api_key=api_key)

    async def estimate(
        self, session: AsyncSession, *, visit_or_procedure: str, region: Region
    ) -> _Estimate | None:
        entry = find_benchmark(visit_or_procedure, region)
        if entry is None:
            return None
        host = (urlparse(entry.url).hostname or "").lower()
        allowed = await usable_sources(session, region=region)
        if not any(host == source.domain or host.endswith("." + source.domain) for source in allowed):
            log.warning("claude cost estimator: %s is not on the allowlist for %s", host, region)
            return None
        try:
            response = self._client.messages.create(
                model="claude-opus-5",
                max_tokens=4096,
                tools=[{"type": "web_fetch_20260209", "name": "web_fetch"}],
                output_config={
                    "format": {"type": "json_schema", "json_schema": ESTIMATE_SCHEMA}
                },
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Fetch {entry.url}. From its own published text only, give the "
                            f"typical low and high fee for {visit_or_procedure.strip()!r} "
                            "in whole currency units, and the currency code. If the page does "
                            "not say, answer null for that field — never estimate one."
                        ),
                    }
                ],
            )
        except Exception:  # noqa: BLE001 — a failed call answers nothing, never a guess
            log.warning("claude cost estimator call failed for %r", visit_or_procedure)
            return None
        if getattr(response, "stop_reason", None) == "refusal":
            return None
        text = self._fetched_text(response)
        payload = self._structured_json(response)
        if payload is None:
            return None
        low = payload.get("low")
        high = payload.get("high")
        low_cents = int(low) * 100 if isinstance(low, int) and _numeral_in(low, text) else None
        high_cents = int(high) * 100 if isinstance(high, int) and _numeral_in(high, text) else None
        if low_cents is None and high_cents is None:
            return None
        return _Estimate(
            low_cents=low_cents,
            high_cents=high_cents,
            source=Source(publisher=entry.publisher, url=entry.url, fetched_at=now().date()),
        )

    @staticmethod
    def _structured_json(response: Any) -> dict[str, Any] | None:
        for block in getattr(response, "content", None) or []:
            piece = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
            if not piece:
                continue
            try:
                payload = json.loads(piece)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                return payload
        return None

    @staticmethod
    def _fetched_text(response: Any) -> str:
        """The fetched page's own text, from the tool's own result block — never the model's
        restated words (the same rule `app.delivery.feed.claude_adapters._fetch_document_text`
        already keeps)."""
        chunks: list[str] = []
        for block in getattr(response, "content", None) or []:
            block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if block_type != "web_fetch_tool_result":
                continue
            content = block.get("content") if isinstance(block, dict) else getattr(block, "content", None)
            document = content.get("content") if isinstance(content, dict) else getattr(content, "content", None)
            source = document.get("source") if isinstance(document, dict) else getattr(document, "source", None)
            data = source.get("data") if isinstance(source, dict) else getattr(source, "data", None)
            if isinstance(data, str):
                chunks.append(data)
        return "\n".join(chunks)


def estimator_for(settings: Settings) -> Estimator:
    """The estimator this deployment runs on: `NURA_ESTIMATOR`, `rule` by default."""
    name = settings.estimator
    if name == "rule":
        return RuleEstimator()
    if name == "claude":
        return ClaudeEstimator(
            api_key=settings.anthropic_api_key,
            demo_mode=settings.demo_mode,
            dev_run=settings.dev_code_sender,
        )
    raise NoEstimator(f"no cost estimator named {name!r} is built; set NURA_ESTIMATOR=rule or claude")


async def expect_cost(
    session: AsyncSession,
    context: KeyContext,
    visit_or_procedure: uuid.UUID,
    *,
    estimator: Estimator | None = None,
    procedure: str | None = None,
) -> CostExpectation:
    """The typical fee range and, where the caller may see it, what his cover on file would
    likely pay, for the visit named by `visit_or_procedure` (an `Appointment.id` — a booked
    visit or a planner-proposed one, both are ordinary appointments). `procedure` overrides
    the words matched against the benchmark table — a procedure a letter named, for the same
    visit — when it differs from the appointment's own `purpose`; the appointment itself is
    still the one gate every figure here is read under (module docstring), so a procedure
    named in a letter with no visit of its own is not yet reachable through this call — a
    known, deliberate gap for a later T3 story (see the PR body).
    """
    appointment_id = visit_or_procedure
    async with audited_guard(session, context, Action.READ, COST_SCOPE, Appointment.__tablename__):
        appointment = await require_appointment(session, context=context, appointment_id=appointment_id)
    profile = await audited_profile_read(session, context)
    lang = profile.language
    name = profile.display_name
    words = procedure if procedure is not None else appointment.purpose

    engine = estimator if estimator is not None else RuleEstimator()
    found = await engine.estimate(session, visit_or_procedure=words, region=context.region)

    region = context.region

    if found is None:
        return CostExpectation(
            appointment_id=appointment_id,
            found=False,
            low_cents=None,
            high_cents=None,
            low_said=None,
            high_said=None,
            currency=_currency(region),
            source=None,
            covered_shown=False,
            covered_low_cents=None,
            covered_high_cents=None,
            covered_low_said=None,
            covered_high_said=None,
            note=(
                Line(
                    "cost.no_benchmark_found",
                    render("cost.no_benchmark_found", lang),
                ),
                Line("cost.ask_the_clinic", render("cost.ask_the_clinic", lang)),
            ),
        )

    base_note = (
        Line("cost.typical_not_a_quote", render("cost.typical_not_a_quote", lang)),
        Line("cost.ask_the_clinic", render("cost.ask_the_clinic", lang)),
    )

    if not context.allows(POLICY_SCOPE):
        return CostExpectation(
            appointment_id=appointment_id,
            found=True,
            low_cents=found.low_cents,
            high_cents=found.high_cents,
            low_said=_said(found.low_cents, region),
            high_said=_said(found.high_cents, region),
            currency=_currency(region),
            source=found.source,
            covered_shown=False,
            covered_low_cents=None,
            covered_high_cents=None,
            covered_low_said=None,
            covered_high_said=None,
            note=base_note
            + (
                Line(
                    "cost.covered_needs_money_scope",
                    render("cost.covered_needs_money_scope", lang, name=name),
                ),
            ),
        )

    policies = await current_policies(session, context=context)
    active = [row for row in policies if row.status is PolicyStatus.ACTIVE]
    high_for_cover = found.high_cents if found.high_cents is not None else found.low_cents
    if active and high_for_cover is not None:
        covered_low_cents: int | None = 0
        covered_high_cents: int | None = high_for_cover
        cover_note = Line("cost.may_be_covered", render("cost.may_be_covered", lang, name=name))
    else:
        covered_low_cents = 0
        covered_high_cents = 0
        # The same line `app.insurance.relevance` already shows when no policy is on file —
        # rule 13 (docs/plain-words.md §13), the same words every time, not a near-duplicate.
        cover_note = Line(
            "insurance.no_cover_on_file", render("insurance.no_cover_on_file", lang, name=name)
        )

    return CostExpectation(
        appointment_id=appointment_id,
        found=True,
        low_cents=found.low_cents,
        high_cents=found.high_cents,
        low_said=_said(found.low_cents, region),
        high_said=_said(found.high_cents, region),
        currency=_currency(region),
        source=found.source,
        covered_shown=True,
        covered_low_cents=covered_low_cents,
        covered_high_cents=covered_high_cents,
        covered_low_said=_said(covered_low_cents, region),
        covered_high_said=_said(covered_high_cents, region),
        note=base_note + (cover_note,),
    )


def _currency(region: Region) -> str:
    return CURRENCY_BY_REGION[region]


def _said(cents: int | None, region: Region) -> str | None:
    if cents is None:
        return None
    return say_money(cents, region)
