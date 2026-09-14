"""Which providers are fixtures, and the one place that decides where they may run.

A fixture stands in for a provider Nura does not have yet — licensed drug data, a recogniser
for photos, speech, a model in the region, an SMS or WhatsApp provider. Each fixture class
says so (`FIXTURE = True`), and `create_app` calls `check_fixtures`: a process that is neither
a declared dev run (`NURA_DEV_CODE_SENDER=1`, a laptop) nor a declared demo
(`NURA_DEMO_MODE=1`, ADR 0008) refuses to start on any of them. `tests/test_fixture_refusals.py`
finds every class named `Fixture…` under `app/` and fails if one does not carry the mark, so a
new fixture cannot slip past this check.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from app.settings import Settings


class FixtureOutsideDevOrDemo(RuntimeError):
    """A fixture provider was given to a process that is neither a dev run nor a demo."""


def is_fixture(provider: object) -> bool:
    return getattr(type(provider), "FIXTURE", False) is True


def fixtures_in(providers: Any) -> list[str]:
    """The names of the providers that are fixtures, in the order `Providers` declares them."""
    return [f.name for f in fields(providers) if is_fixture(getattr(providers, f.name))]


def check_fixtures(settings: Settings, providers: Any) -> None:
    if settings.fixtures_allowed:
        return
    found = fixtures_in(providers)
    if found:
        raise FixtureOutsideDevOrDemo(
            f"fixture providers ({', '.join(found)}) run only on a declared dev run "
            "(NURA_DEV_CODE_SENDER=1) or demo (NURA_DEMO_MODE=1); configure the real ones"
        )
