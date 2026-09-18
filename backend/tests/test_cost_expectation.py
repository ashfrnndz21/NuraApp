"""T3, cost expectation: a typical fee range from a public fee benchmark, cited and dated,
never a quote; what his cover on file would likely pay, always a range, never invented; and
the honest line when nothing was found. `Scope.VISITS` gates the range itself, the same door
a visit's brief already sits behind; `Scope.MONEY` gates the covered part on top of it, named
and never silent for a key without it (the owner's decision, `app.insurance.relevance`)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import now
from app.delivery.feed.sources import ensure_sources
from app.insurance.cost_expectation import (
    ClaudeEstimator,
    RuleEstimator,
    expect_cost,
)
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.regions import Region
from app.safety.plain_words import verify
from tests.safety_support import clinic, let_in, pa
from tests.test_insurance_policy import _write as write_policy
from tests.timeline_support import book


def assert_plain(lines: list[str], language: str) -> None:
    for line in lines:
        failures = [f for f in verify(line, language, "line") if f.severity == "fail"]
        assert not failures, (line, failures)


async def test_a_typical_range_is_cited_from_the_table(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150001")
    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, now(), "cardiology follow-up")

    shown = await expect_cost(sg, owner, visit.id)

    assert shown.found is True
    assert shown.low_cents == 3800
    assert shown.high_cents == 21500
    assert shown.low_said == "S$38"
    assert shown.high_said == "S$215"
    assert shown.currency == "S$"
    assert shown.source is not None
    assert shown.source.publisher == "Ministry of Health Singapore"
    assert shown.source.url.startswith("https://www.moh.gov.sg/")
    ids = [line.id for line in shown.note]
    assert "cost.typical_not_a_quote" in ids
    assert "cost.ask_the_clinic" in ids
    assert_plain([line.text for line in shown.note], "en")


async def test_no_active_policy_gives_a_zero_to_zero_covered_range(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150002")
    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")

    shown = await expect_cost(sg, owner, visit.id)

    assert shown.covered_shown is True
    assert shown.covered_low_cents == 0
    assert shown.covered_high_cents == 0
    assert any("no insurance" in line.text.lower() for line in shown.note)


async def test_an_active_policy_reaches_the_benchmarks_high_never_a_made_up_midpoint(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591150003")
    tan = await clinic(sg, owner)
    await write_policy(sg, owner, insurer_name="Great Eastern")
    visit = await book(sg, owner, tan, now(), "check-up")

    shown = await expect_cost(sg, owner, visit.id)

    assert shown.covered_shown is True
    assert shown.covered_low_cents == 0
    assert shown.covered_high_cents == shown.high_cents
    joined = " ".join(line.text for line in shown.note)
    assert "Great Eastern" not in joined  # the note never re-says the insurer's name
    assert "may pay" in joined.lower()


async def test_a_key_without_money_scope_sees_the_range_but_not_the_covered_part(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591150004")
    tan = await clinic(sg, owner)
    await write_policy(sg, owner, insurer_name="Great Eastern")
    visit = await book(sg, owner, tan, now(), "check-up")
    caregiver = await let_in(sg, owner, phone="+6594440014", name="Lin", role=KeyRole.CAREGIVER)

    shown = await expect_cost(sg, caregiver, visit.id)

    assert shown.found is True  # the typical range itself is not money
    assert shown.low_cents is not None and shown.high_cents is not None
    assert shown.covered_shown is False
    assert shown.covered_low_cents is None
    assert shown.covered_high_cents is None
    joined = " ".join(line.text for line in shown.note)
    assert "insurance" in joined.lower()  # named, never a silent blank
    assert "Great Eastern" not in joined


async def test_a_key_that_cannot_see_the_visit_at_all_is_refused(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150005")
    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    helper = await let_in(sg, owner, phone="+6593330015", name="Kit", role=KeyRole.HELPER)

    with pytest.raises(OutOfScope) as failed:
        await expect_cost(sg, helper, visit.id)
    assert failed.value.scope is Scope.VISITS


async def test_no_benchmark_found_says_so_plainly(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150006")
    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, now(), "a chat about his garden")

    shown = await expect_cost(sg, owner, visit.id)

    assert shown.found is False
    assert shown.low_cents is None
    assert shown.high_cents is None
    assert shown.source is None
    assert shown.covered_shown is False
    ids = [line.id for line in shown.note]
    assert "cost.no_benchmark_found" in ids
    assert "cost.ask_the_clinic" in ids


async def test_malaysia_uses_its_own_benchmark_and_currency(my: AsyncSession) -> None:
    owner = await pa(my, region=Region.MY, phone="+60122200011")
    tan = await clinic(my, owner)
    visit = await book(my, owner, tan, now(), "check-up")

    shown = await expect_cost(my, owner, visit.id)

    assert shown.found is True
    assert shown.currency == "RM"
    assert shown.source is not None
    assert shown.source.publisher == "Ministry of Health Malaysia"
    assert shown.source.url.startswith("https://www.moh.gov.my/")
    assert (shown.low_cents, shown.high_cents) != (3800, 21500)  # not the Singapore figures


async def test_every_line_passes_plain_words_in_every_language(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591150007", language="ms")
    tan = await clinic(sg, owner)
    await write_policy(sg, owner, insurer_name="Great Eastern")
    visit = await book(sg, owner, tan, now(), "check-up")
    shown = await expect_cost(sg, owner, visit.id)
    assert_plain([line.text for line in shown.note], "ms")


class _FakeMessages:
    def __init__(self, response: object) -> None:
        self._response = response

    def create(self, **_kwargs: object) -> object:
        return self._response


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.messages = _FakeMessages(response)


class _FakeResponse:
    def __init__(self, *, stop_reason: str | None, content: list[dict]) -> None:
        self.stop_reason = stop_reason
        self.content = content


def _fetch_result(url: str, text: str) -> dict:
    return {
        "type": "web_fetch_tool_result",
        "content": {"url": url, "content": {"source": {"type": "text", "data": text}}},
    }


def _text_block(payload: dict) -> dict:
    return {"type": "text", "text": json.dumps(payload)}


async def test_claude_estimator_drops_a_number_absent_from_the_fetched_text(
    sg: AsyncSession,
) -> None:
    await ensure_sources(sg)
    url = "https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks"
    # The page itself only ever says $38 — never $250, which the model wrote anyway.
    response = _FakeResponse(
        stop_reason="end_turn",
        content=[
            _fetch_result(url, "Typical consultation fees start from about $38."),
            _text_block({"low": 38, "high": 250, "currency": "SGD"}),
        ],
    )
    estimator = ClaudeEstimator(
        api_key="test-key", demo_mode=True, client=_FakeClient(response)
    )

    found = await estimator.estimate(sg, visit_or_procedure="follow-up consult", region=Region.SG)

    assert found is not None
    assert found.low_cents == 3800  # $38, present on the page
    assert found.high_cents is None  # $250 was never on the page: dropped, never guessed


async def test_claude_estimator_finds_nothing_when_no_number_is_on_the_page(
    sg: AsyncSession,
) -> None:
    await ensure_sources(sg)
    url = "https://www.moh.gov.sg/cost-financing/healthcare-schemes-subsidies/fee-benchmarks"
    response = _FakeResponse(
        stop_reason="end_turn",
        content=[
            _fetch_result(url, "The schedule is being updated."),
            _text_block({"low": 38, "high": 215, "currency": "SGD"}),
        ],
    )
    estimator = ClaudeEstimator(
        api_key="test-key", demo_mode=True, client=_FakeClient(response)
    )

    found = await estimator.estimate(sg, visit_or_procedure="follow-up consult", region=Region.SG)

    assert found is None


async def test_the_default_estimator_is_the_rule_table() -> None:
    assert isinstance(RuleEstimator(), RuleEstimator)
