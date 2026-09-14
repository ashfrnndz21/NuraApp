"""E12-02: the family thread with digests, mixing health cards and messages.

    Digest per day per caregiver; no stream.

A message is kept as said and no fact is read from it; cards and messages interleave, newest
first, a page at a time; the digest is whole sentences that pass the plain-words verifier,
narrowed to what the caregiver's key opens.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.drafts import FactDraft
from app.family.models import CardKind
from app.family.roster import add_slot, add_task
from app.family.thread import NotAMessage, digest, post_card, post_message, read_thread
from app.keys.confirm import confirm
from app.keys.context import KeyContext, OutOfScope
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import ConfidenceState, Event, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact
from app.safety.plain_words import verify
from app.state.service import current_state
from tests.family_support import MONDAY, household

FREE_TEXT = "Pa's BP was 190 over 100 this morning, I gave him 2 tablets of the water pill."


async def _rows(session: AsyncSession, table: type) -> int:  # type: ignore[type-arg]
    return int(await session.scalar(select(func.count()).select_from(table)) or 0)


async def _reading(session: AsyncSession, context: KeyContext, top: int, bottom: int) -> None:
    from app.db import utcnow

    now = utcnow()
    event = await record_event(
        session,
        context=context,
        kind=EventKind.READING,
        occurred_at=now,
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    draft = FactDraft(
        subject="blood_pressure",
        attribute="reading",
        value={"systolic": top, "diastolic": bottom},
        unit="mmHg",
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, context, draft)
    await assert_fact(
        session,
        context=context,
        subject=draft.subject,
        attribute=draft.attribute,
        value=draft.value,
        unit=draft.unit,
        confidence=1.0,
        confidence_state=draft.confidence_state,
        confirmation_id=yes.id,
        event_id=event.id,
        valid_from=now,
    )


async def test_a_message_is_kept_as_said_and_no_fact_is_read_from_it(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    facts, events = await _rows(sg, Fact), await _rows(sg, Event)

    entry = await post_message(sg, context=mei, text=FREE_TEXT)
    assert entry.text == FREE_TEXT and entry.card_kind is None and entry.state_id is None
    assert entry.author_person_id == h.mei.id
    assert (await _rows(sg, Fact), await _rows(sg, Event)) == (facts, events), (
        "the family talking to each other is not a fact about him"
    )
    with pytest.raises(NotAMessage):
        await post_message(sg, context=mei, text="x" * 281)
    with pytest.raises(NotAMessage):
        await post_message(sg, context=mei, text="   ")
    # A caregiver with the family scope posts; the helper, without it, is refused.
    kit = await h.ctx(sg, h.kit)
    await post_message(sg, context=kit, text="I can drive Thursday.")
    siti = await h.ctx(sg, h.siti)
    with pytest.raises(OutOfScope):
        await post_message(sg, context=siti, text="Pak tidak sehat")
    with pytest.raises(OutOfScope):
        await read_thread(sg, context=siti)


async def test_cards_and_messages_interleave_newest_first_a_page_at_a_time(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    pa = await h.ctx(sg, h.pa)
    mei = await h.ctx(sg, h.mei)
    await _reading(sg, pa, 138, 84)

    first = await post_message(sg, context=mei, text="Pa took his tablets, all good.")
    clock.step(timedelta(minutes=1))
    card = await post_card(sg, context=mei, kind=CardKind.READING)
    clock.step(timedelta(minutes=1))
    last = await post_message(sg, context=mei, text="I will drive on Thursday.")

    state = await current_state(sg, context=mei)
    assert card.card_kind is CardKind.READING and card.state_id == state.id and card.text is None

    page, cursor = await read_thread(sg, context=mei, limit=2)
    assert [entry.id for entry in page] == [last.id, card.id]
    assert cursor is not None
    older, end = await read_thread(sg, context=mei, cursor=cursor, limit=2)
    assert [entry.id for entry in older] == [first.id] and end is None


async def test_the_digest_is_whole_sentences_in_his_words_narrowed_to_the_key(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    pa = await h.ctx(sg, h.pa)
    mei = await h.ctx(sg, h.mei)
    await _reading(sg, pa, 138, 84)
    await add_slot(
        sg,
        context=mei,
        person_id=h.mei.id,
        role=KeyRole.CHIEF,
        weekdays=[0, 1, 2, 3, 4],
        from_time=time(8, 0),
        to_time=time(20, 0),
    )
    task = await add_task(sg, context=mei, what="buy the water pill", assigned_person_id=h.siti.id)
    await post_message(sg, context=mei, text=FREE_TEXT)
    await post_card(sg, context=mei, kind=CardKind.READING)
    await post_card(sg, context=mei, kind=CardKind.TASK, task_id=task.id)

    since = MONDAY - timedelta(days=1)
    kit = await h.ctx(sg, h.kit)
    for language in ("en", "ms", "zh"):
        summary = await digest(sg, context=kit, since=since, language=language)
        assert summary.language == language
        for index, line in enumerate(summary.lines):
            kind = "headline" if index == 0 else "line"
            assert not [f for f in verify(line, language, kind) if f.severity == "fail"], line
        # The family's own words travel beside Nura's lines, never inside them.
        assert FREE_TEXT not in " ".join(summary.lines)
        assert [e.text for e in summary.entries if e.kind == "message"] == [FREE_TEXT]

    summary = await digest(sg, context=kit, since=since, language="en")
    assert summary.headline == "Pa on Monday 14 September."
    kinds = [entry.kind for entry in summary.entries]
    assert kinds == ["message", "reading", "task"]
    assert summary.entries[1].lines == [
        "Mei wrote down Pa's blood pressure on Monday 14 September.",
        "It was 138 over 84.",
    ]
    assert summary.entries[2].lines == ["Siti will do this: buy the water pill."]
    assert summary.on_duty == ["Mei"] and summary.lines[-1] == "Mei is on duty today."

    # A caregiver whose key opens the family thread but not the readings sees that a card
    # was posted, not the numbers.
    from app.keys.grants import grant_key

    await grant_key(
        sg,
        context=pa,
        holder=h.kit,
        role=KeyRole.CAREGIVER,
        scopes=(ROLE_SCOPES[KeyRole.CAREGIVER] | {Scope.FAMILY}) - {Scope.READINGS},
    )
    kit = await h.ctx(sg, h.kit)
    assert Scope.READINGS not in kit.scopes
    narrowed = await digest(sg, context=kit, since=since, language="en")
    assert narrowed.entries[1].lines == [
        "Mei wrote down Pa's blood pressure on Monday 14 September."
    ]
    assert "138" not in " ".join(narrowed.lines)

    # Nothing since a moment after everything: the quiet line, and who is on duty.
    quiet = await digest(sg, context=mei, since=MONDAY + timedelta(hours=1), language="en")
    assert quiet.entries == []
    assert quiet.lines == [
        "Pa on Monday 14 September.",
        "There is nothing new since Monday 14 September.",
        "Mei is on duty today.",
    ]
