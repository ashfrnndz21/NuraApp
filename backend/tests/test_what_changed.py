"""E03-04 acceptance.

    Lists new facts, unconfirmed doses and family notes since last open.

"Family notes" are three things: a note someone left on one of his moments (E02-06), what the
family wrote or shared in the thread (E12-02), and the chief's note about a place.

A look is the reader's own and a row of its own; the next "what changed" counts from it. The
first look lists everything and says it is the first. A second look, with a write between,
lists that write and nothing else; a third with nothing between says nothing changed since
the day of the last. Beside the changes, what is still waiting — today's tablets not taken
yet, a card waiting for a yes — every time. Corrections are told old → new with the
provenance of both; a visit that moved is told by its new status; a new amount on a pack is
a question for the doctor and never the amount; keys, agreements and the things we do not
wait for are told. Every line is a whole sentence with the day, passes plain words in his
language, and names the ids it is about; a key that does not reach a part is told it was
withheld.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.clock import FrozenClock
from app.delivery.timeline_strings import verified
from app.drafts import StatusChange
from app.family.thread import post_message
from app.ingestion.notes import add_scribble
from app.ingestion.objects import LocalObjectStore
from app.keys.confirm import confirm
from app.keys.scopes import KeyRole, Scope
from app.memory.changes import Changes, mark_looked, what_changed
from app.memory.episodic import record_event
from app.memory.models import AppointmentStatus, EventKind, SourceChannel
from app.memory.providers import write_chief_note
from app.memory.semantic import supersede_fact
from app.memory.spine import change_appointment_status
from app.regions import Region
from app.safety.red_flags import Feeling, raise_flag
from tests.medicines_support import REGISTRY, add, label, let_in
from tests.paper import PNG_SIGNATURE
from tests.timeline_support import KIT_PHONE, reading, record, trail


def keys(changes: Changes) -> list[str]:
    return [line.key for line in changes.lines]


async def test_the_notes_others_left_and_what_the_family_wrote_are_told_by_who_and_when(
    sg: AsyncSession, clock: FrozenClock, tmp_path: Path
) -> None:
    """Mei writes to the family and leaves a scribble on his blood pressure: his next look
    says so, by who and when, never by what was said; his own note is not news to him. A
    caregiver whose key does not hold the family's part reads the note and is told the family
    was withheld."""
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    kit = await let_in(
        sg,
        rec.owner,
        phone=KIT_PHONE,
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes={Scope.RECORDS, Scope.READINGS},
    )
    before = clock.now()
    clock.step(timedelta(minutes=5))
    moment = rec.readings[0].event_id
    assert moment is not None
    said = await post_message(sg, context=rec.mei, text="I will take Pa on Thursday.")
    drawn = await add_scribble(
        sg,
        context=rec.mei,
        store=store,
        event_id=moment,
        data=PNG_SIGNATURE + b"arrow",
        content_type="image/png",
        captured_at=clock.now(),
        private=False,
        label="ask Dr Tan",
    )
    await add_scribble(
        sg,
        context=rec.owner,
        store=store,
        event_id=moment,
        data=PNG_SIGNATURE + b"mine",
        content_type="image/png",
        captured_at=clock.now(),
        private=False,
    )

    his = await what_changed(sg, context=rec.owner, since=before, registry=REGISTRY)
    told = {line.key: line for line in his.lines}
    assert told["family_message"].text == "Mei wrote to the family on Thursday 3 September."
    assert told["family_message"].refs == {"thread_message_ids": (str(said.id),)}
    assert told["note_left"].text == "Mei left a note on Thursday 3 September."
    assert told["note_left"].refs == {
        "event_note_ids": (str(drawn.note.id),),
        "event_ids": (str(moment),),
    }
    assert [n["event_note_id"] for n in his.sections["notes"]] == [str(drawn.note.id)]
    assert "I will take Pa" not in str(his) and "ask Dr Tan" not in str(his)
    assert all(verified(line.text, "en") for line in his.lines)

    hers = await what_changed(sg, context=kit, since=before, registry=REGISTRY)
    assert "note_left" in keys(hers) and "family_message" not in keys(hers)
    assert Scope.FAMILY in hers.withheld


async def test_the_first_look_lists_everything_and_says_it_is_the_first(sg: AsyncSession) -> None:
    rec = await record(sg)
    found = await what_changed(sg, context=rec.mei, since=None, registry=REGISTRY)
    assert found.first_look and found.lines[0].text == "This is your first look at what changed."
    assert {
        "visit_booked",
        "visit_attended",
        "medicine_added",
        "new_fact",
        "new_photo",
        "episode_opened",
        "attached",
        "key_cut",
        "consent_given",
    } <= set(keys(found))
    texts = [line.text for line in found.lines]
    assert "The visit to Dr Tan on Monday 24 August happened." in texts
    assert "Your blood pressure tablet was added on Thursday 3 September." in texts
    assert "A new blood pressure was written down on Thursday 3 September." in texts
    assert "Mei was given a key on Thursday 3 September." in texts
    assert all(line.refs for line in found.lines[1:])
    assert all(verified(line.text, "en") for line in (*found.lines, *found.waiting))
    assert found.dropped == 0 and found.withheld == ()


async def test_a_second_look_with_a_write_between_lists_the_write_and_what_is_waiting(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    rec = await record(sg)
    look = await mark_looked(sg, context=rec.mei)
    clock.step(timedelta(minutes=1))
    new = await reading(sg, rec.owner, 132, 80, clock.now())
    await write_chief_note(sg, context=rec.mei, provider_id=rec.tan.id, text="parking at B2")
    found = await what_changed(
        sg, context=rec.mei, since=look.looked_at, seen=look.appointments, registry=REGISTRY
    )
    assert keys(found) == ["new_fact", "note_added"]
    assert found.lines[0].refs["fact_ids"] == (str(new.id),)
    assert found.lines[1].text == "Mei wrote a note about Dr Tan on Thursday 3 September."
    # Unconfirmed doses: his tablet today is not taken yet — said at every look.
    assert [line.text for line in found.waiting] == ["One tablet today is not taken yet."]
    # A third look with nothing between says nothing changed since the last.
    last = await mark_looked(sg, context=rec.mei)
    quiet = await what_changed(
        sg, context=rec.mei, since=last.looked_at, seen=last.appointments, registry=REGISTRY
    )
    assert [line.text for line in quiet.lines] == ["Nothing changed since Thursday 3 September."]


async def test_a_correction_is_told_old_to_new_with_the_provenance_of_both(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    rec = await record(sg)
    look = await mark_looked(sg, context=rec.mei)
    clock.step(timedelta(minutes=1))
    old = rec.lab[0]
    new = await supersede_fact(sg, context=rec.owner, fact_id=old.id, value=231, confidence=0.95)
    found = await what_changed(sg, context=rec.mei, since=look.looked_at, seen=look.appointments)
    assert [line.text for line in found.lines] == [
        "The cholesterol test from Thursday 7 September was corrected."
    ]
    [corrected] = found.sections["facts"]["corrected"]
    assert corrected["old"] == {
        "fact_id": str(old.id),
        "artifact_id": str(rec.paper.id),
        "event_id": None,
    }
    assert corrected["new"]["fact_id"] == str(new.id)
    assert corrected["new"]["artifact_id"] == str(rec.paper.id)


async def test_a_visit_that_moved_is_told_by_its_new_status(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    rec = await record(sg)
    look = await mark_looked(sg, context=rec.mei)
    clock.step(timedelta(minutes=1))
    yes = await confirm(
        sg,
        rec.owner,
        StatusChange(appointment_id=rec.next_visit.id, status=AppointmentStatus.CONFIRMED),
    )
    await change_appointment_status(
        sg,
        context=rec.owner,
        appointment_id=rec.next_visit.id,
        status=AppointmentStatus.CONFIRMED,
        confirmation_id=yes.id,
    )
    found = await what_changed(sg, context=rec.mei, since=look.looked_at, seen=look.appointments)
    assert [line.text for line in found.lines] == [
        "The visit to Dr Tan on Thursday 10 September is confirmed."
    ]
    assert found.sections["visits"][0]["was"] == "planned"


async def test_a_new_amount_is_a_question_for_the_doctor_and_never_the_amount(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    rec = await record(sg)
    look = await mark_looked(sg, context=rec.mei)
    clock.step(timedelta(minutes=1))
    await add(sg, rec.owner, label("amlodipine", "10 mg"))
    found = await what_changed(
        sg, context=rec.mei, since=look.looked_at, seen=look.appointments, registry=REGISTRY
    )
    texts = [line.text for line in found.lines]
    assert "The new pack of your blood pressure tablet says a different amount." in texts
    assert "Ask Dr Tan about the new amount." in texts
    assert not any("10" in text or "mg" in text for text in texts)
    [changed] = found.sections["medicines"]["lines"]
    assert changed["change_kind"] == "dose_change" and changed["supersedes_id"]


async def test_the_things_we_do_not_wait_for_are_told(sg: AsyncSession, clock: FrozenClock) -> None:
    rec = await record(sg)
    look = await mark_looked(sg, context=rec.mei)
    clock.step(timedelta(minutes=1))
    said = await record_event(
        sg,
        context=rec.owner,
        kind=EventKind.SYMPTOM,
        occurred_at=clock.now(),
        label="a fall",
        source_channel=SourceChannel.APP,
    )
    await raise_flag(sg, context=rec.owner, feeling=Feeling.FALL, event_id=said.id)
    found = await what_changed(sg, context=rec.mei, since=look.looked_at, seen=look.appointments)
    assert "On Thursday 3 September you told Nura something we do not wait for." in [
        line.text for line in found.lines
    ]


async def test_a_narrow_key_is_told_which_parts_were_withheld(sg: AsyncSession) -> None:
    rec = await record(sg)
    kit = await let_in(
        sg,
        rec.owner,
        phone=KIT_PHONE,
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes={Scope.VISITS, Scope.READINGS},
    )
    found = await what_changed(sg, context=kit, since=None)
    assert set(found.withheld) == {
        Scope.MEDICINES,
        Scope.RECORDS,
        Scope.EMERGENCY,
        Scope.FAMILY,
    }
    assert {line.section for line in found.lines} <= {"look", "visits", "facts"}


@pytest.mark.parametrize(("language", "day"), [("ms", "Khamis"), ("zh", "星期四")])
async def test_the_lines_are_in_his_language_and_pass_plain_words(
    sg: AsyncSession, language: str, day: str
) -> None:
    rec = await record(sg, language=language)
    found = await what_changed(sg, context=rec.mei, since=None, registry=REGISTRY)
    assert found.language == language and found.dropped == 0
    for line in (*found.lines, *found.waiting):
        assert verified(line.text, language), line.text
    assert any(day in line.text for line in found.lines)


async def test_the_look_is_the_readers_own_and_on_the_trail(sg: AsyncSession) -> None:
    rec = await record(sg)
    look = await mark_looked(sg, context=rec.mei)
    assert look.person_id == rec.mei.person_id
    assert look.appointments == {
        str(rec.checkup.id): "attended",
        str(rec.next_visit.id): "planned",
    }
    assert any(
        e.target == "last_looked"
        and e.action is Action.WRITE
        and e.actor_person_id == rec.mei.person_id
        for e in await trail(sg, rec.owner)
    )
