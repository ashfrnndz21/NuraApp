"""The Claude-backed narrator (`NURA_NARRATOR=claude`): a model rephrases the trace's real
steps into a livelier spoken line, behind the port `app.search.narrate.Narrator`. Nothing in
that port module, or `FixtureNarrator` there, changes — the answer itself stays the
rule-based retriever's, untouched; this only ever varies how a step that already happened is
said.

Lives here, not beside the port: `backend/CLAUDE.md` says model calls go through `app/llm/`,
and `tests/test_recall.py::test_recall_calls_no_model` enforces it the same way for the
retriever's own port module — nothing under `app/search/` may import the SDK or the network,
so the port and its fixture stay in `app.search.narrate` and this adapter lives beside
`app/llm/client.py` instead. `narrator_provider.py` (`app.search.narrator_provider`, itself
under `app/search/` because it only selects between adapters and never calls out) imports
`ClaudeNarrator` from here.

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

Checks stand between the model's words and a person, because a model may only rephrase, never
invent or drift — and "reads only" is enforced here in code, not left to the prompt's own
asking:

1. A line for a step id this call was not given is dropped — the model may not narrate a step
   that was never in its input, however plausible one sounds.
2. A line must name the step's own object — the same bare noun its catalogue label uses for
   what was looked at (`ASK_STEP_NAMES`, or `_FIND_STEP_NAMES` for Find's two) — any number it
   does choose to state must agree with the step's own count, when it has one; and it must
   carry none of `_CONCLUSION_WORDS`, the conclusion-or-advice words the prompt already asks
   it to avoid. Together these are the code gate: a line that only opens a part of the record
   still mentions what was opened, never states a count other than the real one, and a line
   that instead says what something means, or what to do, always trips the blocklist. Any
   failure falls back to the catalogue label.
3. Every line is checked against `docs/plain-words.md`
   (`app.delivery.timeline_strings.verified`), the same check any other line spoken to him
   passes before it reaches him; a line that fails is replaced by that step's catalogue label.
4. A line meant for a caregiver's voice (a key that is not his own) is checked against the
   same "speaks to him" pattern the about-him twin test uses (`app.channels.about_him.
   Reader.speaks_to_him`): a rephrasing that says "you" or "your" to someone reading about the
   patient, not as the patient, is replaced by the catalogue label too, never sent as though a
   caregiver were the patient. And it must name him — `reader.name` — rather than lean on a
   bare pronoun (`_PRONOUN_ABOUT_HIM`): "his" or "him" is exactly the word a rephrase could
   have gotten wrong, where his own name cannot be.

Never logged: the step's real content beyond what was already given (nothing sent to this
adapter carries a row to begin with), the prompt, or the model's answer. A log line here says
only that a call happened, and how it ended.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Final

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
)

from app.channels.about_him import Reader
from app.delivery.timeline_strings import ASK_STEP_NAMES, verified
from app.llm.blocks import answer_text
from app.llm.prompts import load_prompt
from app.search.narrate import NarratedLine, NarratedStep

log = logging.getLogger("nura.search.claude_narrate")

MODEL: Final = "claude-opus-5"
MAX_TOKENS: Final = 1024
"""Enough for a handful of one-sentence lines; a trace this build streams never has more than
a few real steps (E03-05's four, Find's one)."""

NARRATE_DEADLINE_S: Final = 10.0
"""A step already happened before this call starts (the module docstring: this only ever
varies how it is said), and the step's own SSE event goes out at once, with its catalogue
label, before this call is even started — never after it (`app.search.narrate.
narrate_step_label`, awaited in the background by `app.channels.api.timeline.ask_stream` and
`app.delivery.feed.find.find_stream`'s route). Opus 5 typically answers in two to six
seconds; a deadline of 1.5s meant it hit this every time and the narrator was never actually
heard. Ten seconds gives it room to answer for real while still bounding how long a
`step_label` follow-up can arrive after its step — and it can never block a real step, a
tool call or the answer, however long it takes: anything slower than it, and any timeout,
connection failure or non-2xx status the SDK itself raises, falls back to the catalogue
label the same way a refusal does, and a caller listening for a follow-up simply never gets
one."""

_FIND_STEP_NAMES: Final[dict[str, dict[str, str]]] = {
    "en": {"web": "online", "videos": "videos"},
    "ms": {"web": "web", "videos": "video"},
    "zh": {"web": "网上", "videos": "视频"},
}
"""The bare noun each of Find's two steps' own label uses for what was looked at
(`app.delivery.strings.FIND_STEPS`) — Find's own twin of `app.delivery.timeline_strings.
ASK_STEP_NAMES`, which only names Ask's four."""

_CONCLUSION_WORDS: Final[dict[str, tuple[str, ...]]] = {
    "en": (
        "looks",
        "seems",
        "should",
        "must",
        "high",
        "low",
        "normal",
        "fine",
        "worse",
        "better",
        "risk",
        "danger",
        "safe",
    ),
    "ms": (
        "nampak",
        "kelihatan",
        "patut",
        "sepatutnya",
        "mesti",
        "tinggi",
        "rendah",
        "normal",
        "elok",
        "lebih teruk",
        "lebih baik",
        "risiko",
        "bahaya",
        "selamat",
    ),
    "zh": (
        "看起来",
        "似乎",
        "应该",
        "必须",
        "高",
        "低",
        "正常",
        "没事",
        "更差",
        "更好",
        "风险",
        "危险",
        "安全",
    ),
}
"""A rephrase may only say a part of the record was opened and how much was there, never what
it means (the prompt's own words, `app/llm/prompts/narrate_steps.txt`). The prompt asks for
that; this is the code gate that does not trust it was heard — a line carrying any of these,
in the reader's own language, is a conclusion or advice, not an opening, and falls back to the
catalogue label whatever else it got right."""

_PRONOUN_ABOUT_HIM: Final[dict[str, re.Pattern[str]]] = {
    "en": re.compile(r"\b(his|him|her|hers)\b", re.IGNORECASE),
    "ms": re.compile(r"\b(dia|nya)\b", re.IGNORECASE),
    "zh": re.compile(r"[他她]"),
}
"""A bare third-person pronoun standing in for the patient, in each language — never enough
on a caregiver's line; she reads about him by his name (`about_him.py`'s own module
docstring), not by a pronoun a rephrase could just as easily have gotten wrong."""

_LINE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["step", "text"],
    "properties": {
        "step": {"type": "string", "description": "The step id, exactly as it was given."},
        "text": {
            "type": "string",
            "description": "One short spoken line rephrasing that step, under ten words, "
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


def _object_noun(step: NarratedStep, language: str) -> str | None:
    """The bare noun the step's own catalogue label uses for what was looked at, or None for
    a step id neither table knows — in which case there is nothing to check a line against,
    so it can never pass (a) below."""
    return ASK_STEP_NAMES.get(language, {}).get(step.key) or _FIND_STEP_NAMES.get(
        language, {}
    ).get(step.key)


def _mentions_object(text: str, noun: str, language: str) -> bool:
    if language == "zh":
        return noun in text
    return noun.lower() in text.lower()


def _carries_same_count(text: str, step: NarratedStep) -> bool:
    """Whether any number `text` states agrees with the step's own count, when it has one (a
    count of 0 means the step never had one, `NarratedStep.count`'s own docstring). The
    catalogue label itself never states a count in words — this never requires a rephrase to
    invent one either, only that a number it does choose to say is the real one, not a
    drifted or invented one."""
    if not step.count:
        return True
    return all(int(found) == step.count for found in re.findall(r"\d+", text))


def _has_conclusion_language(text: str, language: str) -> bool:
    words = _CONCLUSION_WORDS.get(language, ())
    if language == "zh":
        return any(word in text for word in words)
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words)


def _caregiver_names_not_pronouns(text: str, reader: Reader, language: str) -> bool:
    """A caregiver's line must name him, not lean on a bare pronoun a rephrase could have
    gotten wrong. Always true on his own key, where there is no one else's voice to get."""
    if reader.his:
        return True
    if not reader.name or reader.name not in text:
        return False
    pronoun = _PRONOUN_ABOUT_HIM.get(language)
    return pronoun is None or not pronoun.search(text)


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
        step = given.get(step_id)
        if step is None:
            # The model may only rephrase the steps it was given; a step id it was not given
            # is dropped, never shown, however plausible it sounds.
            log.warning("claude narrator: dropped a line for a step id it was not given")
            continue
        text = text.strip()
        if not text or not verified(text, language):
            continue
        noun = _object_noun(step, language)
        if noun is None or not _mentions_object(text, noun, language):
            # "Reads only" enforced in code, not left to the prompt alone: a line that does
            # not name what was actually looked at is not trusted as a rephrase of it.
            continue
        if not _carries_same_count(text, step):
            continue
        if _has_conclusion_language(text, language):
            # A finding or advice, not an opening — whatever else the line got right.
            continue
        if not reader.his and reader.speaks_to_him(text):
            # A caregiver's line must never speak to him directly (about_him's own check).
            continue
        if not _caregiver_names_not_pronouns(text, reader, language):
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
        try:
            message = await asyncio.wait_for(
                self._client.messages.create(  # type: ignore[call-overload]
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=_SYSTEM_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": _user_prompt(steps, language=language, reader=reader),
                        }
                    ],
                    output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
                ),
                timeout=NARRATE_DEADLINE_S,
            )
        except (
            TimeoutError,  # covers asyncio.TimeoutError too (an alias of it since 3.11)
            APITimeoutError,
            APIConnectionError,
            APIStatusError,
        ) as unreachable:
            # A real step is never held back for this: too slow, unreachable or refused by
            # the transport all say it plainly instead, the same fixture fallback a refusal
            # or a truncated answer already falls back to below.
            log.warning(
                "claude narrator: the call did not answer in time (%s); the catalogue said "
                "plainly",
                type(unreachable).__name__,
            )
            for line in _fallback(steps):
                yield line
            return

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
            text = answer_text(message)
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
