"""RE-06: the broker (`app.delivery.recommend.broker.slate`) and its four rules, against a
golden profile, in the pattern of `tests/test_series.py`'s own golden profile (RE-03).

The clock is frozen at Thursday 3 September 2026, 08:00 UTC on Pa's wall (`tests.conftest.
FROZEN_AT`) and stepped a day at a time, so a new medicine, a rising blood pressure, a cloud
tap and two upcoming visits each land on a day of their own — the same shape `test_series.py`
already uses for its own golden read.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.recommend.broker import slate
from app.delivery.recommend.models import Candidate, Evidence, OutputKind, SafetyClass
from app.delivery.recommend.rank import RuleRanker
from app.delivery.recommend.rules import (
    CATALOGUE,
    RULE_DID_YOU_KNOW,
    RULE_FEELING_AFTER_NEW_MEDICINE,
    RULE_NEW_MEDICINE_EXPLAINER,
    RULE_TEST_COMING,
    RULE_VISIT_TOPIC_WEEK,
    RecommendationRule,
    RuleInputs,
)
from app.drafts import AppointmentDraft, FactDraft
from app.keys.confirm import confirm
from app.keys.context import KeyContext
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import Appointment, ConfidenceState, EventKind, ProviderKind, SourceChannel
from app.memory.semantic import assert_fact
from app.memory.spine import add_provider, book_appointment
from app.reasoning.feelings.service import record_tap
from app.regions import Region
from app.safety.red_flags import Feeling
from app.state.service import current_state
from tests.family_support import household
from tests.feelings_support import (
    REGISTRY,
    STORE,
    TRANSCRIBER,
    VIA,
    blood_pressure,
    new_medicine,
    visit_with,
)

RULE_IDS = {
    RULE_NEW_MEDICINE_EXPLAINER,
    RULE_FEELING_AFTER_NEW_MEDICINE,
    RULE_VISIT_TOPIC_WEEK,
    RULE_TEST_COMING,
    RULE_DID_YOU_KNOW,
}


async def _lab_visit(
    session: AsyncSession, owner: KeyContext, *, at: datetime, purpose: str
) -> Appointment:
    """A visit at a lab, the way `tests.feelings_support.visit_with` books one at a doctor."""
    provider = await add_provider(
        session, context=owner, name="City Lab", kind=ProviderKind.LAB, region=Region.SG
    )
    draft = AppointmentDraft(provider_id=provider.id, scheduled_at=at, purpose=purpose)
    yes = await confirm(session, owner, draft)
    return await book_appointment(
        session,
        context=owner,
        provider_id=provider.id,
        scheduled_at=at,
        purpose=purpose,
        confirmation_id=yes.id,
    )


async def _switch_signal(
    session: AsyncSession, owner: KeyContext, *, family: str, on: bool
) -> None:
    """The exact fact shape RE-05/#243 defines: `subject="signals", attribute=<family>`, his
    own confirmed yes — written the same way `app.reasoning.signals.set_signal_use` would,
    without importing that story's module (not on `main`, see `broker.py`'s module doc)."""
    event = await record_event(
        session,
        context=owner,
        # RE-05 (#243, not merged) adds `EventKind.SETTING` for this; `ONBOARDING` is the
        # closest kind already on `main` ("the settings he chose", `app.memory.models`).
        kind=EventKind.ONBOARDING,
        occurred_at=utcnow(),
        label=f"signal {family}: {'on' if on else 'off'}",
        source_channel=SourceChannel.APP,
    )
    draft = FactDraft(
        subject="signals",
        attribute=family,
        value=on,
        unit=None,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        artifact_id=None,
        event_id=event.id,
        episode_id=None,
        supersedes_id=None,
    )
    yes = await confirm(session, owner, draft)
    await assert_fact(
        session,
        context=owner,
        subject="signals",
        attribute=family,
        value=on,
        confidence=1.0,
        confidence_state=ConfidenceState.CONFIRMED_BY_PERSON,
        confirmation_id=yes.id,
        event_id=event.id,
    )


async def test_golden_slate_matches_the_fixture_profile(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)

    await new_medicine(sg, owner)  # amlodipine, started_at = now

    clock.step(timedelta(days=1))
    await blood_pressure(sg, owner, systolic=130, diastolic=84)

    clock.step(timedelta(days=1))
    await blood_pressure(sg, owner, systolic=138, diastolic=84)

    clock.step(timedelta(days=1))
    await blood_pressure(sg, owner, systolic=145, diastolic=84)

    clock.step(timedelta(days=1))
    tapped = await record_tap(
        sg,
        context=owner,
        word=Feeling.DIZZY,  # amlodipine's monograph watch-out ("dizzy_standing")
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )

    now = utcnow()
    await visit_with(sg, owner, at=now + timedelta(days=3))  # DOCTOR, inside BEFORE_VISIT
    await _lab_visit(sg, owner, at=now + timedelta(days=2), purpose="diabetes blood test")

    state = await current_state(sg, context=owner)
    result = await slate(sg, context=owner, state=state, registry=REGISTRY)
    candidates = list(result.candidates)

    assert {c.rule_id for c in candidates} == RULE_IDS

    # Every candidate's evidence resolves to a row this key wrote, and is readable by it.
    for candidate in candidates:
        assert candidate.because, "no candidate is ever built with empty evidence"
        assert candidate.readable_by(owner)

    by_rule: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_rule.setdefault(candidate.rule_id, []).append(candidate)

    # new_medicine_explainer: a READ and a CLIP, on amlodipine's own topic.
    new_medicine_candidates = by_rule[RULE_NEW_MEDICINE_EXPLAINER]
    assert {c.output for c in new_medicine_candidates} == {OutputKind.READ, OutputKind.CLIP}
    assert {c.topic for c in new_medicine_candidates} == {"medicine.blood_pressure_tablet"}

    # feeling_after_new_medicine: a READ and a VISIT_QUESTION, resting on the tap and the line.
    feeling_candidates = by_rule[RULE_FEELING_AFTER_NEW_MEDICINE]
    assert {c.output for c in feeling_candidates} == {OutputKind.READ, OutputKind.VISIT_QUESTION}
    for candidate in feeling_candidates:
        assert candidate.topic == "medicine.blood_pressure_tablet"
        assert {e.kind for e in candidate.because} == {"line", "tap"}
        tap_evidence = next(e for e in candidate.because if e.kind == "tap")
        assert tap_evidence.id == tapped.tap.id

    # visit_topic_week: his systolic pressure rose three readings running, ahead of a DOCTOR
    # visit inside the week — a READ and a CLIP on high blood pressure. Diastolic held level
    # (every reading recorded at 84), so it never becomes a candidate of its own.
    visit_topic_candidates = by_rule[RULE_VISIT_TOPIC_WEEK]
    assert {c.output for c in visit_topic_candidates} == {OutputKind.READ, OutputKind.CLIP}
    assert {c.topic for c in visit_topic_candidates} == {"condition.high_blood_pressure"}

    # test_coming: the lab visit's own purpose tags the diabetes topic.
    test_coming_candidates = by_rule[RULE_TEST_COMING]
    assert [c.output for c in test_coming_candidates] == [OutputKind.CLIP]
    assert test_coming_candidates[0].topic == "condition.diabetes"

    # did_you_know: one topic a day from what rests on his record today — his own new
    # medicine, or the lab visit's own tagged topic (RE-09-style curiosity nudge, brief).
    did_you_know_candidates = by_rule[RULE_DID_YOU_KNOW]
    assert len(did_you_know_candidates) == 1
    assert did_you_know_candidates[0].output is OutputKind.READ
    assert did_you_know_candidates[0].topic in {
        "medicine.blood_pressure_tablet",
        "condition.diabetes",
    }

    # Deterministic ordering: the same inputs rank the same way on a second read...
    again = await slate(sg, context=owner, state=state, registry=REGISTRY)

    def _key(candidate: Candidate) -> tuple[str, OutputKind, str]:
        return (candidate.rule_id, candidate.output, candidate.topic)

    assert [_key(c) for c in again.candidates] == [_key(c) for c in candidates]

    # ...and re-ranking the same set of candidates, given in a different order, lands on the
    # same order again — order-independence, not just repeatability of one code path.
    assert RuleRanker().rank(list(reversed(candidates)), state=state, engagement={}) == candidates


async def test_a_key_without_records_never_sees_what_rests_on_it_named_as_withheld(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """Kit holds every caregiver scope but RECORDS: `feeling_after_new_medicine` needs a
    cloud tap (RECORDS) alongside the line, so it never appears in her slate, and RECORDS is
    named in `Slate.withheld` — not a silent, empty answer standing in for "nothing found"."""
    kit_scopes = ROLE_SCOPES[KeyRole.CAREGIVER] - {Scope.RECORDS}
    home = await household(sg, kit_scopes=kit_scopes)
    owner = await home.ctx(sg, home.pa)
    kit = await home.ctx(sg, home.kit)
    assert not kit.allows(Scope.RECORDS)

    await new_medicine(sg, owner)
    await record_tap(
        sg,
        context=owner,
        word=Feeling.DIZZY,
        registry=REGISTRY,
        store=STORE,
        transcriber=TRANSCRIBER,
        via=VIA,
    )

    # `current_state` itself reads under RECORDS (state's own scope, `STATE_SCOPE`), so a key
    # this narrow cannot read any State at all — not this story's rule to relax, and exactly
    # why `slate()` takes `state: StateView | None`: Kit passes what she actually has, none.
    result = await slate(sg, context=kit, state=None, registry=REGISTRY)

    rule_ids = {c.rule_id for c in result.candidates}
    assert RULE_NEW_MEDICINE_EXPLAINER in rule_ids  # MEDICINES alone is enough for this one
    assert RULE_FEELING_AFTER_NEW_MEDICINE not in rule_ids  # needs RECORDS too

    for candidate in result.candidates:
        assert candidate.readable_by(kit)
        assert Scope.RECORDS not in {e.scope for e in candidate.because}

    assert Scope.RECORDS in result.withheld


def _fixture_food_rule(inputs: RuleInputs) -> list[Candidate]:
    """Stands in for a real family-gated rule (RE-09/RE-10 add the first one): unconditional,
    so the only reason it would ever be missing from a slate is the switch being off."""
    return [
        Candidate(
            rule_id="fixture_food_rule",
            output=OutputKind.READ,
            topic="condition.diabetes",
            because=(Evidence(kind="fact", id=inputs.lines[0].line_id, scope=Scope.MEDICINES),)
            if inputs.lines
            else (Evidence(kind="fact", id=inputs.upcoming_visits[0].appointment_id, scope=Scope.VISITS),),
            safety=SafetyClass.RECORD_BACK,
            audience=frozenset(),
        )
    ]


async def test_a_switched_off_family_produces_no_candidate_from_it(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """A rule that names a `signal_family` is skipped once that family's switch
    (`subject="signals", attribute=<family>`, the exact fact shape RE-05/#243 defines) is off
    — read directly here, since that story has not merged (module doc of `broker.py`). None of
    this story's four rules reads a switchable family yet, so the mechanism is exercised with
    a fixture rule standing in for one RE-09/RE-10 will add for real."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    await new_medicine(sg, owner)

    fixture_rule = RecommendationRule("fixture_food_rule", "food", _fixture_food_rule)
    rules = (*CATALOGUE, fixture_rule)

    state = await current_state(sg, context=owner)

    on = await slate(sg, context=owner, state=state, registry=REGISTRY, rules=rules)
    assert any(c.rule_id == "fixture_food_rule" for c in on.candidates)

    await _switch_signal(sg, owner, family="food", on=False)

    off = await slate(sg, context=owner, state=state, registry=REGISTRY, rules=rules)
    assert not any(c.rule_id == "fixture_food_rule" for c in off.candidates)
    # Every other rule keeps working: switching one family off never touches another.
    assert {c.rule_id for c in off.candidates} & RULE_IDS


async def test_did_you_know_is_skipped_when_its_own_switch_is_off(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """`did_you_know` names `signal_family="did_you_know"` for real (`rules.CATALOGUE`, not a
    fixture stand-in): "What Nura uses" turns it off the same way any other family is turned
    off, before the rule is ever called — never a candidate filtered out afterwards."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    await new_medicine(sg, owner)  # gives did_you_know a topic to pick from

    state = await current_state(sg, context=owner)
    on = await slate(sg, context=owner, state=state, registry=REGISTRY)
    assert any(c.rule_id == RULE_DID_YOU_KNOW for c in on.candidates)

    await _switch_signal(sg, owner, family="did_you_know", on=False)

    off = await slate(sg, context=owner, state=state, registry=REGISTRY)
    assert not any(c.rule_id == RULE_DID_YOU_KNOW for c in off.candidates)
    # Every other rule keeps working: switching this family off never touches another.
    assert {c.rule_id for c in off.candidates} & (RULE_IDS - {RULE_DID_YOU_KNOW})


async def test_did_you_know_never_picks_a_topic_he_has_said_not_for_me_to(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """The broker reads the same thirty-day `declined_topic` fact `_broker_wanted` already
    filters on downstream (`app.delivery.feed.compose`), so `did_you_know` rotates past a
    topic he declined rather than silently producing nothing for the day it would have
    picked it."""
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    await new_medicine(sg, owner)  # amlodipine: medicine.blood_pressure_tablet

    told = await record_event(
        sg,
        context=owner,
        kind=EventKind.ONBOARDING,
        occurred_at=utcnow(),
        label="the conditions he told",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        sg,
        context=owner,
        subject="condition",
        attribute="diabetes",
        value=True,
        confidence=1.0,
        event_id=told.id,
    )

    now = utcnow()
    declined = await record_event(
        sg,
        context=owner,
        kind=EventKind.ENGAGEMENT,
        occurred_at=now,
        label="not for me: a topic",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        sg,
        context=owner,
        subject="declined_topic",
        attribute="medicine.blood_pressure_tablet",
        value={"item_id": "test"},
        confidence=1.0,
        event_id=declined.id,
        valid_from=now,
        valid_to=now + timedelta(days=30),
    )

    state = await current_state(sg, context=owner)
    result = await slate(sg, context=owner, state=state, registry=REGISTRY)
    [candidate] = [c for c in result.candidates if c.rule_id == RULE_DID_YOU_KNOW]
    assert candidate.topic == "condition.diabetes"
