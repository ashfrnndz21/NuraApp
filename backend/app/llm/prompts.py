"""Prompts as files, not strings in code (`backend/CLAUDE.md`): `load_prompt` reads one by
name from `app/llm/prompts/*.txt` and caches it, so a prompt can be read and reviewed on its
own, outside the adapter that asks the model with it.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_DIRECTORY = Path(__file__).resolve().parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    """The text of `app/llm/prompts/{name}.txt`, its trailing newline dropped."""
    return (_DIRECTORY / f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")
