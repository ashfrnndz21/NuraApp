"""The feed at the service: what the schema and the doors refuse, and the ranking's parts.

A card names its State or is not written; a card with a failing line is not written and the
refusal is on the trail; a learning card from outside the allowlist is not written; a
medicine on the list starts an explainer and a daily safety job, and a notice — whether or
not it matches the batch on his pack — is held for the caregiver, or rerouted to a doctor
question when its words would change treatment (#181, #224, #236), and never delivered to
him in the notice's own words (`items.NoticeNotForPatient` refuses one built for
`DeliverTo.PATIENT` outright). Where the batch does match, he gets his own `RECALL_ACTION`
card instead (spec §0, #183), in his own words, saying what he can do about the box in his
hand today.
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

from app.audit.access import audited_read
from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.feed import search as search_module
from app.delivery.feed.compose import (
    DECLINED_TOPIC,
    Day,
    LearningPlan,
    _broker_wanted,
    _declined_topics,
    around_for,
    household,
    plain_day,
    plan_learning_jobs,
    refresh,
    say_ahead,
    today_for,
)
from app.delivery.feed.compress import (
    Compressed,
    FixtureCompressor,
    FixtureSearcher,
    Found,
    changes_treatment,
)
from app.delivery.feed.engagement import record_engagement
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
    EngagementKind,
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
    NoSuchItem,
    NotACursor,
    _endless,
    decode_cursor,
    encode_cursor,
    feed_page,
    in_quiet_hours,
    require_item,
)
from app.delivery.feed.search import Engine, create_job, list_jobs, run_job
from app.delivery.feed.sources import SourceNotAllowlisted
from app.delivery.feed.why_sheet import why_lines
from app.delivery.recommend import broker as broker_module
from app.delivery.recommend.rules import RULE_DID_YOU_KNOW, RULE_NEW_MEDICINE_EXPLAINER
from app.delivery.strings import WHY_THEIRS, Lines, learning_lines, needs_doctor_look_lines, render
from app.drugs.fixture import FixtureRegistry
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, resolve_key_context
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.language.models import ReviewItem
from app.medicines.service import LineView, active_lines
from app.memory.episodic import record_event, store_artifact
from app.memory.models import ArtifactKind, EventKind, SourceChannel
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
from tests.feelings_support import new_medicine
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


async def _run_learning(
    session: AsyncSession, *, context: KeyContext, engine: Engine, day: Day
) -> list[FeedItem]:
    """Today's self-searches, run synchronously on this same session — what
    `app.delivery.feed.background._run` does on its own session, per job, off the request
    entirely. These tests are about which cards a job makes (`plan_learning_jobs`, `run_job`,
    `say_ahead`), not about the background module's own scheduling, concurrency or deadlines
    (`tests/test_feed_background.py` covers that), so there is no task, no timeout, no second
    session here — just the same calls, in order, on `session`.

    Calls `search_module.run_job` (the module, not the name this file also imports) so a test
    that monkeypatches `search_module.run_job` still reaches every job run through here."""
    house = await household(session, context=context)
    state = await current_state(session, context=context)
    medicines: list[LineView] = (
        await active_lines(session, context=context, registry=engine.registry, language=house.language)
        if context.allows(Scope.MEDICINES)
        else []
    )
    every = await audited_read(session, FeedItem, context, Scope.PROFILE)
    keys = {item.dedupe_key for item in every}
    plan: LearningPlan = await plan_learning_jobs(
        session,
        context=context,
        engine=engine,
        state=state,
        day=day,
        house=house,
        keys=keys,
        medicines=medicines,
    )
    made: list[FeedItem] = []
    for job in plan.jobs:
        items = await search_module.run_job(
            session,
            context=context,
            job=job,
            engine=engine,
            state=await current_state(session, context=context),
            language=house.language,
            around=plan.around,
            doctor=house.doctor,
            existing=set(keys),
        )
        if items:
            await say_ahead(session, engine, context, items)
            made.extend(items)
            keys.update(item.dedupe_key for item in items)
    return made


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
    and so is a notice, the same compression of a regulator's page, and the `RECALL_ACTION`
    card built from one (#183): the row carries the line and the body and the voice end on
    it. Every other card shows the record back and carries no line."""
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5, batch="240077")
    _, made = await refresh(sg, context=context, engine=ENGINE)
    made = list(made) + await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
    line = boundary_line(Surface.LEARNING_CARD, "en")
    assert line.splitlines() == [
        "Nura explains one thing in simple words.",
        "This is not a doctor's advice.",
        "Ask your doctor.",
    ]
    inferring = [item for item in made if item.type in SURFACE_OF]
    assert {item.type for item in inferring} == {
        CardType.LEARNING,
        CardType.NOTICE,
        CardType.RECALL_ACTION,
    }
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
    made = list(made) + await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
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
    # #183: the batch on his pack (230001) does not match the notice's (240077) — no
    # RECALL_ACTION card at all, his or otherwise.
    assert CardType.RECALL_ACTION not in by_type
    memos = await current_memos(sg, context=context)
    [memo] = [one for one in memos if one.kind is MemoKind.ASK]
    assert memo.key == "ask_safety_notice"
    assert "skip" not in memo.text.lower() and "dose" not in memo.text.lower()
    # Nothing for the patient carries the notice or the caregiver's copy of the found page.
    page = await feed_page(sg, context=context, engine=ENGINE)
    assert {item.type for item in page.items} & {CardType.NOTICE, CardType.RECALL_ACTION} == set()
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

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
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
    made = list(made) + await _run_learning(sg, context=context, engine=engine, day=today_for(context))
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


async def test_a_notice_that_matches_the_batch_on_his_pack_gives_him_the_action_card_and_his_chief_the_notice(
    sg: AsyncSession,
) -> None:
    """#181, #183: a batch match no longer earns the notice itself a place in his feed (spec
    §0, §9) — it is still hers to act on (`Supply.TODAY`, same as before), still not
    suppressed (a match is relevant, just never a card in the notice's own words), and never
    `DeliverTo.PATIENT`. Where it matches his own pack, he gets his own `RECALL_ACTION` card
    instead, in his own words, made and reviewed like every other card of his: neither the
    notice's own compressed words, nor the batch number on it, ever reach him."""
    context = await _pa(sg)
    await _label(sg, context, name="Warfarin", strength=5, batch="240077")
    _, made = await refresh(sg, context=context, engine=ENGINE)
    made = list(made) + await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
    notice = next(item for item in made if item.type is CardType.NOTICE)
    assert notice.deliver_to is DeliverTo.CAREGIVER and notice.supply is Supply.TODAY
    assert notice.why["suppressed"] is None
    assert notice.body[1] == "Look for the batch number 240077 on your box."
    action = next(item for item in made if item.type is CardType.RECALL_ACTION)
    assert action.deliver_to is DeliverTo.PATIENT and action.supply is Supply.TODAY
    assert action.headline == "The blood thinner tablet was recalled"
    assert action.body == [
        "Take the blood thinner tablet to the pharmacist today.",
        "The pharmacist will tell you what to do next.",
        "Nura explains one thing in simple words.",
        "This is not a doctor's advice.",
        "Ask your doctor.",
    ]
    assert action.voice == action.body
    assert action.boundary == boundary_line(Surface.LEARNING_CARD, "en")
    # No batch number, and no word of the notice's own, reaches him.
    assert "240077" not in " ".join(action.body) and "batch" not in " ".join(action.body)
    assert action.action == "ask_the_pharmacist"
    page = await feed_page(sg, context=context, engine=ENGINE)
    assert [item.type for item in page.items][:3] == [
        CardType.NOW,
        CardType.RECALL_ACTION,
        CardType.GATE,
    ]
    assert CardType.NOTICE not in {item.type for item in page.items}


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

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
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
    made = list(made) + await _run_learning(sg, context=context, engine=engine, day=today_for(context))

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

    # His own feed carries neither the notice nor any question — spec §0, §9. It does carry
    # his own RECALL_ACTION card (#183): the batch match and the treatment-change reroute are
    # independent, so a notice too dangerous to show him in its own words still leaves him
    # with the one thing he needs, in fixed catalogue words that never repeat it.
    his_page = await feed_page(sg, context=context, engine=engine)
    assert {item.type for item in his_page.items} & {CardType.NOTICE, CardType.QUESTION} == set()
    action = next(item for item in made if item.type is CardType.RECALL_ACTION)
    assert action.deliver_to is DeliverTo.PATIENT
    assert action.id in {item.id for item in his_page.items}
    assert "stop" not in " ".join(action.body).lower()

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

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
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


# --- RE-07: the feed consumes the slate --------------------------------------------------


async def test_a_new_medicines_explainer_and_its_clip_lead_the_learning_supply_that_week(
    sg: AsyncSession,
) -> None:
    """docs/recommendation-engine.md §2.6: `_learning`'s `wanted` gains the slate's READ and
    CLIP topics first, already ranked by `RuleRanker` — so a medicine he just started leads
    this week's learning supply, ahead of a gap State already knew about (his diabetes, told
    at onboarding, which starts its own explainer the old way, `_gaps`)."""
    context = await _pa(sg)
    told = await record_event(
        sg,
        context=context,
        kind=EventKind.ONBOARDING,
        occurred_at=utcnow(),
        label="the conditions he told",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        sg,
        context=context,
        subject="condition",
        attribute="diabetes",
        value=True,
        confidence=1.0,
        event_id=told.id,
    )
    await new_medicine(sg, context)  # amlodipine, started now — inside the 14-day window
    _, made = await refresh(sg, context=context, engine=ENGINE)
    made = list(made) + await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))

    supply = [item for item in made if item.type in (CardType.LEARNING, CardType.CLIP)]
    assert len(supply) >= 3, "the medicine's explainer, its clip, and the diabetes explainer"
    leaders = supply[:2]
    assert {item.type for item in leaders} == {CardType.LEARNING, CardType.CLIP}
    for item in leaders:
        assert item.why["rule"] == RULE_NEW_MEDICINE_EXPLAINER
        assert item.why["topic"] == "medicine.blood_pressure_tablet"
        assert "recent_evidence" in item.why["boosts"]
    # The diabetes gap (an older story, `_gaps`) still runs — just behind the slate's own.
    trailing = supply[2:]
    assert any(item.why.get("gap") == "diabetes" for item in trailing)
    assert not any(item.why.get("rule") == RULE_NEW_MEDICINE_EXPLAINER for item in trailing)

    jobs = {(job.kind, tuple(job.terms), job.cadence) for job in await list_jobs(sg, context=context)}
    assert (JobKind.WORTH_KNOWING, ("amlodipine",), "weekly") in jobs


async def test_a_dismissed_topic_comes_back_no_sooner_than_30_days(sg: AsyncSession) -> None:
    """The topic-level "not for me" (`app.delivery.feed.engagement._decline_topic_for_30_days`)
    is a Fact with a validity window, read back by `_declined_topics` — distinct from
    `rank.DECLINED`, which is per card type and holds only for the rest of his day. Checked at
    two levels: the window itself (a hand-written fact, so this does not depend on any one
    rule's own freshness window still holding thirty days out), and the real wiring — declining
    a card the broker's slate proposed keeps that topic out of `_broker_wanted` right away."""
    context = await _pa(sg)
    topic = "medicine.blood_pressure_tablet"
    now = utcnow()

    # The window itself: still declined ten days on, not declined on day thirty-one.
    moment = await record_event(
        sg,
        context=context,
        kind=EventKind.ENGAGEMENT,
        occurred_at=now,
        label="not for me: a topic",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        sg,
        context=context,
        subject=DECLINED_TOPIC,
        attribute=topic,
        value={"item_id": "test"},
        confidence=1.0,
        event_id=moment.id,
        valid_from=now,
        valid_to=now + timedelta(days=30),
    )
    assert topic in await _declined_topics(sg, context=context, at=now + timedelta(days=10))
    assert topic not in await _declined_topics(sg, context=context, at=now + timedelta(days=31))

    # The real wiring: a card the slate proposed, dismissed, and the slate stops proposing it.
    other = await _pa(sg, phone="+6591310099")
    await new_medicine(sg, other)
    state = await current_state(sg, context=other)
    day = today_for(other)
    around = await around_for(sg, context=other, engine=ENGINE, state=state, day=day)
    before = await _broker_wanted(
        sg, context=other, engine=ENGINE, state=state, around=around, moment=day.now
    )
    assert ("amlodipine",) in {terms for _, terms, *_ in before}

    _, made = await refresh(sg, context=other, engine=ENGINE)
    made = list(made) + await _run_learning(sg, context=other, engine=ENGINE, day=today_for(other))
    [card] = [
        item
        for item in made
        if item.type is CardType.LEARNING and item.why.get("rule") == RULE_NEW_MEDICINE_EXPLAINER
    ]
    await record_engagement(sg, context=other, item_id=card.id, kind=EngagementKind.DISMISSED)

    after = await _broker_wanted(
        sg, context=other, engine=ENGINE, state=state, around=around, moment=day.now
    )
    assert ("amlodipine",) not in {terms for _, terms, *_ in after}


async def test_a_candidate_on_a_withheld_scope_never_becomes_a_card_for_that_key(
    sg: AsyncSession,
) -> None:
    """A key without MEDICINES never sees a medicine topic's card, whatever the slate proposes
    to the owner: the broker itself drops what `Candidate.readable_by` refuses before
    `slate()` ever returns it (`test_recommend_broker.
    test_a_key_without_records_never_sees_what_rests_on_it_named_as_withheld`), so
    `_broker_wanted` never queues the job for a narrower key — not a card filtered after the
    fact, a candidate that never reached the wanted list in the first place."""
    context = await _pa(sg)
    await new_medicine(sg, context)  # amlodipine, on Pa's own key
    kit = await let_in(
        sg,
        context,
        phone="+6591230099",
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes=ROLE_SCOPES[KeyRole.CAREGIVER] - {Scope.MEDICINES},
    )
    assert not kit.allows(Scope.MEDICINES)

    state = await current_state(sg, context=kit)
    day = today_for(kit)
    around = await around_for(sg, context=kit, engine=ENGINE, state=state, day=day)
    assert "amlodipine" not in around.medicines, "a scope she does not hold names no medicine"
    wanted = await _broker_wanted(
        sg, context=kit, engine=ENGINE, state=state, around=around, moment=day.now
    )
    assert not wanted, "the withheld scope leaves the broker nothing to propose to her"


async def test_a_private_candidates_card_is_unreadable_to_his_chief_and_readable_to_him(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independent safety review, item 2: `Candidate.private_to` (RE-06, §3.5) never reached
    the card `_broker_wanted`/`run_job` made for it — the day a rule marks a topic private
    (his own search history), the card would still show to his chief. It now travels
    candidate -> `wanted` entry -> `job.reason` -> `create_item(private_to=...)`, so the card
    holds the same `private_to` `FeedItem.private_to` already enforces for every other card
    (RE-01, `rank.require_item`).

    No rule sets `private_to` yet (the search-topic rule is a later story), so this wraps the
    real `RULE_NEW_MEDICINE_EXPLAINER` candidate the way one eventually will: same evidence,
    same topic, `private_to` added."""
    context = await _pa(sg)
    chief = await let_in(
        sg,
        context,
        phone="+6591230077",
        name="Chief",
        role=KeyRole.CAREGIVER,
        scopes=ROLE_SCOPES[KeyRole.CAREGIVER],
    )
    await new_medicine(sg, context)  # amlodipine — fires RULE_NEW_MEDICINE_EXPLAINER

    real_slate = broker_module.slate

    async def _privately(*args: Any, **kwargs: Any) -> broker_module.Slate:
        result = await real_slate(*args, **kwargs)
        private = tuple(replace(one, private_to=context.person_id) for one in result.candidates)
        return broker_module.Slate(private, result.withheld)

    monkeypatch.setattr(broker_module, "slate", _privately)

    _, made = await refresh(sg, context=context, engine=ENGINE)
    made = list(made) + await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
    cards = [item for item in made if item.why.get("rule") == RULE_NEW_MEDICINE_EXPLAINER]
    assert cards, "the medicine's explainer and clip are still made, now privately"
    for card in cards:
        assert card.private_to == context.person_id

        seen = await require_item(sg, context=context, item_id=card.id)
        assert seen.id == card.id

        with pytest.raises(NoSuchItem):
            await require_item(sg, context=chief, item_id=card.id)


async def test_a_did_you_know_card_names_its_topic_and_coexists_with_a_same_day_safety_notice(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """The `did_you_know` rule (`app.delivery.recommend.rules`) becomes a card through the
    same `JobKind.WORTH_KNOWING` pipeline every other broker READ candidate already does
    (`why.rule`/`why.topic` name it, RE-07/RE-08): one card, evidence readable, and — because
    a `CardType.NOTICE` is `DeliverTo.CAREGIVER` while a did-you-know card is `DeliverTo.
    PATIENT` (never the same cap counter, `rank._patient_supply`) — never in competition with
    the same day's safety notice on his own medicine (module doc, brief: "it never displaces a
    safety notice").

    Amlodipine is started well outside `NEW_MEDICINE_WINDOW` (14 days), so `did_you_know` is
    the only rule proposing its topic that day — `new_medicine_explainer` no longer reads it as
    new, and nothing else on this bare profile reads a visit or a tap — while it is still an
    active line, so it is still in `did_you_know`'s own pool (module doc, `rules.
    _did_you_know_pool`: a medicine he takes, not only a new one)."""
    context = await _pa(sg)
    await new_medicine(sg, context)  # amlodipine
    clock.step(timedelta(days=15))  # past NEW_MEDICINE_WINDOW; still active
    await _label(sg, context, name="Warfarin", strength=5, batch="230001")  # a SAFETY notice

    # The ranked, capped page (`rank.feed_page`, which runs `refresh` itself) is where "at
    # most one a day" actually lives (`rank._patient_supply`'s `CapsClass.ONE`) — a job can
    # still turn up more than one page (an article and a clip both about the same medicine,
    # here), so the cap is checked on what he is actually shown, not on every row `refresh`
    # wrote. `refresh` no longer runs today's self-searches inline (`app.delivery.feed.
    # background`, #269/#276, #280), so this test runs them itself, on this session, before
    # `feed_page` builds the capped page from what is now on the record.
    await refresh(sg, context=context, engine=ENGINE)
    await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
    page = await feed_page(sg, context=context, engine=ENGINE)
    on_his_page = [item for item in page.items if item.why.get("rule") == RULE_DID_YOU_KNOW]
    assert len(on_his_page) <= 1, "at most one did-you-know card a day"
    assert on_his_page, "today did have one to show"
    card = on_his_page[0]
    assert card.type in (CardType.LEARNING, CardType.CLIP)
    assert card.deliver_to is DeliverTo.PATIENT
    assert card.why["topic"] == "medicine.blood_pressure_tablet"
    assert card.why["fact_ids"], "the card cites the fact it rests on"
    assert card.scope is Scope.MEDICINES

    all_items = await _items(sg, context)
    notice = next(item for item in all_items if item.type is CardType.NOTICE)
    assert notice.deliver_to is DeliverTo.CAREGIVER
    # Both cards exist from the same day's run: the did-you-know card never displaced the
    # notice, nor the other way round — they were never on the same cap (patient vs.
    # caregiver, `rank._patient_supply` vs. `rank._caregiver_supply`).
    assert {card.id, notice.id} <= {item.id for item in all_items}

    # The Why sheet (RE-08) explains the topic to a caregiver by his name when her key does
    # not cover the scope its evidence rests on (`medicine.blood_pressure_tablet` is Scope.
    # MEDICINES).
    kit = await let_in(
        sg,
        context,
        phone="+6591230088",
        name="Kit",
        role=KeyRole.CAREGIVER,
        scopes=ROLE_SCOPES[KeyRole.CAREGIVER] - {Scope.MEDICINES},
    )
    assert not kit.allows(Scope.MEDICINES)
    lines = why_lines(
        card.why["plain"],
        scope=card.scope,
        context=kit,
        language="en",
        his=False,
        patient_name="Pa",
    )
    assert lines == (WHY_THEIRS["en"]["withheld"].format(patient="Pa"),)
    assert "Pa" in lines[0]


async def test_a_candidate_without_private_to_is_unchanged(sg: AsyncSession) -> None:
    """The other half of the same gap: a candidate that never names `private_to` (every rule
    on `main` today) still makes a card every key with the scope can read, exactly as before
    this fix — carrying `None` through `job.reason` must not narrow anything."""
    context = await _pa(sg)
    chief = await let_in(
        sg,
        context,
        phone="+6591230066",
        name="Chief",
        role=KeyRole.CAREGIVER,
        scopes=ROLE_SCOPES[KeyRole.CAREGIVER],
    )
    await new_medicine(sg, context)  # amlodipine — fires RULE_NEW_MEDICINE_EXPLAINER

    _, made = await refresh(sg, context=context, engine=ENGINE)
    made = list(made) + await _run_learning(sg, context=context, engine=ENGINE, day=today_for(context))
    cards = [item for item in made if item.why.get("rule") == RULE_NEW_MEDICINE_EXPLAINER]
    assert cards
    for card in cards:
        assert card.private_to is None
        seen = await require_item(sg, context=chief, item_id=card.id)
        assert seen.id == card.id


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


class _RotatingSearcher:
    """A different page each time it is actually called — standing in for a live web search's
    own drift over time, unlike the deterministic fixture files the rest of this module reads
    (which would return the very same page, and so be turned away by `_key_for`'s own
    job-scoped, day-blind dedupe key for anything but a local, food or seasonal job)."""

    def __init__(self) -> None:
        self.calls = 0

    def search(
        self,
        kind: str,
        terms: Sequence[str],
        domains: Sequence[str],
        *,
        queries: Sequence[str] | None = None,
    ) -> Sequence[Found]:
        if "catchup.example.sg" not in domains:
            return []
        self.calls += 1
        return [
            Found(
                domain="catchup.example.sg",
                url=f"https://catchup.example.sg/tip-{self.calls}",
                title="A tip about his own record",
                published_at="2026-09-01",
                text="A plain tip about what he takes.",
            )
        ]

    def find(
        self, words: Sequence[str], domains: Sequence[str], *, media: str | None = None
    ) -> Sequence[Found]:
        return []


class _PlainCompressor:
    def compress(self, text: str, language: str, facts: Mapping[str, Any]) -> Compressed | None:
        return Compressed(
            headline="A tip",
            body=("A plain tip about what he takes.",),
            why_topic="his medicines",
            passage=text,
        )


async def test_when_nothing_is_due_a_bounded_catch_up_still_runs_the_stale_job(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """Live-run defect: "no learning cards appear" — a job whose own cadence never makes
    `due()` say yes again (`on_change`, the default for `JobKind.EXPLAINER`), and the same gap
    still on his record so nothing new ever queues it either, would otherwise never run again
    once it had — the first open of a new day would show only what it already found, or
    nothing once that expired. `MAX_CATCH_UP_JOBS` (`compose._learning`) is the fix: when
    nothing at all ran for him today, the most overdue enabled jobs run anyway."""
    context = await _pa(sg)
    source = Source(
        name="Catch-up Example",
        domain="catchup.example.sg",
        kind=SourceKind.HOSPITAL,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    engine = Engine(
        searcher=_RotatingSearcher(), compressor=_PlainCompressor(), registry=FixtureRegistry.load()
    )
    state = await current_state(sg, context=context)
    day = today_for(context)
    around = await around_for(sg, context=context, engine=engine, state=state, day=day)
    # A job with no real gap behind it (an arbitrary term, no medicine or condition on his
    # record names it): `_gaps`/`_broker_wanted` never propose it, so `_learning`'s own
    # "wanted" and "due" loops never touch it again after this — isolating the catch-up path.
    job = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["blood pressure"], reason={"gap": "test"}
    )
    assert job.cadence == "on_change"
    first = await run_job(
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
    assert len(first) == 1, "ran once already — the baseline this test starts stale from"
    first_last_run_at = job.last_run_at

    clock.step(timedelta(days=2))
    _, second_load = await refresh(sg, context=context, engine=engine)
    second_load = list(second_load) + await _run_learning(
        sg, context=context, engine=engine, day=today_for(context)
    )

    caught_up = [item for item in second_load if item.search_job_id == job.id]
    assert caught_up, "the catch-up should have run the stale on_change job again"
    # A genuinely new page (the rotating searcher's second call) became a genuinely new card —
    # not blocked by the first card's own dedupe key, which only the day-blind key of an
    # unchanged page would have done.
    assert caught_up[0].cite is not None
    assert caught_up[0].cite["url"] == "https://catchup.example.sg/tip-2"

    jobs_after = await list_jobs(sg, context=context)
    [reran] = [one for one in jobs_after if one.id == job.id]
    assert reran.last_run_at is not None and reran.last_run_at > first_last_run_at


async def test_a_job_that_ran_but_found_nothing_still_lets_the_catch_up_run(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """Live-run defect, part two ("Pa's feed never creates learning jobs"): the catch-up guard
    used to be "did a job run today" (`not ran`), not "does he have a learning card today". A
    job that runs but finds nothing new to say — the search came back empty, or everything it
    found is already shown — still landed in `ran`, so a day where the one due job came up
    empty looked, wrongly, like a day that needed no catching up at all, and a second,
    genuinely stale job never got its turn. `plan_learning_jobs` reads his own day's cards
    back instead of the jobs' bookkeeping — read at plan time, before either job's next run,
    so what proves the read is the jobs' own bookkeeping and not "what came back today": a
    job that already ran once, today, and found nothing (`empty`, no usable source of its
    own — the search itself has nothing to search), sitting right next to one that is
    genuinely stale (`stale`, `on_change`, never due again on its own). Neither is due when
    the plan is made two days on; the catch-up still reaches the stale one."""
    context = await _pa(sg)
    source = Source(
        name="Catch-up Example",
        domain="catchup.example.sg",
        kind=SourceKind.HOSPITAL,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    engine = Engine(
        searcher=_RotatingSearcher(), compressor=_PlainCompressor(), registry=FixtureRegistry.load()
    )
    state = await current_state(sg, context=context)
    day = today_for(context)
    around = await around_for(sg, context=context, engine=engine, state=state, day=day)

    # A stale job (`on_change`, `_gaps`/`_broker_wanted` never propose it again): the one only
    # a catch-up can ever revive.
    stale = await create_job(
        sg, context=context, kind=JobKind.EXPLAINER, terms=["cholesterol"], reason={"gap": "test"}
    )
    first = await run_job(
        sg,
        context=context,
        job=stale,
        engine=engine,
        state=state,
        language="en",
        around=around,
        doctor=None,
        existing=set(),
    )
    assert len(first) == 1, "ran once already — the baseline this test starts stale from"

    # A second job, run the same day, `on_change` too (so it never becomes independently due
    # again either) and pinned to no usable source of its own (`source_ids=[]`): its own run
    # today genuinely finds nothing, the same as a live search that came up empty — not a
    # stand-in, a real empty result.
    empty = await create_job(
        sg,
        context=context,
        kind=JobKind.SAFETY,
        terms=["diabetes"],
        reason={"gap": "test"},
        source_ids=[],
        cadence="on_change",
    )
    second = await run_job(
        sg,
        context=context,
        job=empty,
        engine=engine,
        state=state,
        language="en",
        around=around,
        doctor=None,
        existing=set(),
    )
    assert second == [], "no usable source: this job's own search has nothing to find"

    clock.step(timedelta(days=2))
    _, second_load = await refresh(sg, context=context, engine=engine)
    second_load = list(second_load) + await _run_learning(
        sg, context=context, engine=engine, day=today_for(context)
    )

    caught_up = [item for item in second_load if item.search_job_id == stale.id]
    assert caught_up, (
        "the other job ran today and found nothing, but the stale job — read back from his "
        "day's own cards, not the jobs' bookkeeping — should still have been caught up"
    )


async def test_the_catch_up_is_bounded_to_max_catch_up_jobs(sg: AsyncSession, clock: FrozenClock) -> None:
    """Bounded, the same way every other inline compose step already is: one open of the feed
    can never fan out into an unbounded run of searches, however many stale jobs a profile has
    built up (docs/design-direction.md; CLAUDE.md's own "never bypass a bound" spirit)."""
    from app.delivery.feed.compose import MAX_CATCH_UP_JOBS

    context = await _pa(sg)
    source = Source(
        name="Catch-up Example",
        domain="catchup.example.sg",
        kind=SourceKind.HOSPITAL,
        regions=["SG"],
        languages=["en"],
        allowlisted=True,
        review_status=ReviewStatus.APPROVED,
    )
    sg.add(source)
    await sg.flush()
    engine = Engine(
        searcher=_RotatingSearcher(), compressor=_PlainCompressor(), registry=FixtureRegistry.load()
    )
    state = await current_state(sg, context=context)
    day = today_for(context)
    around = await around_for(sg, context=context, engine=engine, state=state, day=day)
    made_jobs = []
    for n in range(MAX_CATCH_UP_JOBS + 2):
        job = await create_job(
            sg,
            context=context,
            kind=JobKind.EXPLAINER,
            terms=[f"a tip {n}"],
            reason={"gap": "test"},
        )
        await run_job(
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
        made_jobs.append(job)

    clock.step(timedelta(days=2))
    _, second_load = await refresh(sg, context=context, engine=engine)
    reran_ids = {item.search_job_id for item in second_load if item.search_job_id is not None}
    assert len(reran_ids) <= MAX_CATCH_UP_JOBS


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
