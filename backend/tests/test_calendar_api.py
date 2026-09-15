"""E18-02 over HTTP: Mei uploads a calendar; two proposals; one dismissed; Pa's yes books one."""

from __future__ import annotations

import base64
from pathlib import Path

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.trio_api_support import caregiver

ICS = Path(__file__).resolve().parent / "fixtures" / "calendar" / "three-events.ics"
PA = "+6591110001"
MEI = "+6591110002"


async def test_two_proposals_one_dismissed_one_accepted_by_pa(deployment: Deployment) -> None:
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="en")
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    await caregiver(deployment, pa, profile_id, MEI, ["medicines", "visits", "readings"])
    his, hers = bearer(pa["token"]), bearer(mei["token"])
    base = f"/profiles/{profile_id}"

    withheld = await client.post(f"{base}/connectors/calendar", json={}, headers=his)
    assert (withheld.status_code, withheld.json()) == (403, {"refusal": "ConsentWithheld"})
    not_hers = await client.post(f"{base}/connectors/calendar", json={}, headers=hers)
    assert (not_hers.status_code, not_hers.json()) == (403, {"refusal": "NotTheirsToConnect"})
    connected = await client.post(
        f"{base}/connectors/calendar",
        json={"consent": {"wording_version": "1", "language": "en"}},
        headers=his,
    )
    assert connected.status_code == 201, connected.text
    connector_id = connected.json()["connector_id"]

    scanned = await client.post(
        f"{base}/connectors/{connector_id}/scan",
        json={"ics": base64.b64encode(ICS.read_bytes()).decode()},
        headers=hers,
    )
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert (body["read"], body["dropped"], len(body["proposed"])) == (3, 1, 2)
    assert "Ah Kow" not in scanned.text and "Mei Lim" not in scanned.text
    by_title = {p["title"]: p for p in body["proposed"]}
    visit, dialysis = by_title["Dr Tan follow-up"], by_title["Dialysis SGH"]
    assert visit["lines"] == [
        "Nura found a visit to Dr Tan in the calendar.",
        "It is on Thursday 24 September at 10 in the morning.",
        "Tap Yes to add it to your visits.",
    ]

    dismissed = await client.post(
        f"{base}/proposals/{dialysis['proposal_id']}/dismiss", headers=hers
    )
    assert dismissed.status_code == 200 and dismissed.json()["status"] == "dismissed"

    minted = await client.post(
        f"{base}/confirmations",
        json={"subject": "appointment_proposal", "proposal_id": visit["proposal_id"]},
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    accepted = await client.post(
        f"{base}/proposals/{visit['proposal_id']}/accept",
        json={"confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["appointment_status"] == "planned"
    assert accepted.json()["proposal"]["lines"][-1] == "It is in your visits now."
    again = await client.post(
        f"{base}/proposals/{visit['proposal_id']}/accept",
        json={"confirmation_id": minted.json()["confirmation_id"]},
        headers=his,
    )
    assert (again.status_code, again.json()) == (409, {"refusal": "AlreadyDecided"})

    listed = (await client.get(f"{base}/proposals", headers=hers)).json()
    assert sorted(p["status"] for p in listed) == ["accepted", "dismissed"]
    trail = (await client.get(f"{base}/audit", headers=his)).json()
    targets = {(row["action"], row["target"]) for row in trail if row["outcome"] == "allowed"}
    assert {
        ("write", "connector"),
        ("write", "appointment_proposal"),
        ("write", "appointment"),
    } <= targets
    assert any(row["refused_because"] == "AlreadyDecided" for row in trail)
