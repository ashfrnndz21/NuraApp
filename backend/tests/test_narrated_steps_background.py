"""The narrator redesign (the live-run defect: "the narrator never shows" — Opus 5 routinely
answers slower than the old, synchronous `NARRATE_DEADLINE_S`, so every call hit the deadline
and the trace only ever said the catalogue's own label). `POST /{id}/ask/stream` and `POST
/{id}/find/stream` now send a `step` at once, with its catalogue label, and let a narrator's
own rephrasing arrive later as its own `step_label` event — never holding a step, a tool call
or the answer back for it (`app.channels.api.sse_pump.stream_with_background_pump`,
`app.search.narrate.narrate_step_label`).

Every test here hands the deployment a narrator test double, never the real Claude-backed
one — `tests/test_narrator.py` covers `ClaudeNarrator` and `narrate_step_label` in isolation,
with the `anthropic` client mocked; this file is the wiring those two do not reach: the route
itself, in order, over HTTP.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from app.channels.about_him import Reader
from app.search.narrate import NarratedLine, NarratedStep
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591190001"


@dataclass
class _RewordingNarrator:
    """Always has something different to say, after a short, real await — standing in for a
    `ClaudeNarrator` call that answers before its deadline. Never touches the network."""

    external_processor: str | None = None
    delay_s: float = 0.02

    async def narrate(
        self, steps: list[NarratedStep], *, language: str, reader: Reader
    ) -> Any:
        await asyncio.sleep(self.delay_s)
        for step in steps:
            yield NarratedLine(key=step.key, text=f"{step.label} (said livelier)")


@dataclass
class _EchoingNarrator:
    """Always falls back to the very label it was given, after a short, real await — standing
    in for every one of `ClaudeNarrator`'s own fallback cases (a timeout among them): there is
    nothing new to say."""

    external_processor: str | None = None
    delay_s: float = 0.02

    async def narrate(
        self, steps: list[NarratedStep], *, language: str, reader: Reader
    ) -> Any:
        await asyncio.sleep(self.delay_s)
        for step in steps:
            yield NarratedLine(key=step.key, text=step.label)


def _events(text: str) -> list[dict[str, object]]:
    return [json.loads(line.removeprefix("data: ")) for line in text.split("\n\n") if line.startswith("data: ")]


async def _ask_pa_about_his_blood_pressure(deployment: Deployment) -> list[dict[str, object]]:
    pa = await register_by_phone(deployment, PA, "Pa", language="en")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84, "taken_at": "2026-09-13T08:00:00+08:00"},
        headers=his,
    )
    streamed = await deployment.client.post(
        f"/profiles/{profile_id}/ask/stream",
        json={"question": "what was my blood pressure", "mode": "text"},
        headers=his,
    )
    assert streamed.status_code == 200
    return _events(streamed.text)


async def test_a_step_is_sent_at_once_and_its_rephrasing_follows_as_step_label(
    deployment_factory: Any,
) -> None:
    async with deployment_factory(narrator=_RewordingNarrator()) as deployment:
        events = await _ask_pa_about_his_blood_pressure(deployment)

    steps = [e for e in events if e["type"] == "step"]
    labels = [e for e in events if e["type"] == "step_label"]
    answers = [e for e in events if e["type"] == "answer"]
    assert steps  # the read still happened, and was still traced, unchanged
    assert labels  # and every one of them got a livelier follow-up
    assert {e["key"] for e in labels} <= {e["key"] for e in steps}
    # The answer itself was never held back for the narrator: it went out the moment the
    # rule-based asker had it, whether or not any `step_label` had resolved yet — a
    # `step_label` may legitimately still arrive after it, the connection staying open only
    # long enough to carry a still-running rephrasing (`ask_stream`'s own docstring).
    assert len(answers) == 1

    # Order, not timing: whichever step a `step_label` names, that step's own `step` event was
    # already on the wire before it — the redesign's whole point, and the one thing a client
    # actually depends on (`web/src/screens/Ask.tsx` replaces a step's label in place).
    for label_event in labels:
        key = label_event["key"]
        step_index = next(i for i, e in enumerate(events) if e["type"] == "step" and e["key"] == key)
        label_index = events.index(label_event)
        assert step_index < label_index
        step_event = next(e for e in events if e["type"] == "step" and e["key"] == key)
        assert label_event["label"] == f"{step_event['label']} (said livelier)"
        assert label_event["label"] != step_event["label"]


async def test_a_narrator_that_falls_back_sends_no_step_label_at_all(deployment_factory: Any) -> None:
    """The redesign's other half: when the narrator has nothing new to say — a timeout among
    the reasons, covered directly in `tests/test_narrator.py` — the reader is not shown a
    redundant update repeating the same words the step already carried."""
    async with deployment_factory(narrator=_EchoingNarrator()) as deployment:
        events = await _ask_pa_about_his_blood_pressure(deployment)

    assert any(e["type"] == "step" for e in events)
    assert not any(e["type"] == "step_label" for e in events)
    assert events[-1]["type"] == "answer"
