"""The Why sheet's plain lines (RE-08, docs/recommendation-engine.md §3.3): a card's why,
rendered for the reader in front of it — his voice or hers, in English, Malay and Chinese —
and withheld, never silent, when the reader's key does not cover the scope the card and its
evidence rest on."""

from __future__ import annotations

import uuid

import pytest

from app.delivery.feed.why_sheet import why_lines
from app.delivery.strings import WHY, WHY_THEIRS
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.regions import Region

PROFILE = uuid.uuid4()
PERSON = uuid.uuid4()


def _context(*scopes: Scope) -> KeyContext:
    return KeyContext(
        profile_id=PROFILE, region=Region.SG, person_id=PERSON, scopes=frozenset(scopes)
    )


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_his_own_key_reads_the_plain_reason_when_it_covers_the_scope(language: str) -> None:
    context = _context(Scope.READINGS)
    lines = why_lines(
        "Your blood pressure today was 138 over 84.",
        scope=Scope.READINGS,
        context=context,
        language=language,
        his=True,
    )
    assert lines == ("Your blood pressure today was 138 over 84.",)


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_a_caregiver_without_readings_sees_the_reading_evidence_as_withheld(language: str) -> None:
    """The acceptance line: a caregiver's key without READINGS never reads the reading
    itself — only that a part of the record is withheld, in her own voice, by name."""
    caregiver = _context(Scope.MEDICINES)  # holds a key, but not READINGS
    lines = why_lines(
        "Your blood pressure today was 138 over 84.",
        scope=Scope.READINGS,
        context=caregiver,
        language=language,
        his=False,
        patient_name="Pa",
    )
    assert lines == (WHY_THEIRS[language]["withheld"].format(patient="Pa"),)
    assert "138" not in lines[0]


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_his_own_key_withheld_speaks_in_his_own_voice(language: str) -> None:
    """Contrived (his key normally covers everything), but the branch is still correct: no
    plain content leaks even on a scope his own key happens not to cover."""
    context = _context()  # covers nothing
    lines = why_lines(
        "Your blood pressure today was 138 over 84.",
        scope=Scope.READINGS,
        context=context,
        language=language,
        his=True,
    )
    assert lines == (WHY[language]["withheld"],)


def test_a_caregiver_who_holds_the_scope_reads_the_plain_reason_too() -> None:
    caregiver = _context(Scope.READINGS)
    lines = why_lines(
        "Your blood pressure today was 138 over 84.",
        scope=Scope.READINGS,
        context=caregiver,
        language="en",
        his=False,
        patient_name="Pa",
    )
    # The reason itself is returned unchanged; the caregiver's voice is the existing
    # about_him.py twin pass, which runs afterwards on the same text as `why["plain"]`.
    assert lines == ("Your blood pressure today was 138 over 84.",)


def test_an_empty_reason_is_no_line_at_all() -> None:
    assert why_lines("", scope=Scope.READINGS, context=_context(Scope.READINGS), language="en", his=True) == ()


def test_withheld_never_names_the_scope_it_hides() -> None:
    """The line says a part is withheld; it never names which one, so a caregiver missing
    several scopes learns nothing about what she is missing beyond "a part"."""
    caregiver = _context()
    for scope in (Scope.READINGS, Scope.RECORDS, Scope.MEDICINES):
        lines = why_lines(
            "Some real content.", scope=scope, context=caregiver, language="en", his=False, patient_name="Pa"
        )
        assert scope.value not in lines[0]
