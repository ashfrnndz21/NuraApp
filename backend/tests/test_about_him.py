"""About him, to someone else (D1): on a key that is not his, the lines his chief's Home reads
are said about him by name — the catalogues' twins, in English, Malay and Chinese — and on his
own key nothing changes."""

from __future__ import annotations

import re

import pytest

from app.channels.about_him import LANGUAGES, TO_HIM, Reader, twins
from app.consent.texts import CONSENT_THEIRS, TEXTS
from app.safety.boundary import BOUNDARY_THEIRS, Surface, boundary_line
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6598760451"
MEI = "+6598760452"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_twin_speaks_to_him_and_every_twin_names_only_its_own_slots(language: str) -> None:
    written = [(original, twin) for original, twin in twins(language) if original != twin]
    assert written, "the twins are written"
    for original, twin in written:
        assert not TO_HIM[language].search(twin), (language, twin)
        slots = set(re.findall(r"\{(\w+)\}", twin)) - {"patient"}
        assert slots <= set(re.findall(r"\{(\w+)\}", original)), (original, twin)


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_boundary_twins_are_the_boundary_as_it_is_said(language: str) -> None:
    said = boundary_line(Surface.STATE_POSTURE, language).split("\n")
    for original, _twin in BOUNDARY_THEIRS[language].values():
        assert original in said


@pytest.mark.parametrize(
    ("language", "line", "about_him"),
    [
        (
            "en",
            "Your blood pressure today was 138 over 84.",
            "Pa's blood pressure today was 138 over 84.",
        ),
        (
            "en",
            "Take 1 tablet of your blood pressure tablet with breakfast.",
            "Pa takes 1 tablet of Pa's blood pressure tablet with breakfast.",
        ),
        ("en", "Nothing needs you today.", "Nothing needs doing for Pa today."),
        ("en", "Taken", "Pa took it"),
        ("en", "your blood pressure tablet", "Pa's blood pressure tablet"),
        (
            "en",
            "Nura put your day in order.\nThis is not a doctor's advice.\nAsk your doctor.",
            "Nura put Pa's day in order.\nThis is not a doctor's advice.\nAsk Pa's doctor.",
        ),
        (
            "ms",
            "Tekanan darah anda hari ini 138 atas 84.",
            "Tekanan darah Pa hari ini 138 atas 84.",
        ),
        ("zh", "您今天的血压是138比84。", "Pa今天的血压是138比84。"),
    ],
)
def test_a_line_to_him_is_said_about_him_by_name(language: str, line: str, about_him: str) -> None:
    assert Reader(his=False, name="Pa", language=language).says(line) == about_him
    assert Reader(his=True).says(line) == line


def test_a_line_with_no_twin_is_left_and_a_card_of_his_with_one_is_not_shown() -> None:
    reader = Reader(his=False, name="Pa", language="en")
    assert reader.says("Your own free words to him") == "Your own free words to him"
    assert reader.speaks_to_him(["Pa's day", ["Your own free words"]])
    assert not reader.speaks_to_him(["Pa's blood pressure today"])


async def test_his_state_to_him_and_about_him_to_his_daughter(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    scopes = ["medicines", "records", "family"]
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": scopes},
        headers=his,
    )
    assert granted.status_code == 201, granted.text

    to_him = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert to_him.status_code == 200, to_him.text
    about = await deployment.client.get(
        f"/profiles/{profile_id}/state", headers=bearer(mei["token"])
    )
    assert about.status_code == 200, about.text
    assert to_him.json()["boundary"].startswith("Nura put your day in order.")
    assert about.json()["boundary"].startswith("Nura put Pa's day in order.")
    assert about.json()["boundary"].endswith("Ask Pa's doctor.")
    if to_him.json()["line"]:
        assert not TO_HIM["en"].search(about.json()["line"])


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_consent_twins_are_the_consent_wording_as_it_is_said(language: str) -> None:
    """`CONSENT_THEIRS` quotes the wordings verbatim, the way `BOUNDARY_THEIRS` quotes the
    boundary: a change to a wording that leaves its twin behind is caught here."""
    said = [text.summary for text in TEXTS if text.language == language]
    for original, _twin in CONSENT_THEIRS[language].values():
        assert any(original in summary for summary in said), (language, original)


@pytest.mark.parametrize(
    ("language", "line", "about_him"),
    [
        (
            "en",
            "Mei is the person who runs your care.",
            "Mei is the person who runs Pa's care.",
        ),
        ("en", "- your medicines", "- Pa's medicines"),
        (
            "en",
            "Mei can see them until you say stop.",
            "Mei can see them until Pa says stop.",
        ),
        (
            "en",
            "You are letting Mei, your daughter, see some of your record.",
            "Pa is letting Mei, Pa's daughter, see some of Pa's record.",
        ),
        ("en", "You can stop this at any time.", "Pa can stop this at any time."),
        (
            "en",
            "Nura keeps your papers, your medicines and your blood pressure book.",
            "Nura keeps Pa's papers, Pa's medicines and Pa's blood pressure book.",
        ),
        (
            "en",
            "You can tell Nura to stop at any time.",
            "Pa can tell Nura to stop at any time.",
        ),
        (
            "en",
            "The papers Nura already has stay in your record.",
            "The papers Nura already has stay in Pa's record.",
        ),
        (
            "ms",
            "Mei ialah orang yang mengurus penjagaan anda.",
            "Mei ialah orang yang mengurus penjagaan Pa.",
        ),
        ("ms", "- ubat anda", "- ubat Pa"),
        ("zh", "Mei是照顾您的主要家人。", "Mei是照顾Pa的主要家人。"),
        ("zh", "- 您的药", "- Pa的药"),
    ],
)
def test_the_family_and_consent_lines_are_said_about_him_by_name(
    language: str, line: str, about_him: str
) -> None:
    """The two paths #210 fixed (the family's grant lines) and the one #214 fixed (the
    consent wording) go through the same reader as everything else, and are said about him
    by name on a key that is not his — never left in his voice."""
    assert Reader(his=False, name="Pa", language=language).says(line) == about_him
    assert Reader(his=True).says(line) == line


async def test_grants_and_consents_are_said_about_him_by_name_on_a_key_that_is_not_his(
    deployment: Deployment,
) -> None:
    """#210: the family's grant lines (`GET /grants`). #214: the consent wording (`GET
    /consents`) — his own account-opening agreement and the one that let her in, both quoted
    verbatim on his own key and about him by name on hers."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    mei = await register_by_phone(deployment, MEI, "Mei")
    scopes = ["medicines", "records", "family"]
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "chief", "scopes": scopes},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    hers = bearer(mei["token"])

    his_grants = await deployment.client.get(f"/profiles/{profile_id}/grants", headers=his)
    assert his_grants.status_code == 200, his_grants.text
    her_grants = await deployment.client.get(f"/profiles/{profile_id}/grants", headers=hers)
    assert her_grants.status_code == 200, her_grants.text
    her_lines = [line for grant in her_grants.json() for line in grant["lines"]]
    assert her_lines, "the grants have lines to check"
    for line in her_lines:
        assert not TO_HIM["en"].search(line), line
    assert any("Mei is the person who runs Pa's care." in line for line in her_lines) or any(
        "the person who runs Pa's care" in line for line in her_lines
    )
    his_lines = [line for grant in his_grants.json() for line in grant["lines"]]
    assert any(TO_HIM["en"].search(line) for line in his_lines), "his own key stays in his voice"

    his_consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=his)
    assert his_consents.status_code == 200, his_consents.text
    her_consents = await deployment.client.get(f"/profiles/{profile_id}/consents", headers=hers)
    assert her_consents.status_code == 200, her_consents.text
    assert len(her_consents.json()) >= 2, "his own agreement and the one that let her in"
    for consent in her_consents.json():
        for consent_line in consent["wording_text"].split("\n"):
            assert not TO_HIM["en"].search(consent_line), consent_line
    assert any(
        TO_HIM["en"].search(consent_line)
        for consent in his_consents.json()
        for consent_line in consent["wording_text"].split("\n")
    ), "his own key still reads his own words"
