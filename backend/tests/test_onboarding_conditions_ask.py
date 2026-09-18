"""The follow-up questions a handful of the word cloud's conditions carry (`ask`,
docs/onboarding.html: "On tablets for it" -> "For how long?"), and `check_answers`, the graph's
own check on his answers to them.

Every ask's question and every option's text is his words, in English, Malay and Chinese
(docs/plain-words.md) — the same standard `test_every_condition_name_is_his_words` already
holds every condition name to.
"""

from __future__ import annotations

import pytest

from app.onboarding.conditions import NotAnAnswer, check_answers, graph
from app.onboarding.strings import LANGUAGES
from app.safety.plain_words import verify

ASK_CODES = (
    "bp_tablets",
    "bp_at_home",
    "heart_doctor",
    "cholesterol_tablet",
    "insulin",
    "stent_or_bypass",
    "blood_thinner",
    "pain_tablets_most_days",
    "medicine_allergy",
)


def test_every_ask_code_is_in_the_graph_and_carries_a_question() -> None:
    held = graph().conditions
    for code in ASK_CODES:
        assert code in held, code
        assert held[code].ask is not None, code


def test_conditions_outside_the_list_carry_no_ask() -> None:
    held = graph().conditions
    without = [code for code in held if code not in ASK_CODES]
    assert without  # most conditions have no follow-up question
    for code in without:
        assert held[code].ask is None, code


def test_every_ask_is_named_in_every_language_with_two_or_more_options() -> None:
    held = graph().conditions
    for code in ASK_CODES:
        ask = held[code].ask
        assert ask is not None
        for language in LANGUAGES:
            assert ask.question(language).strip()
        assert len(ask.options) >= 2
        ids = [option.id for option in ask.options]
        assert len(ids) == len(set(ids)), f"{code} repeats an option id"
        for option in ask.options:
            for language in LANGUAGES:
                assert option.text(language).strip()


def test_every_ask_question_and_option_is_his_words() -> None:
    held = graph().conditions
    for code in ASK_CODES:
        ask = held[code].ask
        assert ask is not None
        for language in LANGUAGES:
            failing = [f for f in verify(ask.question(language), language, "phrase") if f.severity == "fail"]
            assert not failing, (code, "question", language, [str(f) for f in failing])
            for option in ask.options:
                failing = [
                    f for f in verify(option.text(language), language, "phrase") if f.severity == "fail"
                ]
                assert not failing, (code, option.id, language, [str(f) for f in failing])


def test_check_answers_accepts_a_picked_words_own_option() -> None:
    checked = check_answers({"bp_tablets": "under_a_year"}, picked=["bp_tablets"])
    assert checked == {"bp_tablets": "under_a_year"}


def test_check_answers_refuses_a_word_that_carries_no_question() -> None:
    with pytest.raises(NotAnAnswer):
        check_answers({"high_blood_pressure": "yes"}, picked=["high_blood_pressure"])


def test_check_answers_refuses_a_word_not_picked() -> None:
    with pytest.raises(NotAnAnswer):
        check_answers({"bp_tablets": "under_a_year"}, picked=[])


def test_check_answers_refuses_an_option_the_question_does_not_offer() -> None:
    with pytest.raises(NotAnAnswer):
        check_answers({"bp_tablets": "not_an_option"}, picked=["bp_tablets"])
