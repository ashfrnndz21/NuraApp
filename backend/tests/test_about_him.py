"""About him, to someone else (D1): on a key that is not his, the lines his chief's Home reads
are said about him by name — the catalogues' twins, in English, Malay and Chinese — and on his
own key nothing changes."""

from __future__ import annotations

import re

import pytest

from app.channels.about_him import LANGUAGES, TO_HIM, Reader, twins
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
    await let_in(deployment, pa, profile_id, MEI, scopes, "daughter", role="caregiver")
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
