"""Every card is also a voice script (E22-03): the same verified lines, said.

The acceptance line is "every patient card has audio within a minute of creation"; the audio
itself is E11's `Voice` port (PR #121), so what is held here is the script it is spoken from:
numbers, dates and units read as words in each language, a pause after each line, a longer
one before the boundary, and words that are a function of the verified lines and nothing else.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.language import voice_script
from app.language.memory import build
from app.language.voice_script import (
    BOUNDARY_PAUSE_MS,
    PAUSE_MS,
    chinese_number,
    english_number,
    english_ordinal,
    malay_number,
    script_for,
    spoken_line,
)
from app.safety import plain_words

# --- numbers, in each language ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n", "en", "ms", "zh"),
    [
        (0, "zero", "sifar", "零"),
        (7, "seven", "tujuh", "七"),
        (10, "ten", "sepuluh", "十"),
        (11, "eleven", "sebelas", "十一"),
        (12, "twelve", "dua belas", "十二"),
        (21, "twenty-one", "dua puluh satu", "二十一"),
        (84, "eighty-four", "lapan puluh empat", "八十四"),
        (105, "one hundred and five", "seratus lima", "一百零五"),
        (110, "one hundred and ten", "seratus sepuluh", "一百一十"),
        (138, "one hundred and thirty-eight", "seratus tiga puluh lapan", "一百三十八"),
        (200, "two hundred", "dua ratus", "两百"),
        (1005, "one thousand and five", "seribu lima", "一千零五"),
        (2026, "two thousand and twenty-six", "dua ribu dua puluh enam", "两千零二十六"),
    ],
)
def test_numbers_are_words_in_every_language(n: int, en: str, ms: str, zh: str) -> None:
    assert english_number(n) == en
    assert malay_number(n) == ms
    assert chinese_number(n) == zh


def test_ordinals_for_the_day_of_the_month() -> None:
    assert [english_ordinal(n) for n in (1, 2, 3, 14, 21, 22, 29, 30, 31)] == [
        "first",
        "second",
        "third",
        "fourteenth",
        "twenty-first",
        "twenty-second",
        "twenty-ninth",
        "thirtieth",
        "thirty-first",
    ]


# --- a blood pressure, as each card says it -------------------------------------------------------


def test_138_over_84_in_english_malay_and_chinese() -> None:
    assert (
        spoken_line("Your blood pressure today was 138 over 84.", "en")
        == "Your blood pressure today was one hundred and thirty-eight over eighty-four."
    )
    assert (
        spoken_line("Tekanan darah anda hari ini 138 atas 84.", "ms")
        == "Tekanan darah anda hari ini seratus tiga puluh lapan atas lapan puluh empat."
    )
    assert spoken_line("您今天的血压是138比84。", "zh") == "您今天的血压是一百三十八比八十四。"


def test_a_reading_written_with_a_slash_is_read_with_the_cards_own_word() -> None:
    """The card says "over", "atas", "比" every time; the script says the same."""
    assert spoken_line("It was 138/84.", "en") == (
        "It was one hundred and thirty-eight over eighty-four."
    )
    assert spoken_line("Ia 138/84.", "ms") == "Ia seratus tiga puluh lapan atas lapan puluh empat."
    assert spoken_line("是138/84。", "zh") == "是一百三十八比八十四。"


# --- the day and the date -------------------------------------------------------------------------


def test_a_day_name_date_is_said_the_way_a_person_says_it() -> None:
    assert (
        spoken_line("You see Dr Tan on Monday 14 September.", "en")
        == "You see Dr Tan on Monday the fourteenth of September."
    )
    assert (
        spoken_line("Anda berjumpa Dr Tan pada Isnin 14 September.", "ms")
        == "Anda berjumpa Dr Tan pada Isnin empat belas September."
    )
    assert spoken_line("您9月14日星期一看Dr Tan。", "zh") == "您九月十四日星期一看Dr Tan。"


def test_a_date_with_its_year() -> None:
    assert spoken_line("Your test from Thursday 7 September 2023 is here.", "en") == (
        "Your test from Thursday the seventh of September twenty twenty-three is here."
    )
    assert spoken_line("Ujian anda dari Khamis 7 September 2023 ada di sini.", "ms") == (
        "Ujian anda dari Khamis tujuh September dua ribu dua puluh tiga ada di sini."
    )
    assert spoken_line("2023年9月7日星期四，您验了血。", "zh") == "二零二三年九月七日星期四，您验了血。"


def test_the_time_of_day_in_each_language() -> None:
    assert spoken_line("Mei will pick you up at 9.", "en") == "Mei will pick you up at nine."
    assert spoken_line("Nura kata pil air pada pukul 8.", "ms") == (
        "Nura kata pil air pada pukul lapan."
    )
    assert spoken_line("Nura 说去水药是 8 点吃。", "zh") == "Nura 说去水药是八点吃。"


# --- units, only where the line carries one -------------------------------------------------------


def test_units_are_said_in_full_where_the_line_has_one() -> None:
    assert spoken_line("Your sugar was 5.5 mmol/L.", "en") == (
        "Your sugar was five point five millimoles per litre."
    )
    assert spoken_line("It was 120 mg/dL.", "en") == (
        "It was one hundred and twenty milligrams per decilitre."
    )
    assert spoken_line("It went up by 1 kg.", "en") == "It went up by one kilo."
    assert spoken_line("Berat Pa ialah 70 kg.", "ms") == "Berat Pa ialah tujuh puluh kilo."
    assert spoken_line("是 7%。", "zh") == "是百分之七。"


def test_a_line_with_no_unit_gains_none() -> None:
    """His cards rarely need a unit; the script never adds one."""
    assert spoken_line("Your blood pressure today was 148.", "en") == (
        "Your blood pressure today was one hundred and forty-eight."
    )


def test_two_before_a_measure_word_is_liang_in_chinese() -> None:
    assert spoken_line("把 2 个数字发给我。", "zh") == "把两个数字发给我。"
    assert spoken_line("每天吃 2 次，每次半片。", "zh") == "每天吃两次，每次半片。"
    assert spoken_line("2月2日星期一", "zh") == "二月二日星期一"


def test_the_emergency_number_is_said_the_way_it_is_dialled() -> None:
    assert spoken_line("Call 995 now.", "en") == "Call nine nine five now."
    assert spoken_line("Telefon 999 sekarang.", "ms") == "Telefon sembilan sembilan sembilan sekarang."
    assert spoken_line("请现在打995。", "zh") == "请现在打九九五。"


def test_a_line_that_begins_with_a_number_still_begins_with_a_capital() -> None:
    assert spoken_line("6 days out of 7.", "en") == "Six days out of seven."


# --- the pauses -----------------------------------------------------------------------------------

LEARNING = (
    "A body salt helps your heart keep its beat.",
    "This comes from HealthHub.",
    "Nura explains one thing in simple words.",
    "This is not a doctor's advice.",
    "Ask Dr Tan.",
)
BOUNDARY = "Nura explains one thing in simple words.\nThis is not a doctor's advice.\nAsk Dr Tan."


def test_a_pause_after_every_line_and_a_longer_one_before_the_boundary() -> None:
    script = script_for(LEARNING, "en", boundary=BOUNDARY)
    assert [s.text for s in script.segments] == list(LEARNING)
    assert [s.pause_ms for s in script.segments] == [
        PAUSE_MS,
        BOUNDARY_PAUSE_MS,
        PAUSE_MS,
        PAUSE_MS,
        PAUSE_MS,
    ]
    assert BOUNDARY_PAUSE_MS > PAUSE_MS


def test_a_card_that_shows_the_record_back_has_no_boundary_pause() -> None:
    script = script_for(("Your blood pressure today was 138 over 84.", "I wrote it down."), "en")
    assert {s.pause_ms for s in script.segments} == {PAUSE_MS}


def test_a_boundary_the_lines_do_not_end_on_adds_no_pause() -> None:
    script = script_for(("One line.", "Two lines."), "en", boundary=BOUNDARY)
    assert {s.pause_ms for s in script.segments} == {PAUSE_MS}


# --- the words are a function of the verified lines only ------------------------------------------


def test_the_script_takes_the_lines_and_nothing_else() -> None:
    """No name, no profile, no provider goes in: only the lines, their language and the
    boundary the card already carries (itself a verified line)."""
    parameters = inspect.signature(script_for).parameters
    assert list(parameters) == ["lines", "language", "boundary"]


def test_each_segment_is_its_own_line_said_and_nothing_more() -> None:
    lines = ("Your blood pressure today was 138 over 84.", "Mei can see it too.")
    script = script_for(lines, "en")
    assert [s.text for s in script.segments] == [spoken_line(line, "en") for line in lines]


def test_a_line_with_no_number_date_or_unit_is_said_exactly_as_written() -> None:
    for line, language in (
        ("This one we do not wait for.", "en"),
        ("Yang ini kita tidak tunggu.", "ms"),
        ("这个我们不等。", "zh"),
        ("Ask Dr Tan.", "en"),
    ):
        assert spoken_line(line, language) == line


def test_the_same_lines_give_the_same_digest_and_other_lines_another() -> None:
    first = script_for(LEARNING, "en", boundary=BOUNDARY)
    again = script_for(list(LEARNING), "en", boundary=BOUNDARY)
    other = script_for((*LEARNING[:-1], "Ask your doctor."), "en")
    assert first.digest == again.digest
    assert first.digest != other.digest
    assert re.fullmatch(r"[0-9a-f]{64}", first.digest)
    assert first.as_json()["digest"] == first.digest


def test_no_catalogue_line_leaves_a_digit_for_the_voice_to_guess() -> None:
    """Every patient line in the translation memory, filled the way the verifier fills it,
    is said with every number as words in its own language."""
    stray = re.compile(r"(?<![A-Za-z])\d(?![A-Za-z])")
    left: list[str] = []
    for entry in build().entries:
        if entry.language not in voice_script.LANGUAGES or entry.exempt:
            continue
        said = spoken_line(plain_words.fill(entry.text, entry.language), entry.language)
        if stray.search(said):
            left.append(f"{entry.id}: {said}")
    assert left == []


# --- amounts are said as one amount, never digit by digit (clinical-safety review) --------------


@pytest.mark.parametrize(
    ("language", "line", "said"),
    [
        ("en", "Take 1,000 mg once a day.", "Take one thousand milligrams once a day."),
        ("ms", "Ambil 1,000 mg sekali sehari.", "Ambil seribu miligram sekali sehari."),
        ("zh", "每天吃一次，1,000 mg。", "每天吃一次，一千毫克。"),
        ("en", "Take 1/2 tablet.", "Take half tablet."),
        ("ms", "Ambil 1/2 biji.", "Ambil setengah biji."),
        ("zh", "吃1/2片。", "吃半片。"),
        ("en", "Take 0.5 mg.", "Take zero point five milligrams."),
        ("ms", "Ambil 0.5 mg.", "Ambil sifar perpuluhan lima miligram."),
        ("zh", "吃0.5 mg。", "吃零点五毫克。"),
    ],
)
def test_an_amount_is_said_as_one_amount(language: str, line: str, said: str) -> None:
    """A spoken amount must be the amount written: "1,000 mg" is never "one, zero milligrams"
    and "1/2 tablet" never "one, two tablet"."""
    assert spoken_line(line, language) == said


def test_a_fraction_a_voice_cannot_say_plainly_is_left_as_written() -> None:
    """A voice never guesses at an amount: a fraction with no everyday words stays digits."""
    for line, language in (("Take 5/8 of it.", "en"), ("Ambil 5/8.", "ms"), ("吃5/8。", "zh")):
        assert "5/8" in spoken_line(line, language)
