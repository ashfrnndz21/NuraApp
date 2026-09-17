"""The fuller insurance record's routes over HTTP (E13-03): the wiring from
`POST /profiles/{id}/confirmations` (subject `policy`, `insurance_claim`,
`insurance_claim_status`) through to `app/channels/api/insurance.py`, exercised end to end —
the unit tests cover the services underneath; this covers the schemas and the dispatch."""

from __future__ import annotations

import uuid

from app.clock import now
from app.keys.context import resolve_key_context
from app.memory.models import ProviderKind
from app.memory.spine import add_provider
from app.regions import Region
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591150001"
LIN = "+6594450001"


async def _cut_a_key(
    deployment: Deployment, owner: dict[str, str], profile_id: str, phone: str, scopes: list[str]
) -> dict[str, str]:
    """A narrower key over HTTP: register the holder, the owner's agreement, then the key
    itself — the two-step `_holder` already uses in `tests/test_row_scope.py`."""
    holder = await register_by_phone(deployment, phone, "Lin")
    await let_in(deployment, owner, profile_id, phone, scopes)
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": phone, "role": "caregiver", "scopes": scopes},
        headers=bearer(owner["token"]),
    )
    assert cut.status_code == 201, cut.text
    return holder


async def _profile_with_a_visit(deployment: Deployment) -> tuple[str, dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    async with deployment.sessions() as session:
        owner = await resolve_key_context(
            session,
            region=Region.SG,
            person_id=uuid.UUID(pa["person_id"]),
            profile_id=uuid.UUID(profile_id),
        )
        tan = await add_provider(
            session, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
        )
        await session.commit()
    when = now().isoformat()
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "appointment",
            "provider_id": str(tan.id),
            "scheduled_at": when,
            "purpose": "check-up",
        },
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    visit = await deployment.client.post(
        f"/profiles/{profile_id}/appointments",
        json={
            "provider_id": str(tan.id),
            "scheduled_at": when,
            "purpose": "check-up",
            "confirmation_id": minted.json()["confirmation_id"],
        },
        headers=his,
    )
    assert visit.status_code == 201, visit.text
    return profile_id, his, visit.json()["appointment_id"]


async def test_a_policy_is_written_and_read_back_over_http(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    minted = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "policy",
            "insurer_name": "Great Eastern",
            "policy_reference": "GE-4471-0932",
            "policy_type": "hospital",
            "covered": "Pa",
            "covers": "Hospital stays, up to $500 a day.",
            "status": "active",
            "guarantee_letter": True,
        },
        headers=his,
    )
    assert minted.status_code == 201, minted.text
    written = await deployment.client.post(
        f"/profiles/{profile_id}/insurance/policies",
        json={
            "insurer_name": "Great Eastern",
            "policy_reference": "GE-4471-0932",
            "policy_type": "hospital",
            "covered": "Pa",
            "covers": "Hospital stays, up to $500 a day.",
            "status": "active",
            "guarantee_letter": True,
            "confirmation_id": minted.json()["confirmation_id"],
        },
        headers=his,
    )
    assert written.status_code == 201, written.text
    policy_id = written.json()["policy_id"]

    held = await deployment.client.get(f"/profiles/{profile_id}/insurance/policies", headers=his)
    assert held.status_code == 200, held.text
    assert [row["policy_id"] for row in held.json()] == [policy_id]
    assert held.json()[0]["insurer_name"] == "Great Eastern"


async def test_a_narrower_key_is_refused_the_policy_routes_over_http(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    lin = await _cut_a_key(deployment, pa, profile_id, LIN, ["profile", "visits", "medicines"])
    lin_headers = bearer(lin["token"])
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/insurance/policies", headers=lin_headers
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["refusal"] == "OutOfScope"
    assert refused.json()["scope"] == "money"


async def test_a_claim_is_filed_and_moved_over_http(deployment: Deployment) -> None:
    profile_id, his, appointment_id = await _profile_with_a_visit(deployment)
    policy_yes = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "policy",
            "insurer_name": "AIA",
            "policy_type": "hospital",
            "status": "active",
        },
        headers=his,
    )
    assert policy_yes.status_code == 201, policy_yes.text
    policy = await deployment.client.post(
        f"/profiles/{profile_id}/insurance/policies",
        json={
            "insurer_name": "AIA",
            "policy_type": "hospital",
            "status": "active",
            "confirmation_id": policy_yes.json()["confirmation_id"],
        },
        headers=his,
    )
    assert policy.status_code == 201, policy.text
    policy_id = policy.json()["policy_id"]

    claim_yes = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={
            "subject": "insurance_claim",
            "policy_id": policy_id,
            "appointment_id": appointment_id,
            "claim_reference": "CLM-1",
        },
        headers=his,
    )
    assert claim_yes.status_code == 201, claim_yes.text
    claim = await deployment.client.post(
        f"/profiles/{profile_id}/insurance/claims",
        json={
            "policy_id": policy_id,
            "appointment_id": appointment_id,
            "claim_reference": "CLM-1",
            "confirmation_id": claim_yes.json()["confirmation_id"],
        },
        headers=his,
    )
    assert claim.status_code == 201, claim.text
    claim_id = claim.json()["claim_id"]
    assert claim.json()["status"] == "submitted"

    listed = await deployment.client.get(
        f"/profiles/{profile_id}/insurance/appointments/{appointment_id}/claims", headers=his
    )
    assert listed.status_code == 200 and [c["claim_id"] for c in listed.json()] == [claim_id]

    papers = await deployment.client.get(
        f"/profiles/{profile_id}/insurance/claims/{claim_id}/papers", headers=his
    )
    assert papers.status_code == 200 and papers.json() == []

    move_yes = await deployment.client.post(
        f"/profiles/{profile_id}/confirmations",
        json={"subject": "insurance_claim_status", "claim_id": claim_id, "status": "in_review"},
        headers=his,
    )
    assert move_yes.status_code == 201, move_yes.text
    moved = await deployment.client.post(
        f"/profiles/{profile_id}/insurance/claims/{claim_id}/status",
        json={"status": "in_review", "confirmation_id": move_yes.json()["confirmation_id"]},
        headers=his,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "in_review"


async def test_pre_visit_relevance_over_http_for_the_owner_and_a_narrower_key(
    deployment: Deployment,
) -> None:
    profile_id, his, appointment_id = await _profile_with_a_visit(deployment)
    owner_view = await deployment.client.get(
        f"/profiles/{profile_id}/insurance/pre-visit/{appointment_id}", headers=his
    )
    assert owner_view.status_code == 200, owner_view.text
    assert owner_view.json()["full"] is True
    assert any("no insurance policy" in line for line in owner_view.json()["note"])

    pa_session = {"token": his["Authorization"].removeprefix("Bearer ")}
    lin = await _cut_a_key(deployment, pa_session, profile_id, LIN, ["profile", "visits"])
    lin_headers = bearer(lin["token"])
    narrow_view = await deployment.client.get(
        f"/profiles/{profile_id}/insurance/pre-visit/{appointment_id}", headers=lin_headers
    )
    assert narrow_view.status_code == 200, narrow_view.text
    assert narrow_view.json()["full"] is False
    assert narrow_view.json()["policies"] == [] and narrow_view.json()["note"] == []
    assert len(narrow_view.json()["bring"]) == 1
    assert "insurance card" in narrow_view.json()["bring"][0]
