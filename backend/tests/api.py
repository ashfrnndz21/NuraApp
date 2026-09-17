"""How a test registers a person over HTTP and speaks for him afterwards.

Registration is the only way to a token, and the fixture sender is the only place a test can
read the code from: nothing on the wire carries it.
"""

from __future__ import annotations

from app.consent.models import ConsentPurpose
from app.consent.opt_in_words import OPT_IN_VERSION
from app.consent.texts import current_version
from tests.conftest import Deployment


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register_by_phone(
    deployment: Deployment,
    phone_e164: str,
    display_name: str | None = None,
    language: str | None = None,
) -> dict[str, str]:
    """Start and verify a phone login; the session the API issued, as a JSON object."""
    body: dict[str, str] = {"phone_e164": phone_e164}
    if display_name is not None:
        body["display_name"] = display_name
    if language is not None:
        body["language"] = language
    started = await deployment.client.post("/auth/phone/start", json=body)
    assert started.status_code == 202, started.text
    verified = await deployment.client.post(
        "/auth/phone/verify",
        json={"phone_e164": phone_e164, "code": deployment.sender.last_code(phone_e164)},
    )
    assert verified.status_code == 200, verified.text
    session: dict[str, str] = verified.json()
    return session


CONSENT = {
    "wording_version": current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
    "language": "en",
    "captured_via": "app",
}
"""The agreement every door takes: today's words, in English, in the app."""


async def own_profile(deployment: Deployment, session: dict[str, str], **body: str) -> str:
    """Open this person's own health graph over HTTP, with today's agreement; its id."""
    created = await deployment.client.post(
        "/profiles/mine", json={"consent": CONSENT, **body}, headers=bearer(session["token"])
    )
    assert created.status_code == 201, created.text
    profile_id: str = created.json()["profile_id"]
    return profile_id


async def let_in(
    deployment: Deployment,
    owner: dict[str, str],
    profile_id: str,
    holder_phone_e164: str,
    scopes: list[str],
    relationship: str | None = None,
    holder_display_name: str = "Mei",
) -> dict[str, object]:
    """The owner agrees to let this number in, to these parts; what a key rests on. By phone
    the words need the name he calls the person (`HolderNeedsAName` without it)."""
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={
            "holder_phone_e164": holder_phone_e164,
            "holder_display_name": holder_display_name,
            "scopes": scopes,
            "relationship": relationship,
            "language": "en",
            "captured_via": "app",
        },
        headers=bearer(owner["token"]),
    )
    assert agreed.status_code == 201, agreed.text
    consent: dict[str, object] = agreed.json()
    return consent


async def accept_whatsapp(
    deployment: Deployment,
    holder: dict[str, str],
    profile_id: str,
    *,
    messages: bool = True,
    group: bool = True,
    language: str = "en",
) -> dict[str, object]:
    """The holder's own answers at the key-accept step (#143, #148, Meta's per-recipient
    opt-in): without his own yes to messages, Nura may send him nothing on WhatsApp, a
    red-flag notice included. Call this for each holder a test expects to reach on WhatsApp;
    skip it for one a test means to leave unasked."""
    answered = await deployment.client.post(
        f"/profiles/{profile_id}/whatsapp-opt-in",
        json={
            "messages": messages,
            "group": group,
            "wording_version": OPT_IN_VERSION,
            "language": language,
        },
        headers=bearer(holder["token"]),
    )
    assert answered.status_code == 201, answered.text
    out: dict[str, object] = answered.json()
    return out
