"""Which providers are fixtures, and the one place that decides where they may run.

A fixture stands in for a provider Nura does not have yet — licensed drug data, a recogniser
for photos, speech, a model in the region, an SMS or WhatsApp provider. Each fixture class
is marked `@fixture`, and `create_app` calls `check_fixtures`: a process that is neither
a declared dev run (`NURA_DEV_CODE_SENDER=1`, a laptop) nor a declared demo
(`NURA_DEMO_MODE=1`, ADR 0008) refuses to start on any of them. `tests/test_fixture_refusals.py`
finds every class named `Fixture…` under `app/` and fails if one is not marked, so a
new fixture cannot slip past this check.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from app.settings import Settings

_FIXTURES: set[type[Any]] = set()


def fixture[C: type[Any]](cls: C) -> C:
    """Mark a class as a fixture provider. The mark is a registry here, not an attribute on
    the class, so a port's shape (what a calendar reader can do, say) is unchanged by it."""
    _FIXTURES.add(cls)
    return cls


def is_fixture_class(cls: type[Any]) -> bool:
    return cls in _FIXTURES


class FixtureOutsideDevOrDemo(RuntimeError):
    """A fixture provider was given to a process that is neither a dev run nor a demo."""


def is_fixture(provider: object) -> bool:
    return any(isinstance(provider, cls) for cls in _FIXTURES)


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
