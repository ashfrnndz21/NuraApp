"""RE-05, "What Nura uses": docs/recommendation-engine.md §3.6, ADR 0016 decision 3.

    GET /profiles/{id}/signals               every family, on or off
    PUT /profiles/{id}/signals/{family}       switch one (owner, chief)

Switching a family off is a confirmed Fact (`subject="signals"`), folded by State into the
preference dimension, and on the audit trail. Search-topic use starts off (owner decision D3);
every other family starts on. Only he or his chief may switch one; anyone else reads them.
"""

from __future__ import annotations

from app.keys.scopes import Scope
from app.state.dimensions import dimension_of
from app.state.models import Dimension
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591230001"
MEI = "+6591230002"
STRANGER = "+6591230003"

EVERY_PART = [scope.value for scope in Scope if scope is not Scope.PROFILE]


def test_signals_is_a_preference_subject() -> None:
    assert dimension_of("signals") is Dimension.PREFERENCE


async def _grant(deployment: Deployment, owner: dict[str, str], profile_id: str, phone: str, role: str) -> dict[str, str]:
    holder = await register_by_phone(deployment, phone, "Mei")
    await let_in(deployment, owner, profile_id, phone, EVERY_PART, relationship="daughter", role=role)
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": role},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text
    return holder


async def test_the_switches_default_on_except_search_topics(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    read = await deployment.client.get(f"/profiles/{profile_id}/signals", headers=bearer(pa["token"]))
    assert read.status_code == 200, read.text
    by_family = {row["family"]: row for row in read.json()["signals"]}
    assert by_family["food"]["on"] is True
    assert by_family["sleep"]["on"] is True
    assert by_family["steps"]["on"] is True
    assert by_family["water"]["on"] is True
    # D3: search-topic use is opt-in only, off until he says otherwise.
    assert by_family["search_topics"]["on"] is False
    assert all(row["fact_id"] is None for row in by_family.values()), "nothing is written until he says"
    assert read.json()["may_set"] is True


async def test_switching_food_off_is_a_confirmed_fact_state_shows_it_and_it_is_on_the_trail(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    off = await deployment.client.put(
        f"/profiles/{profile_id}/signals/food", json={"on": False}, headers=his
    )
    assert off.status_code == 200, off.text
    food = next(row for row in off.json()["signals"] if row["family"] == "food")
    assert food["on"] is False and food["fact_id"]

    # State's preference dimension shows it, confirmed by him.
    state = (await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)).json()
    fact = state["dimensions"]["preference"]["facts"]["signals"]["food"]
    assert fact["value"] is False
    assert fact["confidence_state"] == "confirmed_by_person"

    # The route is on the audit trail: the fact it wrote, by its own id.
    trail = (await deployment.client.get(f"/profiles/{profile_id}/audit", headers=his)).json()
    writes = [
        row
        for row in trail
        if row["action"] == "write" and row["target"] == "fact" and row["target_id"] == food["fact_id"]
    ]
    assert writes, "the switch is on the trail"

    # Turning it back on supersedes the off fact rather than leaving two current ones.
    on = await deployment.client.put(
        f"/profiles/{profile_id}/signals/food", json={"on": True}, headers=his
    )
    assert on.status_code == 200, on.text
    food_again = next(row for row in on.json()["signals"] if row["family"] == "food")
    assert food_again["on"] is True
    state_again = (await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)).json()
    assert state_again["dimensions"]["preference"]["facts"]["signals"]["food"]["value"] is True


async def test_his_chief_may_set_a_switch_too(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    mei = await _grant(deployment, pa, profile_id, MEI, "chief")
    set_by_chief = await deployment.client.put(
        f"/profiles/{profile_id}/signals/sleep", json={"on": False}, headers=bearer(mei["token"])
    )
    assert set_by_chief.status_code == 200, set_by_chief.text
    sleep = next(row for row in set_by_chief.json()["signals"] if row["family"] == "sleep")
    assert sleep["on"] is False


async def test_a_caregiver_who_is_not_the_chief_reads_the_switches_but_may_not_set_one(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    mei = await _grant(deployment, pa, profile_id, MEI, "caregiver")
    hers = bearer(mei["token"])
    read = await deployment.client.get(f"/profiles/{profile_id}/signals", headers=hers)
    assert read.status_code == 200, read.text
    # Her view says whose switches they are: read-only, not hers to flip.
    assert read.json()["may_set"] is False
    refused = await deployment.client.put(
        f"/profiles/{profile_id}/signals/food", json={"on": False}, headers=hers
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NotTheirsToSetSignals"}
