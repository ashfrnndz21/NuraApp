"""The production image installs pinned versions, and pins every runtime dependency.

`backend/requirements.lock` is what the Dockerfile installs (`--no-deps`, then `pip check`,
which fails the image build if a dependency of a dependency is missing). This keeps it honest
the other way: a runtime dependency added to pyproject.toml and not pinned fails here.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^([a-z0-9][a-z0-9._-]*)==([0-9][0-9a-z.+!-]*)$")


def _name(requirement: str) -> str:
    return re.split(r"[\[<>=!~; ]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in (BACKEND / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        found = PIN.match(line.strip())
        assert found, f"not an exact pin: {line!r}"
        pins[found.group(1)] = found.group(2)
    return pins


def test_every_line_is_one_exact_pin() -> None:
    assert _pins()


def test_every_runtime_dependency_is_pinned() -> None:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pinned = _pins()
    for requirement in project["dependencies"]:
        assert _name(requirement) in pinned, f"{requirement} is not pinned in requirements.lock"


def test_an_exact_pin_in_pyproject_is_the_version_the_image_installs() -> None:
    # FastAPI, Starlette and SQLAlchemy are pinned exactly in pyproject.toml (PR #120): the
    # image must run the version the suite ran, not whatever the lock drifted to.
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pinned = _pins()
    for requirement in project["dependencies"]:
        exact = re.search(r"==\s*([0-9][0-9a-z.+!-]*)", requirement)
        if exact:
            assert pinned[_name(requirement)] == exact.group(1), requirement


def test_the_test_only_driver_is_not_shipped() -> None:
    # aiosqlite is how the tests run SQLite; a deployment runs Postgres through asyncpg.
    assert "aiosqlite" not in _pins() and "asyncpg" in _pins()
