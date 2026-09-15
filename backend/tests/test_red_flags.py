"""Red flags, one module (`app/safety/red_flags.py`): the feeling cloud's words (E21), the same
flags heard in free text on WhatsApp (E19-05), the words the not-feeling-well button and the
symptom log hear (E13/E14), and the words heard at a visit with their spans (E05) — one `Flag`
table, one vocabulary of codes, one ladder, one way a flag is kept. Then the symptom tables,
the transcriber port and the strings catalogue: pure tables and a fixture."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.channels import safety_strings as strings
from app.channels.whatsapp.models import MessageKind, WhatsAppMessage
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.triggers.models import Delivery, DeliveryOutcome, Ladder
from app.identity.service import register_person
from app.ingestion.transcribe import NOTHING_HEARD, FixtureTranscriber
from app.ingestion.voice import NotAVoiceNote, VoiceNoteTooLong, check_voice_note
from app.keys.context import KeyContext
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import Artifact, Event, EventKind, Fact, SourceChannel
from app.regions import OutOfRegion, Region
from app.safety.plain_words import verify
from app.safety.red_flags import (
    FEELING_CODE,
    FLAG_TARGET,
    RED_FLAG_TERMS,
    RED_FLAG_WORDS,
    RED_FLAGS,
    Escalation,
    Feeling,
    Flag,
    FlagKind,
    NotAFeeling,
    detect,
    find_red_flags,
    is_red,
    open_flags,
    raise_flag,
    red_flags_in,
    write_red_flag,
)
from app.safety.symptoms import (
    Duration,
    Symptom,
    parse_symptoms,
    severity_level,
    severity_word,
)
from tests.support import agree_to_family_sharing, refused_unit
from tests.visits import pa
from tests.voice import CHEST_PAIN, UNHEARD, VOICE, digest_of, fixture, placeholder_voice
from tests.whatsapp_support import KIT, MEI, family

# --- the words ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("he fell in the bathroom", Feeling.FALL),
        ("Pa jatuh dalam bilik air", Feeling.FALL),
        ("阿公在浴室跌倒了", Feeling.FALL),
        ("he's very breathless just sitting", Feeling.BREATHLESS_AT_REST),
        ("says his chest is tight", Feeling.CHEST_TIGHTNESS),
        ("left leg is swollen since morning", Feeling.ONE_SIDED_SWELLING),
        ("worst headache of his life", Feeling.WORST_HEADACHE),
        ("suddenly cannot see properly", Feeling.SUDDEN_BLURRING),
        ("he is confused and does not recognise me", Feeling.CONFUSION),
        ("shaky and sweaty after the sugar tablet", Feeling.SHAKY_SWEATY),
    ],
)
def test_the_word_table_names_the_flag(text: str, rule: Feeling) -> None:
    assert detect(text) is rule


@pytest.mark.parametrize(
    "text", ["BP 150/90 this morning", "a fellow from church visited", "fall back plan", None, ""]
)
def test_ordinary_words_are_not_a_flag(text: str | None) -> None:
    # "fall" as a word is a fall; a name that merely contains one ("fellow") is not.
    if text == "fall back plan":
        assert detect(text) is Feeling.FALL
    else:
        assert detect(text) is None


def test_the_table_is_the_red_flags_heard_in_words_in_three_languages() -> None:
    # The same nine the feeling cloud raises, less the weight rule: two facts and a
    # discharge, reasoning's to compute, never a word to spot.
    assert set(RED_FLAG_WORDS) == RED_FLAGS - {Feeling.WEIGHT_GAIN}
    assert all(is_red(feeling) for feeling in RED_FLAG_WORDS)
    for patterns in RED_FLAG_WORDS.values():
        assert len(patterns) >= 3


def test_the_other_words_on_the_cloud_are_not_red() -> None:
    assert {feeling for feeling in Feeling if not is_red(feeling)} == {
        Feeling.DIZZY,
        Feeling.CRAMPS,
        Feeling.THIRSTY,
        Feeling.TIRED,
        Feeling.ACHES,
        Feeling.HEADACHE,
        Feeling.PAIN,
        Feeling.BREATHLESS,
        Feeling.LOW,
        Feeling.WORRIED,
        Feeling.CANT_SLEEP,
        Feeling.SWOLLEN_ANKLES,
        Feeling.STOMACH_UPSET,
        Feeling.FINE,
    }


# --- the feeling cloud (E21) -------------------------------------------------------------------


async def _said(session: AsyncSession, context: KeyContext, word: Feeling) -> Event:
    """The SYMPTOM event a tap on the cloud writes, the way `POST /feelings` does."""
    return await record_event(
        session,
        context=context,
        kind=EventKind.SYMPTOM,
        occurred_at=utcnow(),
        label=word.value,
        source_channel=SourceChannel.APP,
    )


async def test_a_red_word_raises_a_flag_that_tells_every_key_with_the_emergency_scope(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    said = await _said(sg, home.owner, Feeling.FALL)
    flag = await raise_flag(sg, context=home.owner, feeling=Feeling.FALL, event_id=said.id)

    assert flag.feeling is Feeling.FALL and flag.event_id == said.id
    assert flag.suppressed_because is None
    assert flag.told == [str(home.mei.id)]
    trail = await read_audit(sg, context=home.owner)
    shares = [e for e in trail if e.action is Action.SHARE and e.target == FLAG_TARGET]
    assert [e.shared_with_person_id for e in shares] == [home.mei.id]
    assert [one.id for one in await open_flags(sg, context=home.owner)] == [flag.id]


async def test_a_word_that_is_not_red_raises_no_flag(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    said = await _said(sg, home.owner, Feeling.TIRED)
    async with refused_unit(sg, NotAFeeling):
        await raise_flag(sg, context=home.owner, feeling=Feeling.TIRED, event_id=said.id)
    assert list(await sg.scalars(select(Flag))) == []


async def test_a_flag_that_depends_on_a_missing_fact_is_written_suppressed_and_tells_nobody(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Shaky-and-sweaty is red on sugar medicines; with none on the record it is written with
    why, so the caregiver sees it was considered, and no one is told (safety.md)."""
    home = await family(sg, tmp_path)
    said = await _said(sg, home.owner, Feeling.SHAKY_SWEATY)
    flag = await raise_flag(sg, context=home.owner, feeling=Feeling.SHAKY_SWEATY, event_id=said.id)
    assert flag.suppressed_because == "no_sugar_condition_on_record"
    assert flag.told == []
    weight = await _said(sg, home.owner, Feeling.WEIGHT_GAIN)
    heavy = await raise_flag(
        sg, context=home.owner, feeling=Feeling.WEIGHT_GAIN, event_id=weight.id
    )
    assert heavy.suppressed_because == "no_recent_discharge_on_record"


async def test_a_flag_leads_for_a_day_and_then_leaves_the_window(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home = await family(sg, tmp_path)
    said = await _said(sg, home.owner, Feeling.CONFUSION)
    flag = await raise_flag(sg, context=home.owner, feeling=Feeling.CONFUSION, event_id=said.id)
    clock.step(timedelta(hours=23))
    assert [one.id for one in await open_flags(sg, context=home.owner)] == [flag.id]
    clock.step(timedelta(hours=2))
    assert list(await open_flags(sg, context=home.owner)) == []


# --- on WhatsApp (E19-05) ----------------------------------------------------------------------


async def test_a_red_flag_is_written_before_anything_else_and_escalates(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    kit = await register_person(sg, region=Region.SG, display_name="Kit", phone_e164=KIT)
    await agree_to_family_sharing(sg, home.owner, kit, scopes={Scope.MEDICINES, Scope.EMERGENCY})
    await grant_key(sg, context=home.owner, holder=kit, role=KeyRole.HELPER)

    handled = await home.inbound(sg, MEI, "he fell in the bathroom just now")
    assert handled.outcome == "red_flag" and handled.flag_id is not None

    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.feeling is Feeling.FALL
    assert flag.raised_by_person_id == home.mei.id and flag.profile_id == home.profile.id
    said = await sg.get(Event, flag.event_id)
    assert said is not None and said.kind is EventKind.SYMPTOM
    assert said.source_channel is SourceChannel.WHATSAPP and said.label == "fall"

    # Before anything else: the moment and the flag on it come before the artefact's line.
    # The clock is frozen, so the order is the order the rows were written in.
    trail = list(
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.profile_id == home.profile.id, AuditEntry.action == Action.WRITE
            )
        )
    )
    targets = [e.target for e in trail if e.actor_person_id == home.mei.id]
    assert targets.index("event") < targets.index("red_flag")
    assert targets.index("red_flag") < targets.index("artifact")
    assert targets.index("artifact") < targets.index("whatsapp_message")

    # The reply in the thread: the doctor's word, and who knows now.
    assert len(handled.replies) == 1
    lines = handled.replies[0].text.splitlines()
    assert lines[0] == "This one we do not wait for."
    assert lines[1] == "Call your doctor today."
    # In his doctor's hours, the doctor today — and the ambulance if it gets worse (E19-05).
    assert lines[2] == "If it gets worse, call the ambulance now on 995."
    assert lines[3] == "Kit knows now."
    assert lines[4] == "Nura does not decide what is wrong."

    # The ladder (E11-06), the one record of who is told: never his own rung (he is the one
    # in trouble), never the poster (she knows). Nobody is on duty and the only chief posted
    # it, so everyone else holding his emergency card, at once — Kit — on WhatsApp.
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == flag.id))).one()
    assert [(step["standing"], step["person_id"]) for step in ladder.rungs] == [
        ("key_holder", str(kit.id))
    ]
    sent = (await sg.scalars(select(Delivery).where(Delivery.ladder_id == ladder.id))).one()
    assert sent.to_person_id == kit.id and sent.outcome is DeliveryOutcome.SENT
    assert sent.template_name == "red_flag_notice" and sent.rule == "red_flag_raised"
    assert list(await sg.scalars(select(Escalation))) == []

    # Nothing was extracted from the words: no fact, no proposal; the message is kept.
    assert list(await sg.scalars(select(Fact))) == []
    kept = (await sg.scalars(select(WhatsAppMessage))).all()
    assert next(m.kind for m in kept if m.person_id == home.mei.id) is MessageKind.RED_FLAG
    assert (await sg.get(Artifact, handled.artifact_id)) is not None


async def test_a_helper_whose_key_holds_the_emergency_scope_but_not_the_record_starts_it(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """A helper's key covers his medicines and the emergency, not the record. Her word that
    he fell is enough: the moment, the flag and her words are kept under the emergency
    scope, and the ladder (E11) is started."""
    home = await family(
        sg,
        tmp_path,
        mei_scopes=frozenset({Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND}),
        mei_role=KeyRole.HELPER,
    )
    assert not home.chief.allows(Scope.RECORDS)
    handled = await home.inbound(sg, MEI, "he fell in the bathroom")
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    assert (await sg.scalars(select(Ladder))).one().flag_id == handled.flag_id
    assert handled.replies[0].text.splitlines()[0] == "This one we do not wait for."


async def test_a_flag_heard_on_whatsapp_that_depends_on_a_missing_fact_is_kept_not_escalated(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "shaky and sweaty after lunch")
    assert handled.outcome == "red_flag_suppressed" and handled.flag_id is not None
    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.suppressed_because == "no_sugar_condition_on_record"
    assert list(await sg.scalars(select(Ladder))) == []
    # Not escalated, and still a next step for the poster: who to call if it gets worse.
    assert len(handled.replies) == 1
    assert handled.replies[0].text.splitlines() == [
        "I wrote it down.",
        "If it gets worse, call your doctor today.",
    ]


async def test_a_red_flag_from_a_key_without_the_emergency_scope_is_refused_and_written_down(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The keys are not bypassed for a flag: a key cut without the emergency scope cannot
    write one, and the reaching is on the trail. Every role but a clinic holds it."""
    home = await family(
        sg, tmp_path, mei_scopes=frozenset({Scope.MEDICINES}), mei_role=KeyRole.HELPER
    )
    handled = await home.inbound(sg, MEI, "he fell in the bathroom")
    assert handled.outcome == "refused" and handled.refused == "OutOfScope"
    assert list(await sg.scalars(select(Flag))) == []
    trail = await read_audit(sg, context=home.owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.target == FLAG_TARGET
        and e.scope is Scope.EMERGENCY
        and e.actor_person_id == home.mei.id
        for e in trail
    )


# --- the words heard (E05) -------------------------------------------------------------------


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
    } <= set(RED_FLAG_TERMS)


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


# --- the feeling cloud (E21) and the one table -----------------------------------------------


def test_every_red_feeling_has_a_code_the_words_heard_share() -> None:
    assert set(FEELING_CODE) == RED_FLAGS
    assert not any(is_red(feeling) for feeling in Feeling if feeling not in RED_FLAGS)
    # Every code but the number rule (a kilo in two days) is one a transcript can carry too.
    assert set(FEELING_CODE.values()) - {"weight_gain"} <= set(RED_FLAG_TERMS)


async def test_a_feeling_tapped_and_a_word_heard_raise_the_same_row_and_only_the_tap_leads_the_feed(
    sg: AsyncSession,
) -> None:
    context = await pa(sg, language="en")
    said = await record_event(
        sg,
        context=context,
        kind=EventKind.SYMPTOM,
        occurred_at=utcnow(),
        label=Feeling.CHEST_TIGHTNESS.value,
        source_channel=SourceChannel.APP,
    )
    tapped = await raise_flag(
        sg, context=context, feeling=Feeling.CHEST_TIGHTNESS, event_id=said.id
    )
    heard = await write_red_flag(
        sg,
        context=context,
        kind=FlagKind.RED_FLAG,
        code="chest_pain",
        subject="symptom",
        payload={"word": "chest pain", "span": {"start": 7, "end": 17}, "found_in": "transcript"},
        raised_at=utcnow(),
    )
    change = await write_red_flag(
        sg,
        context=context,
        kind=FlagKind.MEDICINE_CHANGE_HEARD,
        code="dose",
        subject="frusemide",
        payload={"generic": "frusemide", "change": "dose", "ask_the_doctor": True},
        raised_at=utcnow(),
    )

    rows = (await sg.scalars(select(Flag))).all()
    assert {row.id for row in rows} == {tapped.id, heard.id, change.id}
    # One vocabulary: the tight chest tapped and the chest pain heard are the same code.
    assert tapped.code == heard.code == "chest_pain"
    assert tapped.feeling is Feeling.CHEST_TIGHTNESS and tapped.event_id == said.id
    assert heard.feeling is None and heard.event_id is None
    assert {row.raised_by_person_id for row in rows} == {context.person_id}
    # The feed's emergency card is for what he said he feels; the visit's flags are the
    # summary card's and the doctor's questions.
    assert [flag.id for flag in await open_flags(sg, context=context)] == [tapped.id]


# --- the words the button hears (E13/E14) ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("I have chest pain", Feeling.CHEST_TIGHTNESS),
        ("pain in my chest", Feeling.CHEST_TIGHTNESS),
        ("dada saya sakit", Feeling.CHEST_TIGHTNESS),
        ("我胸口闷", Feeling.CHEST_TIGHTNESS),
        ("I cannot breathe sitting down", Feeling.BREATHLESS_AT_REST),
        ("semput", Feeling.BREATHLESS_AT_REST),
        ("sebelah kaki bengkak", Feeling.ONE_SIDED_SWELLING),
        ("everything suddenly blur", Feeling.SUDDEN_BLURRING),
        ("I fell down in the bathroom", Feeling.FALL),
        ("saya jatuh", Feeling.FALL),
        ("I feel confused, not making sense", Feeling.CONFUSION),
        ("shaky and sweaty", Feeling.SHAKY_SWEATY),
    ],
)
def test_the_words_the_button_hears_are_the_same_table(text: str, rule: Feeling) -> None:
    """One table of words for every channel: what E13's own table heard is heard here."""
    assert detect(text) is rule


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
    "date": date(2026, 9, 14),  # a Monday; `render` says it in the line's own language
    "words": "chest pain",
    "symptom": "dizzy",
    "severity": "quite bad",
    "since": "this morning",
    "insurer": "Great Eastern",
}


def test_every_template_in_the_catalogue_passes_the_verifier_filled() -> None:
    failures: list[str] = []
    for template_id, language, text in strings.catalogue():
        rendered = strings.render(template_id, language, **FILLERS)
        found = [
            f
            for f in verify(rendered, language, strings.KIND_OF.get(template_id, "line"))
            if f.severity == "fail"
        ]
        failures.extend(f"{template_id} [{language}]: {f.problem} — {text}" for f in found)
    assert failures == []


def test_a_line_that_fails_the_standard_is_refused_not_shown() -> None:
    with pytest.raises(strings.NotPlainWords):
        strings.render("nfw.not_taken", "en", medicine="the diuretic 40mg overdue dose")
    with pytest.raises(strings.NoSuchTemplate):
        strings.render("nfw.does_not_exist", "en")


def test_no_template_tells_him_to_start_stop_or_change_a_medicine() -> None:
    forbidden = (
        "stop taking",
        "start taking",
        "double",
        "take 2",
        "skip",
        "increase",
        "reduce",
        " mg",
    )
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
