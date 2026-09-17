"""The owner's decision (2026-09-17): the fuller insurance record sits behind money — him and
his chief see it. Everyone else who can see a visit at all sees exactly one line, "bring his
insurance card", which reveals nothing about whether cover exists, which insurer, or what it
costs. A key that cannot see the visit at all is refused before either tier is reached."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import now
from app.insurance.policy import current_policies
from app.insurance.relevance import pre_visit_relevance
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.attach import require_appointment
from app.safety.plain_words import verify
from tests.safety_support import clinic, let_in, pa
from tests.test_insurance_policy import _write as write_policy
from tests.timeline_support import book


async def test_a_chief_sees_the_full_picture_when_cover_is_on_file(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591140001")
    tan = await clinic(sg, owner)
    mei = await let_in(sg, owner, phone="+6592220001", name="Mei", role=KeyRole.CHIEF)
    await write_policy(sg, owner, insurer_name="Great Eastern")
    visit = await book(sg, owner, tan, now(), "check-up")

    shown = await pre_visit_relevance(sg, context=mei, appointment_id=visit.id)
    assert shown.full is True
    assert [row.insurer_name for row in shown.policies] == ["Great Eastern"]
    joined = " ".join(line.text for line in shown.note)
    assert "Great Eastern" not in joined  # the note names cover may apply, never re-says it
    assert "may apply" in joined or "Confirm" in joined
    for word in ("covered", "cover is", "is covered"):
        assert word not in joined.lower() or "may apply" in joined.lower()
    assert any("insurance card" in line.text for line in shown.bring)


async def test_the_owner_sees_no_cover_on_file_when_there_is_none(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591140002")
    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    shown = await pre_visit_relevance(sg, context=owner, appointment_id=visit.id)
    assert shown.full is True
    assert shown.policies == ()
    assert shown.bring == ()
    assert any("no insurance policy" in line.text for line in shown.note)


async def test_a_helper_and_a_caregiver_are_refused_the_full_record_but_still_get_the_bring_card_line(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591140003")
    tan = await clinic(sg, owner)
    await write_policy(sg, owner, insurer_name="Great Eastern", guarantee_letter=True)
    visit = await book(sg, owner, tan, now(), "check-up")
    caregiver = await let_in(sg, owner, phone="+6594440003", name="Lin", role=KeyRole.CAREGIVER)

    # Refused the full record, on the trail: a caregiver holds VISITS but not MONEY.
    with pytest.raises(OutOfScope) as failed:
        await current_policies(sg, context=caregiver)
    assert failed.value.scope is Scope.MONEY

    # Still gets exactly the one line, nothing about the insurer, the cover, or the letter.
    shown = await pre_visit_relevance(sg, context=caregiver, appointment_id=visit.id)
    assert shown.full is False
    assert shown.policies == () and shown.note == ()
    assert [line.id for line in shown.bring] == ["insurance.bring_card"]
    assert "Great Eastern" not in shown.bring[0].text
    assert "guarantee" not in shown.bring[0].text.lower()
    assert "insurance card" in shown.bring[0].text


async def test_a_key_that_cannot_see_the_visit_at_all_is_refused_outright(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591140004")
    tan = await clinic(sg, owner)
    visit = await book(sg, owner, tan, now(), "check-up")
    # A pure helper key holds neither MONEY nor VISITS: the door beneath this module (reading
    # the visit at all, `app.memory.attach.require_appointment`) refuses it before either
    # tier is reached — this module does not widen that door to give the narrowed line.
    helper = await let_in(sg, owner, phone="+6593330004", name="Kit", role=KeyRole.HELPER)
    with pytest.raises(OutOfScope) as failed:
        await require_appointment(sg, context=helper, appointment_id=visit.id)
    assert failed.value.scope is Scope.VISITS
    with pytest.raises(OutOfScope):
        await pre_visit_relevance(sg, context=helper, appointment_id=visit.id)


async def test_the_narrowed_line_never_depends_on_whether_cover_exists(sg: AsyncSession) -> None:
    """The same line, whether or not a policy is on file — nothing is revealed either way."""
    with_cover_owner = await pa(sg, phone="+6591140005")
    tan = await clinic(sg, with_cover_owner)
    await write_policy(sg, with_cover_owner)
    visit_with_cover = await book(sg, with_cover_owner, tan, now(), "check-up")
    caregiver_with = await let_in(
        sg, with_cover_owner, phone="+6594440005", name="Lin", role=KeyRole.CAREGIVER
    )

    no_cover_owner = await pa(sg, phone="+6591140006")
    tan2 = await clinic(sg, no_cover_owner)
    visit_no_cover = await book(sg, no_cover_owner, tan2, now(), "check-up")
    caregiver_without = await let_in(
        sg, no_cover_owner, phone="+6594440006", name="Wan", role=KeyRole.CAREGIVER
    )

    shown_with = await pre_visit_relevance(sg, context=caregiver_with, appointment_id=visit_with_cover.id)
    shown_without = await pre_visit_relevance(
        sg, context=caregiver_without, appointment_id=visit_no_cover.id
    )
    assert shown_with.full is False and shown_without.full is False
    assert [line.id for line in shown_with.bring] == [line.id for line in shown_without.bring]


async def test_every_line_passes_plain_words_in_every_language(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591140007", language="ms")
    tan = await clinic(sg, owner)
    await write_policy(sg, owner, guarantee_letter=True)
    visit = await book(sg, owner, tan, now(), "check-up")

    for index, language in enumerate(("en", "ms", "zh")):
        full = await pre_visit_relevance(sg, context=owner, appointment_id=visit.id, language=language)
        for line in (*full.note, *full.bring):
            failures = [f for f in verify(line.text, language, "line") if f.severity == "fail"]
            assert failures == [], (language, line.text, failures)

        caregiver = await let_in(
            sg,
            owner,
            phone=f"+6595550{index:03d}7",
            name="Lin",
            role=KeyRole.CAREGIVER,
            language=language,
        )
        narrow = await pre_visit_relevance(
            sg, context=caregiver, appointment_id=visit.id, language=language
        )
        for line in narrow.bring:
            failures = [f for f in verify(line.text, language, "line") if f.severity == "fail"]
            assert failures == [], (language, line.text, failures)
