"""The Claude-backed narrator (`NURA_NARRATOR=claude`): a model rephrases the trace's real
steps into a livelier spoken line, behind the same port (`app.search.narrate.Narrator`).
Nothing above this file, or `FixtureNarrator` beside it, changes — the answer itself stays the
rule-based retriever's, untouched; this only ever varies how a step that already happened is
said.

Demo only (ADR 0017). Anthropic's first-party API processes in the US or globally, never in
SG or MY, and no in-region provider exists yet. This adapter is a runtime feature that may
only run where every word it is shown is demo or test data: a declared demo
(`NURA_DEMO_MODE=1`). `narrator_for` (`app.search.narrator_provider`) refuses to build it
otherwise, and that refusal is the whole of this adapter's residency story. ADR 0008 (demo
mode) is not this adapter's residency authority, for the same reason it is not the document
extractor's (`app.ingestion.claude_extract`, whose module docstring this one mirrors): ADR
0017 is what actually admits a US-processing adapter, and only for these Claude-backed runtime
features, only under the demo declaration.

What is asked for is exactly one line per step it is given, as a JSON schema (`output_config`,
not the deprecated `output_format`): the step's id, unchanged, and a short spoken line for it.
`stop_reason` is checked before any content is read: `"refusal"` and `"max_tokens"` both fall
back to every step's own catalogue label, the honest "say it plainly" every other adapter's
failure case gives — a rephrasing that was declined or cut off is not shown half-said. A
response that does not parse as the schema asks falls back the same way.

Three more checks stand between the model's words and a person, because a model may only
rephrase, never invent or drift:

1. A line for a step id this call was not given is dropped — the model may not narrate a step
   that was never in its input, however plausible one sounds.
2. Every line is checked against `docs/plain-words.md`
   (`app.delivery.timeline_strings.verified`), the same check any other line spoken to him
   passes before it reaches him; a line that fails is replaced by that step's catalogue label.
3. A line meant for a caregiver's voice (a key that is not his own) is checked against the
   same "speaks to him" pattern the about-him twin test uses (`app.channels.about_him.
   Reader.speaks_to_him`): a rephrasing that says "you" or "your" to someone reading about the
   patient, not as the patient, is replaced by the catalogue label too, never sent as though a
   caregiver were the patient.

Never logged: the step's real content beyond what was already given (nothing sent to this
adapter carries a row to begin with), the prompt, or the model's answer. A log line here says
only that a call happened, and how it ended.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Final

from anthropic import AsyncAnthropic

from app.channels.about_him import Reader
from app.delivery.timeline_strings import verified
from app.llm.prompts import load_prompt
from app.search.narrate import NarratedLine, NarratedStep

log = logging.getLogger("nura.search.claude_narrate")

MODEL: Final = "claude-opus-5"
MAX_TOKENS: Final = 1024
"""Enough for a handful of one-sentence lines; a trace this build streams never has more than
a few real steps (E03-05's four, Find's one)."""

_LINE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["step", "text"],
    "properties": {
        "step": {"type": "string", "description": "The step id, exactly as it was given."},
        "text": {
            "type": "string",
            "description": "One short spoken line rephrasing that step, under twelve words, "
            "the same facts and the same voice as the step's own label.",
        },
    },
}

_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines"],
    "properties": {
        "lines": {
            "type": "array",
            "description": "One entry per step given, in the same order.",
            "items": _LINE_SCHEMA,
        },
    },
}

_SYSTEM_PROMPT: Final = load_prompt("narrate_steps")
"""`app/llm/prompts/narrate_steps.txt` (`backend/CLAUDE.md`: prompts are files, not strings
in code)."""


def _user_prompt(steps: Sequence[NarratedStep], *, language: str, reader: Reader) -> str:
    voice = (
        "You are narrating to the patient himself."
        if reader.his
        else f"You are narrating to a family member, about the patient, whose name is "
        f"{reader.name or 'the patient'}. Never say 'you' or 'your' to her about him."
    )
    lines = [voice, f"The reader's language is {language}.", "The steps, in order:"]
    for step in steps:
        detail = f'{{"step": "{step.key}", "label": {json.dumps(step.label)}'
        if step.count:
            detail += f', "count": {step.count}'
        detail += "}"
        lines.append(detail)
    return "\n".join(lines)


def _fallback(steps: Sequence[NarratedStep]) -> list[NarratedLine]:
    return [NarratedLine(key=step.key, text=step.label) for step in steps]


def _lines_from_payload(
    payload: Mapping[str, Any],
    steps: Sequence[NarratedStep],
    *,
    language: str,
    reader: Reader,
) -> list[NarratedLine]:
    given = {step.key: step for step in steps}
    by_key: dict[str, str] = {}
    raw = payload["lines"]
    if not isinstance(raw, list):
        raise TypeError("the model's answer did not give lines as a list")
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        step_id, text = entry.get("step"), entry.get("text")
        if not isinstance(step_id, str) or not isinstance(text, str):
            continue
        if step_id not in given:
            # The model may only rephrase the steps it was given; a step id it was not given
            # is dropped, never shown, however plausible it sounds.
            log.warning("claude narrator: dropped a line for a step id it was not given")
            continue
        text = text.strip()
        if not text or not verified(text, language):
            continue
        if not reader.his and reader.speaks_to_him(text):
            # A caregiver's line must never speak to him directly (about_him's own check).
            continue
        by_key[step_id] = text
    return [
        NarratedLine(key=step.key, text=by_key.get(step.key, step.label)) for step in steps
    ]


class ClaudeNarrator:
    """Rephrases a trace's real steps with Claude. See the module docstring for the residency,
    dropping and safety rules `narrator_for` and this class hold to."""

    external_processor: str | None = "anthropic"
    """Every call sends the given steps' ids, labels and counts to Anthropic's first-party
    API (see the module docstring): a caller writes the audit line a fixture narration never
    needs, the way `app.ingestion.review.review_artifact` does for the extractor."""

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def narrate(
        self, steps: Sequence[NarratedStep], *, language: str, reader: Reader
    ) -> AsyncIterator[NarratedLine]:
        if not steps:
            return
        message = await self._client.messages.create(  # type: ignore[call-overload]
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _user_prompt(steps, language=language, reader=reader)}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )

        if message.stop_reason == "refusal":
            log.info("claude narrator: the model refused to narrate; the catalogue said plainly")
            for line in _fallback(steps):
                yield line
            return
        if message.stop_reason == "max_tokens":
            log.warning("claude narrator: the model's answer was cut off at max_tokens")
            for line in _fallback(steps):
                yield line
            return

        try:
            text = message.content[0].text  # type: ignore[union-attr]
            payload = json.loads(text)
            if not isinstance(payload, Mapping):
                raise TypeError("the model's answer was not a JSON object")
            lines = _lines_from_payload(payload, steps, language=language, reader=reader)
        except (
            IndexError,
            AttributeError,
            TypeError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as malformed:
            log.warning(
                "claude narrator: the model's answer did not match the schema asked (%s: %s)",
                type(malformed).__name__,
                malformed,
            )
            lines = _fallback(steps)

        for line in lines:
            yield line
