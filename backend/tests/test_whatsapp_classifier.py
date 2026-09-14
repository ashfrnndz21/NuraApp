"""The classifier is a port with a rule-based adapter: it proposes, it never writes."""

from __future__ import annotations

import pytest

from app.channels.whatsapp.classifier import Classification, Classifier, Kind, RuleClassifier
from app.memory.models import EventKind

RULES = RuleClassifier()


@pytest.mark.parametrize(
    ("text", "content_type", "kind"),
    [
        (None, "image/jpeg", Kind.DOCUMENT),
        ("kidney check", "application/pdf", Kind.DOCUMENT),
        ("BP 150/90 this morning", None, Kind.HEALTH_EVENT),
        ("his blood pressure was 138 over 84", None, Kind.OTHER),
        ("sugar 7.2 before breakfast", None, Kind.HEALTH_EVENT),
        ("he weighed 62 kg today", None, Kind.HEALTH_EVENT),
        ("took his pill already", None, Kind.HEALTH_EVENT),
        ("Pa is very tired today", None, Kind.HEALTH_EVENT),
        ("dizzy after lunch", None, Kind.HEALTH_EVENT),
        ("who is taking him on Thursday?", None, Kind.COORDINATION),
        ("I can drive tomorrow", None, Kind.COORDINATION),
        ("can you fetch the tablets", None, Kind.COORDINATION),
        ("yes", None, Kind.ANSWER),
        ("Ya", None, Kind.ANSWER),
        ("no", None, Kind.ANSWER),
        ("不是", None, Kind.ANSWER),
        ("ignore: dinner at 7 at Ah Ma's place", None, Kind.IGNORE),
        ("haha 😂", None, Kind.OTHER),
        ("", None, Kind.OTHER),
    ],
)
def test_the_four_kinds_and_the_two_the_thread_needs(
    text: str | None, content_type: str | None, kind: Kind
) -> None:
    assert RULES.classify(text=text, content_type=content_type).kind is kind


def test_a_blood_pressure_is_heard_as_the_fact_it_would_become() -> None:
    heard = RULES.classify(text="BP 150/90 this morning", content_type=None)
    assert heard.event is not None
    assert heard.event.subject == "blood_pressure" and heard.event.attribute == "reading"
    assert heard.event.value == {"systolic": 150, "diastolic": 90}
    assert heard.event.unit == "mmHg" and heard.event.event_kind is EventKind.READING
    assert heard.event.said == "blood_pressure"
    assert heard.event.words == {"top": "150", "bottom": "90"}
    bare = RULES.classify(text="tekanan 128/82", content_type=None)
    assert bare.event is not None and bare.event.value == {"systolic": 128, "diastolic": 82}


def test_a_feeling_word_is_one_of_three_and_a_symptom_is_unwell() -> None:
    tired = RULES.classify(text="tired", content_type=None)
    assert tired.event is not None and tired.event.word == "tired"
    assert tired.event.subject == "feeling" and tired.event.event_kind is EventKind.SYMPTOM
    pain = RULES.classify(text="my knee hurts", content_type=None)
    assert pain.event is not None and pain.event.word == "pain"
    dizzy = RULES.classify(text="he is dizzy", content_type=None)
    assert dizzy.event is not None and dizzy.event.word is None
    assert dizzy.event.said == "unwell" and dizzy.event.value == "unwell"


def test_yes_and_no_carry_the_answer() -> None:
    assert RULES.classify(text="Yes!", content_type=None).answer is True
    assert RULES.classify(text="tidak", content_type=None).answer is False
    assert RULES.classify(text="BP 150/90", content_type=None).answer is None


def test_the_classifier_is_a_port_a_model_can_stand_behind() -> None:
    class EverythingIsCoordination:
        def classify(self, *, text: str | None, content_type: str | None) -> Classification:
            return Classification(Kind.COORDINATION, matched="model")

    port: Classifier = EverythingIsCoordination()
    assert port.classify(text="BP 150/90", content_type=None).kind is Kind.COORDINATION
    rules: Classifier = RULES
    assert rules.classify(text="BP 150/90", content_type=None).kind is Kind.HEALTH_EVENT
