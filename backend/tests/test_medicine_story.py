"""The medication story (E04-06, E04-07): templates keyed by the licensed monograph, in his
language, to docs/plain-words.md. No model. No sentence starts, stops or changes a medicine."""

from __future__ import annotations

import re

import pytest

from app.drugs.registry import Interaction, LabelFields, Severity, UnknownDrug
from app.medicines import strings
from app.medicines.dose import parse_dose_text
from app.medicines.models import ChangeKind
from app.medicines.story import interaction_question, medication_story
from tests.medicines_support import REGISTRY

RED_WORDS = re.compile(
    r"\b(missed|failed|overdue|non-compliant|dose|doses|recheck|follow-up|flag|flagged|log|adherence)\b",
    re.IGNORECASE,
)
"""Plain words, rules 11 and 12: no red words, nothing to decode."""

TREATMENT_VERBS = re.compile(
    r"\b(start|stop|stops|stopped|starting|stopping|increase|reduce|double|halve|skip)\b",
    re.IGNORECASE,
)
"""The boundary: no sentence tells him to start, stop or change a medicine."""


def _story(
    generic: str,
    dose: str = "1 tab OD",
    *,
    language: str = "en",
    change: ChangeKind = ChangeKind.NEW_LINE,
):
    (match, *_) = REGISTRY.identify(strings_label(generic))
    return medication_story(
        generic=generic,
        strength=match.strength,
        dose=parse_dose_text(dose),
        prescriber="Dr Tan",
        change_kind=change,
        monograph=REGISTRY.monograph(generic),
        language=language,
    )


def strings_label(generic: str) -> LabelFields:
    return LabelFields(generic=generic)


def test_the_story_has_every_section_in_his_words_with_the_chemical_name_kept_small() -> None:
    told = _story("amlodipine")
    assert told.purpose == [
        "This is your blood pressure tablet.",
        "It keeps your blood pressure down.",
    ]
    assert told.how_to_take == [
        "Take 1 tablet once a day.",
        "Take it with breakfast.",
        "Food does not matter for this one.",
    ]
    assert told.watch_out == [
        "If your ankles swell, tell Dr Tan.",
        "If you feel dizzy when you stand up, sit down first.",
        "Then tell Dr Tan.",
    ]
    assert told.avoid == ["Grapefruit does not go with your blood pressure tablet."]
    assert told.if_forgotten == [
        "If you forgot, take it when you remember.",
        "If the next one is soon, wait for the next one.",
        "Never take 2 at once.",
    ]
    assert told.boundary == [
        "This helps you take what Dr Tan prescribed.",
        "Ask Dr Tan or the pharmacist before you change anything.",
    ]
    assert told.doctor_question == []
    # The chemical name is a field for the small print; it is in no sentence.
    assert told.generic == "amlodipine" and told.strength == "5 mg"
    assert all("amlodipine" not in line for line in told.lines)
    assert told.lines == [
        *told.purpose,
        *told.how_to_take,
        *told.watch_out,
        *told.avoid,
        *told.if_forgotten,
        *told.boundary,
    ]


def test_the_story_renders_in_malay_and_chinese_from_the_same_rule_ids() -> None:
    malay = _story("frusemide", "1 tab OM", language="ms")
    assert malay.language == "ms"
    assert malay.purpose == ["Ini pil air.", "Ia mengeluarkan air lebihan dari badan anda."]
    assert malay.how_to_take[0] == "Ambil 1 biji sekali sehari."
    assert "Dr Tan" in malay.watch_out[-1]
    chinese = _story("metformin", "1 tab BD", language="zh")
    assert chinese.language == "zh"
    assert chinese.purpose == ["这是降糖药。", "它让您的血糖不会太高。"]
    assert chinese.how_to_take == [
        "每天吃 2 次，每次1 片。",
        "早餐时吃一次，晚餐时吃一次。",
        "和食物一起吃。",
    ]
    # An unknown language falls back to English rather than to nothing.
    assert _story("metformin", language="ta").language == "en"


def test_the_dose_is_told_from_the_label_with_his_anchors_never_a_bare_code() -> None:
    twice = _story("metformin", "1 tab BD")
    assert twice.how_to_take[:2] == [
        "Take 1 tablet 2 times a day.",
        "Take one with breakfast and one with dinner.",
    ]
    half = _story("warfarin", "½ tab ON")
    assert half.how_to_take[:2] == ["Take half a tablet once a day.", "Take it before bed."]
    weekly = _story("methotrexate", "3 tablets once a week")
    assert weekly.how_to_take[:2] == [
        "Take 3 tablets once a week.",
        "Take it with breakfast, on the same day each week.",
    ]
    prn = _story("paracetamol", "2 tabs prn")
    assert prn.how_to_take == ["Take 2 tablets only when you need it."]
    assert prn.if_forgotten == [
        "This one is only when you need it.",
        "There is nothing to catch up.",
    ]
    units = medication_story(
        generic="insulin glargine",
        strength="100 units/ml",
        dose=parse_dose_text("10 units ON"),
        prescriber=None,
        change_kind=ChangeKind.NEW_LINE,
        monograph=REGISTRY.monograph("insulin glargine"),
        language="en",
    )
    assert units.how_to_take[:2] == ["Take 10 units once a day.", "Take it before bed."]
    assert units.watch_out[-1] == "Then tell your doctor."  # no prescriber on the label


def test_the_missed_dose_guidance_is_per_drug_from_the_monograph() -> None:
    assert _story("warfarin").if_forgotten == [
        "If you forgot and it is still the same day, take it now.",
        "If the day has passed, leave it and tell Dr Tan.",
        "Never take 2 at once.",
    ]
    assert _story("insulin glargine", "10 units ON").if_forgotten == [
        "If you forgot your insulin, call Dr Tan before you take any.",
        "Do not take extra to catch up.",
    ]
    assert _story("gliclazide", "1 tab OM").if_forgotten[0] == "If you forgot, leave it."
    assert _story("frusemide", "1 tab OM").if_forgotten == [
        "If you forgot in the morning, take it by lunch.",
        "After lunch, leave it until tomorrow.",
    ]
    assert (
        _story("methotrexate", "3 tabs weekly")
        .if_forgotten[0]
        .startswith("If you forgot your weekly tablet")
    )


def test_a_dose_change_is_a_question_for_the_doctor_and_never_the_new_amount() -> None:
    changed = _story("amlodipine", "1 tab OD", change=ChangeKind.DOSE_CHANGE)
    assert changed.doctor_question == [
        "Your new pack says a different amount from before.",
        "Ask Dr Tan about the new amount.",
    ]
    assert changed.how_to_take == [*changed.doctor_question, "Food does not matter for this one."]
    assert not any(line.startswith("Take ") for line in changed.lines)
    for language, asked in (
        ("ms", "Tanya Dr Tan tentang jumlah baru itu."),
        ("zh", "问Dr Tan新的分量。"),
    ):
        assert (
            _story("amlodipine", change=ChangeKind.DOSE_CHANGE, language=language).doctor_question[
                -1
            ]
            == asked
        )


def test_an_interaction_is_a_question_with_both_medicines_named_in_his_words() -> None:
    names = {"warfarin": "the blood thinner tablet", "aspirin": "the aspirin"}
    flagged = Interaction(("warfarin", "aspirin"), Severity.MAJOR, "bleeding_risk")
    assert interaction_question(flagged, names=names, prescriber="Dr Tan", language="en") == [
        "Ask Dr Tan about taking the blood thinner tablet and the aspirin together.",
        "Together they can make you bleed more easily.",
    ]
    assert interaction_question(flagged, names=names, prescriber=None, language="ms")[0] == (
        "Tanya doktor anda tentang mengambil the blood thinner tablet dan the aspirin bersama."
    )


def test_no_story_can_be_told_without_the_licensed_monograph() -> None:
    with pytest.raises(UnknownDrug):
        REGISTRY.monograph("digoxin")


def test_every_line_passes_plain_words() -> None:
    """One idea per line, a whole sentence, no red words, nothing to decode, and never a
    sentence that starts, stops or changes a medicine. Checked over the whole catalogue in
    all three languages, and over every rendered story."""
    rendered: list[str] = []
    for generic in sorted(REGISTRY.generics):
        for language in strings.LANGUAGES:
            for change in ChangeKind:
                rendered.extend(_story(generic, "1 tab BD", language=language, change=change).lines)
    buttons = set(strings.TAKEN.values())  # a button is one word, not a sentence
    for line in [*strings.catalogue(), *rendered]:
        assert line.strip() == line and line, repr(line)
        assert line in buttons or line[-1] in ".。", line
        assert not RED_WORDS.search(line), line
        assert not TREATMENT_VERBS.search(line), line
        assert "  " not in line, line
    english = [line for line in rendered if re.fullmatch(r"[\x00-\x7f]+", line)]
    long = [line for line in english if len(line.split()) > 14]
    assert long == [], long
    # The English catalogue: at most two clauses a line, never a fragment without a verb.
    for line in english:
        assert line[0].isupper(), line
        assert line.count(",") <= 2, line


def test_the_amount_is_said_as_digits_small_and_few() -> None:
    assert strings.say_amount(0.5, "tablet", "en") == "half a tablet"
    assert strings.say_amount(1, "tablet", "en") == "1 tablet"
    assert strings.say_amount(2, "tablet", "en") == "2 tablets"
    assert strings.say_amount(18, "unit", "ms") == "18 unit"
    assert strings.say_amount(1.5, "tablet", "en") == "1.5 tablets"
    assert (
        strings.say_date(__import__("datetime").date(2026, 9, 29), "en") == "Tuesday 29 September"
    )
    assert strings.say_date(__import__("datetime").date(2026, 9, 29), "ms") == "Selasa 29 September"
