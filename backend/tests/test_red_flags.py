"""The red-flag table (app/safety/red_flags.py): words in, hits with spans out, nothing judged."""

from __future__ import annotations

from app.safety.red_flags import RED_FLAGS, find_red_flags, red_flags_in


def test_the_words_the_rules_name_are_in_the_table() -> None:
    assert {
        "chest_pain",
        "breathless",
        "black_stool",
        "fall",
        "confusion",
        "one_sided_swelling",
        "worst_headache",
        "sudden_blurring",
        "shaky_and_sweaty",
        "fever_on_medicine",
    } <= set(RED_FLAGS)


def test_a_red_flag_word_is_found_with_its_span_in_three_languages() -> None:
    hits = find_red_flags("He had chest pain twice this week.")
    assert [(h.code, h.word) for h in hits] == [("chest_pain", "chest pain")]
    assert "He had chest pain twice this week."[hits[0].start : hits[0].end] == "chest pain"
    assert [h.code for h in find_red_flags("Dia sesak nafas malam tadi.")] == ["breathless"]
    assert [h.code for h in find_red_flags("他昨晚跌倒了。")] == ["fall"]


def test_a_fever_counts_only_beside_a_medicine() -> None:
    assert find_red_flags("He has a fever.") == []
    assert [h.code for h in find_red_flags("He has a fever since the new tablet.")] == [
        "fever_on_medicine"
    ]
    assert [h.code for h in find_red_flags("Fever today.", medicine_names=("warfarin",))] == []
    assert [h.code for h in find_red_flags("Fever on warfarin.", medicine_names=("warfarin",))] == [
        "fever_on_medicine"
    ]


def test_words_inside_a_fact_value_are_found_and_ordinary_words_are_not() -> None:
    assert [h.code for h in red_flags_in({"reported": "black stool this morning"})] == [
        "black_stool"
    ]
    assert red_flags_in({"systolic": 142, "diastolic": 88}, "blood pressure was fine") == []
    # "fall" as a season, or "confused" about a date, is a whole-word match on the phrase.
    assert find_red_flags("It will be autumn, not fall.") == []
    assert [h.code for h in find_red_flags("She said he was confused at breakfast.")] == [
        "confusion"
    ]
