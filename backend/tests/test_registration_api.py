"""E00-09: registration by phone code and by email link, over HTTP.

    The phone code is never returned by the API.

The code goes out through the sender and nowhere else. The rest of these are the shape of a
one-time code done properly: six digits, ten minutes, one use, five tries; a session token
handed over once on verify; logout closes it; and a person pinned to Malaysia gets nothing
from the Singapore deployment.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy import select

from app.db import utcnow
from app.identity.models import LoginChallenge, LoginSession, Person
from app.regions import Region
from tests.api import bearer, register_by_phone
from tests.conftest import Deployment

PA = "+6591110001"


async def _challenge_for(deployment: Deployment, address: str) -> LoginChallenge:
    async with deployment.sessions() as session:
        found = await session.scalars(
            select(LoginChallenge)
            .where(LoginChallenge.phone_e164 == address)
            .order_by(LoginChallenge.issued_at.desc())
        )
        challenge = found.first()
        assert challenge is not None
        return challenge


# --- the code never comes back over the wire ---------------------------------------------


async def test_the_phone_code_is_sent_and_never_returned_by_the_api(
    deployment: Deployment,
) -> None:
    started = await deployment.client.post(
        "/auth/phone/start", json={"phone_e164": PA, "display_name": "Pa"}
    )
    assert started.status_code == 202
    code = deployment.sender.last_code(PA)
    assert len(code) == 6 and code.isdigit()

    # Not in the body, not in a header, and not in what the table holds either.
    assert code not in started.text
    assert code not in " ".join(started.headers.values())
    challenge = await _challenge_for(deployment, PA)
    assert code not in " ".join(str(value) for value in vars(challenge).values())
    assert challenge.code_hash != hashlib.sha256(code.encode()).hexdigest()

    verified = await deployment.client.post(
        "/auth/phone/verify", json={"phone_e164": PA, "code": code}
    )
    assert verified.status_code == 200
    assert code not in verified.text
    session = verified.json()
    assert set(session) == {"token", "person_id", "region"}
    assert session["region"] == "SG"

    # The token is handed over once. The table holds a hash of it, not the token.
    async with deployment.sessions() as db:
        rows = (await db.scalars(select(LoginSession))).all()
    assert len(rows) == 1
    assert rows[0].token_hash != session["token"]
    assert session["token"] not in " ".join(str(value) for value in vars(rows[0]).values())
    assert rows[0].expires_at - rows[0].created_at == timedelta(days=30)

    me = await deployment.client.get("/me", headers=bearer(session["token"]))
    assert me.status_code == 200
    assert me.json()["display_name"] == "Pa"
    assert me.json()["phone_e164"] == PA
    assert me.json()["profile_id"] is None


async def test_registering_twice_from_the_same_number_is_one_account(
    deployment: Deployment,
) -> None:
    first = await register_by_phone(deployment, PA, "Pa")
    second = await register_by_phone(deployment, PA, "Somebody Else")
    assert first["person_id"] == second["person_id"]
    # A name given at registration fills an empty one; it never overwrites a chosen one.
    me = await deployment.client.get("/me", headers=bearer(second["token"]))
    assert me.json()["display_name"] == "Pa"


# --- the code is one use, ten minutes, five tries ----------------------------------------


async def test_a_code_is_single_use(deployment: Deployment) -> None:
    await deployment.client.post("/auth/phone/start", json={"phone_e164": PA})
    code = deployment.sender.last_code(PA)
    body = {"phone_e164": PA, "code": code}
    assert (await deployment.client.post("/auth/phone/verify", json=body)).status_code == 200
    again = await deployment.client.post("/auth/phone/verify", json=body)
    assert again.status_code == 400
    assert again.json() == {"refusal": "NoOpenChallenge"}


async def test_five_wrong_codes_lock_the_challenge(deployment: Deployment) -> None:
    await deployment.client.post("/auth/phone/start", json={"phone_e164": PA})
    code = deployment.sender.last_code(PA)
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        refused = await deployment.client.post(
            "/auth/phone/verify", json={"phone_e164": PA, "code": wrong}
        )
        assert refused.status_code == 400
        assert refused.json() == {"refusal": "WrongCode"}

    # The right code is refused now: the challenge is spent.
    locked = await deployment.client.post(
        "/auth/phone/verify", json={"phone_e164": PA, "code": code}
    )
    assert locked.status_code == 400
    assert locked.json() == {"refusal": "ChallengeLocked"}
    assert (await _challenge_for(deployment, PA)).attempts == 5

    # Nobody was registered by any of it.
    async with deployment.sessions() as db:
        assert (await db.scalars(select(Person))).all() == []

    # Asking for a new code opens a fresh challenge, and that one works.
    await deployment.client.post("/auth/phone/start", json={"phone_e164": PA})
    fresh = await deployment.client.post(
        "/auth/phone/verify",
        json={"phone_e164": PA, "code": deployment.sender.last_code(PA)},
    )
    assert fresh.status_code == 200


async def test_an_expired_code_is_refused(deployment: Deployment) -> None:
    await deployment.client.post("/auth/phone/start", json={"phone_e164": PA})
    code = deployment.sender.last_code(PA)
    challenge = await _challenge_for(deployment, PA)
    assert challenge.expires_at - challenge.issued_at == timedelta(minutes=10)

    async with deployment.sessions() as db:
        row = await db.get(LoginChallenge, challenge.id)
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()

    expired = await deployment.client.post(
        "/auth/phone/verify", json={"phone_e164": PA, "code": code}
    )
    assert expired.status_code == 400
    assert expired.json() == {"refusal": "ChallengeExpired"}


async def test_a_wrong_number_or_a_number_that_never_asked_is_refused_in_the_same_words(
    deployment: Deployment,
) -> None:
    never = await deployment.client.post(
        "/auth/phone/verify", json={"phone_e164": "+6591110099", "code": "123456"}
    )
    assert never.status_code == 400
    assert never.json() == {"refusal": "NoOpenChallenge"}

    malformed = await deployment.client.post("/auth/phone/start", json={"phone_e164": "9111 0001"})
    assert malformed.status_code == 422


# --- email, the alternative --------------------------------------------------------------


async def test_registration_by_email_link(deployment: Deployment) -> None:
    email = "pa@example.sg"
    started = await deployment.client.post(
        "/auth/email/start", json={"email": email, "display_name": "Pa"}
    )
    assert started.status_code == 202
    token = deployment.sender.last_email_token(email)
    assert token not in started.text

    wrong = await deployment.client.post(
        "/auth/email/verify", json={"email": email, "token": "not-the-token"}
    )
    assert wrong.json() == {"refusal": "WrongCode"}

    verified = await deployment.client.post(
        "/auth/email/verify", json={"email": email, "token": token}
    )
    assert verified.status_code == 200
    me = await deployment.client.get("/me", headers=bearer(verified.json()["token"]))
    assert me.json()["email"] == email
    assert me.json()["phone_e164"] is None


# --- sessions ----------------------------------------------------------------------------


async def test_logout_revokes_the_session(deployment: Deployment) -> None:
    session = await register_by_phone(deployment, PA, "Pa")
    headers = bearer(session["token"])
    assert (await deployment.client.get("/me", headers=headers)).status_code == 200

    assert (await deployment.client.post("/auth/logout", headers=headers)).status_code == 204

    gone = await deployment.client.get("/me", headers=headers)
    assert gone.status_code == 401
    assert gone.json() == {"refusal": "NoSession"}
    # Logging out twice is not an error worth a second word: the session is closed.
    assert (await deployment.client.post("/auth/logout", headers=headers)).status_code == 401

    async with deployment.sessions() as db:
        rows = (await db.scalars(select(LoginSession))).all()
    assert len(rows) == 1 and rows[0].revoked_at is not None


async def test_a_made_up_or_missing_token_is_no_session(deployment: Deployment) -> None:
    for headers in ({}, bearer("not-a-token"), {"Authorization": "Basic abc"}):
        response = await deployment.client.get("/me", headers=headers)
        assert response.status_code == 401
        assert response.json() == {"refusal": "NoSession"}


async def test_an_expired_session_is_no_session(deployment: Deployment) -> None:
    session = await register_by_phone(deployment, PA, "Pa")
    async with deployment.sessions() as db:
        row = (await db.scalars(select(LoginSession))).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        await db.commit()
    gone = await deployment.client.get("/me", headers=bearer(session["token"]))
    assert gone.status_code == 401


# --- the region --------------------------------------------------------------------------


async def test_a_person_pinned_to_malaysia_is_refused_by_the_singapore_deployment(
    deployment: Deployment,
) -> None:
    """However his row got here, this deployment will not sign him in or open a graph."""
    async with deployment.sessions() as db:
        db.add(Person(region=Region.MY, display_name="Ash", phone_e164="+60121110001"))
        await db.commit()

    started = await deployment.client.post("/auth/phone/start", json={"phone_e164": "+60121110001"})
    assert started.status_code == 202
    verified = await deployment.client.post(
        "/auth/phone/verify",
        json={"phone_e164": "+60121110001", "code": deployment.sender.last_code("+60121110001")},
    )
    assert verified.status_code == 403
    assert verified.json() == {"refusal": "OutOfRegion"}

    async with deployment.sessions() as db:
        assert (await db.scalars(select(LoginSession))).all() == []
