"""Independent review of #309, round 2.

R-2: the advice-language check read the raw extractor value, and every later step strips what a
reader never sees — so one zero-width space walked a sentence past the check and he then read it
intact. R-1: the prompt told the model to stop at 12 items a list, the same number the app cuts
at, so "there may be more on the policy" could never be said in the real flow. R-6: a soft hyphen
and the Arabic letter mark are unseen too."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ingestion.review import _carries_advice_language
from app.insurance.policy import ESSENTIAL_LIST_CAP, _clean

PROMPT = Path(__file__).parents[1] / "app" / "llm" / "prompts" / "extract_document.txt"


@pytest.mark.parametrize("unseen", [chr(c) for c in (0x200B, 0xAD, 0x61C, 0x202E, 0xFEFF, 0x07)])
def test_an_unseen_character_never_walks_advice_past_the_check(unseen: str) -> None:
    plain = "You are covered up to S$150,000"
    assert _carries_advice_language(plain)
    assert _carries_advice_language(f"You a{unseen}re cov{unseen}ered up to S$150,000")


def test_a_printed_line_with_no_advice_in_it_is_still_not_flagged() -> None:
    assert not _carries_advice_language("Room and board at a panel hospital")


@pytest.mark.parametrize("unseen", [chr(c) for c in (0xAD, 0x61C, 0x200B)])
def test_what_is_stored_carries_no_unseen_character(unseen: str) -> None:
    assert _clean(f"Room{unseen} and board") == "Room and board"


def test_the_prompt_lets_the_model_give_more_than_the_app_shows_so_the_cut_can_be_said() -> None:
    [cap] = re.findall(r"up to (\d+) per list", PROMPT.read_text(encoding="utf-8"))
    assert int(cap) > ESSENTIAL_LIST_CAP
