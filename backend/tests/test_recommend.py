"""RE-01: the broker's types. No `why`, no recommendation — an empty `because` raises at
construction, and a candidate is readable only by a key that holds every scope its evidence
rests on, and, when it is his alone, only by him (docs/recommendation-engine.md §2.4, §3.3,
§3.5)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.recommend.models import (
    Audience,
    Candidate,
    Evidence,
    NoEvidence,
    OutputKind,
    SafetyClass,
    readable_by,
)
from app.keys.scopes import Scope
from tests.family_support import household


def _evidence(scope: Scope, kind: str = "fact") -> Evidence:
    return Evidence(kind=kind, id=uuid.uuid4(), scope=scope)


def test_a_candidate_with_no_evidence_is_refused_at_construction() -> None:
    with pytest.raises(NoEvidence):
        Candidate(
            rule_id="new_medicine_explainer",
            output=OutputKind.READ,
            topic="amlodipine",
            because=(),
            safety=SafetyClass.RECORD_BACK,
            audience=frozenset({Audience.PATIENT}),
        )


async def test_readable_by_holds_the_one_door_rule(sg: AsyncSession) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    helper = await home.ctx(sg, home.siti)  # holds only PROFILE, MEDICINES, EMERGENCY, SEND

    records_evidence = _evidence(Scope.RECORDS)
    assert records_evidence.readable_by(owner)
    assert not records_evidence.readable_by(helper)

    medicines_evidence = _evidence(Scope.MEDICINES, kind="line")
    assert medicines_evidence.readable_by(helper)

    # A candidate spanning two scopes is readable only by a key that holds every one of them:
    # the one-door rule (ADR 0004 decision 10) `Pattern` and `FeelingNote` already keep to.
    candidate = Candidate(
        rule_id="feeling_after_new_medicine",
        output=OutputKind.VISIT_QUESTION,
        topic="dizzy",
        because=(medicines_evidence, records_evidence),
        safety=SafetyClass.RECORD_BACK,
        audience=frozenset({Audience.PATIENT, Audience.MEMO}),
    )
    assert candidate.readable_by(owner)
    assert not candidate.readable_by(helper)  # holds MEDICINES but not RECORDS
    assert readable_by(candidate.because, owner)
    assert not readable_by(candidate.because, helper)


async def test_a_private_candidate_is_readable_only_by_the_one_it_is_private_to(
    sg: AsyncSession,
) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    chief = await home.ctx(sg, home.mei)  # ALL_SCOPES, including ASK — no exception (§3.5)

    private_evidence = _evidence(Scope.ASK, kind="asked_topic")
    candidate = Candidate(
        rule_id="asked_about",
        output=OutputKind.READ,
        topic="kidney_test",
        because=(private_evidence,),
        safety=SafetyClass.EXTERNAL,
        audience=frozenset({Audience.PATIENT}),
        private_to=owner.person_id,
    )
    # The chief's key covers every scope the evidence rests on, and still may not see it:
    # `private_to` is not a scope, so no scope a caregiver holds is an exception.
    assert candidate.readable_by(owner)
    assert not candidate.readable_by(chief)
