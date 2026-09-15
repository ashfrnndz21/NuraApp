"""E03-01 and E03-02 acceptance.

    E03-01  Every artefact can attach to an appointment; radar shows all three anchors.
    E03-02  An episode groups events across visits; timeline filters by episode.

The spine is the visits: the last check-up, the last visit and the next visit, said in his
words with the day and the date. Under it, newest first and paged, each visit with its
provider and each episode with its visits, and what hangs off each — papers, events, facts —
every one read under its own scope and withheld by name where the key does not reach, a part
the owner keeps "only me" included. Hanging a paper takes a person's yes for exactly that; a
card confirmed into an open episode hangs its photo there under the card's own yes.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import now
from app.delivery.timeline_strings import verified
from app.drafts import AttachDraft
from app.ingestion.notes import add_scribble
from app.ingestion.objects import LocalObjectStore
from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.attach import AlreadyHangsThere, attach_to_appointment, attach_to_episode
from app.memory.models import AppointmentStatus, ArtifactKind, EventKind, ProviderKind
from app.memory.spine import add_provider
from app.memory.timeline import NotACursor, episode_view, timeline
from app.memory.working import NoSuchEpisode, close_episode
from app.regions import Region
from tests.medicines_support import let_in
from tests.support import agree_to_recording
from tests.timeline_support import (
    KIT_PHONE,
    again,
    artefact,
    book,
    keep_only_me,
    record,
    refusals,
)


async def test_the_header_shows_all_three_anchors_in_his_words(sg: AsyncSession) -> None:
    rec = await record(sg)
    page = await timeline(sg, context=rec.owner)
    assert [anchor.key for anchor in page.header] == ["last_checkup", "last_visit", "next_visit"]
    assert [anchor.line for anchor in page.header] == [
        "Your last check-up was with Dr Tan on Monday 24 August.",
        "Your last visit was to Dr Tan on Monday 24 August.",
        "Your next visit is to Dr Tan on Thursday 10 September.",
    ]
    assert [anchor.appointment.id for anchor in page.header if anchor.appointment] == [
        rec.checkup.id,
        rec.checkup.id,
        rec.next_visit.id,
    ]


@pytest.mark.parametrize(("language", "day"), [("ms", "Isnin"), ("zh", "星期一")])
async def test_the_anchors_come_in_his_language_and_pass_plain_words(
    sg: AsyncSession, language: str, day: str
) -> None:
    rec = await record(sg, language=language)
    page = await timeline(sg, context=rec.owner)
    assert page.language == language
    for anchor in page.header:
        assert verified(anchor.line, language), anchor.line
        assert "Dr Tan" in anchor.line
    assert day in page.header[0].line


async def test_an_empty_spine_says_so_in_whole_lines(sg: AsyncSession) -> None:
    from tests.medicines_support import pa

    owner = await pa(sg, language="en")
    page = await timeline(sg, context=owner)
    assert [anchor.line for anchor in page.header] == [
        "No check-up is written down yet.",
        "No visit is written down yet.",
        "No next visit is booked yet.",
    ]
    assert page.items == ()


async def test_every_artefact_can_hang_off_a_visit_and_the_visit_shows_it(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    await agree_to_recording(sg, rec.owner)  # a visit's transcript is a consult (ADR 0003)
    hung = []
    for kind in ArtifactKind:
        paper = await artefact(sg, rec.owner, kind=kind)
        yes = await confirm(
            sg,
            rec.owner,
            AttachDraft(artifact_id=paper.id, episode_id=None, appointment_id=rec.checkup.id),
        )
        row = await attach_to_appointment(
            sg,
            context=rec.owner,
            artifact_id=paper.id,
            appointment_id=rec.checkup.id,
            confirmation_id=yes.id,
        )
        assert row.attached_by_person_id == rec.owner.person_id
        hung.append(paper.id)
    page = await timeline(sg, context=rec.owner)
    visit = next(item for item in page.items if item.id == rec.checkup.id)
    assert visit.provider is not None and visit.provider.name == "Dr Tan"
    assert {artifact.id for artifact in visit.hanging.artifacts} == set(hung)


async def test_hanging_a_paper_takes_a_yes_for_exactly_that_and_a_refusal_is_on_the_trail(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    paper = await artefact(sg, rec.owner)
    # A yes for this paper on the visit is not a yes for it on the illness.
    wrong = await confirm(
        sg,
        rec.owner,
        AttachDraft(artifact_id=paper.id, episode_id=None, appointment_id=rec.checkup.id),
    )
    with pytest.raises(NotWhatWasConfirmed):
        await attach_to_episode(
            sg,
            context=rec.owner,
            artifact_id=paper.id,
            episode_id=rec.episode.id,
            confirmation_id=wrong.id,
        )
    assert any(
        e.refused_because == "NotWhatWasConfirmed" and e.target == "attachment"
        for e in await refusals(sg, rec.owner)
    )
    # Once is enough.
    again_yes = await confirm(
        sg,
        rec.owner,
        AttachDraft(artifact_id=rec.paper.id, episode_id=rec.episode.id, appointment_id=None),
    )
    with pytest.raises(AlreadyHangsThere):
        await attach_to_episode(
            sg,
            context=rec.owner,
            artifact_id=rec.paper.id,
            episode_id=rec.episode.id,
            confirmation_id=again_yes.id,
        )
    # Nothing hangs off an illness that is over.
    await close_episode(sg, context=rec.owner, episode_id=rec.episode.id)
    late = await confirm(
        sg,
        rec.owner,
        AttachDraft(artifact_id=paper.id, episode_id=rec.episode.id, appointment_id=None),
    )
    with pytest.raises(NoSuchEpisode):
        await attach_to_episode(
            sg,
            context=rec.owner,
            artifact_id=paper.id,
            episode_id=rec.episode.id,
            confirmation_id=late.id,
        )


async def test_an_episode_groups_events_across_visits(sg: AsyncSession) -> None:
    rec = await record(sg)
    lim = await add_provider(
        sg, context=rec.owner, name="Dr Lim", kind=ProviderKind.CLINIC, region=Region.SG
    )
    second = await book(
        sg,
        rec.owner,
        lim,
        now() - timedelta(days=2),
        "chest",
        steps=(AppointmentStatus.CONFIRMED, AppointmentStatus.ATTENDED),
        episode_id=rec.episode.id,
    )
    view = await episode_view(sg, context=rec.owner, episode_id=rec.episode.id)
    assert [visit.id for visit in view.visits] == [rec.next_visit.id, second.id]
    assert {visit.provider.name for visit in view.visits if visit.provider} == {"Dr Tan", "Dr Lim"}
    hanging = view.item.hanging
    assert [event.kind for event in hanging.events] == [EventKind.READING]
    assert [artifact.id for artifact in hanging.artifacts] == [rec.paper.id]
    assert {fact.id for fact in hanging.facts} == {rec.readings[1].id, *(f.id for f in rec.lab)}
    assert view.item.visits == (rec.next_visit.id, second.id)


async def test_the_timeline_filters_by_episode(sg: AsyncSession) -> None:
    rec = await record(sg)
    page = await timeline(sg, context=rec.owner, episode_id=rec.episode.id)
    assert [item.id for item in page.items] == [rec.next_visit.id, rec.episode.id]
    everything = await timeline(sg, context=rec.owner)
    assert [item.id for item in everything.items] == [
        rec.next_visit.id,
        rec.episode.id,
        rec.checkup.id,
    ]


async def test_newest_first_paged_by_cursor_and_narrowed_by_time(sg: AsyncSession) -> None:
    rec = await record(sg)
    first = await timeline(sg, context=rec.owner, limit=1)
    assert [item.id for item in first.items] == [rec.next_visit.id]
    assert first.next_cursor is not None
    second = await timeline(sg, context=rec.owner, limit=1, cursor=first.next_cursor)
    third = await timeline(sg, context=rec.owner, limit=1, cursor=second.next_cursor)
    assert [second.items[0].id, third.items[0].id] == [rec.episode.id, rec.checkup.id]
    assert third.next_cursor is None
    # The same cursor answers the same page.
    repeat = await timeline(sg, context=rec.owner, limit=1, cursor=first.next_cursor)
    assert [item.id for item in repeat.items] == [rec.episode.id]
    recent = await timeline(sg, context=rec.owner, since=now() - timedelta(days=5))
    assert [item.id for item in recent.items] == [rec.next_visit.id, rec.episode.id]
    before = await timeline(sg, context=rec.owner, until=now())
    assert [item.id for item in before.items] == [rec.episode.id, rec.checkup.id]
    with pytest.raises(NotACursor):
        await timeline(sg, context=rec.owner, cursor="not a cursor")


async def test_each_part_is_read_under_its_own_scope_and_withheld_by_name(
    sg: AsyncSession,
) -> None:
    rec = await record(sg)
    kit = await let_in(
        sg, rec.owner, phone=KIT_PHONE, name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.VISITS}
    )
    page = await timeline(sg, context=kit)
    assert [item.kind for item in page.items] == ["appointment", "appointment"]
    assert all(not item.hanging.artifacts and not item.hanging.facts for item in page.items)
    assert set(page.withheld) == {Scope.RECORDS, Scope.READINGS, Scope.MEDICINES}
    # The spine is the visits'; a key without them is refused, and it is written down.
    siti = await let_in(
        sg,
        rec.owner,
        phone="+6597770004",
        name="Siti",
        role=KeyRole.HELPER,
        scopes={Scope.MEDICINES},
    )
    with pytest.raises(OutOfScope):
        await timeline(sg, context=siti)
    assert any(
        e.refused_because == "OutOfScope"
        and e.scope is Scope.VISITS
        and e.actor_person_id == siti.person_id
        for e in await refusals(sg, rec.owner)
    )


async def test_a_part_the_owner_keeps_only_me_is_withheld_from_his_chief(sg: AsyncSession) -> None:
    rec = await record(sg)
    before = await episode_view(sg, context=rec.mei, episode_id=rec.episode.id)
    assert rec.readings[1].id in {fact.id for fact in before.item.hanging.facts}
    await keep_only_me(sg, rec.owner, Scope.READINGS)
    mei = await again(sg, rec.mei)
    page = await timeline(sg, context=mei)
    assert Scope.READINGS in page.withheld
    episode = next(item for item in page.items if item.id == rec.episode.id)
    # The number is gone, and so is the moment it was taken; the paper stays.
    assert {fact.id for fact in episode.hanging.facts} == {fact.id for fact in rec.lab}
    assert episode.hanging.events == ()
    # Pa himself still sees all of it.
    his = await episode_view(sg, context=rec.owner, episode_id=rec.episode.id)
    assert rec.readings[1].id in {fact.id for fact in his.item.hanging.facts}


async def test_the_notes_on_an_event_hang_off_it_by_reference(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """A voice note or a scribble left on the reading taken during the illness (E02-06) hangs
    off that event on the timeline: the note's row, never its image or its words. A private
    note is the notes scope's; a key without it sees the shared one and is told `notes` was
    withheld."""
    rec = await record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    drawn = b"\x89PNG\r\n\x1a\n a scribble on this morning's blood pressure"
    for private in (False, True):
        await add_scribble(
            sg,
            context=rec.owner,
            store=store,
            event_id=rec.readings[1].event_id,
            data=drawn + str(private).encode(),
            content_type="image/png",
            captured_at=now(),
            private=private,
        )
    his = await episode_view(sg, context=rec.owner, episode_id=rec.episode.id)
    # Written in the same instant here, so compared as a set of kinds, not an order.
    assert sorted(note.private for note in his.item.hanging.notes) == [False, True]
    assert {note.event_id for note in his.item.hanging.notes} == {rec.readings[1].event_id}
    kit = await let_in(
        sg,
        rec.owner,
        phone=KIT_PHONE,
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes={Scope.VISITS, Scope.RECORDS, Scope.READINGS},
    )
    page = await timeline(sg, context=kit)
    episode = next(item for item in page.items if item.id == rec.episode.id)
    assert [note.private for note in episode.hanging.notes] == [False]
    assert Scope.NOTES in page.withheld
