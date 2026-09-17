"""#184: setting his area takes his own yes, once the graph is his.

Before his claim, a steward may still set it on the declared basis the stewardship rests
on, without a confirmation — that path is unchanged and covered by `test_feed_formats.py`
(`test_an_area_is_coarse_and_his_to_set`, `test_his_trail_says_who_set_his_area_and_when_it_
was_refused`). This file covers the gap: once the graph is his, his own write of it now
takes a `Confirmation`, minted for exactly the area he is shown (`ConfirmSubject.AREA`,
`app.drafts.AreaDraft`), the same content-digest machinery every other yes rests on.
"""

from __future__ import annotations

import uuid

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591150001"


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    return pa, await own_profile(deployment, pa)


async def _mint(deployment: Deployment, token: str, profile_id: str, area: str | None) -> str:
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "area", "area": area},
        headers=bearer(token),
    )
    assert minted.status_code == 201, minted.text
    confirmation_id: str = minted.json()["confirmation_id"]
    return confirmation_id


async def test_setting_the_area_without_a_yes_is_refused_and_on_his_trail(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    refused = await deployment.client.put(
        f"/profiles/{profile_id}/area", json={"area": "Bedok"}, headers=bearer(pa["token"])
    )
    assert refused.status_code == 400
    assert refused.json() == {"refusal": "AreaNotConfirmed"}

    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"]), params={"limit": 500}
    )
    assert trail.status_code == 200
    refusals = [
        row
        for row in trail.json()
        if row["outcome"] == "refused" and row["target"] == "profile.area"
    ]
    assert any(row["refused_because"] == "AreaNotConfirmed" for row in refusals)

    # Nothing was kept.
    read = await deployment.client.get(f"/profiles/{profile_id}/area", headers=bearer(pa["token"]))
    assert read.status_code == 200 and read.json()["area"] is None


async def test_his_yes_binds_to_exactly_the_area_shown(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    confirmation_id = await _mint(deployment, pa["token"], profile_id, "Bedok")

    # A yes minted for "Bedok" cannot be spent setting the area to something else.
    mismatched = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": "Toa Payoh", "confirmation_id": confirmation_id},
        headers=bearer(pa["token"]),
    )
    assert mismatched.status_code == 400
    assert mismatched.json() == {"refusal": "NotWhatWasConfirmed"}

    kept = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": "Bedok", "confirmation_id": confirmation_id},
        headers=bearer(pa["token"]),
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["area"] == "Bedok"

    # The same yes cannot be spent twice.
    again = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": "Bedok", "confirmation_id": confirmation_id},
        headers=bearer(pa["token"]),
    )
    assert again.status_code == 400
    assert again.json() == {"refusal": "AlreadySpent"}


async def test_a_yes_for_clearing_his_area_binds_to_exactly_that(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    confirmation_id = await _mint(deployment, pa["token"], profile_id, "Bedok")
    kept = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": "Bedok", "confirmation_id": confirmation_id},
        headers=bearer(pa["token"]),
    )
    assert kept.status_code == 200, kept.text

    clearing_id = await _mint(deployment, pa["token"], profile_id, None)
    cleared = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": None, "confirmation_id": clearing_id},
        headers=bearer(pa["token"]),
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["area"] is None


async def test_a_confirmation_id_that_is_nobodys_yes_here_is_refused(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    bogus = await deployment.client.put(
        f"/profiles/{profile_id}/area",
        json={"area": "Bedok", "confirmation_id": str(uuid.uuid4())},
        headers=bearer(pa["token"]),
    )
    assert bogus.status_code == 400
    assert bogus.json() == {"refusal": "NotAConfirmerHere"}
