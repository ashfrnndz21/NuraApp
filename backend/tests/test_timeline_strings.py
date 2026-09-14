"""The timeline's words (E03): every template passes docs/plain-words.md in its language, and
so does every line once it is filled with a real doctor and a real day; the honest line ends
on the same words as the boundary it is followed by."""

from __future__ import annotations

from datetime import date

import pytest

from app.delivery import timeline_strings as words
from app.medicines.strings import say_date
from app.safety.boundary import Surface, boundary_lines
from app.safety.plain_words import verify

DAY = date(2026, 9, 14)


@pytest.mark.parametrize("language", words.LANGUAGES)
def test_every_template_passes_plain_words_in_its_language(language: str) -> None:
    tables = (words.ANCHORS, words.CHANGED, words.WAITING, words.RECALL)
    templates = [line for table in tables for line in table[language].values()]
    templates += [*words.READING[language], *words.HONEST[language], *words.REROUTE[language]]
    for template in templates:
        failures = [f for f in verify(template, language) if f.severity == "fail"]
        assert not failures, (template, [str(f) for f in failures])


@pytest.mark.parametrize("language", words.LANGUAGES)
def test_the_lines_pass_once_filled_with_a_real_doctor_and_day(language: str) -> None:
    when = say_date(DAY, language)
    for key in words.ANCHORS[language]:
        line = words.anchor_line(key, language, doctor="Dr Tan", when=when)
        assert words.verified(line, language), line
    for key in words.CHANGED[language]:
        line = words.changed_line(
            key,
            language,
            doctor="Dr Tan",
            who="Mei",
            what=words.what_word("lipid_panel", language),
            name="your blood pressure tablet" if language == "en" else "Norvasc",
            date=when,
        )
        assert words.verified(line, language), line
    for line in words.reading_lines(language, date=when, top_number="138", bottom_number="84"):
        assert words.verified(line, language), line


@pytest.mark.parametrize("language", words.LANGUAGES)
def test_the_honest_line_ends_on_the_same_words_as_the_boundary(language: str) -> None:
    honest = words.honest_lines(language, "Dr Tan")
    boundary = boundary_lines(Surface.RECALL, language, doctor="Dr Tan")
    assert honest[-1] == boundary[-1]


def test_a_line_opening_with_his_name_for_a_medicine_starts_with_a_capital() -> None:
    assert (
        words.changed_line(
            "medicine_added", "en", name="your blood pressure tablet", date="Monday 14 September"
        )
        == "Your blood pressure tablet was added on Monday 14 September."
    )
