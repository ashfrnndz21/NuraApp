"""#204: the red-flag tiers stay off until a clinician signs them off.

`NURA_RED_FLAG_TIERS=1` turns on the tiering of ADR 0010 — whether a red flag means the
ambulance, the hospital now, or tonight (`docs/trust/clinical-sign-off.md`, item 2). Unset,
every red flag's step is the ambulance, the stricter step the not-feeling-well card already
gives (`Settings.red_flag_tiers`'s own docstring, `backend/app/settings.py`).

Three things hold that guard, and this test is two of them: the default is off (anything but
the exact string `1` is off, and absent is off), and neither deploy config sets it — so a line
added to `fly.toml` or `render.yaml` in a hurry would turn on un-signed-off clinical triage in
production, and this is the check that stops it, rather than the convention that everyone
remembers to check `Makefile`'s `dev` target is the only place that sets it.
"""

from __future__ import annotations

from pathlib import Path

from app.settings import Settings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}


def test_red_flag_tiers_default_off() -> None:
    assert Settings.__dataclass_fields__["red_flag_tiers"].default is False
    assert load_settings(ENV).red_flag_tiers is False
    assert load_settings({**ENV, "NURA_RED_FLAG_TIERS": "0"}).red_flag_tiers is False
    assert load_settings({**ENV, "NURA_RED_FLAG_TIERS": "true"}).red_flag_tiers is False
    assert load_settings({**ENV, "NURA_RED_FLAG_TIERS": "yes"}).red_flag_tiers is False
    assert load_settings({**ENV, "NURA_RED_FLAG_TIERS": "1"}).red_flag_tiers is True


def test_deploy_configs_never_set_red_flag_tiers() -> None:
    for name in ("fly.toml", "render.yaml"):
        text = (REPO_ROOT / name).read_text()
        assert "NURA_RED_FLAG_TIERS" not in text, (
            f"{name} must never set NURA_RED_FLAG_TIERS: the tiers of ADR 0010 are not "
            "signed off yet (docs/trust/clinical-sign-off.md, item 2), and setting it there "
            "would turn on un-signed-off clinical triage in production"
        )


def test_only_the_dev_makefile_target_sets_it() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    lines_setting_it = [line for line in makefile.splitlines() if "NURA_RED_FLAG_TIERS" in line]
    assert lines_setting_it, "Makefile no longer sets NURA_RED_FLAG_TIERS anywhere"
    assert all(line.startswith("dev:") for line in lines_setting_it), lines_setting_it
