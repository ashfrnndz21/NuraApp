"""The feed at the service: what the schema and the doors refuse, and the ranking's parts.

A card names its State or is not written; a card with a failing line is not written and the
refusal is on the trail; a learning card from outside the allowlist is not written; a
medicine on the list starts an explainer and a daily safety job, and a notice — whether or
not it matches the batch on his pack — is held for the caregiver, or rerouted to the memo as
a doctor question, and never delivered to him (#181; `items.NoticeNotForPatient` refuses one
built for `DeliverTo.PATIENT` outright).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.delivery.feed import search as search_module
from app.delivery.feed.compose import Day, around_for, plain_day, refresh, today_for
from app.delivery.feed.compress import (
    Compressed,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    changes_treatment,
)
from app.delivery.feed.items import (
    SURFACE_OF,
    NoticeNotForPatient,
    NotPlainWords,
    TreatmentChangingCard,
    Why,
    create_item,
)
from app.delivery.feed.models import (
    CardType,
    DeliverTo,
    FeedItem,
    JobKind,
    JobStatus,
    ReviewStatus,
    SearchJob,
    Source,
    SourceKind,
    Supply,
)
from app.delivery.feed.rank import (
    PAGE_SIZE,
    NotACursor,
    _endless,
    decode_cursor,
    encode_cursor,
    feed_page,
    in_quiet_hours,
)
from app.delivery.feed.search import Engine, create_job, list_jobs, run_job
from app.delivery.feed.sources import SourceNotAllowlisted
from app.delivery.strings import Lines, learning_lines, needs_doctor_look_lines, render
from app.drugs.fixture import FixtureRegistry
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import KeyRole, Scope
from app.language.models import ReviewItem
from app.memory.episodic import store_artifact
from app.memory.models import ArtifactKind, SourceChannel
from app.memory.semantic import assert_fact
from app.reasoning.visits.memos import current_memos
from app.reasoning.visits.models import MemoKind
from app.reasoning.visits.questions import question_from_memo
from app.regions import Region
from app.safety.boundary import Surface, boundary_line
from app.safety.plain_words import verify
from app.state.models import NotRenderedFromState
from app.state.service import NoBoundaryLine, current_state
from tests.conftest import FEED
from tests.medicines_support import let_in
from tests.support import OPENING_CONSENT

MONDAY = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
ENGINE = Engine(
    searcher=FixtureSearcher(FEED),
    compressor=FixtureCompressor(FEED),
    registry=FixtureRegistry.load(),
)


async def _pa(
    session: AsyncSession, phone: str = "+6591310011", language: str = "en"
) -> KeyContext:
    pa = await register_person(session, region=Region.SG, display_name="Pa", phone_e164=phone)
    profile = await create_own_profile(
        session, region=Region.SG, owner=pa, consent=OPENING_CONSENT, language=language
    )
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


async def _label(session: AsyncSession, context: KeyContext, **fields: object) -> None:
    """Medicine facts read off one label photo, the way the review card writes them."""
    photo = await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/label-{uuid.uuid4()}.jpg",
        content_type="image/jpeg",
        sha256="d" * 64,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    for attribute, value in fields.items():
        await assert_fact(
            session,
            context=context,
            subject="medicine",
            attribute=attribute,
            value=value,
            confidence=0.95,
            artifact_id=photo.id,
        )


def _lines(*body: str, why: str = "You took your blood pressure today.") -> Lines:
    return Lines(
        language="en", headline="Your blood pressure today", body=body, voice=body, why=why
    )


# --- the schema and the doors ------------------------------------------------------------------


async def test_a_card_that_names_no_state_is_refused_by_the_table(sg: AsyncSession) -> None:
    context = await _pa(sg)
    sg.add(
        FeedItem(
            profile_id=context.profile_id,
            type=CardType.GATE,
            supply=Supply.GATE,
            caps_class="supply",
            deliver_to=DeliverTo.PATIENT,
            scope=Scope.PROFILE,
            language="en",
            format="text",
            headline="That is all that is new",
            body=[],
            voice=[],
            why={},
            priority=1,
            day="2026-09-03",
            dedupe_key="gate:bare",
            expires_at=MONDAY,
        )
    )
    with pytest.raises(NotRenderedFromState):
        await sg.flush()
    await sg.rollback()


async def test_a_card_with_a_line_that_fails_plain_words_is_not_made_and_the_refusal_is_on_the_trail(
    sg: AsyncSession,
) -> None:
    context = await _pa(sg)
    state = await current_state(sg, context=context)
    with pytest.raises(NotPlainWords) as refused:
        await create_item(
            sg,
            context=context,
            state=state,
            type=CardType.READING,
            lines=_lines("Your BP reading was logged; dose unchanged."),
            why=Why(kind="reading", plain="You took your blood pressure today."),
            scope=Scope.READINGS,
            deliver_to=DeliverTo.PATIENT,
            day="2026-09-03",
            dedupe_key="reading:bad",
            expires_at=MONDAY,
        )
    rules = {finding.rule for finding in refused.value.findings}
    assert {4, 12} <= rules, rules  # "reading", "logged", "dose", "BP"
    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.READINGS)
    refusals = [e for e in trail if e.outcome is Outcome.REFUSED]
    assert refusals and refusals[0].refused_because == "NotPlainWords"
    assert refusals[0].target == "feed_item"
    assert not [item for item in await _items(sg, context)]


async def test_a_learning_card_from_outside_the_allowlist_is_not_made(sg: AsyncSession) -> None:
    context = await _pa(sg)
    state = await current_state(sg, context=context)
    shop = Source(
        name="A supplement shop",
        domain="supplement-shop.example",
        kind=SourceKind.VIDEO,
        regions=["SG"],
        languages=["en"],
        allowlisted=False,
        review_status=ReviewStatus.PENDING,
    )
    sg.add(shop)
    await sg.flush()
    good = _lines(
        "Sit down and rest for 5 minutes first.", why="This is about your blood pressure."
    )
    for source in (None, shop):
        with pytest.raises(SourceNotAllowlisted):
            await create_item(
                sg,
                context=context,
                state=state,
                type=CardType.LEARNING,
                lines=good,
                why=Why(kind="learning", plain=good.why),
                scope=Scope.RECORDS,
                deliver_to=DeliverTo.PATIENT,
                day="2026-09-03",
                dedupe_key=f"learning:{uuid.uuid4()}",
                expires_at=MONDAY,
                source=source,
            )
    # Approved but pinned to the other country is not allowlisted here either.
    npra = Source(
        name="NPRA",
        domain="npra.gov.my",
        kind=SourceKind.REGULATOR,
        regions=["MY"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(npra)
    await sg.flush()
    with pytest.raises(SourceNotAllowlisted):
        await create_item(
            sg,
            context=context,
            state=state,
            type=CardType.LEARNING,
            lines=good,
            why=Why(kind="learning", plain=good.why),
            scope=Scope.RECORDS,
            deliver_to=DeliverTo.PATIENT,
            day="2026-09-03",
            dedupe_key="learning:npra",
            expires_at=MONDAY,
            source=npra,
        )
    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.RECORDS)
    assert sum(1 for e in trail if e.refused_because == "SourceNotAllowlisted") == 3


async def test_learning_cards_carry_the_boundary_line_and_cards_that_infer_nothing_carry_none(
    sg: AsyncSession,
) -> None:
    """E16-01 on the feed. A learning card is an inferring surface (`Surface.LEARNING_CARD`),
    and so is a notice, the same compression of a regulator's page: the row carries the line
    and the body and the voice end on it. Every other card shows the record back and
    carries no line."""
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5, batch="240077")
    _, made = await refresh(sg, context=context, engine=ENGINE)
    line = boundary_line(Surface.LEARNING_CARD, "en")
    assert line.splitlines() == [
        "Nura explains one thing in simple words.",
        "This is not a doctor's advice.",
        "Ask your doctor.",
    ]
    inferring = [item for item in made if item.type in SURFACE_OF]
    assert {item.type for item in inferring} == {CardType.LEARNING, CardType.NOTICE}
    for item in inferring:
        assert item.boundary == line, item.type
        assert item.body[-3:] == line.splitlines() and item.voice[-3:] == line.splitlines()
    plain = [item for item in made if item.type not in SURFACE_OF]
    assert {CardType.NOW, CardType.STORY} <= {item.type for item in plain}
    assert all(item.boundary is None for item in plain), [(i.type, i.boundary) for i in plain]


async def test_a_learning_card_without_its_line_is_not_made_nor_a_plain_card_with_one(
    sg: AsyncSession,
) -> None:
    """The line is structure on the feed too: a learning card that does not end on its line,
    or carries another surface's, is refused; a reading card that carries one is refused;
    every refusal is on the trail by name."""
    context = await _pa(sg)
    state = await current_state(sg, context=context)
    regulator = Source(
        name="Health Sciences Authority",
        domain="boundary-test.gov.sg",
        kind=SourceKind.REGULATOR,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(regulator)
    await sg.flush()
    good = learning_lines(
        "en",
        headline="Your blood pressure",
        body=("Sit down and rest for 5 minutes first.",),
        topic="your blood pressure",
        source_name=regulator.name,
        doctor="Dr Tan",
    )
    assert good.boundary == boundary_line(Surface.LEARNING_CARD, "en", doctor="Dr Tan")
    brief = boundary_line(Surface.BRIEF, "en", doctor="Dr Tan")
    cut = good.body[:-3]
    refused = (
        (CardType.LEARNING, replace(good, boundary=None)),
        (CardType.LEARNING, replace(good, body=cut, voice=cut)),
        (
            CardType.LEARNING,
            replace(
                good,
                body=(*cut, *brief.splitlines()),
                voice=(*cut, *brief.splitlines()),
                boundary=brief,
            ),
        ),
        (
            CardType.READING,
            replace(_lines("Your blood pressure today was 138 over 84."), boundary=good.boundary),
        ),
    )
    for n, (type, lines) in enumerate(refused):
        with pytest.raises(NoBoundaryLine):
            await create_item(
                sg,
                context=context,
                state=state,
                type=type,
                lines=lines,
                why=Why(kind=type.value, plain=lines.why),
                scope=Scope.RECORDS,
                deliver_to=DeliverTo.PATIENT,
                day="2026-09-03",
                dedupe_key=f"boundary:{n}",
                expires_at=MONDAY,
                source=regulator if type is CardType.LEARNING else None,
            )
    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.RECORDS)
    assert sum(1 for e in trail if e.refused_because == "NoBoundaryLine") == len(refused)
    made = await create_item(
        sg,
        context=context,
        state=state,
        type=CardType.LEARNING,
        lines=good,
        why=Why(kind="learning", plain=good.why),
        scope=Scope.RECORDS,
        deliver_to=DeliverTo.PATIENT,
        day="2026-09-03",
        dedupe_key="boundary:good",
        expires_at=MONDAY,
        source=regulator,
    )
    assert made.boundary == good.boundary and made.body[-1] == "Ask Dr Tan."


async def _items(session: AsyncSession, context: KeyContext) -> list[FeedItem]:
    from app.audit.access import audited_read

    return list(await audited_read(session, FeedItem, context, Scope.PROFILE))


# --- §9: a new medicine starts an explainer and a daily safety job; the batch decides ---------


async def test_a_medicine_starts_an_explainer_and_a_daily_safety_job_and_a_notice_off_batch_is_held(
    sg: AsyncSession,
) -> None:
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5, batch="230001")
    _, made = await refresh(sg, context=context, engine=ENGINE)
    jobs = {
        (job.kind, tuple(job.terms), job.cadence, job.status.value)
        for job in await list_jobs(sg, context=context)
    }
    assert (JobKind.EXPLAINER, ("warfarin",), "on_change", "done") in jobs
    assert (JobKind.SAFETY, ("warfarin",), "daily", "done") in jobs
    by_type = {}
    for item in made:
        by_type.setdefault(item.type, []).append(item)
    assert by_type[CardType.NOW][0].scope is Scope.MEDICINES
    assert by_type[CardType.NOW][0].body[0] == "Your tablets for today are on your list."
    learning = by_type[CardType.LEARNING]
    his_learning = [item for item in learning if item.deliver_to is DeliverTo.PATIENT]
    assert len(his_learning) == 1 and his_learning[0].cite is not None
    assert his_learning[0].cite["url"].startswith("https://www.hsa.gov.sg/")
    assert his_learning[0].why["fact_ids"], "the explainer cites the facts it is about"
    notice = by_type[CardType.NOTICE][0]
    assert notice.deliver_to is DeliverTo.CAREGIVER
    assert notice.why["suppressed"] == "batch_does_not_match_the_pack"
    assert notice.cite is not None and notice.cite["batch"] == "240077"
    # #231: the "skip a dose" page used to become an orphaned QUESTION/DeliverTo.MEMO FeedItem
    # nothing read. Now it is held for the chief as a real card, and — because the EXPLAINER
    # job it came from names a medicine he takes — also filed as a real doctor question.
    her_learning = [item for item in learning if item.deliver_to is DeliverTo.CAREGIVER]
    assert len(her_learning) == 1
    assert her_learning[0].cite is not None and "warfarin-inr" in her_learning[0].cite["url"]
    assert CardType.QUESTION not in by_type, "no orphaned FeedItem question"
    memos = await current_memos(sg, context=context)
    [memo] = [one for one in memos if one.kind is MemoKind.ASK]
    assert memo.key == "ask_safety_notice"
    assert "skip" not in memo.text.lower() and "dose" not in memo.text.lower()
    # Nothing for the patient carries the notice or the caregiver's copy of the found page.
    page = await feed_page(sg, context=context, engine=ENGINE)
    assert CardType.NOTICE not in {item.type for item in page.items}
    assert her_learning[0].id not in {item.id for item in page.items}
    # Delivery, not existence: his chief's own, independently resolved key actually reads
    # both the notice and the redirected learning card back.
    mei = await let_in(
        sg, context, phone="+6591230098", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.MEDICINES}
    )
    her_page = await feed_page(sg, context=mei, engine=ENGINE)
    her_ids = {item.id for item in her_page.items}
    assert notice.id in her_ids and her_learning[0].id in her_ids
    assert [item.type for item in page.items][:4] == [
        CardType.NOW,
        CardType.GATE,
        CardType.STORY,  # the label photo is one of his papers
        CardType.LEARNING,
    ]


class _TreatyFoodSearcher:
    """A food page whose words would change treatment — a hazard/season/food job names no
    medicine, so this is the case #231's routing must hold for the chief alone, no doctor
    question invented from a name it does not have."""

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        if kind != "food" or "food.example.sg" not in domains:
            return []
        return [
            Found(
                domain="food.example.sg",
                url="https://food.example.sg/diabetes-meal",
                title="A diabetes meal that skips your tablet",
                published_at="2026-09-01",
                text=(
                    "Skip your diabetes tablet before this meal and see how you feel "
                    "afterwards."
                ),
            )
        ]

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        return []


class _TreatyFoodCompressor:
    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        return Compressed(
            headline="A meal idea for diabetes",
            body=("Skip your diabetes tablet before this meal.",),
            why_topic="your diabetes",
            passage=text,
        )


async def test_a_food_page_that_would_change_treatment_is_held_for_his_chief_alone(
    sg: AsyncSession,
) -> None:
    """#231/#236: the general (non-SAFETY) `changes_treatment` reroute used to write an
    orphaned `CardType.QUESTION`/`DeliverTo.MEMO` `FeedItem` nothing reads — the exact gap
    #224 closed for a safety notice, left open one branch over. A food (or local, or seasonal)
    job names no medicine, so it is held for the chief as a real card, the same card he would
    have had, redirected — never in its own words (`items.TreatmentChangingCard`). #236: no
    drug name to ask about is not a reason to file no question at all — a name-free one is
    filed instead (`"ask_medicines_change"`), so this is a real, standing question for the
    doctor, not a silent drop."""
    context = await _pa(sg)
    photo = await store_artifact(
        sg,
        context=context,
        kind=ArtifactKind.PHOTO,
        storage_key=f"sg/profiles/pa/onboarding-{uuid.uuid4()}.jpg",
        content_type="image/jpeg",
        sha256="e" * 64,
        captured_at=MONDAY,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )
    await assert_fact(
        sg,
        context=context,
        subject="condition",
        attribute="diabetes",
        value=True,
        confidence=1.0,
        artifact_id=photo.id,
    )
    source = Source(
        name="Food Example",
        domain="food.example.sg",
        kind=SourceKind.HOSPITAL,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    engine = Engine(
        searcher=_TreatyFoodSearcher(),
        compressor=_TreatyFoodCompressor(),
        registry=FixtureRegistry.load(),
    )
    _, made = await refresh(sg, context=context, engine=engine)
    food = next(item for item in made if item.type is CardType.FOOD)
    assert food.deliver_to is DeliverTo.CAREGIVER
    assert CardType.QUESTION not in {item.type for item in made}, "no orphaned FeedItem question"
    # The finding's own words never reached the card: the reroute copy did.
    assert not changes_treatment([food.headline, *food.body])
    assert food.why["kind"] == "needs_doctor_look"
    # No medicine name was ever known for this job, but a question is filed all the same
    # (#236): name-free, never invented, never dropped.
    memos = await current_memos(sg, context=context)
    [memo] = [one for one in memos if one.kind is MemoKind.ASK]
    assert memo.key == "ask_medicines_change"
    assert memo.slots == {"doctor": "your doctor"}
    assert food.why["memo_id"] == str(memo.id)
    # His own feed never carries it.
    his_page = await feed_page(sg, context=context, engine=engine)
    assert food.id not in {item.id for item in his_page.items}
    # Delivery, not existence: his chief's own, independently resolved key reads it back.
    mei = await let_in(
        sg, context, phone="+6591230097", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS}
    )
    her_page = await feed_page(sg, context=mei, engine=engine)
    assert food.id in {item.id for item in her_page.items}
    # #236: rerouted for a treatment-changing finding, this KEPT_AS_WRITTEN type is sampled
    # for the pharmacist's first fifty even though it is held for the chief, not him.
    rows = (
        await sg.scalars(select(ReviewItem).where(ReviewItem.card_type == CardType.FOOD.value))
    ).all()
    assert len(rows) == 1


async def test_a_notice_that_matches_the_batch_on_his_pack_is_still_never_his_card(
    sg: AsyncSession,
) -> None:
    """#181: a batch match no longer earns a notice a place in his feed (spec §0, §9). It is
    still hers to act on — `Supply.TODAY`, same as before — and still not suppressed (a match
    is relevant, just never a card he reads); it is simply never `DeliverTo.PATIENT`."""
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5, batch="240077")
    _, made = await refresh(sg, context=context, engine=ENGINE)
    notice = next(item for item in made if item.type is CardType.NOTICE)
    assert notice.deliver_to is DeliverTo.CAREGIVER and notice.supply is Supply.TODAY
    assert notice.why["suppressed"] is None
    assert notice.body[1] == "Look for the batch number 240077 on your box."
    page = await feed_page(sg, context=context, engine=ENGINE)
    assert CardType.NOTICE not in {item.type for item in page.items}
    assert [item.type for item in page.items][:4] == [
        CardType.NOW,
        CardType.GATE,
        CardType.STORY,  # the label photo is one of his papers
        CardType.LEARNING,
    ]


async def test_a_notice_is_refused_outright_if_a_caller_ever_sends_it_to_the_patient(
    sg: AsyncSession,
) -> None:
    """The choke point holds even if a future job or caller gets the routing wrong: `create_item`
    refuses a `CardType.NOTICE` built for `DeliverTo.PATIENT` before it looks at its words."""
    context = await _pa(sg)
    state = await current_state(sg, context=context)
    lines = learning_lines(
        "en",
        headline="A notice about one batch of your blood thinner",
        body=("Look for the batch number 240077 on your box.",),
        topic="your blood thinner",
        source_name="Health Sciences Authority",
        doctor="your doctor",
    )
    with pytest.raises(NoticeNotForPatient):
        await create_item(
            sg,
            context=context,
            state=state,
            type=CardType.NOTICE,
            lines=lines,
            why=Why(kind="notice", plain=lines.why),
            scope=Scope.MEDICINES,
            deliver_to=DeliverTo.PATIENT,
            day="2026-09-03",
            dedupe_key="notice:refused",
            expires_at=MONDAY,
        )
    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.MEDICINES)
    refusals = [e for e in trail if e.outcome is Outcome.REFUSED]
    assert refusals and refusals[-1].refused_because == "NoticeNotForPatient"
    assert not [item for item in await _items(sg, context) if item.type is CardType.NOTICE]


async def test_treatment_changing_words_never_reach_any_card_for_any_audience(
    sg: AsyncSession,
) -> None:
    """#236 (review finding on #231's own PR): the choke point holds regardless of
    `deliver_to`. `search.run_job` addressed a treatment-changing finding to
    `DeliverTo.CAREGIVER` in the finding's own words on the theory that her fuller words
    (docs/plain-words.md §3) covered it; §3 is about wording, not about whether advice to
    start, stop or change a medicine may appear on a card at all. It may not, whoever holds
    the card — `items.create_item` refuses it before it looks at anything else
    (`TreatmentChangingCard`), the same way `NoticeNotForPatient` refuses a notice addressed
    to the patient before it looks at its words. Proven for every `DeliverTo` a card can name,
    not only the caregiver: a future caller cannot route around this by picking `MEMO` either."""
    context = await _pa(sg)
    state = await current_state(sg, context=context)
    lines = learning_lines(
        "en",
        headline="An update about your warfarin",
        body=("Stop taking your warfarin for two days before your next blood test.",),
        topic="your warfarin",
        source_name="Medicine Example",
        doctor="your doctor",
    )
    assert changes_treatment([lines.headline, *lines.body])
    for n, deliver_to in enumerate(DeliverTo):
        with pytest.raises(TreatmentChangingCard):
            await create_item(
                sg,
                context=context,
                state=state,
                type=CardType.LEARNING,
                lines=lines,
                why=Why(kind="learning", plain=lines.why),
                scope=Scope.MEDICINES,
                deliver_to=deliver_to,
                day="2026-09-03",
                dedupe_key=f"treaty:{n}",
                expires_at=MONDAY,
                source=Source(
                    name="Medicine Example",
                    domain="medicine.example.sg",
                    kind=SourceKind.HOSPITAL,
                    regions=["SG"],
                    languages=["en"],
                    allowlisted=True,
                    review_status=ReviewStatus.APPROVED,
                ),
            )
    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.MEDICINES)
    refusals = [e for e in trail if e.refused_because == "TreatmentChangingCard"]
    assert len(refusals) == len(DeliverTo)
    assert not [item for item in await _items(sg, context) if item.type is CardType.LEARNING]


def test_the_needs_doctor_look_line_can_never_itself_fail(sg: AsyncSession) -> None:
    """#236: a treatment-changing finding never reaches the caregiver in its own words — a
    fixed catalogue line reaches her instead, naming that a question was filed for the doctor.
    That line must never be able to fail the same check the words it stands in for would have
    failed, in any of his languages, or the reroute would just move a silent drop one step
    over."""
    for language in ("en", "ms", "zh"):
        lines = needs_doctor_look_lines(language, doctor="Dr Tan")
        findings = verify(lines.headline, language, "headline")
        for line in (*lines.body, *lines.voice, lines.why):
            findings += verify(line, language, "line")
        failing = [f for f in findings if f.severity == "fail"]
        assert not failing, (language, failing)
        assert lines.boundary is not None
        assert lines.body[-3:] == tuple(lines.boundary.splitlines())
        assert lines.voice[-3:] == tuple(lines.boundary.splitlines())
        assert not changes_treatment([lines.headline, *lines.body]), (
            "the reroute card itself must never read as treatment-changing"
        )


async def test_the_needs_doctor_look_card_writes_a_real_card_for_the_caregiver(
    sg: AsyncSession,
) -> None:
    """The reroute content is a genuine, writable `FeedItem` — every other check `create_item`
    runs (the boundary line, the card grammar, the source) still has to pass it, the same as
    any other notice."""
    context = await _pa(sg)
    state = await current_state(sg, context=context)
    source = Source(
        name="Health Sciences Authority",
        domain="hsa.gov.sg",
        kind=SourceKind.REGULATOR,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    lines = needs_doctor_look_lines("en", doctor="Dr Tan")
    rerouted = await create_item(
        sg,
        context=context,
        state=state,
        type=CardType.NOTICE,
        lines=lines,
        why=Why(
            kind="needs_doctor_look",
            plain=lines.why,
            source_id=str(source.id),
            memo_id="a-memo-id",
        ),
        scope=Scope.MEDICINES,
        deliver_to=DeliverTo.CAREGIVER,
        day="2026-09-03",
        dedupe_key="notice:rerouted",
        expires_at=MONDAY,
        source=source,
    )
    assert rerouted.deliver_to is DeliverTo.CAREGIVER
    assert rerouted.headline == "Nura kept this for Dr Tan"
    assert rerouted.why["memo_id"] == "a-memo-id"


class _TreatyNoticeSearcher:
    """A safety notice whose words would change treatment — never the fixture data other
    tests share, so this scenario cannot leak into theirs."""

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        if kind != "safety" or "notices.example.sg" not in domains:
            return []
        return [
            Found(
                domain="notices.example.sg",
                url="https://notices.example.sg/warfarin-stop-240077",
                title="Stop taking this batch of warfarin",
                published_at="2026-09-01",
                text=(
                    "Stop taking tablets from batch 240077 of warfarin immediately and "
                    "return them to your pharmacy."
                ),
                batch="240077",
            )
        ]

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        return []


class _TreatyNoticeCompressor:
    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        return Compressed(
            headline="A notice about your blood thinner",
            body=(
                "Stop taking tablets from this batch immediately.",
                "Return them to your pharmacy.",
            ),
            why_topic="your blood thinner",
            passage=text,
        )


async def test_a_treatment_changing_notice_on_his_own_box_still_reaches_his_chief(
    sg: AsyncSession,
) -> None:
    """#224 (review finding on #181's own PR): the most dangerous version of a safety notice
    — one that matches the batch on his own box *and* reads as a reason to start, stop or
    change a medicine — used to reach nobody. A `continue` after the treatment-change reroute
    skipped the caregiver notice entirely, and the reroute itself wrote a `CardType.QUESTION`
    `FeedItem` with `deliver_to=DeliverTo.MEMO` that nothing reads: `rank._patient_supply`
    excludes anything not `DeliverTo.PATIENT`, `rank._caregiver_supply` excludes anything not
    `PATIENT`/`CAREGIVER`, and no route ever queried `FeedItem` for `deliver_to == MEMO`.

    Fixed both ways: the caregiver notice is now unconditional (batch match and
    treatment-change reroute are independent, not exclusive), and the reroute files a real
    doctor question through `reasoning.visits.memos.write_memo` — the same door the post-visit
    summary uses — never a `FeedItem`. This test proves delivery through the real paths both
    land on, not that a row merely exists: his chief's own `feed_page` (a second, independently
    resolved `KeyContext`, not a `deliver_to` field read off the row) for the notice, and
    `current_memos` (what `brief.py` and `questions.py` themselves call) for the question."""
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5, batch="240077")
    source = Source(
        name="Notices Example",
        domain="notices.example.sg",
        kind=SourceKind.REGULATOR,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    engine = Engine(
        searcher=_TreatyNoticeSearcher(),
        compressor=_TreatyNoticeCompressor(),
        registry=FixtureRegistry.load(),
    )
    _, made = await refresh(sg, context=context, engine=engine)

    # The caregiver notice: still made, still hers, and the match is on it — this is the
    # confirmed-his-own-box case, not a maybe.
    assert CardType.QUESTION not in {item.type for item in made}, "no orphaned FeedItem question"
    notice = next(item for item in made if item.type is CardType.NOTICE)
    assert notice.deliver_to is DeliverTo.CAREGIVER
    assert notice.why["suppressed"] is None, "the batch matches: this is not held back as unrelated"
    assert notice.cite is not None and notice.cite["batch"] == "240077"
    # #236: the finding's own words ("stop taking...immediately") never reach any card, hers
    # included — the reroute copy does, and it points at the question filed below.
    assert not changes_treatment([notice.headline, *notice.body])
    assert notice.why["kind"] == "needs_doctor_look"

    # Delivery, not existence: his chief's own key, resolved independently of Pa's, actually
    # reads it back through the real feed page.
    mei = await let_in(
        sg, context, phone="+6591230099", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.MEDICINES}
    )
    her_page = await feed_page(sg, context=mei, engine=engine)
    assert notice.id in {item.id for item in her_page.items}

    # His own feed carries neither the notice nor any question — spec §0, §9.
    his_page = await feed_page(sg, context=context, engine=engine)
    assert {item.type for item in his_page.items} & {CardType.NOTICE, CardType.QUESTION} == set()

    # The doctor question: a real Memo, read back through the same function the post-visit
    # brief and the pre-visit question loop both call — not a raw table query.
    memos = await current_memos(sg, context=context)
    [memo] = [one for one in memos if one.kind is MemoKind.ASK]
    assert memo.key == "ask_safety_notice"
    assert notice.why["memo_id"] == str(memo.id), "the card points at the question it filed"
    assert memo.slots == {
        "doctor": "your doctor",
        "medicine": "the blood thinner tablet (warfarin)",
    }
    assert memo.text == (
        "Ask your doctor about the notice on the blood thinner tablet (warfarin)."
    )
    assert memo.appointment_id is None, "a standing question, not tied to one visit yet"
    # The words of the notice itself never reach the memo: only that there is one to ask
    # about, the same discipline the caregiver notice already keeps.
    assert "stop" not in memo.text.lower() and "240077" not in memo.text
    # It becomes a real question, the way `questions.questions_for` would pick it up.
    proposed = question_from_memo(memo)
    assert proposed.key == "ask_safety_notice" and proposed.slots == memo.slots


class _TreatyMedicineSearcher:
    """A page about a medicine he actually takes, found by a watch added by hand — the
    `add_search_job` shape (`reason={"asked": ..., "by": ...}`, no `"scope"` key at all)."""

    def search(self, kind: str, terms: Sequence[str], domains: Sequence[str]) -> Sequence[Found]:
        if kind != "explainer" or "medicine.example.sg" not in domains:
            return []
        return [
            Found(
                domain="medicine.example.sg",
                url="https://medicine.example.sg/warfarin-update",
                title="An update about warfarin",
                published_at="2026-09-01",
                text="Stop taking warfarin for two days before your next blood test.",
            )
        ]

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        return []


class _TreatyMedicineCompressor:
    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        return Compressed(
            headline="An update about your warfarin",
            body=("Stop taking your warfarin for two days before your next blood test.",),
            why_topic="your warfarin",
            passage=text,
        )


async def _hand_added_warfarin_job(sg: AsyncSession, context: KeyContext) -> tuple[Engine, Any]:
    """A watch on a medicine he takes, added the way `add_search_job` adds one — `create_job`
    directly, never `refresh()`'s planner — against a page that would change treatment."""
    await _label(sg, context, name="Warfarin", strength=5)
    source = Source(
        name="Medicine Example",
        domain="medicine.example.sg",
        kind=SourceKind.HOSPITAL,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    engine = Engine(
        searcher=_TreatyMedicineSearcher(),
        compressor=_TreatyMedicineCompressor(),
        registry=FixtureRegistry.load(),
    )
    job = await create_job(
        sg,
        context=context,
        kind=JobKind.EXPLAINER,
        terms=["warfarin"],
        # The exact shape `add_search_job` builds (feed.py:254-262): no `"scope"` key.
        reason={"asked": "what is this pill for", "by": str(context.person_id)},
    )
    return engine, job


async def test_a_hand_added_watch_on_a_medicine_he_takes_files_a_real_doctor_question(
    sg: AsyncSession,
) -> None:
    """#236: `is_medicine_job`/`_scope_of` used to decide whether a real drug name was known
    by reading `job.reason["scope"] == "medicines"` — but a watch added by hand
    (`app.channels.api.feed.add_search_job`) builds `reason={"asked": ..., "by": ...}` with no
    `"scope"` at all. A chief who added a watch naming a medicine he actually takes therefore
    got no doctor question when its finding changed treatment — the record fixed for the
    planner's own jobs (#224) stayed broken for hers. Fixed by deciding it from whether the
    job's own first term is a medicine on his list instead (`_medicine_he_takes`), so this
    proves it through `create_job` directly — not the auto-generated `refresh()` path, which
    always carries a `"scope"` and so never exercised the bug."""
    context = await _pa(sg)
    engine, job = await _hand_added_warfarin_job(sg, context)
    state = await current_state(sg, context=context)
    around = await around_for(
        sg, context=context, engine=engine, state=state, day=today_for(context)
    )
    made = await run_job(
        sg,
        context=context,
        job=job,
        engine=engine,
        state=state,
        language="en",
        around=around,
        doctor=None,
        existing=set(),
    )
    card = next(item for item in made if item.type is CardType.LEARNING)
    assert card.deliver_to is DeliverTo.CAREGIVER, "a treatment-changing finding is never his"
    assert card.scope is Scope.MEDICINES, "a real drug name was known, from his own list"
    # #236: the page's own words ("Stop taking warfarin...") never reach her card either.
    assert not changes_treatment([card.headline, *card.body])

    # A real doctor question, filed through the same door #224 built for a safety notice.
    memos = await current_memos(sg, context=context)
    [memo] = [one for one in memos if one.kind is MemoKind.ASK]
    assert memo.key == "ask_safety_notice"
    assert memo.slots == {"doctor": "your doctor", "medicine": "the blood thinner tablet (warfarin)"}
    assert card.why["memo_id"] == str(memo.id)

    # Delivery, not existence: his chief's own, independently resolved key reads the card.
    mei = await let_in(
        sg,
        context,
        phone="+6591230098",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.MEDICINES},
    )
    her_page = await feed_page(sg, context=mei, engine=engine)
    assert card.id in {item.id for item in her_page.items}
    # His own feed carries neither the card nor a question — spec §0, §9.
    his_page = await feed_page(sg, context=context, engine=engine)
    assert card.id not in {item.id for item in his_page.items}
    assert CardType.QUESTION not in {item.type for item in his_page.items}


async def test_a_failed_doctor_question_filing_still_leaves_an_audit_record(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#236: `_ask_the_doctor`'s blanket `except Exception` used to only call `log.warning` —
    a filing failure was invisible anywhere a caregiver, an auditor or a reviewer could see
    it. It must still never cost him the caregiver notice (the sibling test above proves that
    path on its own); this proves the other half a forced failure of `write_memo` is written
    to the audit trail as a refusal before it is swallowed."""
    context = await _pa(sg)
    engine, job = await _hand_added_warfarin_job(sg, context)
    state = await current_state(sg, context=context)
    around = await around_for(
        sg, context=context, engine=engine, state=state, day=today_for(context)
    )

    async def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("memo store unreachable")

    monkeypatch.setattr(search_module, "write_memo", _boom)
    made = await run_job(
        sg,
        context=context,
        job=job,
        engine=engine,
        state=state,
        language="en",
        around=around,
        doctor=None,
        existing=set(),
    )
    # The caregiver notice never depends on the question filing: it still lands.
    card = next(item for item in made if item.type is CardType.LEARNING)
    assert card.deliver_to is DeliverTo.CAREGIVER
    # No question was filed...
    memos = await current_memos(sg, context=context)
    assert not [one for one in memos if one.kind is MemoKind.ASK]
    # ...but the failure did not vanish into a log line: it is on the trail.
    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.VISITS)
    refusals = [e for e in trail if e.outcome is Outcome.REFUSED]
    assert refusals and refusals[-1].refused_because == "RuntimeError"


async def test_refresh_makes_each_card_once(sg: AsyncSession) -> None:
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5)
    _, first = await refresh(sg, context=context, engine=ENGINE)
    _, second = await refresh(sg, context=context, engine=ENGINE)
    assert first and second == []


def test_the_dedupe_key_is_job_aware_so_two_jobs_cannot_race_on_one_page() -> None:
    """#236: `_key_for` used to key only on the page, the language and the kind — never the
    job — so two different jobs that both turn up the same page shared one dedupe slot in
    `existing` (`compose.refresh`'s `keys`, one dict threaded through every job a run touches).
    Whichever job ran first silently decided, for both, whether a card was made and a question
    filed — row order, not anything about either finding, decided the outcome. The review's
    own example: an EXPLAINER job on `("metformin",)` and one on `("diabetes",)` both finding
    one page; only the metformin job's term is a medicine he takes
    (`_medicine_he_takes`), so whichever ran first decided whether a doctor question existed
    at all. Keyed on `job.id` too, each job's dedupe is independent of every other job's, so
    running order can no longer change what gets filed, and a job stays idempotent against its
    own earlier run (the same job, run twice, gets the same key back)."""
    day = Day(
        tz=ZoneInfo("Asia/Singapore"),
        now=MONDAY,
        local=MONDAY.astimezone(ZoneInfo("Asia/Singapore")),
    )
    found = Found(
        domain="medicine.example.sg",
        url="https://medicine.example.sg/metformin-and-diabetes",
        title="Metformin and diabetes",
        published_at="2026-09-01",
        text="Metformin is a tablet for diabetes.",
    )
    metformin_job = SearchJob(
        id=uuid.uuid4(),
        kind=JobKind.EXPLAINER,
        terms=["metformin"],
        source_ids=[],
        cadence="on_change",
        reason={},
        status=JobStatus.QUEUED,
    )
    diabetes_job = SearchJob(
        id=uuid.uuid4(),
        kind=JobKind.EXPLAINER,
        terms=["diabetes"],
        source_ids=[],
        cadence="on_change",
        reason={},
        status=JobStatus.QUEUED,
    )
    metformin_key = search_module._key_for(metformin_job, found, "en", day, None)
    diabetes_key = search_module._key_for(diabetes_job, found, "en", day, None)
    assert metformin_key != diabetes_key, "two different jobs must never share a dedupe slot"
    assert search_module._key_for(metformin_job, found, "en", day, None) == metformin_key, (
        "the same job, run again, must still dedupe against its own earlier run"
    )


def test_a_medicine_named_by_its_brand_is_recognised_as_one_he_takes() -> None:
    """#236: `_medicine_he_takes`'s registry fallback used to ask the register "is `written` a
    generic?" (`LabelFields(generic=written)`) — a query `identify` narrows to products whose
    own generic already equals `written`, so it could only ever repeat the fact the line above
    it already checked and already returned False on: a no-op, identical to the check before
    it, never able to resolve a brand. Asking by brand instead resolves a term written as a
    brand name ("Marevan", the fixture register's brand for warfarin) to the generic on his
    list — the case the docstring always described and the code never did, so a watch on a
    brand-named medicine he takes still got no doctor question when its finding changed
    treatment (the sibling of the bug #236 already fixed for `job.reason["scope"]`)."""
    registry = FixtureRegistry.load()
    day = Day(
        tz=ZoneInfo("Asia/Singapore"),
        now=MONDAY,
        local=MONDAY.astimezone(ZoneInfo("Asia/Singapore")),
    )
    around = search_module.Around(day=day, medicines=("warfarin",))
    assert search_module._medicine_he_takes("marevan", around, registry)
    assert not search_module._medicine_he_takes("paracetamol", around, registry)


# --- the parts of ranking ----------------------------------------------------------------------


def test_quiet_hours_are_nine_to_seven_on_his_wall_clock() -> None:
    sg_time = ZoneInfo("Asia/Singapore")
    assert in_quiet_hours(datetime(2026, 9, 3, 21, 0, tzinfo=sg_time))
    assert in_quiet_hours(datetime(2026, 9, 3, 23, 59, tzinfo=sg_time))
    assert in_quiet_hours(datetime(2026, 9, 4, 6, 59, tzinfo=sg_time))
    assert not in_quiet_hours(datetime(2026, 9, 4, 7, 0, tzinfo=sg_time))
    assert not in_quiet_hours(datetime(2026, 9, 3, 20, 59, tzinfo=sg_time))


def test_the_cursor_is_opaque_and_round_trips() -> None:
    as_of = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
    cursor = encode_cursor(12, as_of)
    assert "12" not in cursor and "2026" not in cursor
    assert decode_cursor(cursor) == (12, as_of)
    for bad in ("", "nope", encode_cursor(-1, as_of), "eyJvIjoxfQ"):
        with pytest.raises(NotACursor):
            decode_cursor(bad)


def _bare(type: CardType, supply: Supply, n: int) -> FeedItem:
    return FeedItem(type=type, supply=supply, priority=n, dedupe_key=f"{type}:{n}")


def test_past_the_gate_the_supply_repeats_and_without_a_tail_it_ends() -> None:
    ordered = [
        _bare(CardType.NOW, Supply.NOW, 1),
        _bare(CardType.GATE, Supply.GATE, 2),
        _bare(CardType.STORY, Supply.STORY, 3),
        _bare(CardType.LEARNING, Supply.LEARNING, 4),
    ]
    page, next_offset = _endless(ordered, 0)
    assert [item.dedupe_key for item in page] == [
        "now:1",
        "gate:2",
        "story:3",
        "learning:4",
        "story:3",
    ]
    assert next_offset == PAGE_SIZE
    page, next_offset = _endless(ordered, 100)
    assert len(page) == PAGE_SIZE and {item.supply for item in page} <= {
        Supply.STORY,
        Supply.LEARNING,
    }
    assert next_offset == 105
    only_today = ordered[:2]
    page, next_offset = _endless(only_today, 0)
    assert [item.dedupe_key for item in page] == ["now:1", "gate:2"] and next_offset is None


def test_the_day_and_the_date_are_said_his_way() -> None:
    monday = datetime(2026, 9, 14, 9, 0, tzinfo=ZoneInfo("Asia/Singapore"))
    assert plain_day(monday, "en") == "Monday 14 September"
    assert plain_day(monday, "ms") == "Isnin 14 September"
    assert plain_day(monday, "zh") == "9月14日星期一"
    assert plain_day(monday, "ta") == "Monday 14 September"


def test_today_ends_at_midnight_on_his_wall_clock(clock: FrozenClock) -> None:
    class Context:
        region = Region.SG

    day: Day = today_for(Context())  # type: ignore[arg-type]
    assert day.key == "2026-09-03"
    assert day.ends_at == datetime(2026, 9, 3, 16, 0, tzinfo=UTC)  # 00:00 on 4 September in SG
    assert day.same_day(datetime(2026, 9, 3, 15, 59, tzinfo=UTC))
    assert not day.same_day(datetime(2026, 9, 3, 16, 0, tzinfo=UTC))
    clock.step(timedelta(hours=9))
    assert today_for(Context()).key == "2026-09-04"  # type: ignore[arg-type]


def test_lines_that_would_change_treatment_are_caught() -> None:
    assert changes_treatment(["Skip a dose of warfarin if your number is too high."])
    assert changes_treatment(["Stop taking the water pill for two days."])
    assert not changes_treatment(["Keep the same amount of greens each week."])
    assert not changes_treatment(["Tell your doctor before any new tablet or herb."])


def test_render_fills_the_templates_in_his_language() -> None:
    lines = render("visit", "zh", body=("visit",), doctor="陈医生", day="9月21日星期一")
    assert lines.headline == "9月21日星期一看陈医生"
    assert lines.body[0] == "您9月21日星期一看陈医生。"
    assert lines.voice == lines.body
    english = render(
        "reading", "ta", body=("reading", "reading_alone"), top_number=138, bottom_number=84
    )
    assert english.language == "en", "Tamil falls back to English until its lines are on file"
    assert english.body == (
        "Your blood pressure today was 138 over 84.",
        "It is in your blood pressure book.",
        "I wrote it down.",
    )
