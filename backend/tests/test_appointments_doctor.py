"""The visits still to come carry the doctor's name as the family wrote it (D1: her Home's
"Not in the papers yet" note says "the questions for Dr Tan on Wednesday 16 September"), read
under the visits scope like the visits themselves; a key without that scope reads neither."""

from __future__ import annotations

from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6598760441"
MEI = "+6598760442"
AT = "2026-09-16T09:00:00+08:00"


async def test_each_visit_to_come_names_its_doctor(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    client = deployment.client
    provider = await client.post(
        f"/profiles/{profile_id}/providers", json={"name": "Dr Tan", "kind": "doctor"}, headers=his
    )
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["provider_id"]
    purpose = "blood pressure review"
    yes = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "appointment",
            "provider_id": provider_id,
            "scheduled_at": AT,
            "purpose": purpose,
        },
        headers=his,
    )
    assert yes.status_code == 201, yes.text
    booked = await client.post(
        f"/profiles/{profile_id}/appointments",
        json={
            "provider_id": provider_id,
            "scheduled_at": AT,
            "purpose": purpose,
            "confirmation_id": yes.json()["confirmation_id"],
        },
        headers=his,
    )
    assert booked.status_code == 201, booked.text

    listed = await client.get(f"/profiles/{profile_id}/appointments", headers=his)
    assert listed.status_code == 200, listed.text
    assert [(one["provider_id"], one["doctor"]) for one in listed.json()] == [
        (provider_id, "Dr Tan")
    ]

    # A key without the visits scope reads no visit, and so no doctor's name.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["medicines"], "daughter")
    granted = await client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["medicines"]},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    theirs = await client.get(f"/profiles/{profile_id}/appointments", headers=bearer(mei["token"]))
    assert theirs.status_code == 403 and theirs.json()["scope"] == "visits"
