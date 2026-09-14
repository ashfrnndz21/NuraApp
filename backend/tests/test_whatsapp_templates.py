"""E19-01: the six approved templates, their slots, and the business number that approves them."""

from __future__ import annotations

import pytest

from app.channels.whatsapp.config import VerificationState, business_number_for
from app.channels.whatsapp.strings import REPLIES, reply
from app.channels.whatsapp.templates import (
    LANGUAGES,
    TEMPLATE_NAMES,
    TEMPLATES,
    MissingSlot,
    NotATemplate,
    render,
)
from app.regions import Region
from app.safety.plain_words import verify
from app.settings import Settings

SIX = (
    "morning_card",
    "visit_reminder",
    "reorder",
    "family_digest",
    "feeling_check_in",
    "red_flag_notice",
)

DOSES = {
    "en": "Take 1 tablet of your blood pressure tablet with breakfast.",
    "ms": "Ambil 1 biji ubat tekanan darah anda bersama sarapan.",
    "zh": "早餐时吃 1 片您的血压药。",
}
"""The doses slot is what the medicines module renders in the profile's language."""

FILL = {
    "name": "Pa",
    "day": "Monday 14 September",
    "doctor": "Dr Tan",
    "time": "10 am",
    "who": "Mei",
    "medicine": "the water pill",
    "count": "3",
    "top": "150",
    "bottom": "90",
    "value": "7.2",
    "weight": "62",
    "word": "tired",
    "names": "Mei and Kit",
}


def test_there_are_six_and_each_has_every_language() -> None:
    assert TEMPLATE_NAMES == SIX
    for template in TEMPLATES.values():
        assert set(template.text) == set(LANGUAGES)
        for language, body in template.text.items():
            for slot in template.slots:
                assert f"{{{slot}}}" in body, (template.name, language, slot)


@pytest.mark.parametrize("name", SIX)
@pytest.mark.parametrize("language", LANGUAGES)
def test_every_template_renders_and_passes_plain_words(name: str, language: str) -> None:
    params = {slot: {**FILL, "doses": DOSES[language]}[slot] for slot in TEMPLATES[name].slots}
    text = render(name, language, params)
    assert "{" not in text and "}" not in text
    assert [f for f in verify(text, language) if f.severity == "fail"] == []


@pytest.mark.parametrize("key", sorted(REPLIES))
@pytest.mark.parametrize("language", LANGUAGES)
def test_every_reply_renders_and_passes_plain_words(key: str, language: str) -> None:
    params = {slot: FILL[slot] for slot in FILL}
    text = reply(key, language, **params)
    assert [f for f in verify(text, language) if f.severity == "fail"] == []


def test_slots_are_filled_exactly() -> None:
    with pytest.raises(MissingSlot):
        render("morning_card", "en", {"name": "Pa", "day": "Monday 14 September"})
    with pytest.raises(MissingSlot):
        render("feeling_check_in", "en", {"name": "Pa", "extra": "x"})
    with pytest.raises(NotATemplate):
        render("marketing_blast", "en", {})


def test_the_business_number_names_its_provider_state_and_templates() -> None:
    sandbox = business_number_for(
        Settings(region=Region.MY, database_url="sqlite://", dev_code_sender=True)
    )
    assert sandbox.region is Region.MY
    assert sandbox.provider_name == "fixture"
    assert sandbox.verification is VerificationState.SANDBOX
    assert sandbox.templates == SIX
    assert sandbox.approves("morning_card") and not sandbox.approves("marketing_blast")
    named = business_number_for(
        Settings(
            region=Region.SG,
            database_url="sqlite://",
            whatsapp_provider="gupshup",
            whatsapp_number="+6581234567",
        )
    )
    assert named.phone_e164 == "+6581234567"
    assert named.verification is VerificationState.PENDING
