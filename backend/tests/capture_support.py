"""What the capture-extras tests share (E02-02, E02-03, E02-06, E02-08): uploads, decisions,
the yes and the confirm, a family member let in, and the recording consent — over HTTP."""

from __future__ import annotations

import base64
from typing import Any

from app.consent.models import ConsentPurpose
from app.consent.texts import current_version
from tests.api import bearer, let_in
from tests.conftest import Deployment
from tests.paper import placeholder_of
from tests.voice_notes import CONTENT_TYPE, placeholder_voice

JSON = dict[str, Any]


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def photo(label: str, *, hint: str | None = None, at: str = "2026-09-14T00:00:00Z") -> JSON:
    body: JSON = {
        "data": b64(placeholder_of(label)),
        "content_type": "image/png",
        "captured_at": at,
    }
    if hint is not None:
        body["document_kind"] = hint
    return body


def pdf(label: str, *, source: str = "portal", hint: str | None = None) -> JSON:
    body: JSON = {
        "data": b64(placeholder_of(label)),
        "content_type": "application/pdf",
        "captured_at": "2026-09-01T00:00:00Z",
        "source": source,
    }
    if hint is not None:
        body["document_kind"] = hint
    return body


def voice(sample: str, **extra: Any) -> JSON:
    """A voice note of one of the fixture samples (`tests.voice_notes`); `extra` fills or
    overrides the body — a `label`, `private`, another content type."""
    return {
        "kind": "voice",
        "data": b64(placeholder_voice(sample)),
        "content_type": CONTENT_TYPE,
        "captured_at": "2026-09-03T07:50:00Z",
        **extra,
    }


def decide(
    card: JSON, *, correct: dict[str, Any] | None = None, reject: set[str] = frozenset()
) -> list[JSON]:
    """Confirm every field, except those corrected (to the value given) or rejected."""
    decisions: list[JSON] = []
    for field in card["fields"]:
        if correct and field["attribute"] in correct:
            decisions.append(
                {
                    "field_id": field["field_id"],
                    "decision": "corrected",
                    "corrected_value": correct[field["attribute"]],
                }
            )
        elif field["attribute"] in reject:
            decisions.append({"field_id": field["field_id"], "decision": "rejected"})
        else:
            decisions.append({"field_id": field["field_id"], "decision": "confirmed"})
    return decisions


async def mint(
    deployment: Deployment, token: str, profile_id: str, card: JSON, decisions: list[JSON]
) -> Any:
    return await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
        headers=bearer(token),
    )


async def confirm(
    deployment: Deployment, token: str, profile_id: str, card: JSON, decisions: list[JSON]
) -> Any:
    """Mint the yes for exactly these decisions, then spend it. The confirm's response."""
    minted = await mint(deployment, token, profile_id, card, decisions)
    assert minted.status_code == 201, minted.text
    return await deployment.client.post(
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        json={"decisions": decisions, "confirmation_id": minted.json()["confirmation_id"]},
        headers=bearer(token),
    )


async def key_for(
    deployment: Deployment,
    owner: dict[str, str],
    profile_id: str,
    phone: str,
    scopes: list[str],
) -> None:
    """The owner lets this number in to these parts and cuts a caregiver key to them."""
    await let_in(deployment, owner, profile_id, phone, scopes, relationship="daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "caregiver", "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert granted.status_code == 201, granted.text


async def agree_to_recording(
    deployment: Deployment, owner: dict[str, str], profile_id: str
) -> None:
    """The owner agrees, in today's words, to Nura keeping what is said (E16-02)."""
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/recording",
        json={
            "wording_version": current_version(ConsentPurpose.RECORDING),
            "language": "en",
            "captured_via": "app",
        },
        headers=bearer(owner["token"]),
    )
    assert agreed.status_code == 201, agreed.text


async def refusals(deployment: Deployment, owner: dict[str, str], profile_id: str) -> set[str]:
    """The names of every refusal on the owner's trail."""
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", params={"limit": 500}, headers=bearer(owner["token"])
    )
    assert trail.status_code == 200, trail.text
    return {e["refused_because"] for e in trail.json() if e["outcome"] == "refused"}
