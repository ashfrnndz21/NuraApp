"""How many external model calls this process has made, by task and model — counts only.

The cost work this module belongs to (`app.llm.models`, the run cap in `app.delivery.feed.
background`) is meant to be checked, not just trusted: an operator watching a live feed run
should be able to say exactly how many calls it made, not estimate from a log line's prose.
Every Claude-backed adapter's own call site calls `record_call(task, model)` right where it
calls the SDK — never the request's content, never a token count, never anything that could
carry a person's data, only which task and which model, and how many times.

This is a plain in-process counter, the same posture `app.delivery.feed.background._runs`
already takes for a run's own state: never persisted, reset on restart, and wrong the moment
a second worker process exists — acceptable for the one-process deployment this build runs as
today (a laptop, a demo), and a line for the PR, not a migration, ahead of its clock running
out. `GET /dev/model-calls` (`app.channels.api.dev_model_calls`) reads it back, gated the same
way every other `/dev/*` door is: a declared dev run only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from app.llm.models import Task

_counts: Counter[tuple[Task, str]] = Counter()
"""(task, model id) -> how many times `record_call` has been told that call happened, this
process, since the last `reset()`."""


def record_call(task: Task, model: str) -> None:
    """Count one external model call. Called once per `messages.create`, right at the call
    site — never batched, never inferred from a response, so a call that itself raises or
    times out is still counted (it still reached Anthropic's API and, on the cost this module
    exists to watch, still cost something)."""
    _counts[(task, model)] += 1


def counts() -> Mapping[tuple[Task, str], int]:
    """A snapshot, task and model to count, for `GET /dev/model-calls` and for a run's own
    summary log line. Never mutated by the caller — a `dict`, not the live `Counter`."""
    return dict(_counts)


def total_calls() -> int:
    """Every call this process has made, across every task and model — the one number a run's
    summary log line leads with."""
    return sum(_counts.values())


def reset() -> None:
    """Zero the counter. Tests only — a real process never calls this; its count is its
    whole run's own history."""
    _counts.clear()
