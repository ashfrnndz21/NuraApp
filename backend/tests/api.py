"""How a test registers a person over HTTP and speaks for him afterwards.

Registration is the only way to a token, and the fixture sender is the only place a test can
read the code from: nothing on the wire carries it.
"""

from __future__ import annotations

import uuid

from app.identity.models import Person
from app.identity.service import create_own_profile
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


CONSENT = {"wording_version": "1", "language": "en", "captured_via": "app"}
"""The agreement every door takes: which words, in which language, captured how."""


async def own_profile(deployment: Deployment, session: dict[str, str], **body: str) -> str:
    """Open this person's own health graph on the deployment; its id.

    `POST /profiles/mine` is shut until the consent service can record the agreement
    (`ConsentNotRecordedYet`), so the tests open the graph through the service, the way the
    consent merge will wire the door. Committed, so the app's own sessions see it.
    """
    async with deployment.sessions() as db:
        person = await db.get(Person, uuid.UUID(session["person_id"]))
        assert person is not None
        profile = await create_own_profile(db, region=deployment.region, owner=person, **body)
        await db.commit()
        return str(profile.id)
