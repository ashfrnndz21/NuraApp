"""E12-04: the audit trail visible to Dad, with "only me" marking.

    Dad sees who looked at what; only-me hides from all grants.

Only me takes the part out of every live key at once and out of every key cut after; a
caregiver reading the notes a moment later is refused and it is on the trail in his words.
The trail never renders a class name, a table name or an id, in any of the three languages.
"""

from __future__ import annotations

import importlib
import pkgutil
import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app
from app.audit.models import Outcome
from app.audit.strings import DEFAULT, REFUSAL_FAMILY, refusal_family, refused_lines
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import Base
from app.errors import Refusal
from app.family.privacy import (
    AlreadyMarked,
    NotAPartToMark,
    NotMarked,
    NotTheOwner,
    lift_only_me,
    mark_only_me,
    marked,
    only_me_draft,
)
from app.family.trail import trail
from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.keys.context import OutOfScope
from app.keys.grants import grant_key, revoke_key
from app.keys.scopes import ALL_SCOPES, KeyRole, Scope
from app.notes.service import list_notes, write_note
from tests.family_support import MONDAY, household

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _every_refusal_name() -> set[str]:
    """Every `Refusal` subclass the app defines, by importing every module under `app`."""
    for module in pkgutil.walk_packages(app.__path__, "app."):
        if module.name != "app.main":  # the process, which reads its settings on import
            importlib.import_module(module.name)

    def walk(cls: type) -> set[str]:
        found = {cls.__name__}
        for sub in cls.__subclasses__():
            found |= walk(sub)
        return found

    return walk(Refusal) - {"Refusal"}


async def _mark(session: AsyncSession, h, scope: Scope):  # type: ignore[no-untyped-def]
    pa = await h.ctx(session, h.pa)
    yes = await confirm(session, pa, only_me_draft(scope, only_me=True))
    return await mark_only_me(session, context=pa, scope=scope, confirmation_id=yes.id)


async def test_only_me_takes_the_part_out_of_a_live_key_at_once_and_it_is_on_the_trail(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    pa = await h.ctx(sg, h.pa)
    await write_note(sg, context=pa, text="I did not tell the children about the fall.")
    mei = await h.ctx(sg, h.mei)
    assert len(await list_notes(sg, context=mei)) == 1, "a chief preset to the notes reads them"

    await _mark(sg, h, Scope.NOTES)

    # The very next resolution of Mei's key is without the notes; her key row is untouched.
    mei = await h.ctx(sg, h.mei)
    assert Scope.NOTES not in mei.scopes and mei.key_id == h.mei_key.id
    with pytest.raises(OutOfScope):
        await list_notes(sg, context=mei)

    refused = [
        e
        for e in await read_audit(sg, context=pa, actor_person_id=h.mei.id)
        if e.outcome is Outcome.REFUSED and e.scope is Scope.NOTES
    ]
    assert refused and refused[0].refused_because == "OutOfScope"

    # And Pa reads it in his words: who, what, which day, and that only he can.
    days = await trail(sg, context=pa, language="en")
    assert days[0].day_words == "Monday 14 September"
    lines = [line for day in days for line in day.lines if line.who == "Mei"]
    assert [
        "Mei asked to see your private notes on Monday 14 September.",
        "Only you can.",
    ] in [line.sentences for line in lines]


async def test_only_me_keeps_a_new_key_out_of_the_part_until_it_is_lifted(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    pa = await h.ctx(sg, h.pa)
    row = await _mark(sg, h, Scope.MONEY)

    recut = await grant_key(sg, context=pa, holder=h.mei, role=KeyRole.CHIEF)
    assert Scope.MONEY not in recut.scopes_held
    assert (await h.ctx(sg, h.mei)).scopes == ALL_SCOPES - {Scope.MONEY}

    yes = await confirm(sg, pa, only_me_draft(Scope.MONEY, only_me=False))
    lifted = await lift_only_me(sg, context=pa, scope=Scope.MONEY, confirmation_id=yes.id)
    assert lifted.id == row.id and lifted.lifted_at is not None
    assert lifted.lifted_by_person_id == h.pa.id
    # The key cut while the mark stood stays as cut; a key cut before it opens the part again.
    assert Scope.MONEY not in (await h.ctx(sg, h.mei)).scopes
    await revoke_key(sg, context=pa, key_id=recut.id)
    again = await grant_key(sg, context=pa, holder=h.mei, role=KeyRole.CHIEF)
    assert Scope.MONEY in again.scopes_held
    assert len(await marked(sg, context=pa)) == 1


async def test_only_the_owner_marks_only_real_parts_on_his_own_yes(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    pa = await h.ctx(sg, h.pa)
    mei = await h.ctx(sg, h.mei)

    yes = await confirm(sg, mei, only_me_draft(Scope.NOTES, only_me=True))
    with pytest.raises(NotTheOwner):
        await mark_only_me(sg, context=mei, scope=Scope.NOTES, confirmation_id=yes.id)
    for scope in (Scope.PROFILE, Scope.EMERGENCY):
        yes = await confirm(sg, pa, only_me_draft(scope, only_me=True))
        with pytest.raises(NotAPartToMark):
            await mark_only_me(sg, context=pa, scope=scope, confirmation_id=yes.id)
    # A yes for lifting does not mark, and the other way round.
    yes = await confirm(sg, pa, only_me_draft(Scope.NOTES, only_me=False))
    with pytest.raises(NotWhatWasConfirmed):
        await mark_only_me(sg, context=pa, scope=Scope.NOTES, confirmation_id=yes.id)
    with pytest.raises(NotMarked):
        await lift_only_me(sg, context=pa, scope=Scope.NOTES, confirmation_id=yes.id)
    await _mark(sg, h, Scope.NOTES)
    yes = await confirm(sg, pa, only_me_draft(Scope.NOTES, only_me=True))
    with pytest.raises(AlreadyMarked):
        await mark_only_me(sg, context=pa, scope=Scope.NOTES, confirmation_id=yes.id)

    names = {
        e.refused_because for e in await read_audit(sg, context=pa) if e.outcome is Outcome.REFUSED
    }
    assert {
        "NotTheOwner",
        "NotAPartToMark",
        "NotWhatWasConfirmed",
        "NotMarked",
        "AlreadyMarked",
    } <= names


async def test_the_trail_in_his_words_never_renders_a_class_name_a_table_or_an_id(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    pa = await h.ctx(sg, h.pa)
    kit = await h.ctx(sg, h.kit)
    await write_note(sg, context=pa, text="Private.")
    with pytest.raises(OutOfScope):
        await list_notes(sg, context=kit)
    await _mark(sg, h, Scope.NOTES)
    mei = await h.ctx(sg, h.mei)
    with pytest.raises(OutOfScope):
        await list_notes(sg, context=mei)
    await revoke_key(sg, context=pa, key_id=h.kit_key.id)
    with pytest.raises(Refusal):
        await h.ctx(sg, h.kit)

    # Class names, and the table names that are code and not words ("audit_entry",
    # "state_snapshot"); a table called "key" or "note" shares its name with his words.
    forbidden = (
        _every_refusal_name()
        | {table for table in Base.metadata.tables if "_" in table}
        | {"Refusal", "None", "OutOfScope", "refused", "REFUSED"}
    )
    for language in ("en", "ms", "zh"):
        days = await trail(sg, context=pa, language=language)
        assert days, language
        sentences = [s for day in days for line in day.lines for s in line.sentences]
        assert sentences
        for sentence in sentences:
            assert not _UUID.search(sentence), sentence
            for word in forbidden:
                assert not re.search(rf"\b{re.escape(word)}\b", sentence), (word, sentence)
        # Grouped by day, newest first, each with the day in words.
        assert all(day.day_words for day in days)
        assert [day.day for day in days] == sorted((day.day for day in days), reverse=True)
        for day in days:
            assert [line.at for line in day.lines] == sorted(
                (line.at for line in day.lines), reverse=True
            )
    days = await trail(sg, context=pa, language="en")
    kit_lines = [line.sentences for day in days for line in day.lines if line.who == "Kit"]
    assert [
        "Kit asked to see your private notes on Monday 14 September.",
        "Only you can.",
    ] in kit_lines
    assert [
        "Kit tried to open your record on Monday 14 September.",
        "That key is closed, so nothing was shown.",
    ] in kit_lines
    # A repeated reach on one day is one sentence, not one per try.
    assert (
        kit_lines.count(
            ["Kit asked to see your private notes on Monday 14 September.", "Only you can."]
        )
        == 1
    )
    # The same day in Malay and Chinese.
    assert (await trail(sg, context=pa, language="ms"))[0].day_words == "Isnin 14 September"
    assert (await trail(sg, context=pa, language="zh"))[0].day_words == "9月14日星期一"


def test_every_refusal_nura_raises_renders_as_a_sentence_and_so_does_a_name_from_tomorrow() -> None:
    names = _every_refusal_name()
    assert names >= {"OutOfScope", "NoKey", "WouldWiden", "NotTheDoer", "NotTheOwner"}
    for name in names | {"SomethingNobodyWroteYet"}:
        family = refusal_family(name, Scope.RECORDS, only_me=frozenset())
        for language in ("en", "ms", "zh"):
            lines = refused_lines(
                family, language, who="Mei", what="your papers", day="Monday 14 September"
            )
            assert lines and all(lines)
            assert not any(name in line or "{" in line for line in lines), (name, lines)
    assert refusal_family("SomethingNobodyWroteYet", Scope.RECORDS, only_me=frozenset()) == DEFAULT
    # A part he keeps to himself answers "only you can", by mark or by preset.
    assert refusal_family("OutOfScope", Scope.NOTES, only_me=frozenset()) == "only_you"
    assert refusal_family("OutOfScope", Scope.MEDICINES, only_me=frozenset({Scope.MEDICINES})) == (
        "only_you"
    )
    assert refusal_family("OutOfScope", Scope.MEDICINES, only_me=frozenset()) == "no_key_to_part"
    # Every name in the map is a family that has words in every language.
    for language in ("en", "ms", "zh"):
        for family in set(REFUSAL_FAMILY.values()):
            assert refused_lines(family, language, who="Mei", what="x", day="Monday 14 September")
