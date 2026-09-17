"""#185: his yes binds the role and the window he agreed to, not only the person and the
parts. `POST /consents/sharing` and its preview always name a role and a window; the words
he reads name both, in every language Nura speaks, and a key cut under that consent is
refused for a different role or for a window that outlasts it (`app.keys.grants.grant_key`,
`KeyNotAsAgreed`). This is the real client's own request shape
(`web/src/api/family.ts::SharingBody`) — not a test-only convenience, per the independent
review that found the web client sent neither and #185 was therefore unmet for any real
family.
"""

from __future__ import annotations

from app.family.strings import ROLE_WORDS, WINDOW_LINES
from app.keys.scopes import KeyRole, KeyWindow
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591140001"
KIT = "+6591140002"


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    return pa, await own_profile(deployment, pa)


def _body(*, role: str, window: str, scopes: list[str] | None = None, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "holder_phone_e164": KIT,
        "holder_display_name": "Kit",
        "scopes": scopes or ["medicines", "visits"],
        "role": role,
        "window": window,
        "relationship": "son",
        "language": "en",
    }
    body.update(overrides)
    return body


async def _agree(
    deployment: Deployment,
    pa: dict[str, str],
    profile_id: str,
    *,
    role: str,
    window: str,
    scopes: list[str] | None = None,
) -> dict[str, object]:
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json=_body(role=role, window=window, scopes=scopes, captured_via="app"),
        headers=bearer(pa["token"]),
    )
    assert agreed.status_code == 201, agreed.text
    consent: dict[str, object] = agreed.json()
    return consent


async def _refusals(deployment: Deployment, pa: dict[str, str], profile_id: str) -> set[str]:
    trail = await deployment.client.get(
        f"/profiles/{profile_id}/audit", headers=bearer(pa["token"]), params={"limit": 500}
    )
    assert trail.status_code == 200
    return {row["refused_because"] for row in trail.json() if row["outcome"] == "refused"}


async def test_role_and_window_are_required_to_let_someone_in(deployment: Deployment) -> None:
    """Letting someone in without saying what they are to him and for how long is not a
    thing (#185): both are required on the wire, on the preview and on the agreement, the
    same shape the real client (`web/src/api/family.ts`) always sends."""
    pa, profile_id = await _pa(deployment)
    no_role = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json=_body(role="caregiver", window="always", captured_via="app") | {"role": None},
        headers=bearer(pa["token"]),
    )
    assert no_role.status_code == 422
    no_window = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing/preview",
        json=_body(role="caregiver", window="always") | {"window": None},
        headers=bearer(pa["token"]),
    )
    assert no_window.status_code == 422


async def test_a_key_cut_as_a_different_role_than_the_consent_is_refused_on_his_trail(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _agree(deployment, pa, profile_id, role="caregiver", window="always")

    wrong_role = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": KIT,
            "role": "viewer",
            "scopes": ["medicines", "visits"],
        },
        headers=bearer(pa["token"]),
    )
    assert wrong_role.status_code == 403
    assert wrong_role.json() == {"refusal": "KeyNotAsAgreed"}
    assert "KeyNotAsAgreed" in await _refusals(deployment, pa, profile_id)

    # The role he actually agreed to still cuts the key.
    matched = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={
            "holder_phone_e164": KIT,
            "role": "caregiver",
            "scopes": ["medicines", "visits"],
        },
        headers=bearer(pa["token"]),
    )
    assert matched.status_code == 201, matched.text
    assert matched.json()["role"] == "caregiver"


async def test_a_key_cut_for_longer_than_the_consents_window_is_refused_on_his_trail(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _agree(
        deployment, pa, profile_id, role="viewer", window="thirty_days", scopes=["medicines"]
    )

    longer = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KIT, "role": "viewer", "window": "always"},
        headers=bearer(pa["token"]),
    )
    assert longer.status_code == 403
    assert longer.json() == {"refusal": "KeyNotAsAgreed"}
    assert "KeyNotAsAgreed" in await _refusals(deployment, pa, profile_id)

    # A window no longer than the one he agreed to is never refused for that reason.
    same = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KIT, "role": "viewer", "window": "thirty_days"},
        headers=bearer(pa["token"]),
    )
    assert same.status_code == 201, same.text
    assert same.json()["expires_at"] is not None


async def test_a_shorter_window_than_the_consent_is_never_refused_for_that(
    deployment: Deployment,
) -> None:
    pa, profile_id = await _pa(deployment)
    await _agree(
        deployment, pa, profile_id, role="viewer", window="thirty_days", scopes=["medicines"]
    )
    shorter = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KIT, "role": "viewer", "window": "one_day"},
        headers=bearer(pa["token"]),
    )
    assert shorter.status_code == 201, shorter.text


async def test_a_role_or_window_cannot_be_recorded_against_an_older_wording(
    deployment: Deployment,
) -> None:
    """Only the current wording (version 3) renders `{role_line}`/`{window_line}`; naming a
    role or a window against an older version would enforce a constraint the words the
    patient actually read never stated (independent review of #185). Since role and window
    are always named now, this means a `SHARE_WITH_PERSON` consent can only ever be recorded
    at the current wording — capturing a past agreement at an older version, offered by
    `text_version` for other purposes, is not offered here any more."""
    pa, profile_id = await _pa(deployment)
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json=_body(
            role="caregiver",
            window="always",
            scopes=["medicines"],
            captured_via="app",
            wording_version="2",
        ),
        headers=bearer(pa["token"]),
    )
    assert refused.status_code == 400
    assert refused.json() == {"refusal": "RoleWindowNeedCurrentWording"}
    assert "RoleWindowNeedCurrentWording" in await _refusals(deployment, pa, profile_id)


async def test_the_consents_words_name_the_role_and_the_window_in_every_language(
    deployment: Deployment,
) -> None:
    for number, language in enumerate(("en", "ms", "zh")):
        phone = f"+659114100{number}"
        pa = await register_by_phone(deployment, phone, "Pa", language)
        profile_id = await own_profile(deployment, pa, language=language)
        preview = await deployment.client.post(
            f"/profiles/{profile_id}/consents/sharing/preview",
            json=_body(
                role="caregiver", window="thirty_days", scopes=["medicines", "visits"], language=language
            ),
            headers=bearer(pa["token"]),
        )
        assert preview.status_code == 200, preview.text
        words = "\n".join(preview.json()["lines"])
        assert ROLE_WORDS[language][KeyRole.CAREGIVER] in words, (language, words)
        assert WINDOW_LINES[language][KeyWindow.THIRTY_DAYS].format(name="Kit") in words, (
            language,
            words,
        )

        agreed = await deployment.client.post(
            f"/profiles/{profile_id}/consents/sharing",
            json=_body(
                role="caregiver",
                window="thirty_days",
                scopes=["medicines", "visits"],
                language=language,
                captured_via="app",
                wording_version=preview.json()["wording_version"],
            ),
            headers=bearer(pa["token"]),
        )
        assert agreed.status_code == 201, agreed.text
        # The preview and the consent render the words the same way (#185's digest is the
        # same rendering, so what he read first is what was kept).
        assert agreed.json()["wording_text"] == words
