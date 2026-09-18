"""`app.llm.blocks.answer_text`: the answer's text by the block's type, never its position."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.blocks import NoTextInAnswer, answer_text


def _message(*blocks: object) -> SimpleNamespace:
    return SimpleNamespace(content=list(blocks))


def test_the_text_is_found_behind_a_thinking_block() -> None:
    thinking = SimpleNamespace(type="thinking", thinking="…")
    text = SimpleNamespace(type="text", text='{"ok": true}')
    assert answer_text(_message(thinking, text)) == '{"ok": true}'


def test_several_text_blocks_are_joined_in_order_and_other_blocks_passed_over() -> None:
    blocks = (
        {"type": "text", "text": '{"a":'},
        {"type": "server_tool_use", "name": "web_search"},
        {"type": "text", "text": " 1}"},
    )
    assert answer_text(_message(*blocks)) == '{"a": 1}'


@pytest.mark.parametrize("content", [[], None, [SimpleNamespace(type="thinking", thinking="…")]])
def test_no_text_block_at_all_is_said_not_crashed_on(content: object) -> None:
    with pytest.raises(NoTextInAnswer):
        answer_text(SimpleNamespace(content=content))
