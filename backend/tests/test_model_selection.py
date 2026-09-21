"""One task -> one model (`app.llm.models`), and the cost work built on it: every `*_for`
factory reads its own task's model from `Settings.models`, never a literal — CLAUDE.md forbids
hard-coding a provider or a model in a caller — and `app.llm.call_counter` counts what actually
called out, gated behind a dev-only route the same way `app.channels.api.dev_clock` already is.

The live incident this whole file is about: one feed run made about 48 Opus calls with web
search and produced one card, and drained two credit top-ups. This module is the cheaper-
model half of the fix; `tests/test_feed_background.py::
test_a_plan_bigger_than_the_run_cap_runs_only_the_first_n_and_defers_the_rest` is the run-cap
half.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.channels.api import dev_model_calls
from app.delivery.feed.claude_adapters import (
    ClaudeCompressor,
    ClaudeSearcher,
    compressor_for,
    searcher_for,
)
from app.ingestion.claude_extract import ClaudeExtractor
from app.ingestion.extract_provider import extractor_for
from app.insurance.cost_expectation import ClaudeEstimator, estimator_for
from app.llm import call_counter
from app.llm.ask_agent import ClaudeAsker
from app.llm.models import (
    ALLOWED_MODELS,
    DEFAULT_MODELS,
    HAIKU_4_5,
    OPUS_5,
    SONNET_5,
    Task,
    UnknownModel,
    model_table_for,
)
from app.llm.narrate import ClaudeNarrator
from app.llm.navigation_draft import ClaudeDrafter
from app.reasoning.analyst.claude_adapter import ClaudeAnalyst
from app.reasoning.analyst.provider import analyst_for
from app.reasoning.navigation.drafter_provider import drafter_for
from app.regions import Region
from app.search.asker_provider import asker_for
from app.settings import Settings

# ---------------------------------------------------------------------------
# app.llm.models: the table itself.
# ---------------------------------------------------------------------------


def test_every_task_has_a_default_on_the_allow_list() -> None:
    assert set(DEFAULT_MODELS) == set(Task)
    assert all(model in ALLOWED_MODELS for model in DEFAULT_MODELS.values())


def test_the_defaults_match_the_brief() -> None:
    """Opus 5 where quality and safety matter most; Sonnet 5 for the analyst, the searcher
    (its server tools need it), the estimator and the drafter; Haiku 4.5 for the short
    rewrites."""
    assert DEFAULT_MODELS[Task.EXTRACT] == OPUS_5
    assert DEFAULT_MODELS[Task.ASK] == OPUS_5
    assert DEFAULT_MODELS[Task.ANALYST] == SONNET_5
    assert DEFAULT_MODELS[Task.SEARCH] == SONNET_5
    assert DEFAULT_MODELS[Task.ESTIMATE] == SONNET_5
    assert DEFAULT_MODELS[Task.DRAFT] == SONNET_5
    assert DEFAULT_MODELS[Task.COMPRESS] == HAIKU_4_5
    assert DEFAULT_MODELS[Task.CLIP] == HAIKU_4_5
    assert DEFAULT_MODELS[Task.NARRATE] == HAIKU_4_5


def test_an_env_override_replaces_one_task_and_leaves_the_rest() -> None:
    table = model_table_for({"NURA_MODEL_EXTRACT": HAIKU_4_5})
    assert table.for_task(Task.EXTRACT) == HAIKU_4_5
    assert table.for_task(Task.ASK) == OPUS_5  # untouched


def test_an_unknown_model_id_refuses_to_resolve() -> None:
    with pytest.raises(UnknownModel, match="NURA_MODEL_ASK"):
        model_table_for({"NURA_MODEL_ASK": "gpt-5"})


def test_settings_reads_the_table_from_the_environment() -> None:
    settings = Settings(
        region=Region.SG,
        database_url="sqlite+aiosqlite://",
        models=model_table_for({"NURA_MODEL_COMPRESS": OPUS_5}),
    )
    assert settings.models.for_task(Task.COMPRESS) == OPUS_5
    assert settings.models.for_task(Task.SEARCH) == SONNET_5  # still the default


# ---------------------------------------------------------------------------
# Each *_for factory: the constructed adapter carries its own task's model.
# ---------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "region": Region.SG,
        "database_url": "sqlite+aiosqlite://",
        "demo_mode": True,
        "anthropic_api_key": "sk-test",
    }
    base.update(overrides)
    return Settings(**base)


def test_searcher_for_claude_uses_the_search_task_model() -> None:
    settings = _settings(searcher="claude", models=model_table_for({"NURA_MODEL_SEARCH": HAIKU_4_5}))
    searcher = searcher_for(settings)
    assert isinstance(searcher, ClaudeSearcher)
    assert searcher._model == HAIKU_4_5


def test_compressor_for_claude_uses_the_compress_task_model() -> None:
    settings = _settings(compressor="claude", models=model_table_for({"NURA_MODEL_COMPRESS": OPUS_5}))
    compressor = compressor_for(settings)
    assert isinstance(compressor, ClaudeCompressor)
    assert compressor._model == OPUS_5


def test_extractor_for_claude_uses_the_extract_task_model() -> None:
    settings = _settings(extractor="claude", models=model_table_for({"NURA_MODEL_EXTRACT": HAIKU_4_5}))
    extractor = extractor_for(settings)
    assert isinstance(extractor, ClaudeExtractor)
    assert extractor._model == HAIKU_4_5


def test_estimator_for_claude_uses_the_estimate_task_model() -> None:
    settings = _settings(estimator="claude", models=model_table_for({"NURA_MODEL_ESTIMATE": HAIKU_4_5}))
    estimator = estimator_for(settings)
    assert isinstance(estimator, ClaudeEstimator)
    assert estimator._model == HAIKU_4_5


def test_narrator_for_claude_uses_the_narrate_task_model() -> None:
    from app.search.narrator_provider import narrator_for

    settings = _settings(narrator="claude", models=model_table_for({"NURA_MODEL_NARRATE": OPUS_5}))
    narrator = narrator_for(settings)
    assert isinstance(narrator, ClaudeNarrator)
    assert narrator._model == OPUS_5


def test_drafter_for_claude_uses_the_draft_task_model() -> None:
    settings = _settings(drafter="claude", models=model_table_for({"NURA_MODEL_DRAFT": HAIKU_4_5}))
    drafter = drafter_for(settings)
    assert isinstance(drafter, ClaudeDrafter)
    assert drafter._model == HAIKU_4_5


def test_analyst_for_claude_uses_the_analyst_task_model() -> None:
    settings = _settings(analyst="claude", models=model_table_for({"NURA_MODEL_ANALYST": HAIKU_4_5}))
    analyst = analyst_for(settings)
    assert isinstance(analyst, ClaudeAnalyst)
    assert analyst._model == HAIKU_4_5


def test_asker_for_claude_uses_the_ask_task_model_and_its_own_searcher_the_search_one() -> None:
    """`asker_for` builds a `ClaudeSearcher` of its own for Ask's own tool use — each carries
    its own task's model, never the same one by accident."""
    settings = _settings(
        asker="claude",
        models=model_table_for({"NURA_MODEL_ASK": OPUS_5, "NURA_MODEL_SEARCH": HAIKU_4_5}),
    )
    asker = asker_for(settings)
    assert isinstance(asker, ClaudeAsker)
    assert asker._model == OPUS_5
    assert asker._searcher._model == HAIKU_4_5


# ---------------------------------------------------------------------------
# app.llm.call_counter: counts only, by task and model.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_call_counter() -> Any:
    call_counter.reset()
    yield
    call_counter.reset()


def test_record_call_counts_by_task_and_model() -> None:
    call_counter.record_call(Task.SEARCH, SONNET_5)
    call_counter.record_call(Task.SEARCH, SONNET_5)
    call_counter.record_call(Task.COMPRESS, HAIKU_4_5)

    counts = call_counter.counts()
    assert counts[(Task.SEARCH, SONNET_5)] == 2
    assert counts[(Task.COMPRESS, HAIKU_4_5)] == 1
    assert call_counter.total_calls() == 3


def test_reset_zeroes_the_counter() -> None:
    call_counter.record_call(Task.ASK, OPUS_5)
    call_counter.reset()
    assert call_counter.counts() == {}
    assert call_counter.total_calls() == 0


# ---------------------------------------------------------------------------
# GET /dev/model-calls: counts only, dev runs only.
# ---------------------------------------------------------------------------


def _model_calls_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.include_router(dev_model_calls.router)
    return app


async def test_there_is_no_model_calls_route_outside_a_dev_run() -> None:
    production = Settings(region=Region.SG, database_url="sqlite+aiosqlite://")
    async with AsyncClient(
        transport=ASGITransport(app=_model_calls_app(production)), base_url="http://nura.test"
    ) as http:
        assert (await http.get("/dev/model-calls")).status_code == 404


async def test_the_model_calls_route_reports_counts_only_on_a_dev_run() -> None:
    call_counter.record_call(Task.SEARCH, SONNET_5)
    call_counter.record_call(Task.SEARCH, SONNET_5)
    call_counter.record_call(Task.NARRATE, HAIKU_4_5)
    dev = Settings(region=Region.SG, database_url="sqlite+aiosqlite://", dev_code_sender=True)
    async with AsyncClient(
        transport=ASGITransport(app=_model_calls_app(dev)), base_url="http://nura.test"
    ) as http:
        out = await http.get("/dev/model-calls")
    assert out.status_code == 200
    body = out.json()
    assert body["total"] == 3
    lines = {(line["task"], line["model"]): line["calls"] for line in body["by_task_and_model"]}
    assert lines[("search", SONNET_5)] == 2
    assert lines[("narrate", HAIKU_4_5)] == 1
    # Counts only: no content, no token counts, nothing that could carry a person's data.
    assert "content" not in out.text and "tokens" not in out.text
