"""The boundary copy on every inferring surface (E16-01).

    Acceptance: organises, prepares, surfaces patterns to discuss; does not diagnose or treat.

The register `INFERRING_SURFACES` has words in every language Nura speaks, every line passes
docs/plain-words.md, no line in any language tells him to start, stop or change a medicine or
names a diagnosis, and the register agrees with the table in
docs/trust/samd-boundary-review.md. The line is structure: a rendered row of an inferring
surface cannot be written without it (`render_from_state`), the not-feeling-well card may
carry the discharge letter's own words with the line still last, and State's posture at
`GET /profiles/{id}/state` carries the line in the profile's language. The feed's learning
cards, the other inferring surface on main, are held to it in `tests/test_feed.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.regions import Region
from app.safety.boundary import (
    INFERRING_SURFACES,
    LANGUAGES,
    NOT_ADVICE,
    URGENT_CLOSING,
    WHAT_NURA_DID,
    Surface,
    boundary_line,
    boundary_lines,
    is_boundary_line,
)
from app.safety.plain_words import verify
from app.state.service import NoBoundaryLine
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.support import OPENING_CONSENT, render_card

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "00-MASTER-BUILD-SPEC.md"
REVIEW = REPO / "docs" / "trust" / "samd-boundary-review.md"

PA = "+6591110001"
MEI = "+6591110002"

# Anything that starts, stops or changes a medicine, or names a diagnosis, in each language.
FORBIDDEN: dict[str, re.Pattern[str]] = {
    "en": re.compile(
        r"\b(start|stop|change|take|increase|reduce|double|halve|skip)\b.*"
        r"\b(medicine|tablet|pill|insulin|dose)\b|\byou have\b|\bdiagnos",
        re.IGNORECASE,
    ),
    "ms": re.compile(
        r"\b(mula|berhenti|henti|ubah|tukar|ambil|makan|tambah|kurang|gandakan|langkau)\b.*"
        r"\b(ubat|pil|insulin|dos)\b|\banda (ada|menghidap)\b|\bdiagnos|\bpenyakit\b",
        re.IGNORECASE,
    ),
    "zh": re.compile(r"(开始|停|换|改|吃|加|减|跳过).*(药|片|胰岛素|剂量)|您有|诊断|您得了"),
}


async def _pa(session: AsyncSession) -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=PA)
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


def test_every_inferring_surface_has_its_words_in_every_language() -> None:
    assert set(INFERRING_SURFACES) == set(Surface)
    for language in LANGUAGES:
        assert set(WHAT_NURA_DID[language]) == set(Surface), language
        assert len(NOT_ADVICE[language]) == 2
        for surface in INFERRING_SURFACES:
            lines = boundary_lines(surface, language, doctor="Dr Tan")
            assert len(lines) == (4 if surface is Surface.NOT_FEELING_WELL else 3), (
                surface,
                language,
            )
            assert all(lines) and "Dr Tan" in lines[-1], (surface, language)


def test_every_line_passes_plain_words_in_its_language() -> None:
    failures = [
        (surface.value, language, finding.problem)
        for language in LANGUAGES
        for surface in INFERRING_SURFACES
        for told in (None, "Ash")
        for line in boundary_lines(surface, language, doctor="Dr Tan", told=told)
        for finding in verify(line, language)
        if finding.severity != "note"
    ]
    assert failures == []


def test_the_last_two_lines_are_the_same_words_on_every_surface() -> None:
    """Rule 13: once it is "This is not a doctor's advice. Ask Dr Tan.", it is never anything
    else, whichever surface he is on, whatever else the card carries."""
    for language in LANGUAGES:
        endings = {boundary_lines(s, language, doctor="Dr Tan")[-2:] for s in INFERRING_SURFACES}
        endings.add(
            boundary_lines(
                Surface.NOT_FEELING_WELL,
                language,
                doctor="Dr Tan",
                letter="Come back today.",
                told="Ash",
            )[-2:]
        )
        assert len(endings) == 1, language
    assert boundary_lines(Surface.STATE_POSTURE, "en", doctor="Dr Tan")[-2:] == (
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_line_starts_stops_or_changes_a_medicine_or_names_a_diagnosis(language: str) -> None:
    for surface in INFERRING_SURFACES:
        text = boundary_line(surface, language, doctor="Dr Tan", told="Ash")
        assert not FORBIDDEN[language].search(text), (surface, language, text)


def test_without_a_named_doctor_the_line_says_your_doctor() -> None:
    assert boundary_line(Surface.QUESTIONS) == (
        "Nura wrote these questions for you to ask your doctor.\n"
        "This is not a doctor's advice.\n"
        "Ask your doctor."
    )
    assert (
        boundary_line(Surface.STATE_POSTURE, "en").splitlines()[0] == "Nura put your day in order."
    )
    assert boundary_lines(Surface.SUMMARY, "ms")[-1] == "Tanya doktor anda."
    assert boundary_lines(Surface.SUMMARY, "zh")[-1] == "问您的医生。"
    # A language Nura does not speak yet falls back to English rather than to nothing.
    assert boundary_line(Surface.BRIEF, "ta") == boundary_line(Surface.BRIEF, "en")


def test_the_not_feeling_well_card_reassures_first_and_may_carry_the_letters_own_words() -> None:
    """Rule 9 first; then what Nura did; then, where a Fact holds it, the discharge letter's
    own instruction in the letter's name; the boundary last. No other surface may carry a
    letter."""
    assert boundary_lines(Surface.NOT_FEELING_WELL, "en", doctor="Dr Tan") == (
        "You did right to say so.",
        "Nura wrote down how you feel.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    )
    with_letter = boundary_lines(
        Surface.NOT_FEELING_WELL,
        "en",
        doctor="Dr Tan",
        told="Ash",
        letter="If you gain 1 kg in two days, come back the same day.",
    )
    assert with_letter == (
        "Ash knows now.",
        "Nura wrote down how you feel.",
        "If you gain 1 kg in two days, come back the same day.",
        "Dr Tan wrote this in your hospital letter.",
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    )
    assert boundary_lines(Surface.NOT_FEELING_WELL, "ms", told="Mei")[0] == "Mei sudah tahu."
    assert boundary_lines(Surface.NOT_FEELING_WELL, "zh")[0] == "您说出来是对的。"
    with pytest.raises(ValueError):
        boundary_lines(Surface.BRIEF, "en", letter="Come back today.")


def test_is_boundary_line_recognises_the_register_and_nothing_else() -> None:
    for language in LANGUAGES:
        for surface in INFERRING_SURFACES:
            for doctor in (None, "Dr Tan", "Dr Lim Wei"):
                assert is_boundary_line(surface, boundary_line(surface, language, doctor=doctor))
    ok = boundary_line(Surface.NOT_FEELING_WELL, "en", told="Ash", letter="Come back today.")
    assert is_boundary_line(Surface.NOT_FEELING_WELL, ok)
    assert not is_boundary_line(Surface.BRIEF, boundary_line(Surface.QUESTIONS))
    assert not is_boundary_line(Surface.BRIEF, None)
    assert not is_boundary_line(Surface.BRIEF, "")
    assert not is_boundary_line(Surface.BRIEF, "Nura prepared this from your papers.")
    assert not is_boundary_line(Surface.BRIEF, "Ask Dr Tan.\nThis is not a doctor's advice.")
    assert not is_boundary_line(
        Surface.BRIEF, "Nura prepared this from your papers.\nTake one more tablet.\nAsk Dr Tan."
    )
    # A letter's words with the line that names the letter missing: not the register's line.
    assert not is_boundary_line(
        Surface.NOT_FEELING_WELL,
        "Ash knows now.\nNura wrote down how you feel.\nCome back today.\n"
        "This is not a doctor's advice.\nAsk Dr Tan.",
    )


async def test_a_rendered_row_of_an_inferring_surface_cannot_be_written_without_its_line(
    sg: AsyncSession,
) -> None:
    """The line is structure, like the State id: `render_from_state` refuses the row."""
    owner = await _pa(sg)
    with pytest.raises(NoBoundaryLine):
        await render_card(sg, owner, kind="brief", surface=Surface.BRIEF)
    with pytest.raises(NoBoundaryLine):
        await render_card(sg, owner, kind="brief", surface=Surface.BRIEF, boundary="Ask Dr Tan.")
    with pytest.raises(NoBoundaryLine):
        await render_card(
            sg, owner, kind="brief", surface=Surface.BRIEF, boundary=boundary_line(Surface.SUMMARY)
        )
    # A row that infers nothing names no surface and carries no line.
    with pytest.raises(NoBoundaryLine):
        await render_card(sg, owner, kind="reminder", boundary=boundary_line(Surface.BRIEF))
    plain = await render_card(sg, owner, kind="reminder")
    assert plain.boundary is None
    line = boundary_line(Surface.BRIEF, "ms", doctor="Dr Tan")
    card = await render_card(sg, owner, kind="brief", surface=Surface.BRIEF, boundary=line)
    assert card.boundary == line and card.state_id is not None


def test_the_register_matches_the_spec_and_the_samd_review_table() -> None:
    """Section 10 of the spec asks for the line on every inferring surface; the SaMD review
    lists them one row each, by code. The register is that list, no more and no less."""
    section_10 = SPEC.read_text(encoding="utf-8").split("## 10.")[1].split("## 11.")[0]
    assert "boundary line on every inferring surface" in section_10
    review = REVIEW.read_text(encoding="utf-8")
    in_table = set(re.findall(r"^\| `([a-z_]+)` \|", review, re.MULTILINE))
    assert in_table == {surface.value for surface in INFERRING_SURFACES}
    # The review quotes the register's English lines verbatim.
    for surface in INFERRING_SURFACES:
        assert WHAT_NURA_DID["en"][surface].replace("{doctor}", "Dr Tan") in review, surface


async def test_state_carries_the_boundary_in_the_profiles_language(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])

    seen = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert seen.status_code == 200, seen.text
    assert seen.json()["boundary"] == boundary_line(Surface.STATE_POSTURE, "ms")
    assert seen.json()["boundary"].splitlines() == [
        "Nura menyusun hari anda.",
        "Ini bukan nasihat doktor.",
        "Tanya doktor anda.",
    ]

    asked = await deployment.client.get(
        f"/profiles/{profile_id}/state", params={"language": "zh"}, headers=his
    )
    assert asked.json()["boundary"] == boundary_line(Surface.STATE_POSTURE, "zh")

    # A caregiver reading State through her key sees the same line: the boundary is on the
    # surface, not on the person.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, ["records"], "daughter")
    granted = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["records"]},
        headers=his,
    )
    assert granted.status_code == 201, granted.text
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/state", headers=bearer(mei["token"])
    )
    assert hers.status_code == 200, hers.text
    assert hers.json()["boundary"] == seen.json()["boundary"]


def test_an_urgent_card_closes_on_one_line_and_never_sends_him_to_his_doctor() -> None:
    """A red flag's not-feeling-well card: the reassurance, the calls (the card's own lines,
    between), and one closing line. After an emergency number nothing says "Ask your doctor."."""
    assert boundary_lines(Surface.NOT_FEELING_WELL, "en", told="Mei", urgent=True) == (
        "Mei knows now.",
        "Nura does not decide what is wrong.",
    )
    assert boundary_lines(Surface.NOT_FEELING_WELL, "en", urgent=True) == (
        "You did right to say so.",
        "Nura does not decide what is wrong.",
    )
    for language in LANGUAGES:
        urgent = boundary_lines(Surface.NOT_FEELING_WELL, language, told="Mei", urgent=True)
        assert len(urgent) == 2 and urgent[-1] == URGENT_CLOSING[language]
        assert NOT_ADVICE[language][0] not in urgent
        assert is_boundary_line(Surface.NOT_FEELING_WELL, "\n".join(urgent))
        assert not [f for f in verify(urgent[-1], language) if f.severity == "fail"]
        # The ordinary card keeps the standard closing.
        ordinary = boundary_lines(Surface.NOT_FEELING_WELL, language, told="Mei")
        assert ordinary[-2] == NOT_ADVICE[language][0] and URGENT_CLOSING[language] not in ordinary
    lettered = boundary_line(
        Surface.NOT_FEELING_WELL, "en", told="Ash", letter="Come back today.", urgent=True
    )
    assert is_boundary_line(Surface.NOT_FEELING_WELL, lettered)
    assert not is_boundary_line(Surface.NOT_FEELING_WELL, "Nura does not decide what is wrong.")
    assert not is_boundary_line(
        Surface.NOT_FEELING_WELL,
        "Mei knows now.\nNura does not decide what is wrong.\nAsk your doctor.",
    )
    assert not is_boundary_line(
        Surface.BRIEF, "Mei knows now.\nNura does not decide what is wrong."
    )
    with pytest.raises(ValueError):
        boundary_lines(Surface.BRIEF, "en", urgent=True)
