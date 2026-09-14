"""How a test registers a person over HTTP and speaks for him afterwards.

Registration is the only way to a token, and the fixture sender is the only place a test can
read the code from: nothing on the wire carries it.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import Deployment


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def register_by_phone(
    deployment: Deployment, phone_e164: str, display_name: str | None = None
) -> dict[str, str]:
    """Start and verify a phone login; the session the API issued, as a JSON object."""
    body: dict[str, str] = {"phone_e164": phone_e164}
    if display_name is not None:
        body["display_name"] = display_name
    started = await deployment.client.post("/auth/phone/start", json=body)
    assert started.status_code == 202, started.text
    verified = await deployment.client.post(
        "/auth/phone/verify",
        json={"phone_e164": phone_e164, "code": deployment.sender.last_code(phone_e164)},
    )
    assert verified.status_code == 200, verified.text
    session: dict[str, str] = verified.json()
    return session


async def own_profile(client: AsyncClient, token: str, **body: str) -> str:
    """Open the caller's own health graph; its id."""
    created = await client.post("/profiles/mine", json=body, headers=bearer(token))
    assert created.status_code == 201, created.text
    profile_id: str = created.json()["profile_id"]
    return profile_id
