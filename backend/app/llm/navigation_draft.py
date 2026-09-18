"""The Claude-backed care-navigation drafter (`NURA_DRAFTER=claude`): a model writes the
drafted message, behind the port `app.reasoning.navigation.models.Drafter` the rule-based
`RuleDrafter` already answers. Lives here, not beside the port, for the reason every other
Claude-backed adapter does (`backend/CLAUDE.md`: model calls go through `app/llm/`):
`app.reasoning.navigation.drafter_provider` (under `app/reasoning/`, so it only selects an
adapter and never calls out) imports `ClaudeDrafter` from here.

Demo only (ADR 0017): gated the same way every other Claude-backed adapter is,
`app.llm.residency.allow_external_model`, called once, at `drafter_provider.drafter_for`'s
construction site — never here.

The model is given only what `app.reasoning.navigation.needs.list_needs` already read: the
need's kind, who is writing, a name already on the record and a date, never a dose, never a
diagnosis (`_user_prompt` builds exactly that and nothing more) — so there is nothing for it
to leak that it was not first handed. Its own answer still passes every check the rule
drafter's does before it is trusted: `app.safety.plain_words.verify` (no failing finding) and
`app.reasoning.navigation.rule_drafter.names_dose_or_diagnosis` (neither). A refusal, a
timeout, an answer that does not parse, or one that fails either check falls back to
`RuleDrafter` whole — the same honest "say it plainly" every other Claude-backed adapter's
failure case gives, never a half-trusted rewrite."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any, Final

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
)

from app.llm.prompts import load_prompt
from app.reasoning.navigation.models import Need, NeedKind
from app.reasoning.navigation.rule_drafter import RuleDrafter, names_dose_or_diagnosis
from app.safety.plain_words import verify

log = logging.getLogger("nura.reasoning.claude_navigation_draft")

MODEL: Final = "claude-opus-5"
MAX_TOKENS: Final = 512
DRAFT_DEADLINE_S: Final = 10.0

_SYSTEM_PROMPT: Final = load_prompt("navigation_draft")

_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {
        "text": {
            "type": "string",
            "description": "Two to four short whole sentences, one to a line separated by "
            "a newline: who is writing, the plain need, and the ask, ending in a question.",
        }
    },
}


def _user_prompt(
    *, need: Need, language: str, patient_name: str, drafter_name: str | None, is_self: bool
) -> str:
    who = (
        f"The patient himself, {patient_name}."
        if is_self
        else f"{drafter_name or 'A family member'}, writing about {patient_name}, naming "
        "herself in the message."
    )
    lines = [
        who,
        f"Write in this language: {language}.",
        f"The kind of need: {need.kind.value}.",
    ]
    if need.doctor:
        lines.append(f"The doctor or place already on the record: {need.doctor}.")
    if need.when is not None:
        lines.append(f"The date already on the record: {need.when.isoformat()}.")
    if need.kind is NeedKind.HOME_CARE and need.category:
        lines.append(f"The kind of home care: {need.category}.")
    return "\n".join(lines)


class ClaudeDrafter:
    """Writes the drafted message with Claude; falls back to `RuleDrafter` on anything it
    cannot trust. See the module docstring for the residency and the safety checks."""

    external_processor: str | None = "anthropic"

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client
        self._fallback = RuleDrafter()

    async def draft(
        self,
        *,
        need: Need,
        language: str,
        patient_name: str,
        drafter_name: str | None,
        is_self: bool,
    ) -> str:
        prompt = _user_prompt(
            need=need,
            language=language,
            patient_name=patient_name,
            drafter_name=drafter_name,
            is_self=is_self,
        )
        try:
            message = await asyncio.wait_for(
                self._client.messages.create(  # type: ignore[call-overload]
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                    output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
                ),
                timeout=DRAFT_DEADLINE_S,
            )
        except (TimeoutError, APITimeoutError, APIConnectionError, APIStatusError) as problem:
            log.warning(
                "claude navigation drafter: the call did not answer in time (%s); the rule "
                "draft said it plainly",
                type(problem).__name__,
            )
            return await self._fallback.draft(
                need=need,
                language=language,
                patient_name=patient_name,
                drafter_name=drafter_name,
                is_self=is_self,
            )

        text = self._text_from(message, need=need, language=language)
        if text is not None:
            return text
        return await self._fallback.draft(
            need=need,
            language=language,
            patient_name=patient_name,
            drafter_name=drafter_name,
            is_self=is_self,
        )

    def _text_from(self, message: Any, *, need: Need, language: str) -> str | None:
        if message.stop_reason in ("refusal", "max_tokens"):
            log.info("claude navigation drafter: %s; the rule draft said it plainly", message.stop_reason)
            return None
        try:
            raw = message.content[0].text  # type: ignore[union-attr]
            payload = json.loads(raw)
            if not isinstance(payload, Mapping):
                raise TypeError("the model's answer was not a JSON object")
            text = payload["text"]
            if not isinstance(text, str) or not text.strip():
                raise TypeError("the model's answer carried no text")
        except (IndexError, AttributeError, TypeError, ValueError, KeyError, json.JSONDecodeError) as malformed:
            log.warning(
                "claude navigation drafter: the model's answer did not match the schema "
                "asked (%s: %s)",
                type(malformed).__name__,
                malformed,
            )
            return None
        text = text.strip()
        if any(finding.severity == "fail" for finding in verify(text, language, "line")):
            log.info("claude navigation drafter: the model's line failed plain-words")
            return None
        if names_dose_or_diagnosis(text) is not None:
            log.info("claude navigation drafter: the model's line named a dose or a diagnosis")
            return None
        return text
