"""Over HTTP, the steps the trend, routine and calendar tests take: a paper through the
review card, a medicine from a label, a caregiver let in with a key."""

from __future__ import annotations

import base64
from typing import Any

from tests.api import bearer, let_in
from tests.conftest import Deployment
from tests.paper import placeholder_png


def photo(label: str) -> dict[str, str]:
    return {
        "data": base64.b64encode(placeholder_png(label)).decode(),
        "content_type": "image/png",
        "captured_at": "2026-09-03T08:00:00Z",
    }


async def confirm_paper(
    deployment: Deployment, token: str, profile_id: str, label: str
) -> dict[str, Any]:
    """Upload the paper, confirm every field as read with one yes; the confirmed card."""
    client = deployment.client
    card = (
        await client.post(
            f"/profiles/{profile_id}/photos", json=photo(label), headers=bearer(token)
        )
    ).json()
    decisions = [{"field_id": f["field_id"], "decision": "confirmed"} for f in card["fields"]]
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        headers=bearer(token),
    )
    assert minted.status_code == 201, minted.text
    done = await client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=bearer(token),
    )
    assert done.status_code == 200, done.text
    confirmed: dict[str, Any] = done.json()
    return confirmed


async def add_medicine(
    deployment: Deployment, token: str, profile_id: str, generic: str, strength: str, dose_text: str
) -> dict[str, Any]:
    client = deployment.client
    made = await client.post(
        f"/profiles/{profile_id}/photos",
        json=photo(f"label-{generic}-{strength}"),
        headers=bearer(token),
    )
    assert made.status_code == 201, made.text
    label = {
        "generic": generic,
        "strength": strength,
        "dose_text": dose_text,
        "quantity": 30,
        "prescriber": "Dr Tan",
        "source_kind": "retail",
    }
    body = {"label": label, "source_artifact_id": made.json()["artifact_id"]}
    minted = await client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "medicine", **body},
        headers=bearer(token),
    )
    assert minted.status_code == 201, minted.text
    added = await client.post(
        f"/profiles/{profile_id}/medicines",
        json={**body, "confirmation_id": minted.json()["confirmation_id"]},
        headers=bearer(token),
    )
    assert added.status_code == 201, added.text
    line: dict[str, Any] = added.json()
    return line


async def caregiver(
    deployment: Deployment,
    owner: dict[str, str],
    profile_id: str,
    phone: str,
    scopes: list[str],
    role: str = "caregiver",
) -> None:
    await let_in(deployment, owner, profile_id, phone, scopes, "daughter", role=role)
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": role, "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text
