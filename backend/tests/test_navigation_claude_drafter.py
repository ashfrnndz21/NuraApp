"""The Claude-backed care-navigation drafter (T3): `ClaudeDrafter` may write the message
itself, never invent a dose or a diagnosis, and falls back to `RuleDrafter` whole on anything
it cannot trust. No live call: every test hands it a fake that answers in memory, in
`client.messages.create`'s exact shape (`anthropic`) — never a real API key, never a real
request.

`drafter_for` (`app.reasoning.navigation.drafter_provider`) is the other half:
`NURA_DRAFTER=claude` must refuse to build outside a declared demo or a declared dev run
(ADR 0017), mirroring `narrator_for`'s own refusal.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.llm.navigation_draft import ClaudeDrafter
from app.reasoning.navigation.drafter_provider import (
    ClaudeDrafterOutsideDemo,
    NoDrafter,
    drafter_for,
)
from app.reasoning.navigation.models import Need, NeedKind
from app.reasoning.navigation.rule_drafter import RuleDrafter
from app.regions import Region
from app.settings import MissingSetting, Settings

FOLLOW_UP_NEED = Need(
    id="follow_up:1",
    kind=NeedKind.FOLLOW_UP,
    evidence_kind="fact",
    evidence_id=uuid.uuid4(),
    provider_id=None,
    doctor="Dr Tan",
    when=None,
)


@dataclass
class _TextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[_TextBlock]
    stop_reason: str = "end_turn"


@dataclass
class _FakeMessages:
    answers: list[_FakeMessage]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        return self.answers.pop(0)


@dataclass
class _FakeClient:
    messages: _FakeMessages


def _client_answering(*payloads: dict[str, Any] | str, stop_reason: str = "end_turn") -> _FakeClient:
    answers = [
        _FakeMessage(
            content=[_TextBlock(text=p if isinstance(p, str) else json.dumps(p))],
            stop_reason=stop_reason,
        )
        for p in payloads
    ]
    return _FakeClient(messages=_FakeMessages(answers=answers))


async def _drafted(client: _FakeClient) -> str:
    drafter = ClaudeDrafter(client)  # type: ignore[arg-type]
    return await drafter.draft(
        need=FOLLOW_UP_NEED, language="en", patient_name="Pa", drafter_name=None, is_self=True
    )


async def test_a_safe_answer_is_used() -> None:
    answer = "Pa is writing this.\nCould we book a check-up, please?"
    client = _client_answering({"text": answer})
    text = await _drafted(client)
    assert text == answer


async def test_an_answer_naming_a_dose_falls_back_to_the_rule_draft() -> None:
    client = _client_answering({"text": "Pa needs to take 5 mg. Could we book a time, please?"})
    text = await _drafted(client)
    rule_text = await RuleDrafter().draft(
        need=FOLLOW_UP_NEED, language="en", patient_name="Pa", drafter_name=None, is_self=True
    )
    assert text == rule_text


async def test_an_answer_naming_a_condition_falls_back_to_the_rule_draft() -> None:
    client = _client_answering({"text": "Pa has diabetes and needs a check-up."})
    text = await _drafted(client)
    rule_text = await RuleDrafter().draft(
        need=FOLLOW_UP_NEED, language="en", patient_name="Pa", drafter_name=None, is_self=True
    )
    assert text == rule_text


async def test_a_refusal_falls_back_to_the_rule_draft() -> None:
    client = _client_answering({"text": "unused"}, stop_reason="refusal")
    text = await _drafted(client)
    rule_text = await RuleDrafter().draft(
        need=FOLLOW_UP_NEED, language="en", patient_name="Pa", drafter_name=None, is_self=True
    )
    assert text == rule_text


async def test_a_malformed_answer_falls_back_not_a_crash() -> None:
    client = _client_answering("not json at all")
    text = await _drafted(client)
    rule_text = await RuleDrafter().draft(
        need=FOLLOW_UP_NEED, language="en", patient_name="Pa", drafter_name=None, is_self=True
    )
    assert text == rule_text


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"region": Region.SG, "database_url": "sqlite+aiosqlite://"}
    base.update(overrides)
    return Settings(**base)


def test_the_default_drafter_is_the_rule_one() -> None:
    assert isinstance(drafter_for(_settings()), RuleDrafter)


def test_claude_refuses_to_build_outside_a_declared_demo_and_dev_run() -> None:
    with pytest.raises(ClaudeDrafterOutsideDemo):
        drafter_for(_settings(drafter="claude", anthropic_api_key="sk-test-not-real"))


def test_claude_builds_on_a_declared_dev_run() -> None:
    drafter = drafter_for(
        _settings(drafter="claude", dev_code_sender=True, anthropic_api_key="sk-test-not-real")
    )
    assert isinstance(drafter, ClaudeDrafter)


def test_claude_builds_on_a_declared_demo() -> None:
    drafter = drafter_for(
        _settings(
            drafter="claude",
            demo_mode=True,
            demo_login_code="123456",
            anthropic_api_key="sk-test-not-real",
        )
    )
    assert isinstance(drafter, ClaudeDrafter)


def test_claude_refuses_to_build_without_a_key_even_on_a_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingSetting):
        drafter_for(_settings(drafter="claude", demo_mode=True, demo_login_code="123456"))


def test_an_unknown_drafter_name_refuses_to_start() -> None:
    with pytest.raises(NoDrafter):
        drafter_for(_settings(drafter="chatty-3000"))
