"""Which registry a deployment runs on.

There is no licensed registry wired yet. A deployment that names `fixture` — the dev run, the
tests — gets the fixture; one that names anything else refuses to start rather than start on
a registry that is not what it says. When a licensed client arrives it is a second class
behind the same port, chosen here, and nothing above this module changes.
"""

from __future__ import annotations

from app.drugs.fixture import FixtureRegistry
from app.drugs.registry import DrugRegistry
from app.settings import Settings

FIXTURE = "fixture"


class NoDrugRegistry(RuntimeError):
    """The deployment names a drug registry this build does not have."""


def drug_registry_for(settings: Settings) -> DrugRegistry:
    if settings.drug_registry == FIXTURE:
        return FixtureRegistry.load()
    raise NoDrugRegistry(
        f"no drug registry named {settings.drug_registry!r}; only {FIXTURE!r} is built. "
        "Set NURA_DRUG_REGISTRY=fixture for a local run"
    )
