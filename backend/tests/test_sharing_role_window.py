"""#185: his yes binds the role and the window he agreed to, not only the person and the
parts. `POST /consents/sharing` may now name a role and a window; when it does, a key cut
under that consent is refused for a different role or for a window that outlasts it
(`app.keys.grants.grant_key`, `KeyNotAsAgreed`), and the words he read name both, in every
language Nura speaks. A consent that does not name them — the shape every caller used before
this story — still constrains neither, so nothing here narrows what already worked.
"""

from __future__ import annotations

from app.family.strings import ROLE_WORDS, WINDOW_LINES
from app.keys.scopes import KeyRole, KeyWindow
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591140001"
KIT = "+6591140002"


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, "Pa")
    return pa, await own_profile(deployment, pa)


async def _agree(
    deployment: Deployment,
    pa: dict[str, str],
    profile_id: str,
    *,
    role: str | None,
    window: str | None,
    scopes: list[str] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "holder_phone_e164": KIT,
        "holder_display_name": "Kit",
        "scopes": scopes or ["medicines", "visits"],
        "relationship": "son",
        "language": "en",
        "captured_via": "app",
    }
    if role is not None:
        body["role"] = role
    if window is not None:
        body["window"] = window
    agreed = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing", json=body, headers=bearer(pa["token"])
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
    patient actually read never stated (independent review of #185)."""
    pa, profile_id = await _pa(deployment)
    refused = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={
            "holder_phone_e164": KIT,
            "holder_display_name": "Kit",
            "scopes": ["medicines"],
            "role": "caregiver",
            "window": "always",
            "relationship": "son",
            "language": "en",
            "captured_via": "app",
            "wording_version": "2",
        },
        headers=bearer(pa["token"]),
    )
    assert refused.status_code == 400
    assert refused.json() == {"refusal": "RoleWindowNeedCurrentWording"}

    # The same ask, without naming a role or a window, is fine against the older version.
    fine = await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={
            "holder_phone_e164": KIT,
            "holder_display_name": "Kit",
            "scopes": ["medicines"],
            "relationship": "son",
            "language": "en",
            "captured_via": "app",
            "wording_version": "2",
        },
        headers=bearer(pa["token"]),
    )
    assert fine.status_code == 201, fine.text


async def test_a_consent_naming_neither_constrains_neither(deployment: Deployment) -> None:
    """The shape every caller used before #185: a key of any role, for any window, still
    rests on it — nothing here narrows what already worked."""
    pa, profile_id = await _pa(deployment)
    await let_in(deployment, pa, profile_id, KIT, ["medicines"], relationship="son")
    cut = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KIT, "role": "chief", "window": "always"},
        headers=bearer(pa["token"]),
    )
    assert cut.status_code == 201, cut.text


async def test_the_consents_words_name_the_role_and_the_window_in_every_language(
    deployment: Deployment,
) -> None:
    for number, language in enumerate(("en", "ms", "zh")):
        phone = f"+659114100{number}"
        pa = await register_by_phone(deployment, phone, "Pa", language)
        profile_id = await own_profile(deployment, pa, language=language)
        preview = await deployment.client.post(
            f"/profiles/{profile_id}/consents/sharing/preview",
            json={
                "holder_phone_e164": KIT,
                "holder_display_name": "Kit",
                "scopes": ["medicines", "visits"],
                "role": "caregiver",
                "window": "thirty_days",
                "relationship": "son",
                "language": language,
            },
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
            json={
                "holder_phone_e164": KIT,
                "holder_display_name": "Kit",
                "scopes": ["medicines", "visits"],
                "role": "caregiver",
                "window": "thirty_days",
                "relationship": "son",
                "language": language,
                "captured_via": "app",
                "wording_version": preview.json()["wording_version"],
            },
            headers=bearer(pa["token"]),
        )
        assert agreed.status_code == 201, agreed.text
        # The preview and the consent render the words the same way (#185's digest is the
        # same rendering, so what he read first is what was kept).
        assert agreed.json()["wording_text"] == words
