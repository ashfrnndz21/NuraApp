"""Pa, Mei and the papers of a health biography, as the onboarding tests reach them over HTTP."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from tests.api import CONSENT, bearer, register_by_phone
from tests.conftest import Deployment
from tests.paper import LIPID_PANEL, WARFARIN_LABEL, placeholder_png

PA = "+6591150001"
MEI = "+6591150002"
KIT = "+6591150003"
SITI = "+6591150004"

CONDITIONS = [
    "high_blood_pressure",
    "cholesterol",
    "diabetes",
    "blood_thinner",
    "hospital_last_year",
]
SETTINGS: dict[str, Any] = {
    "language": "ms",
    "conditions": CONDITIONS,
    "density": "simple",
    "large_text": True,
    "voice_on": True,
    "breakfast_time": "07:30",
    "checkin_time": "18:00",
    "doctor_name": "Dr Tan",
    "preferred_name": "Pa",
    "birth_decade": 1950,
}
"""Pa's settings as Mei saves them: Malay, simple, large text, voice on, breakfast at 07:30,
Dr Tan, and five conditions tapped in the cloud."""


def paper(label: str, kind: str) -> dict[str, str]:
    return {
        "data": base64.b64encode(placeholder_png(label)).decode(),
        "content_type": "image/png",
        "captured_at": "2026-09-03T08:00:00Z",
        "paper": kind,
    }


async def call(
    deployment: Deployment, method: str, path: str, token: str, expect: int, **kwargs: Any
) -> Any:
    answer = await deployment.client.request(method, path, headers=bearer(token), **kwargs)
    assert answer.status_code == expect, answer.text
    return answer.json()


async def refused(
    deployment: Deployment,
    method: str,
    path: str,
    token: str,
    expect: int,
    refusal: str,
    **kwargs: Any,
) -> None:
    body = await call(deployment, method, path, token, expect, **kwargs)
    assert body["refusal"] == refusal, body


async def stewarded(deployment: Deployment) -> tuple[dict[str, str], str]:
    """Mei registers and sets up a profile for Pa by his number, in Malay, as he asked."""
    mei = await register_by_phone(deployment, MEI, "Mei")
    made = await call(
        deployment,
        "POST",
        "/profiles/for-someone",
        mei["token"],
        201,
        json={
            "patient_phone_e164": PA,
            "display_name": "Pa",
            "language": "ms",
            "consent": CONSENT,
            "basis": "patient_asked",
            "relationship": "daughter",
        },
    )
    return mei, made["profile_id"]


async def confirm_card(
    deployment: Deployment, token: str, profile_id: str, card: dict[str, Any], **corrections: Any
) -> dict[str, Any]:
    """His one tap on a review card: every field confirmed, the corrections made."""
    decisions: list[dict[str, Any]] = []
    for field in card["fields"]:
        if field["attribute"] in corrections:
            decisions.append(
                {
                    "field_id": field["field_id"],
                    "decision": "corrected",
                    "corrected_value": corrections[field["attribute"]],
                }
            )
        else:
            decisions.append({"field_id": field["field_id"], "decision": "confirmed"})
    minted = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/confirmations",
        token,
        201,
        json={"subject": "review_card", "card_id": card["card_id"], "decisions": decisions},
    )
    confirmed: dict[str, Any] = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/review-cards/{card['card_id']}/confirm",
        token,
        200,
        json={"decisions": decisions, "confirmation_id": minted["confirmation_id"]},
    )
    return confirmed


async def add_paper(
    deployment: Deployment, token: str, profile_id: str, label: str, kind: str, **corrections: Any
) -> dict[str, Any]:
    """A paper added to the sitting and its card confirmed."""
    added: dict[str, Any] = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/biography/papers",
        token,
        201,
        json=paper(label, kind),
    )
    await confirm_card(deployment, token, profile_id, added["card"], **corrections)
    return added


async def through_the_papers(
    deployment: Deployment,
    token: str,
    profile_id: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Open a sitting, save the settings, add and confirm the lipid report (the misread
    triglycerides corrected) and the warfarin label. Where it stands after."""
    await call(deployment, "POST", f"/profiles/{profile_id}/biography", token, 201)
    await call(
        deployment,
        "PUT",
        f"/profiles/{profile_id}/settings",
        token,
        200,
        json=settings or SETTINGS,
    )
    await add_paper(deployment, token, profile_id, LIPID_PANEL, "lab_result", triglycerides=54)
    await add_paper(deployment, token, profile_id, WARFARIN_LABEL, "medicine")
    view: dict[str, Any] = await call(
        deployment, "GET", f"/profiles/{profile_id}/biography", token, 200
    )
    return view


def answers(
    view: dict[str, Any], no: Callable[[str], bool] = lambda line: False
) -> list[dict[str, str]]:
    """Every read-back line answered: yes, but no where `no` says so."""
    return [
        {"fact_id": line["fact_id"], "answer": "no" if no(line["line"]) else "yes"}
        for line in view["read_back"]
    ]
