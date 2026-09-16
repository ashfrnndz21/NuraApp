"""E19-01, E11, B1: the twenty-two templates, their slots, which are approved, and the business number."""

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

EVERY_TEMPLATE = (
    "morning_card",
    "visit_reminder",
    "reorder",
    "family_digest",
    "feeling_check_in",
    "red_flag_notice",
    "dose_reminder",
    "dose_check",
    "dose_resolved",
    "reorder_family",
    "doses_count",
    "papers_waiting",
    "family_note",
    "red_flag_notice_self",
    "red_flag_notice_ambiguous",
    "nudge",
    "red_flag_notice_ambulance",
    "red_flag_notice_hospital",
    "red_flag_notice_night",
    "red_flag_notice_urgent",
    "visit_brief",
    "unheard_note_notice",
    "unheard_note_notice_call",
    "unheard_note_notice_from",
)
"""E19's six, then E11's ten (the ladder's two asks, the ladder standing down for whoever it
reached (#198), the reorder to the family, the count, the papers waiting, a family message,
the red-flag notice's two variants, and the day's smart nudge), then B1's five (the red-flag
notice for the ambulance tier, out of the doctor's hours with the hospital on his insurance or
without, its neutral fallback for when a tier's own template is not yet approved (#174), and
the pre-visit brief at T-3), then the three for a voice note nobody could hear, in the order
they are submitted for approval."""

E19_SIX = EVERY_TEMPLATE[:6]
"""Approved: the only templates a deployment's number carries until Meta approves the rest."""

DOSES = {
    "en": "Take 1 tablet of your blood pressure tablet with breakfast.",
    "ms": "Ambil 1 biji ubat tekanan darah anda bersama sarapan.",
    "zh": "早餐时吃 1 片您的血压药。",
}
"""The doses slot is what the medicines module renders in the profile's language."""

CHOICES = {
    "en": (
        "Send 1 for your blood pressure tablet, 5 on the box, with breakfast.\n"
        "Send 2 for the water pill, 40 on the box, with breakfast."
    ),
    "ms": (
        "Hantar 1 untuk ubat tekanan darah anda, kotak bertulis 5, bersama sarapan.\n"
        "Hantar 2 untuk pil air, kotak bertulis 40, bersama sarapan."
    ),
    "zh": "请发 1：您的血压药，盒子上写着 5，早餐时吃。\n请发 2：去水药，盒子上写着 40，早餐时吃。",
}
TOOK_LINES = {
    "en": "You took your blood pressure tablet with breakfast.",
    "ms": "Anda sudah ambil ubat tekanan darah anda bersama sarapan.",
    "zh": "您早餐时吃了您的血压药。",
}

MESSAGES = {
    "en": "Mei will pick you up at 9.",
    "ms": "Mei akan ambil anda pada pukul 9.",
    "zh": "Mei 九点来接您。",
}
"""A chief's previewed lines, in the language she wrote them in (E12-06)."""

AT_THE_START = {"reorder_family"}
"""Templates whose `{medicine}` starts a line: the engine fills it with a capital (`engine`)."""

DAYS = {"en": "Monday 14 September", "ms": "Isnin 14 September", "zh": "9月14日星期一"}
"""The day slot as `app.delivery.feed.compose.plain_day` renders it in each language: rule 5
reads a Malay line for a Malay weekday (docs/plain-words.md)."""

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
    "anchor": "with breakfast",
    "message": "Mei will pick you up at 9.",
    "emergency_number": "995",
    "hospital": "Gleneagles",
    "subject": "your blood pressure",
    "both": "Pa and Ma",
    "either": "Pa or Ma",
}


def test_there_are_twenty_three_and_each_has_every_language() -> None:
    assert TEMPLATE_NAMES == EVERY_TEMPLATE
    for template in TEMPLATES.values():
        assert set(template.text) == set(LANGUAGES)
        for language, body in template.text.items():
            for slot in template.slots:
                assert f"{{{slot}}}" in body, (template.name, language, slot)


@pytest.mark.parametrize("name", EVERY_TEMPLATE)
@pytest.mark.parametrize("language", LANGUAGES)
def test_every_template_renders_and_passes_plain_words(name: str, language: str) -> None:
    fill = {
        **FILL,
        "doses": DOSES[language],
        "day": DAYS[language],
        "message": MESSAGES[language],
    }
    if name in AT_THE_START:
        fill["medicine"] = fill["medicine"][:1].upper() + fill["medicine"][1:]
    params = {slot: fill[slot] for slot in TEMPLATES[name].slots}
    text = render(name, language, params)
    assert "{" not in text and "}" not in text
    assert [f for f in verify(text, language) if f.severity == "fail"] == []


@pytest.mark.parametrize("key", sorted(REPLIES))
@pytest.mark.parametrize("language", LANGUAGES)
def test_every_reply_renders_and_passes_plain_words(key: str, language: str) -> None:
    params = {slot: FILL[slot] for slot in FILL}
    # A day is said in the reader's language: "Isnin 14 September", "9月14日星期一".
    params["day"] = {"en": FILL["day"], "ms": "Isnin 14 September", "zh": "9月14日星期一"}[language]
    # The list in "which tablet?" and the lines naming what "Taken" wrote down (#162) are
    # whole lines, in the reader's language, as the inbound thread fills them.
    params["doses"] = CHOICES[language]
    params["took"] = TOOK_LINES[language]
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
    assert sandbox.templates == EVERY_TEMPLATE
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


def test_e11s_templates_wait_for_meta_and_a_deployment_carries_only_the_approved() -> None:
    pending = [template.name for template in TEMPLATES.values() if not template.approved]
    assert pending == list(EVERY_TEMPLATE[6:])
    live = business_number_for(
        Settings(region=Region.SG, database_url="sqlite://", dev_code_sender=False)
    )
    assert live.templates == E19_SIX
    assert live.approves("morning_card") and not live.approves("dose_reminder")


def test_the_tiered_notices_say_the_same_words_as_free_text_until_meta_approves() -> None:
    """The free-text notice sent inside a family member's window is the pending template's
    words exactly: one wording, whichever way it goes (B1)."""
    for name in ("red_flag_notice_ambulance", "red_flag_notice_hospital", "red_flag_notice_night"):
        for language in LANGUAGES:
            params = {slot: FILL[slot] for slot in TEMPLATES[name].slots}
            assert render(name, language, params) == reply(f"{name}_text", language, **params)


def test_no_template_parameter_carries_a_line_break_for_the_brief() -> None:
    """A Meta template parameter holds no line break: the brief's slots are a name, a day, a
    time and a subject, and the lines are the template's own."""
    assert TEMPLATES["visit_brief"].slots == ("doctor", "day", "time", "subject")


def test_every_red_flag_notice_is_exempt_from_his_whatsapp_consent() -> None:
    """After he stops WhatsApp his family still hears when he is unwell (#163). The exemption
    is matched by the notice's name, so a notice added later — the tiered ones (#147), a new
    version of the words (#160), the free-text twin outside the window — is never held back at
    the moment it matters most, and nothing else is let through."""
    from app.channels.whatsapp.outbound.send import is_red_flag_notice

    notices = [name for name in TEMPLATE_NAMES if name.startswith("red_flag_notice")]
    assert len(notices) >= 3
    for name in notices:
        assert is_red_flag_notice(name), name
        assert is_red_flag_notice(f"{name}_text"), name
    for name in TEMPLATE_NAMES:
        if not name.startswith("red_flag_notice"):
            assert not is_red_flag_notice(name), name
    assert not is_red_flag_notice(None)
