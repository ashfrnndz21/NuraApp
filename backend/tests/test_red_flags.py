"""Red flags, one module (`app/safety/red_flags.py`): the feeling cloud's words (E21) and the
same flags heard in free text on WhatsApp (E19-05) — one `Flag`, one table of words, one
ladder."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Outcome
from app.audit.trail import read_audit
from app.channels.whatsapp.models import MessageKind, WhatsAppMessage
from app.clock import FrozenClock
from app.db import utcnow
from app.identity.service import register_person
from app.keys.context import KeyContext
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import Artifact, Event, EventKind, Fact, SourceChannel
from app.regions import Region
from app.safety.red_flags import (
    FLAG_TARGET,
    RED_FLAG_WORDS,
    RED_FLAGS,
    Escalation,
    Feeling,
    Flag,
    NotAFeeling,
    detect,
    is_red,
    open_flags,
    raise_flag,
)
from tests.support import agree_to_family_sharing, refused_unit
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
    flag = await raise_flag(
        sg, context=home.owner, feeling=Feeling.SHAKY_SWEATY, event_id=said.id
    )
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
    assert targets.index("whatsapp_message") < targets.index("safety_escalation")

    # The reply in the thread: the doctor's word, and who knows now.
    assert len(handled.replies) == 1
    lines = handled.replies[0].text.splitlines()
    assert lines[0] == "This one we do not wait for."
    assert lines[1] == "Call your doctor today."
    assert lines[2] == "Pa and Kit know now."

    # The ladder: owner, then chiefs (Mei is the poster and left out), then the rest.
    ladder = (await sg.scalars(select(Escalation).where(Escalation.flag_id == flag.id))).one()
    assert [step["standing"] for step in ladder.roster] == ["owner", "helper"]
    assert [step["person_id"] for step in ladder.roster] == [str(home.pa.id), str(kit.id)]
    assert ladder.told == [str(home.mei.id)]

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
    scope, and the ladder is written."""
    home = await family(
        sg,
        tmp_path,
        mei_scopes=frozenset({Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND}),
        mei_role=KeyRole.HELPER,
    )
    assert not home.chief.allows(Scope.RECORDS)
    handled = await home.inbound(sg, MEI, "he fell in the bathroom")
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    assert (await sg.scalars(select(Escalation))).one().flag_id == handled.flag_id
    assert handled.replies[0].text.splitlines()[0] == "This one we do not wait for."


async def test_a_flag_heard_on_whatsapp_that_depends_on_a_missing_fact_is_kept_not_escalated(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "shaky and sweaty after lunch")
    assert handled.outcome == "red_flag_suppressed" and handled.flag_id is not None
    flag = await sg.get(Flag, handled.flag_id)
    assert flag is not None and flag.suppressed_because == "no_sugar_condition_on_record"
    assert list(await sg.scalars(select(Escalation))) == []
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
