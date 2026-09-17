"""The one place `AsyncAnthropic` is constructed (`backend/CLAUDE.md`: model calls go through
`app/llm/`). Every Claude-backed adapter calls `client_for`, never the SDK directly, so a
region-pinned provider arriving later is a new function here, not a new caller elsewhere.
"""

from __future__ import annotations

import os

from anthropic import AsyncAnthropic

from app.settings import MissingSetting, Settings


def client_for(settings: Settings) -> AsyncAnthropic:
    """The Anthropic client a Claude-backed adapter calls with.

    `NURA_ANTHROPIC_API_KEY` from the platform's secrets, never the repo. Unset, the SDK
    falls back to its own `ANTHROPIC_API_KEY` read from the environment if it is there; with
    neither set, this refuses before the client is ever built rather than let the SDK fail
    on the first call."""
    if settings.anthropic_api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingSetting(
            "NURA_EXTRACTOR=claude needs NURA_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) "
            "set; from the platform's secrets, never the repo"
        )
    return AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=60.0)
