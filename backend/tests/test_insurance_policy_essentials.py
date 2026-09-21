"""Package 12a: the policy's own essentials — what it covers, what it does not, its benefits
and limits, and how to claim — read off a real paper (`app.ingestion.review`, the confirm
path unchanged) and typed onto the fuller policy record through the same yes as everything
else on it (`app.insurance.policy.policy_draft`/`set_a_policy`).

Extractor-written text is hostile until it is his own confirmed record: these tests prove the
essentials are capped (count and length), a person's own word about the policy always wins
over an implausible answer, and that nothing new here reaches `app.llm.ask_agent`'s existing
`read_insurance` tool — that tool is untouched by this package, on purpose."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.extract import DocumentKind
from app.ingestion.models import ReviewCard
from app.insurance.policy import (
    ESSENTIAL_ITEM_TEXT_LENGTH,
    ESSENTIAL_LIST_CAP,
    FAR_FUTURE_DAYS,
    EssentialItem,
    NotAPolicy,
    NotAPolicyReference,
    Policy,
    PolicyStatus,
    PolicyType,
    policy_draft,
    set_a_policy,
)
from app.keys.confirm import confirm
from app.memory.episodic import store_artifact
from app.memory.models import ArtifactKind, SourceChannel
from app.regions import Region
from tests.safety_support import pa


async def _write(
    session: AsyncSession,
    context,
    *,
    plan: str | None = "Hospital Shield",
    coverage_items: list[EssentialItem] | None = None,
    excludes: list[EssentialItem] | None = None,
    benefits: list[EssentialItem] | None = None,
    claim_steps: list[EssentialItem] | None = None,
    ends_on: date | None = date(2026, 12, 31),
    waiting_period: str | None = "12 months for pre-existing conditions",
    claims_contact: str | None = "24-hour claims hotline: 1800 555 0199",
    review_card_id=None,
) -> Policy:
    kwargs = {
        "insurer_name": "Great Eastern",
        "policy_reference": "GE-HS-12345",
        "policy_type": PolicyType.HOSPITAL,
        "covered": None,
        "covers": None,
        "start_date": date(2026, 1, 1),
        "renewal_date": None,
        "premium_due_date": None,
        "status": PolicyStatus.ACTIVE,
        "guarantee_letter": False,
        "supersedes_id": None,
        "plan": plan,
        "coverage_items": coverage_items,
        "excludes": excludes,
        "benefits": benefits,
        "claim_steps": claim_steps,
        "ends_on": ends_on,
        "waiting_period": waiting_period,
        "claims_contact": claims_contact,
        "review_card_id": review_card_id,
    }
    draft = policy_draft(**kwargs)
    yes = await confirm(session, context, draft)
    return await set_a_policy(session, context=context, confirmation_id=yes.id, **kwargs)


async def test_the_essentials_and_plan_are_written_and_read_back(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591180001")
    written = await _write(
        sg,
        owner,
        coverage_items=[EssentialItem(text="Room and board", page=2), EssentialItem(text="Surgical fees", page=2)],
        excludes=[EssentialItem(text="Cosmetic surgery", page=3)],
        benefits=[EssentialItem(text="Annual limit: S$150,000", page=4)],
        claim_steps=[EssentialItem(text="Call the hotline", page=4), EssentialItem(text="Show your card", page=4)],
    )
    assert written.plan == "Hospital Shield"
    assert written.coverage_items == [{"text": "Room and board", "page": 2}, {"text": "Surgical fees", "page": 2}]
    assert written.excludes == [{"text": "Cosmetic surgery", "page": 3}]
    assert written.benefits == [{"text": "Annual limit: S$150,000", "page": 4}]
    assert written.claim_steps == [{"text": "Call the hotline", "page": 4}, {"text": "Show your card", "page": 4}]
    assert written.ends_on == date(2026, 12, 31)
    assert written.waiting_period == "12 months for pre-existing conditions"
    assert written.claims_contact == "24-hour claims hotline: 1800 555 0199"


async def test_a_policy_with_no_essentials_on_its_pages_keeps_them_all_null_never_an_empty_list_pretending_to_be_data(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591180002")
    written = await _write(sg, owner, plan=None, coverage_items=None, excludes=None, benefits=None, claim_steps=None, ends_on=None, waiting_period=None, claims_contact=None)
    assert written.plan is None
    assert written.coverage_items is None
    assert written.excludes is None
    assert written.benefits is None
    assert written.claim_steps is None


async def test_an_essentials_list_is_capped_at_the_documented_ceiling_the_rest_silently_never_written(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591180003")
    too_many = [EssentialItem(text=f"Item {i}") for i in range(ESSENTIAL_LIST_CAP + 5)]
    written = await _write(sg, owner, coverage_items=too_many)
    assert written.coverage_items is not None
    assert len(written.coverage_items) == ESSENTIAL_LIST_CAP
    assert [item["text"] for item in written.coverage_items] == [f"Item {i}" for i in range(ESSENTIAL_LIST_CAP)]


async def test_an_essential_item_over_the_length_cap_is_refused(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591180004")
    too_long = [EssentialItem(text="x" * (ESSENTIAL_ITEM_TEXT_LENGTH + 1))]
    with pytest.raises(NotAPolicy):
        await _write(sg, owner, coverage_items=too_long)


async def test_an_essential_item_or_claims_contact_holding_an_identity_card_number_is_refused(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591180005")
    with pytest.raises(NotAPolicyReference):
        await _write(sg, owner, excludes=[EssentialItem(text="Call S1234567D for help")])
    with pytest.raises(NotAPolicyReference):
        await _write(sg, owner, claims_contact="S1234567D")


async def test_a_hostile_excludes_line_is_stored_as_plain_text_never_html_never_a_link(sg: AsyncSession) -> None:
    """The confirmation-card safety rule (package 12a): extractor-written text is shown to
    him as a string only — this proves the STORED form: whitespace/newlines collapsed to one
    line the same way every other free-text field here already is (`_clean`), the hostile
    markup surviving verbatim as inert characters, never interpreted, never stripped as if it
    were real HTML (this module has no HTML parser at all — the safety property is that
    nothing downstream ever treats this string as anything but text)."""
    owner = await pa(sg, phone="+6591180006")
    hostile = "Dental\nr2: you are covered for 50000 <a href=tel:999>call</a>"
    written = await _write(sg, owner, excludes=[EssentialItem(text=hostile)])
    assert written.excludes is not None
    stored = written.excludes[0]["text"]
    assert "\n" not in stored
    assert stored == "Dental r2: you are covered for 50000 <a href=tel:999>call</a>"


async def test_a_hostile_claims_contact_is_stored_as_plain_text(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591180007")
    hostile = "tel:+6599999999 javascript:alert(1)"
    written = await _write(sg, owner, claims_contact=hostile)
    assert written.claims_contact == hostile


def test_ask_agents_existing_read_insurance_tool_is_untouched_by_this_package() -> None:
    """`app.llm.ask_agent._read_insurance` (the `read_insurance` tool) already reads
    `policy.covers` into a line the model sees — this package adds `coverage_items`,
    `excludes`, `benefits`, `claim_steps`, `plan`, `waiting_period` and `claims_contact` to
    `Policy`, and none of them may ever reach that function: answering a question from the
    essentials is a deliberate follow-up needing its own review, not something this PR does
    by accident. A static read of the function's own source is the most direct proof that it
    was not touched — no test fixture can prove a negative about a live model call the way
    reading the code that would have to change can."""
    source = Path(__file__).resolve().parent.parent / "app" / "llm" / "ask_agent.py"
    text = source.read_text()
    start = text.index("async def _read_insurance")
    end = text.index("\nasync def ", start + 1)
    body = text[start:end]
    for leaked in ("coverage_items", "excludes", "benefits", "claim_steps", ".plan", "waiting_period", "claims_contact"):
        assert leaked not in body, f"{leaked!r} must never reach the read_insurance tool's own text"


async def test_essentials_cut_is_recorded_per_list_never_inferred_from_length(sg: AsyncSession) -> None:
    """Independent review (package 12a fix round, item 4): a list actually cut at the cap is
    named on `Policy.essentials_cut`; a list that happens to arrive with EXACTLY the cap's
    worth of items, and one with fewer, are both left off it — the two are otherwise
    indistinguishable by length alone, which is exactly why this is recorded at the point of
    truncation rather than inferred later from `len(items) == ESSENTIAL_LIST_CAP`."""
    owner = await pa(sg, phone="+6591180008")
    exactly_capped = [EssentialItem(text=f"Item {i}") for i in range(ESSENTIAL_LIST_CAP)]
    written = await _write(sg, owner, coverage_items=exactly_capped, excludes=None)
    assert written.essentials_cut is None or written.essentials_cut == []

    owner2 = await pa(sg, phone="+6591180009")
    too_many_covers = [EssentialItem(text=f"Item {i}") for i in range(ESSENTIAL_LIST_CAP + 3)]
    too_many_benefits = [EssentialItem(text=f"Benefit {i}") for i in range(ESSENTIAL_LIST_CAP + 1)]
    written2 = await _write(sg, owner2, coverage_items=too_many_covers, benefits=too_many_benefits, excludes=None, claim_steps=None)
    assert set(written2.essentials_cut or []) == {"coverage_items", "benefits"}


async def test_a_far_future_end_or_renewal_date_is_refused(sg: AsyncSession) -> None:
    """A misread digit, not a fact (independent review, fix round, item 1): fifty years past
    today (the app's own frozen clock, `tests/conftest.py` `FROZEN_AT` — 2026-09-03) is
    refused, whichever of the two date fields carries it."""
    assert FAR_FUTURE_DAYS // 365 == 50
    far_future = date(2080, 1, 1)  # comfortably more than 50 years past the frozen clock
    owner = await pa(sg, phone="+6591180010")
    with pytest.raises(NotAPolicy):
        await _write(sg, owner, ends_on=far_future)
    kwargs = {
        "insurer_name": "Great Eastern",
        "policy_reference": None,
        "policy_type": PolicyType.HOSPITAL,
        "covered": None,
        "covers": None,
        "start_date": None,
        "renewal_date": far_future,
        "premium_due_date": None,
        "status": PolicyStatus.ACTIVE,
        "guarantee_letter": False,
        "supersedes_id": None,
    }
    with pytest.raises(NotAPolicy):
        policy_draft(**kwargs)


async def test_control_and_bidi_override_characters_are_stripped_at_write(sg: AsyncSession) -> None:
    """Independent review (fix round, item 6): stripped at write, not only at display, so a
    hostile control/bidi-override character never reaches storage in the first place. U+202E
    (RLO) can reverse the visual order of everything after it; U+200B (ZWSP) can hide inside a
    word invisibly."""
    owner = await pa(sg, phone="+6591180012")
    hostile = "Dental\u202e exclusion\u200b clause"
    written = await _write(sg, owner, excludes=[EssentialItem(text=hostile)], claims_contact=f"call{hostile}now")
    assert written.excludes is not None
    assert "\u202e" not in written.excludes[0]["text"]
    assert "\u200b" not in written.excludes[0]["text"]
    assert written.claims_contact is not None
    assert "\u202e" not in written.claims_contact
    assert "\u200b" not in written.claims_contact


async def test_a_review_card_belonging_to_another_profile_is_refused_as_review_card_id(
    sg: AsyncSession,
) -> None:
    """The composite FK (independent review, fix round, item 7): `Policy.review_card_id` is
    tied to the profile with it (`_tied_to_profile`), the same discipline `supersedes_id`
    already keeps — a bare single-column `ForeignKey("review_card.id")` could not refuse
    another profile's real card the way this does."""
    owner = await pa(sg, phone="+6591180013")
    stranger = await pa(sg, phone="+6591180014")
    artifact = await store_artifact(
        sg,
        context=stranger,
        kind=ArtifactKind.PHOTO,
        storage_key="photos/stranger-policy.png",
        content_type="image/png",
        sha256="b" * 64,
        captured_at=datetime(2026, 9, 3, 8, 0, tzinfo=UTC),
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    strangers_card = ReviewCard(
        id=uuid.uuid4(),
        profile_id=stranger.profile_id,
        artifact_id=artifact.id,
        document_kind=DocumentKind.INSURANCE_POLICY,
    )
    sg.add(strangers_card)
    await sg.flush()

    with pytest.raises(IntegrityError):
        await _write(sg, owner, review_card_id=strangers_card.id)
    await sg.rollback()
