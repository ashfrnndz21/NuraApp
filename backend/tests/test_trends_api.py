"""E09-01 over HTTP: `GET /profiles/{id}/trends/{analyte}`, in his language, from his papers."""

from __future__ import annotations

from app.safety.boundary import Surface, boundary_line
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.paper import LIPID_PANEL, LIPID_PANEL_2025
from tests.trio_api_support import caregiver, confirm_paper

PA = "+6591110001"
MEI = "+6591110002"


async def test_pa_reads_his_cholesterol_trend_in_malay(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa", "ms")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="ms")
    for label in (LIPID_PANEL, LIPID_PANEL_2025):
        await confirm_paper(deployment, pa["token"], profile_id, label)
    his = bearer(pa["token"])

    got = await deployment.client.get(f"/profiles/{profile_id}/trends/total_cholesterol", headers=his)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["language"] == "ms" and body["direction"] == "down"
    assert [(p["value"], p["on"], p["band"]) for p in body["points"]] == [
        (230, "2023-09-07", "above"),
        (212, "2025-08-29", "above"),
    ]
    assert body["points"][0]["range"]["source"] == "guideline"
    assert body["points"][0]["range"]["source_id"] == "ncep-atp3-2001"
    assert body["points"][1]["range"]["source_id"] == "lab:bukit_lab"
    assert all(p["artifact_id"] for p in body["points"])
    assert body["birth_decade"] == 1950 and body["sex"] == "male"
    assert body["lines"] == [
        "Kolesterol anda ialah 212 pada Jumaat 29 Ogos 2025.",
        "Julat pada ujian darah anda ialah bawah 200.",
        "Ia di atas julat pada ujian darah anda.",
        "Ia telah turun sejak Khamis 7 September 2023.",
        "Nura menyusun ujian darah anda mengikut tarikh.",
        "Ini bukan nasihat doktor.",
        "Tanya doktor anda.",
    ]
    assert body["boundary"] == boundary_line(Surface.TREND, "ms")

    chinese = await deployment.client.get(
        f"/profiles/{profile_id}/trends/total_cholesterol", params={"language": "zh"}, headers=his
    )
    assert chinese.json()["lines"][:2] == ["2025年8月29日星期五，您验了血。", "您的胆固醇是212。"]

    unknown = await deployment.client.get(f"/profiles/{profile_id}/trends/unobtanium", headers=his)
    assert (unknown.status_code, unknown.json()) == (404, {"refusal": "NoSuchAnalyte"})


async def test_a_caregiver_reads_the_trend_until_the_record_moves_past_state(
    deployment: Deployment,
) -> None:
    """Her key cannot recompute State: she reads the trend from the last snapshot, gets 409
    once a result lands that State has not folded in, and reads it again once the owner's
    read catches State up. The refusal is on his trail."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="en")
    await confirm_paper(deployment, pa["token"], profile_id, LIPID_PANEL)
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    await caregiver(deployment, pa, profile_id, MEI, ["readings", "records"])
    route = f"/profiles/{profile_id}/trends/total_cholesterol"

    hers = await client.get(route, headers=bearer(mei["token"]))
    assert hers.status_code == 200, hers.text
    assert [p["value"] for p in hers.json()["points"]] == [230]
    assert hers.json()["boundary"] == boundary_line(Surface.TREND, "en")

    await confirm_paper(deployment, mei["token"], profile_id, LIPID_PANEL_2025)
    behind = await client.get(route, headers=bearer(mei["token"]))
    assert (behind.status_code, behind.json()) == (409, {"refusal": "StaleState"})
    # The whole trail: under the frozen clock every line has the same moment, so the refusal is
    # not guaranteed to be on the first page of 200.
    trail = await client.get(
        f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=bearer(pa["token"])
    )
    assert any(
        row["refused_because"] == "StaleState" and row["actor_person_id"] == mei["person_id"]
        for row in trail.json()
    )

    assert (await client.get(f"/profiles/{profile_id}/state", headers=bearer(pa["token"]))).status_code == 200
    caught_up = await client.get(route, headers=bearer(mei["token"]))
    assert caught_up.status_code == 200, caught_up.text
    assert [p["value"] for p in caught_up.json()["points"]] == [230, 212]
