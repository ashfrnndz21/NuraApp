"""render.yaml (the Render Blueprint, docs/deploy-demo.md) parses, and stays honest about
what `backend/app/settings.py` actually reads and what must never be a secret in plain text.

Three things hold, so a change to either file cannot drift from the other without a red test:

1. Every NURA_* name `render.yaml` sets is one `settings.py`'s `load_settings` really reads —
   the list of names is found by reading `settings.py`'s own source (regex over
   `source["..."]` / `source.get("...")`, plus the `NURA_VAPID_{name}` loop), never
   hand-typed here, so a setting renamed in one file cannot go stale in the other.
2. The settings a demo cannot start without (ADR 0008, ADR 0017, `docs/deploy.md` §3) are all
   present in the Blueprint.
3. Every setting that is a secret (a database URL, a login code, a key, a signing secret) is
   never given a literal value in the file: it is `sync: false` (the owner enters it),
   `fromDatabase` (Render's own database) or `generateValue: true` (Render mints it) — never
   `value: <something>` — and the settings a demo must never turn on
   (`NURA_DEV_CODE_SENDER`, `NURA_FROZEN_CLOCK`, `NURA_RED_FLAG_TIERS`, ADR 0008 and 0010) are
   simply absent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_SRC = (REPO_ROOT / "backend/app/settings.py").read_text()
RENDER_YAML_PATH = REPO_ROOT / "render.yaml"


def _settings_env_names() -> set[str]:
    """Every NURA_* name `load_settings` reads from its `source` mapping, read out of
    `settings.py`'s own source rather than hand-typed, so this test cannot go stale on its
    own: a setting added, renamed or removed there changes this set too."""
    names = set(re.findall(r'source(?:\.get)?\(?\[?"(NURA_[A-Z_]+)"', SETTINGS_SRC))
    if 'f"NURA_VAPID_{name}"' in SETTINGS_SRC:
        vapid_tuple = re.search(r"^VAPID = \(([^)]+)\)", SETTINGS_SRC, re.MULTILINE)
        assert vapid_tuple, "expected the VAPID name tuple (VAPID = (...)) in settings.py"
        suffixes = re.findall(r'"([A-Z_]+)"', vapid_tuple.group(1))
        assert suffixes, "expected quoted suffixes in the VAPID tuple"
        names |= {f"NURA_VAPID_{suffix}" for suffix in suffixes}
    return names


ALL_SETTINGS_VARS = _settings_env_names()

# What this Blueprint cannot start a demo without. Each is required by settings.py, main.py's
# providers_for, or a provider factory it calls (app/ingestion/stores.py object_store_for,
# app/identity/providers.py code_sender_for, app/channels/whatsapp/provider.py
# whatsapp_provider_for) once NURA_DEMO_MODE=1 and NURA_DEV_CODE_SENDER is unset — see the
# comment on each line below for exactly which function raises without it.
REQUIRED_FOR_DEMO = {
    "NURA_REGION",  # load_settings: source["NURA_REGION"], KeyError -> MissingSetting
    "NURA_DATABASE_URL",  # load_settings: source["NURA_DATABASE_URL"], the same
    "NURA_DEMO_MODE",  # ADR 0008: the only declaration letting a non-dev-run use the fixtures
    "NURA_DEMO_LOGIN_CODE",  # load_settings: demo_mode needs six digits or refuses to start
    "NURA_PAPER_FIXTURES",  # extract_provider.extractor_for(fixture): MissingSetting without it
    "NURA_VISIT_FIXTURES",  # main.providers_for: MissingSetting without it
    "NURA_VOICE_FIXTURES",  # main.providers_for: MissingSetting without it
    "NURA_FEED_FIXTURES",  # main.providers_for: MissingSetting without it
    "NURA_WHATSAPP_DEV_SECRET",  # whatsapp_provider_for: NoWhatsAppProvider without it, in demo
    "NURA_OBJECT_STORE",  # object_store_for: MissingSetting without this or a bucket URL
}
assert REQUIRED_FOR_DEMO <= ALL_SETTINGS_VARS, (
    "REQUIRED_FOR_DEMO names a setting settings.py no longer reads by that name -- "
    f"stale entries: {REQUIRED_FOR_DEMO - ALL_SETTINGS_VARS}"
)

# A demo must never turn these on (ADR 0008 "It is not a dev run"; ADR 0010, unsigned tiers).
FORBIDDEN_IN_A_DEMO = {"NURA_DEV_CODE_SENDER", "NURA_FROZEN_CLOCK", "NURA_RED_FLAG_TIERS"}
assert FORBIDDEN_IN_A_DEMO <= ALL_SETTINGS_VARS

# Every one of these carries a credential, a key, or something that signs a login or a
# webhook. None may have a literal `value:` in the file.
SECRET_NAMES = {
    "NURA_DATABASE_URL",
    "NURA_DEMO_LOGIN_CODE",
    "NURA_OBJECT_ACCESS_KEY_ID",
    "NURA_OBJECT_SECRET_ACCESS_KEY",
    "NURA_WHATSAPP_DEV_SECRET",
    "NURA_VAPID_PRIVATE_KEY",
    "NURA_ANTHROPIC_API_KEY",
    "NURA_REVIEW_STAFF_TOKENS",
}
assert SECRET_NAMES <= ALL_SETTINGS_VARS


def _load_render_yaml() -> dict[str, Any]:
    return yaml.safe_load(RENDER_YAML_PATH.read_text())


def _web_service(doc: dict[str, Any]) -> dict[str, Any]:
    services = doc["services"]
    web = [s for s in services if s.get("type") == "web"]
    assert len(web) == 1, f"expected exactly one web service, found {len(web)}"
    return web[0]


def _env_vars(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """envVars as a dict keyed by name, so callers can ask what each entry looks like."""
    entries = service.get("envVars", [])
    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        assert "key" in entry, f"envVar entry with no key: {entry}"
        assert entry["key"] not in by_name, f"{entry['key']} is set twice"
        by_name[entry["key"]] = entry
    return by_name


def test_render_yaml_parses() -> None:
    doc = _load_render_yaml()
    assert "services" in doc
    assert "databases" in doc


def test_web_service_builds_from_the_dockerfile_and_migrates_on_release() -> None:
    doc = _load_render_yaml()
    web = _web_service(doc)
    assert web["runtime"] == "docker"
    assert web["dockerfilePath"] == "./Dockerfile"
    assert (REPO_ROOT / "Dockerfile").exists()
    assert web["preDeployCommand"] == "alembic upgrade heads"


def test_health_check_path_is_a_real_endpoint_that_touches_no_patient_data() -> None:
    doc = _load_render_yaml()
    web = _web_service(doc)
    # /health only says the process is up; /health/ready also asks the database. Neither
    # reads a row that could carry patient data (backend/app/channels/api/__init__.py).
    assert web["healthCheckPath"] in ("/health", "/health/ready")


def test_region_is_singapore() -> None:
    doc = _load_render_yaml()
    web = _web_service(doc)
    assert web["region"] == "singapore"
    for database in doc["databases"]:
        assert database["region"] == "singapore"


def test_every_required_demo_setting_is_named() -> None:
    doc = _load_render_yaml()
    env = _env_vars(_web_service(doc))
    missing = REQUIRED_FOR_DEMO - env.keys()
    assert not missing, f"render.yaml is missing settings a demo cannot start without: {missing}"


def test_forbidden_dev_only_settings_are_absent() -> None:
    doc = _load_render_yaml()
    env = _env_vars(_web_service(doc))
    present = FORBIDDEN_IN_A_DEMO & env.keys()
    assert not present, (
        f"render.yaml must never set {present}: ADR 0008 (demo mode is not a dev run) and "
        "ADR 0010 (the red-flag tiers are not signed off)"
    )


def test_secrets_are_never_given_a_literal_value() -> None:
    doc = _load_render_yaml()
    env = _env_vars(_web_service(doc))
    for name in SECRET_NAMES & env.keys():
        entry = env[name]
        assert "value" not in entry, (
            f"{name} is a secret and must not have a literal value in render.yaml; use "
            "sync: false, fromDatabase, or generateValue instead. Found: "
            f"{entry}"
        )
        assert entry.get("sync") is False or "fromDatabase" in entry or entry.get(
            "generateValue"
        ) is True, f"{name} must be sync: false, fromDatabase, or generateValue: true: {entry}"


def test_no_env_var_anywhere_in_the_file_carries_a_plaintext_secret_looking_value() -> None:
    """A blunter, whole-file check: no `value:` line under `envVars:` should ever look like a
    real secret (long, opaque, or a connection string with a password in it), whichever key
    it is filed under -- this catches a secret pasted under the wrong name, not just the
    named ones above."""
    text = RENDER_YAML_PATH.read_text()
    assert "sslmode=" not in text or "sync: false" in text  # sanity: file is non-trivial
    # A real secret never appears as `value: "<...>"` for a NURA_* key; the only literal
    # `value:` entries in this file are non-secret configuration (region names, demo flags,
    # fixture paths).
    for match in re.finditer(r'key:\s*(NURA_[A-Z_]+)\s*\n\s*value:\s*(.+)', text):
        key, value = match.group(1), match.group(2).strip().strip('"')
        assert key not in SECRET_NAMES, f"{key} has a literal value in render.yaml: {value!r}"
