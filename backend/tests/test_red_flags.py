"""The red-flag table, the symptom tables, the transcriber port and the strings catalogue.

Pure tables and a fixture: no database. What the words map to, in three languages; that the
conditional row is suppressed and named when the medicines are unknown; that severity maps
both ways; that the fixture transcriber answers by digest and says nothing for bytes it has
no file for; and that every template in the catalogue passes the plain-words verifier with
representative fillers, in every language.
"""

from __future__ import annotations

import pytest

from app.channels import safety_strings as strings
from app.regions import OutOfRegion, Region
from app.safety.plain_words import verify
from app.safety.red_flags import RED_FLAGS, RedFlag, match_red_flags, words_for
from app.safety.symptoms import (
    Duration,
    Symptom,
    parse_symptoms,
    severity_level,
    severity_word,
)
from app.safety.transcribe import (
    NOTHING_HEARD,
    FixtureTranscriber,
    NotAVoiceNote,
    VoiceNoteTooLong,
    check_voice_note,
)
from tests.voice import CHEST_PAIN, UNHEARD, VOICE, digest_of, fixture, placeholder_voice

# --- the red-flag table ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "flag"),
    [
        ("I have chest pain", RedFlag.CHEST_PAIN),
        ("my chest feels tight, chest tightness", RedFlag.CHEST_PAIN),
        ("dada saya sakit", RedFlag.CHEST_PAIN),
        ("我胸口闷", RedFlag.CHEST_PAIN),
        ("I cannot breathe sitting down", RedFlag.BREATHLESS_AT_REST),
        ("sesak nafas", RedFlag.BREATHLESS_AT_REST),
        ("one leg swollen since yesterday", RedFlag.ONE_SIDED_SWELLING),
        ("worst headache of my life", RedFlag.WORST_HEADACHE),
        ("everything suddenly blur", RedFlag.SUDDEN_BLURRING),
        ("I fell down in the bathroom", RedFlag.FALL),
        ("saya jatuh", RedFlag.FALL),
        ("跌倒了", RedFlag.FALL),
        ("I feel confused, not making sense", RedFlag.CONFUSION),
    ],
)
def test_the_words_of_the_table_are_flags_in_every_language(said: str, flag: RedFlag) -> None:
    heard = match_red_flags(said, on_sugar_medicine=False)
    assert flag in heard.flags
    assert heard.suppressed == ()


@pytest.mark.parametrize("said", ["tired today", "letih", "a bit dizzy", "no appetite", ""])
def test_ordinary_words_are_not_flags(said: str) -> None:
    heard = match_red_flags(said, on_sugar_medicine=True)
    assert heard.flags == ()
    assert not heard.any


def test_shaky_and_sweaty_is_a_flag_only_on_a_sugar_medicine_and_named_when_unknown() -> None:
    on = match_red_flags("shaky and sweaty", on_sugar_medicine=True)
    assert on.flags == (RedFlag.SHAKY_SWEATY,)
    # Known medicines, none a sugar one — or one the list does not know: held back, visibly.
    off = match_red_flags("shaky and sweaty", on_sugar_medicine=False)
    assert off.flags == () and off.suppressed == (RedFlag.SHAKY_SWEATY,)
    unknown = match_red_flags("shaky and sweaty", on_sugar_medicine=None)
    assert unknown.flags == ()
    assert unknown.suppressed == (RedFlag.SHAKY_SWEATY,)


def test_the_table_is_the_whole_rule_and_the_scales_row_has_no_words() -> None:
    flags = {rule.flag for rule in RED_FLAGS}
    assert flags == set(RedFlag)
    scales = next(rule for rule in RED_FLAGS if rule.flag is RedFlag.WEIGHT_GAIN_AFTER_DISCHARGE)
    assert scales.from_readings and scales.words == {}
    assert words_for(RedFlag.CHEST_PAIN, "ms") == "sakit dada"
    assert words_for(RedFlag.WEIGHT_GAIN_AFTER_DISCHARGE, "en") == "weight gain after discharge"


# --- the symptom tables ---------------------------------------------------------------------


def test_a_symptom_is_read_with_how_much_and_since_when() -> None:
    parsed = parse_symptoms("dizzy, quite a lot, since this morning")
    assert parsed.symptoms == (Symptom.DIZZY,)
    assert parsed.severity == 2
    assert parsed.duration is Duration.THIS_MORNING


def test_the_worst_severity_word_wins_and_nothing_is_guessed() -> None:
    assert parse_symptoms("very tired and a bit dizzy").severity == 3
    quiet = parse_symptoms("headache")
    assert quiet.symptoms == (Symptom.HEADACHE,)
    assert quiet.severity is None and quiet.duration is None
    assert not parse_symptoms("").heard_anything


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
@pytest.mark.parametrize("level", [1, 2, 3])
def test_severity_words_map_both_ways(language: str, level: int) -> None:
    """The word the table hears for a level is the level again, and the words the catalogue
    says back ("a little / quite a lot / very bad") are heard as that level too."""
    assert severity_level(severity_word(level, language)) == level
    said_back = strings.SEVERITY_WORDS[language][level]
    assert severity_level(said_back) == level, said_back


def test_malay_and_chinese_words_are_read_too() -> None:
    assert Symptom.DIZZY in parse_symptoms("saya pening sikit").symptoms
    assert parse_symptoms("saya pening sikit").severity == 1
    assert Symptom.TIRED in parse_symptoms("我很累").symptoms
    assert parse_symptoms("我很累").severity == 3


# --- the transcriber port -------------------------------------------------------------------


async def test_the_fixture_transcriber_answers_by_digest_and_hears_nothing_otherwise() -> None:
    transcriber = FixtureTranscriber(VOICE, Region.SG)
    note = placeholder_voice(CHEST_PAIN)
    assert transcriber.path_of(note).name == f"{digest_of(CHEST_PAIN)}.json"
    heard = await transcriber.transcribe(note, "audio/m4a", "en", Region.SG)
    assert heard.text == fixture(CHEST_PAIN)["text"] == "I have chest pain"
    assert heard.confidence == 0.94 and heard.heard
    silent = await transcriber.transcribe(placeholder_voice(UNHEARD), "audio/m4a", "en", Region.SG)
    assert silent == NOTHING_HEARD and not silent.heard


async def test_the_transcriber_is_pinned_to_its_region() -> None:
    """A voice note is health data: a Singapore note never reaches a Malaysian transcriber."""
    transcriber = FixtureTranscriber(VOICE, Region.MY)
    assert transcriber.region is Region.MY
    with pytest.raises(OutOfRegion):
        await transcriber.transcribe(placeholder_voice(CHEST_PAIN), "audio/m4a", "en", Region.SG)


def test_a_voice_note_is_audio_and_not_a_recording_of_a_whole_visit() -> None:
    assert check_voice_note(b"abc", "Audio/M4A; codecs=mp4a") == "audio/m4a"
    with pytest.raises(NotAVoiceNote):
        check_voice_note(b"abc", "image/jpeg")
    with pytest.raises(NotAVoiceNote):
        check_voice_note(b"", "audio/m4a")
    with pytest.raises(VoiceNoteTooLong):
        check_voice_note(b"x" * (5 * 1024 * 1024 + 1), "audio/m4a")


# --- the catalogue --------------------------------------------------------------------------

FILLERS = {
    "name": "Pa",
    "chief": "Mei",
    "patient": "Pa",
    "who": "Mei",
    "speaks": "Malay",
    "band": "70 to 79",
    "condition": "high blood pressure",
    "medicine": "the water pill (frusemide)",
    "amount": "1 tablet",
    "when": "every morning",
    "thing": "Penicillin",
    "group": "O positive",
    "doctor": "Dr Tan",
    "clinic": "Bedok Clinic",
    "number": "995",
    "date": "Monday 14 September",
    "words": "chest pain",
    "symptom": "dizzy",
    "severity": "quite bad",
    "since": "this morning",
}


def test_every_template_in_the_catalogue_passes_the_verifier_filled() -> None:
    failures: list[str] = []
    for template_id, language, text in strings.catalogue():
        rendered = strings.render(template_id, language, **FILLERS)
        found = [f for f in verify(rendered, language, strings.KIND_OF.get(template_id, "line")) if f.severity == "fail"]
        failures.extend(f"{template_id} [{language}]: {f.problem} — {text}" for f in found)
    assert failures == []


def test_a_line_that_fails_the_standard_is_refused_not_shown() -> None:
    with pytest.raises(strings.NotPlainWords):
        strings.render("nfw.not_taken", "en", medicine="the diuretic 40mg overdue dose")
    with pytest.raises(strings.NoSuchTemplate):
        strings.render("nfw.does_not_exist", "en")


def test_no_template_tells_him_to_start_stop_or_change_a_medicine() -> None:
    forbidden = ("stop taking", "start taking", "double", "take 2", "skip", "increase", "reduce", " mg")
    for template_id, language, text in strings.catalogue():
        low = text.lower()
        for word in forbidden:
            assert word not in low, (template_id, language, text)


def test_one_vocabulary_for_the_three_levels() -> None:
    """What the table hears first for a level is what the catalogue says back."""
    for language in ("en", "ms", "zh"):
        for level in (1, 2, 3):
            assert severity_word(level, language) == strings.SEVERITY_WORDS[language][level]
            assert strings.severity_said(level, language) == severity_word(level, language)


def test_every_what_to_do_line_is_checked_as_an_action() -> None:
    """Rules 6 and 7 — what to do and when, who does the next thing — run on the one card
    whose whole job is what happens next."""
    for template_id in strings.WHAT_TO_DO:
        assert strings.KIND_OF[template_id] == "action", template_id
