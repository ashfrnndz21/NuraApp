"""The boundary copy on every inferring surface (E16-01).

    Acceptance: organises, prepares, surfaces patterns to discuss; does not diagnose or treat.

The register `INFERRING_SURFACES` has words in every language Nura speaks, every line passes
docs/plain-words.md, no line tells him to start, stop or change a medicine, and the register
agrees with the table in docs/trust/samd-boundary-review.md. The one inferring surface on
main today, State's posture at `GET /profiles/{id}/state`, carries the line in the profile's
language.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.safety.boundary import (
    INFERRING_SURFACES,
    LANGUAGES,
    NOT_ADVICE,
    WHAT_NURA_DID,
    Surface,
    boundary_line,
    boundary_lines,
)
from app.safety.plain_words import verify
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "00-MASTER-BUILD-SPEC.md"
REVIEW = REPO / "docs" / "trust" / "samd-boundary-review.md"

PA = "+6591110001"
MEI = "+6591110002"


def test_every_inferring_surface_has_its_words_in_every_language() -> None:
    assert set(INFERRING_SURFACES) == set(Surface)
    for language in LANGUAGES:
        assert set(WHAT_NURA_DID[language]) == set(Surface), language
        assert len(NOT_ADVICE[language]) == 2
        for surface in INFERRING_SURFACES:
            lines = boundary_lines(surface, language, doctor="Dr Tan")
            assert len(lines) == 3 and all(lines), (surface, language)
            assert "Dr Tan" in lines[-1], (surface, language)


def test_every_line_passes_plain_words_in_its_language() -> None:
    failures = [
        (surface.value, language, finding.problem)
        for language in LANGUAGES
        for surface in INFERRING_SURFACES
        for line in boundary_lines(surface, language, doctor="Dr Tan")
        for finding in verify(line, language)
        if finding.severity != "note"
    ]
    assert failures == []


def test_the_last_two_lines_are_the_same_words_on_every_surface() -> None:
    """Rule 13: once it is "This is not a doctor's advice. Ask Dr Tan.", it is never anything
    else, whichever surface he is on."""
    for language in LANGUAGES:
        endings = {boundary_lines(s, language, doctor="Dr Tan")[1:] for s in INFERRING_SURFACES}
        assert len(endings) == 1, language
    assert boundary_lines(Surface.STATE_POSTURE, "en", doctor="Dr Tan")[1:] == (
        "This is not a doctor's advice.",
        "Ask Dr Tan.",
    )


def test_no_line_starts_stops_or_changes_a_medicine_or_names_a_diagnosis() -> None:
    forbidden = re.compile(
        r"\b(start|stop|change|take|increase|reduce|double|halve|skip)\b.*"
        r"\b(medicine|tablet|pill|insulin|dose)\b|\byou have\b|\bdiagnos",
        re.IGNORECASE,
    )
    for surface in INFERRING_SURFACES:
        assert not forbidden.search(boundary_line(surface, "en", doctor="Dr Tan")), surface


def test_without_a_named_doctor_the_line_says_your_doctor() -> None:
    assert boundary_line(Surface.QUESTIONS) == (
        "Nura wrote these questions for you to ask your doctor.\n"
        "This is not a doctor's advice.\n"
        "Ask your doctor."
    )
    assert boundary_lines(Surface.SUMMARY, "ms")[-1] == "Tanya doktor anda."
    assert boundary_lines(Surface.SUMMARY, "zh")[-1] == "问您的医生。"
    # A language Nura does not speak yet falls back to English rather than to nothing.
    assert boundary_line(Surface.BRIEF, "ta") == boundary_line(Surface.BRIEF, "en")


def test_the_register_matches_the_spec_and_the_samd_review_table() -> None:
    """Section 10 of the spec asks for the line on every inferring surface; the SaMD review
    lists them one row each, by code. The register is that list, no more and no less."""
    section_10 = SPEC.read_text(encoding="utf-8").split("## 10.")[1].split("## 11.")[0]
    assert "boundary line on every inferring surface" in section_10
    review = REVIEW.read_text(encoding="utf-8")
    in_table = set(re.findall(r"^\| `([a-z_]+)` \|", review, re.MULTILINE))
    assert in_table == {surface.value for surface in INFERRING_SURFACES}


async def test_state_carries_the_boundary_in_the_profiles_language(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    his = bearer(pa["token"])

    seen = await deployment.client.get(f"/profiles/{profile_id}/state", headers=his)
    assert seen.status_code == 200, seen.text
    assert seen.json()["boundary"] == boundary_line(Surface.STATE_POSTURE, "ms")
    assert seen.json()["boundary"].splitlines() == [
        "Nura menyusun dan menyediakan.",
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
