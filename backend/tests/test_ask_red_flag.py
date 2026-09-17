"""A red word typed into Ask or search (D1: the bar on top of his Today, "Ask about Pa" on
hers) takes the red-flag path before anything is looked up, exactly as the same word tapped on
the feeling cloud: the flag written and kept, the family told, the urgent card said back with
"Nura does not decide what is wrong." last — in English, Malay and Chinese. A question with no
red word is answered as before."""

from __future__ import annotations

import pytest

from app.safety.boundary import URGENT_CLOSING
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6598760431"
MEI = "+6598760432"
KOW = "+6598760433"
SITI = "+6598760434"


@pytest.mark.parametrize(
    ("language", "question", "plain"),
    [
        ("en", "My chest is tight", "what was my blood pressure"),
        ("ms", "Dada saya ketat", "berapa tekanan darah saya"),
        ("zh", "我胸口闷", "我的血压是多少"),
    ],
)
async def test_a_red_word_in_a_question_takes_the_red_flag_path_first(
    deployment: Deployment, language: str, question: str, plain: str
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language=language)
    his = bearer(pa["token"])
    client = deployment.client

    red = await client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": question, "language": language},
        headers=his,
    )
    assert red.status_code == 200, red.text
    flagged = red.json()["red_flag"]
    assert flagged is not None
    assert flagged["red_flag"] is True and flagged["word"] == "chest_tightness"
    assert flagged["flag_id"], "the flag is written"
    assert flagged["opens"] == "not_feeling_well" and flagged["question"] is None
    assert flagged["language"] == language
    assert flagged["lines"][-1] == URGENT_CLOSING[language]
    # Nothing looked up after it: the card is the whole answer.
    assert red.json()["question_artifact_id"] is None and red.json()["lines"] == []

    # The flag is there to be read back, as a tap on the cloud leaves it: a second tap of the
    # same word is its own moment, and the question's flag is not undone by the answer after it.
    again = await client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "chest_tightness"}, headers=his
    )
    assert again.status_code == 201, again.text
    assert again.json()["flag_id"] != flagged["flag_id"]

    none = await client.post(
        f"/profiles/{profile_id}/ask", json={"question": plain, "language": language}, headers=his
    )
    assert none.status_code == 200, none.text
    assert none.json()["red_flag"] is None


async def test_a_family_red_word_about_him_takes_the_same_path_or_is_refused_as_a_tap_is(
    deployment: Deployment,
) -> None:
    """ "Ask about Pa" on her screens. A key holding his emergency card raises his flag from her
    words, as her tap on the button would; a key he gave without it is refused exactly as that
    tap is (`OutOfScope`, emergency) — never answered in its place, so the app shows the kept
    card and the refusal named."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    hers = bearer(mei["token"])
    scopes = ["medicines", "records", "family", "ask"]
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter", role="caregiver")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": scopes},
        headers=his,
    )
    assert granted.status_code == 201, granted.text

    refused = await deployment.client.post(
        f"/profiles/{profile_id}/ask", json={"question": "Pa fell in the bathroom"}, headers=hers
    )
    tapped = await deployment.client.post(
        f"/profiles/{profile_id}/feelings", json={"word": "fall"}, headers=hers
    )
    assert refused.status_code == tapped.status_code == 403, refused.text
    assert refused.json() == tapped.json() == {"refusal": "OutOfScope", "scope": "emergency"}

    plain = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "what was his blood pressure"},
        headers=hers,
    )
    assert plain.status_code == 200, plain.text
    assert plain.json()["red_flag"] is None

    # Ah Kow, his son, holds the emergency card as well: his words raise the flag.
    kow = await register_by_phone(deployment, KOW, "Ah Kow")
    with_card = [*scopes, "emergency"]
    await let_in(deployment, pa, profile_id, KOW, with_card, "son", holder_display_name="Ah Kow", role="caregiver")
    granted_card = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": KOW, "role": "caregiver", "scopes": with_card},
        headers=his,
    )
    assert granted_card.status_code == 201, granted_card.text
    asked = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "Pa fell in the bathroom"},
        headers=bearer(kow["token"]),
    )
    assert asked.status_code == 200, asked.text
    flagged = asked.json()["red_flag"]
    assert flagged is not None and flagged["red_flag"] is True and flagged["word"] == "fall"
    assert flagged["flag_id"] and flagged["lines"][-1] == URGENT_CLOSING["en"]


async def test_a_helper_holding_the_card_but_not_ask_still_gets_the_urgent_card(
    deployment: Deployment,
) -> None:
    """A helper's key holds his emergency card and not ask. Her red word raises his flag and
    she is shown what to do now — never a refusal for the lookup that does not follow."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    siti = await register_by_phone(deployment, SITI, "Siti")
    scopes = ["medicines", "emergency"]
    await let_in(deployment, pa, profile_id, SITI, scopes, "helper", holder_display_name="Siti", role="helper")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": SITI, "role": "helper", "scopes": scopes},
        headers=bearer(pa["token"]),
    )
    assert granted.status_code == 201, granted.text
    asked = await deployment.client.post(
        f"/profiles/{profile_id}/ask",
        json={"question": "Pa fell in the bathroom"},
        headers=bearer(siti["token"]),
    )
    assert asked.status_code == 200, asked.text
    flagged = asked.json()["red_flag"]
    assert flagged is not None and flagged["red_flag"] is True and flagged["flag_id"]
    assert flagged["lines"][-1] == URGENT_CLOSING["en"]
