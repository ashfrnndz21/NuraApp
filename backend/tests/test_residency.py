"""`app.llm.residency.allow_external_model`: the one gate every Claude-backed adapter's
construction site shares (ADR 0017, and its dev-run addendum). The per-adapter tests
(`test_claude_extractor.py`, `test_claude_feed_adapters.py`, `test_narrator.py`) each hold
this rule for their own construction site; this file holds the gate itself, once, so the rule
cannot drift between them.
"""

from __future__ import annotations

import logging

import pytest

from app.llm.residency import allow_external_model


class _Refused(RuntimeError):
    """A stand-in for a real adapter's own refusal type."""


def test_permits_silently_on_a_declared_demo(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        allow_external_model(demo_mode=True, dev_run=False, refusal=_Refused, what="the thing")
    assert caplog.records == []


def test_permits_and_logs_plainly_on_a_declared_dev_run(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        allow_external_model(demo_mode=False, dev_run=True, refusal=_Refused, what="the thing")
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "the thing" in message
    assert "outside the region" in message
    assert "owner's own" in message


def test_permits_on_both_demo_and_dev_run_together() -> None:
    # DemoAndDevTogether (app.settings) already keeps Settings from holding both at once;
    # this gate does not re-derive that rule, it only ORs the two flags it is given.
    allow_external_model(demo_mode=True, dev_run=True, refusal=_Refused, what="the thing")


def test_refuses_outside_both_demo_and_dev_run() -> None:
    with pytest.raises(_Refused, match="declared demo"):
        allow_external_model(demo_mode=False, dev_run=False, refusal=_Refused, what="the thing")


def test_the_refusal_names_what_it_refused() -> None:
    with pytest.raises(_Refused, match="the searcher"):
        allow_external_model(
            demo_mode=False, dev_run=False, refusal=_Refused, what="the searcher"
        )


def test_the_refusal_is_the_callers_own_exception_type() -> None:
    """`refusal` is never a residency-module type of its own: each adapter's construction
    site keeps its own exception, so an existing `except ClaudeExtractorOutsideDemo:` (or
    the narrator's, or the feed adapters') still catches what this gate raises."""

    class _AdapterOwnRefusal(RuntimeError):
        pass

    with pytest.raises(_AdapterOwnRefusal):
        allow_external_model(
            demo_mode=False, dev_run=False, refusal=_AdapterOwnRefusal, what="the thing"
        )


def test_the_gate_never_takes_or_logs_a_key(caplog: pytest.LogCaptureFixture) -> None:
    """The gate's signature has no `api_key` parameter at all — it cannot log what it is
    never given. A key stays local to each adapter's own `_checked_key`/`client_for`."""
    import inspect

    params = inspect.signature(allow_external_model).parameters
    assert "api_key" not in params
    assert "key" not in params

    with caplog.at_level(logging.WARNING):
        allow_external_model(demo_mode=False, dev_run=True, refusal=_Refused, what="the thing")
    for record in caplog.records:
        assert "sk-" not in record.getMessage()
