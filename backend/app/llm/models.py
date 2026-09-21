"""The one place a task is mapped to the model id that answers it.

Every Claude-backed adapter used to write its own model id as a literal (`MODEL = "claude-
opus-5"`), and every one of them defaulted to the most expensive model whether the task
needed it or not — one live feed run made about 48 Opus calls with web search and produced
one card, and drained two credit top-ups. `CLAUDE.md` forbids hard-coding a provider or a
model in a caller; this module is what makes that true for models the way `app.llm.client.
client_for` already is for the SDK client itself.

`Task` names what the call is *for*, never which model answers it — a caller asks `TABLE.
for_task(Task.SEARCH)` (via `Settings.models`, resolved once at startup) and never writes a
model id itself. `DEFAULT_MODELS` picks the cheapest model that still keeps the behaviour the
task needs:

- `claude-opus-5` (dearest): reading a paper (`Task.EXTRACT`) and Ask (`Task.ASK`) — quality
  and safety matter most on both: a misread field or a wrong answer reaches a family directly.
- `claude-sonnet-5`: the Health Analyst (`Task.ANALYST`, replacing the older `claude-
  sonnet-4-5`), the feed searcher (`Task.SEARCH` — it calls the server tools `web_search_
  20260209`/`web_fetch_20260209`, which Sonnet 5 supports and Haiku 4.5 does not; do not move
  the searcher to Haiku), the cost estimator (`Task.ESTIMATE`) and the navigation drafter
  (`Task.DRAFT`).
- `claude-haiku-4-5-20251001` (cheapest): the feed compressor (`Task.COMPRESS`), the clip
  maker's script step (`Task.CLIP`) and the narrator (`Task.NARRATE`) — short rewriting tasks
  over text Nura already has, not open-ended reasoning.

Each default is overridable per deployment, one environment variable per task (`_ENV_VAR`),
so a laptop or a demo can move a task to a different model without a code change. An id that
is not on `ALLOWED_MODELS` refuses to start (`UnknownModel`) rather than reach the API and
fail on the first call — the same "a deployment that cannot say X must not start" posture
`app.settings.MissingSetting` already holds every other setting to.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class Task(str, Enum):
    """What a Claude-backed call is for. Never a model id itself — see the module docstring."""

    EXTRACT = "extract"
    ASK = "ask"
    ANALYST = "analyst"
    SEARCH = "search"
    COMPRESS = "compress"
    CLIP = "clip"
    NARRATE = "narrate"
    DRAFT = "draft"
    ESTIMATE = "estimate"


OPUS_5 = "claude-opus-5"
SONNET_5 = "claude-sonnet-5"
HAIKU_4_5 = "claude-haiku-4-5-20251001"

ALLOWED_MODELS: frozenset[str] = frozenset({OPUS_5, SONNET_5, HAIKU_4_5})
"""The model ids this build actually knows how to call. `model_table_for` refuses to resolve
an id outside this set, from a default or from an override alike, so a typo'd env var or a
stale default is caught at startup, not on the adapter's first call."""

DEFAULT_MODELS: Mapping[Task, str] = {
    Task.EXTRACT: OPUS_5,
    Task.ASK: OPUS_5,
    Task.ANALYST: SONNET_5,
    Task.SEARCH: SONNET_5,
    Task.COMPRESS: HAIKU_4_5,
    Task.CLIP: HAIKU_4_5,
    Task.NARRATE: HAIKU_4_5,
    Task.DRAFT: SONNET_5,
    Task.ESTIMATE: SONNET_5,
}
"""The cheapest model that still keeps each task's behaviour — see the module docstring for
the reason behind each one."""

_ENV_VAR: Mapping[Task, str] = {
    Task.EXTRACT: "NURA_MODEL_EXTRACT",
    Task.ASK: "NURA_MODEL_ASK",
    Task.ANALYST: "NURA_MODEL_ANALYST",
    Task.SEARCH: "NURA_MODEL_SEARCH",
    Task.COMPRESS: "NURA_MODEL_COMPRESS",
    Task.CLIP: "NURA_MODEL_CLIP",
    Task.NARRATE: "NURA_MODEL_NARRATE",
    Task.DRAFT: "NURA_MODEL_DRAFT",
    Task.ESTIMATE: "NURA_MODEL_ESTIMATE",
}
"""The one environment variable that overrides each task's model. Read once, at startup
(`model_table_for`), never again from inside an adapter."""


class UnknownModel(RuntimeError):
    """An env override — or, if `DEFAULT_MODELS` is ever edited to a stale id, a default —
    names a model id outside `ALLOWED_MODELS`. A deployment that cannot name a model this
    build actually knows how to call must not start, the same `MissingSetting`-style refusal
    every other setting in `app.settings` is held to."""


@dataclass(frozen=True, slots=True)
class ModelTable:
    """task -> model id, resolved once at startup and passed down (`app.settings.Settings.
    models`) like every other setting. Never rebuilt inside a request; an adapter that wants a
    different model gets a new deployment, not a per-call lookup."""

    _by_task: Mapping[Task, str]

    def for_task(self, task: Task) -> str:
        return self._by_task[task]


def model_table_for(env: Mapping[str, str]) -> ModelTable:
    """`NURA_MODEL_<TASK>` overrides `DEFAULT_MODELS` per task, each checked against
    `ALLOWED_MODELS`. Unset, a task keeps its default. An id — default or override — outside
    the allow-list raises `UnknownModel` naming the task and the id, so a deployment refuses
    to start rather than let an adapter's first call fail on it.
    """
    resolved: dict[Task, str] = {}
    for task, default in DEFAULT_MODELS.items():
        var = _ENV_VAR[task]
        value = env.get(var) or default
        if value not in ALLOWED_MODELS:
            raise UnknownModel(
                f"{var}={value!r} names a model this build does not know how to call; "
                "allowed: " + ", ".join(sorted(ALLOWED_MODELS))
            )
        resolved[task] = value
    return ModelTable(resolved)
