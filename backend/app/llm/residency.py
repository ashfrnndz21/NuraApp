"""The one shared gate a Claude-backed *runtime* adapter refuses to build outside of.

`app.search.narrator_provider.narrator_for` and `app.ingestion.extract_provider.extractor_for`
each hold the same rule inline, with their own exception class: Anthropic's first-party API
does not process in SG or MY, and no in-region provider exists yet, so an adapter that reaches
it at runtime may only be built where every word or document it will be shown is demo or test
data — a declared demo, `NURA_DEMO_MODE=1` (ADR 0017; not ADR 0008, the demo declaration
itself, which does not reach to residency). `app.search.asker_provider.asker_for` is the first
caller of this shared form; a later widening of the gate to a declared dev run too is one
change here; not a matching one in every provider that duplicated the check inline before this
module existed.
"""

from __future__ import annotations

from app.settings import Settings


class ClaudeAdapterOutsideDemo(RuntimeError):
    """A Claude-backed runtime adapter was named outside a declared demo (`NURA_DEMO_MODE=1`):
    Anthropic's first-party API processes outside SG and MY, so it may only be built where
    every word it will be shown is demo or test data (ADR 0017)."""


def require_demo(settings: Settings, *, what: str, env_var: str) -> None:
    """Refuse unless this is a declared demo. `what` names the adapter in the message
    ("asker"); `env_var` names the setting that chose it (`NURA_ASKER`), so the refusal tells
    the operator exactly what to unset."""
    if not settings.demo_mode:
        raise ClaudeAdapterOutsideDemo(
            f"{env_var}=claude runs only on a declared demo (NURA_DEMO_MODE=1): Anthropic's "
            "first-party API does not process in SG or MY, no in-region provider exists yet, "
            f"and a demo is the only deployment where every word the {what} is shown is demo "
            f"or test data (ADR 0017). Use {env_var}=rule anywhere else."
        )
