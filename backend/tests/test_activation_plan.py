"""E01-04: the first-week activation plan.

Acceptance: prompts stop once the record has medicines, last visit and next visit.

The close of a biography makes the plan from what it did not capture, one prompt a day from
tomorrow at his breakfast time on his clock; a prompt is done the moment what it asks for
arrives, skipped when he says Later; `due_prompts(profile, at)` answers with the one prompt
due, and with nothing at all once the record holds his medicines and both visits.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.clock import FrozenClock
from app.db import unit_of_work
from app.drafts import AppointmentDraft
from app.keys.confirm import confirm
from app.keys.context import resolve_key_context
from app.keys.scopes import KeyRole, Scope
from app.memory.models import AppointmentStatus, ProviderKind
from app.memory.semantic import current_facts
from app.memory.spine import add_provider, book_appointment
from app.onboarding.plan import close_prompts_on_fact, current_plan, due_prompts
from app.regions import Region
from tests.api import let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.onboarding_support import (
    KIT,
    PA,
    answers,
    call,
    refused,
    stewarded,
    through_the_papers,
)

PLAN_GAPS = [
    "bp_numbers",
    "discharge_letter",
    "sugar_result",
    "kidney_result",
    "next_visit",
    "last_visit",
    "insurance",
]
"""What Pa's biography left open, tier first: the seven days of his first week."""

FIRST_MORNING = datetime(2026, 9, 3, 23, 30, tzinfo=UTC)
"""The clock stands at Thursday 3 September 2026, 16:00 in Singapore: the first prompt is
Friday 4 September at 07:30 on his clock, 23:30 the evening before in UTC."""


async def _closed(deployment: Deployment) -> tuple[dict[str, str], str, dict[str, object]]:
    mei, profile_id = await stewarded(deployment)
    view = await through_the_papers(deployment, mei["token"], profile_id)
    await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/biography/read-back",
        mei["token"],
        200,
        json={"answers": answers(view)},
    )
    closed = await call(
        deployment, "POST", f"/profiles/{profile_id}/biography/close", mei["token"], 200
    )
    return mei, profile_id, closed["plan"]


async def test_seven_prompts_one_a_day_from_tomorrow_at_breakfast(deployment: Deployment) -> None:
    mei, profile_id, plan = await _closed(deployment)
    assert plan["first_day"] == "2026-09-04" and plan["breakfast_time"] == "07:30"
    assert plan["timezone"] == "Asia/Singapore" and plan["stopped"] is False
    prompts = plan["prompts"]
    assert [p["prompt"] for p in prompts] == PLAN_GAPS
    assert [p["day"] for p in prompts] == [1, 2, 3, 4, 5, 6, 7]
    assert prompts[0]["due_at"].startswith("2026-09-03T23:30:00")
    assert prompts[0]["due_local"] == "2026-09-04T07:30:00+08:00"
    assert prompts[6]["due_local"] == "2026-09-10T07:30:00+08:00"
    assert all(p["status"] == "pending" for p in prompts)
    assert prompts[0]["headline"] == "Nombor tekanan darah biasa anda"
    assert prompts[0]["action"] == "Hari ini, ambil gambar mesin tekanan darah anda."
    assert prompts[4]["headline"] == "Lawatan anda yang seterusnya ke Dr Tan"
    assert (prompts[0]["word"], prompts[0]["capture"], prompts[0]["tier"]) == (
        "Darah tinggi",
        "photo",
        1,
    )
    assert (prompts[3]["word"], prompts[3]["capture"]) == ("Masalah buah pinggang", "pdf")
    assert (prompts[4]["word"], prompts[6]["capture"]) == (None, "photo")
    assert plan["due"] == []  # nothing before the first morning

    got = await call(deployment, "GET", f"/profiles/{profile_id}/plan", mei["token"], 200)
    assert [p["prompt"] for p in got["prompts"]] == PLAN_GAPS


async def test_one_prompt_is_due_at_a_time(deployment: Deployment, clock: FrozenClock) -> None:
    mei, profile_id, _ = await _closed(deployment)
    her = mei["token"]
    path = f"/profiles/{profile_id}/plan"

    def at(moment: datetime) -> dict[str, str]:
        return {"at": moment.isoformat()}

    early = await call(
        deployment, "GET", path, her, 200, params=at(FIRST_MORNING - timedelta(minutes=1))
    )
    assert early["due"] == []
    first = await call(deployment, "GET", path, her, 200, params=at(FIRST_MORNING))
    assert [p["prompt"] for p in first["due"]] == ["bp_numbers"]
    # Three mornings on, the first is still the one due: one a day, never three.
    later = await call(
        deployment, "GET", path, her, 200, params=at(FIRST_MORNING + timedelta(days=2))
    )
    assert [p["prompt"] for p in later["due"]] == ["bp_numbers"]

    skipped = await call(deployment, "POST", f"{path}/bp_numbers/skip", her, 200)
    assert skipped["status"] == "skipped" and skipped["skipped_at"]
    await refused(deployment, "POST", f"{path}/bp_numbers/skip", her, 409, "PromptAlreadySettled")
    await refused(deployment, "POST", f"{path}/no_such_gap/skip", her, 404, "NoSuchPrompt")
    after = await call(
        deployment, "GET", path, her, 200, params=at(FIRST_MORNING + timedelta(days=2))
    )
    assert [p["prompt"] for p in after["due"]] == ["discharge_letter"]

    # The exposed call, as a delivery surface makes it.
    async with deployment.sessions() as session:
        async with unit_of_work(session):
            context = await resolve_key_context(
                session,
                region=Region.SG,
                person_id=uuid.UUID(mei["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            due = await due_prompts(session, context=context, at=FIRST_MORNING + timedelta(days=2))
            assert [p.gap for p in due] == ["discharge_letter"]
        await session.commit()


async def test_a_prompt_is_done_when_what_it_asks_for_arrives(deployment: Deployment) -> None:
    mei, profile_id, _ = await _closed(deployment)
    her = mei["token"]
    reading = await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/readings",
        her,
        201,
        json={"systolic": 138, "diastolic": 84},
    )
    plan = await call(deployment, "GET", f"/profiles/{profile_id}/plan", her, 200)
    by_gap = {p["prompt"]: p for p in plan["prompts"]}
    assert by_gap["bp_numbers"]["status"] == "done"
    assert by_gap["bp_numbers"]["done_by_fact_id"] == reading["fact_id"]
    assert all(by_gap[gap]["status"] == "pending" for gap in PLAN_GAPS[1:])
    # Day one's prompt is done before its morning: nothing is due then, and day two's comes
    # on day two's morning, not early.
    path = f"/profiles/{profile_id}/plan"
    first = await call(deployment, "GET", path, her, 200, params={"at": FIRST_MORNING.isoformat()})
    assert first["due"] == []
    second = await call(
        deployment,
        "GET",
        path,
        her,
        200,
        params={"at": (FIRST_MORNING + timedelta(days=1)).isoformat()},
    )
    assert [p["prompt"] for p in second["due"]] == ["discharge_letter"]


async def test_prompts_stop_once_the_record_has_medicines_last_visit_and_next_visit(
    deployment: Deployment,
) -> None:
    mei, profile_id, _ = await _closed(deployment)
    her = mei["token"]
    before = await call(deployment, "GET", f"/profiles/{profile_id}/plan", her, 200)
    assert before["stopped_because"] == ["medicines"] and before["stopped"] is False

    async with deployment.sessions() as session:
        async with unit_of_work(session):
            context = await resolve_key_context(
                session,
                region=Region.SG,
                person_id=uuid.UUID(mei["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            doctor = await add_provider(
                session, context=context, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
            )
            for when, status in (
                (datetime(2026, 8, 20, 2, 0, tzinfo=UTC), AppointmentStatus.ATTENDED),
                (datetime(2026, 10, 1, 2, 0, tzinfo=UTC), AppointmentStatus.PLANNED),
            ):
                draft = AppointmentDraft(
                    provider_id=doctor.id, scheduled_at=when, purpose="check-up"
                )
                yes = await confirm(session, context, draft)
                await book_appointment(
                    session,
                    context=context,
                    provider_id=doctor.id,
                    scheduled_at=when,
                    purpose="check-up",
                    confirmation_id=yes.id,
                    status=status,
                )
            assert (
                await due_prompts(session, context=context, at=FIRST_MORNING + timedelta(days=3))
                == []
            )
            view = await current_plan(session, context=context)
            assert view.stopped
        await session.commit()

    after = await call(
        deployment,
        "GET",
        f"/profiles/{profile_id}/plan",
        her,
        200,
        params={"at": (FIRST_MORNING + timedelta(days=3)).isoformat()},
    )
    assert after["stopped"] is True and after["due"] == []
    assert after["stopped_because"] == ["medicines", "last_visit", "next_visit"]
    by_gap = {p["prompt"]: p["status"] for p in after["prompts"]}
    assert by_gap["next_visit"] == "done" and by_gap["last_visit"] == "done"
    assert by_gap["bp_numbers"] == "pending"  # still in his list; not asked for any more


async def test_fewer_gaps_fewer_prompts_and_breakfast_at_half_past_seven_until_he_says(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    kit = await register_by_phone(deployment, KIT, "Kit")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    await call(deployment, "POST", f"/profiles/{profile_id}/biography", his, 201)
    await call(
        deployment, "PUT", f"/profiles/{profile_id}/settings", his, 200, json={"language": "en"}
    )
    closed = await call(deployment, "POST", f"/profiles/{profile_id}/biography/close", his, 200)
    plan = closed["plan"]
    # Neither he nor a routine has said: the one breakfast time's default (`app.routines.breakfast`).
    assert plan["breakfast_time"] == "07:30"
    assert [p["prompt"] for p in plan["prompts"]] == [
        "medicines",
        "insurance",
        "meal_times",
        "someone_to_see",
    ]
    assert plan["prompts"][0]["due_local"] == "2026-09-04T07:30:00+08:00"
    assert plan["prompts"][0]["action"] == "Today, take a photo of the medicine bag."
    how = {p["prompt"]: (p["capture"], p["word"]) for p in plan["prompts"]}
    assert how["meal_times"] == ("tap", None) and how["someone_to_see"] == ("invite", None)
    assert closed["summary"]["lines"][-3:] == [
        "Tomorrow at breakfast, Nura will ask for one more thing.",
        "There are 4 things to ask, one each day.",
        "Your Today page comes from what you told us.",
    ]

    # Letting Kit in closes the last one the next time the plan is read; saying when he has
    # breakfast closes another the moment it is saved.
    await let_in(deployment, pa, profile_id, KIT, ["records"], "son")
    await call(
        deployment,
        "POST",
        f"/profiles/{profile_id}/keys",
        his,
        201,
        json={"holder_phone_e164": KIT, "role": "caregiver", "scopes": ["records"]},
    )
    await call(
        deployment,
        "PUT",
        f"/profiles/{profile_id}/settings",
        his,
        200,
        json={"language": "en", "breakfast_time": "07:00"},
    )
    now = await call(deployment, "GET", f"/profiles/{profile_id}/plan", his, 200)
    status = {p["prompt"]: p["status"] for p in now["prompts"]}
    assert status == {
        "medicines": "pending",
        "insurance": "pending",
        "meal_times": "done",
        "someone_to_see": "done",
    }
    # A caregiver reads the plan; Later is not hers to say.
    await call(deployment, "GET", f"/profiles/{profile_id}/plan", kit["token"], 200)
    await refused(
        deployment,
        "POST",
        f"/profiles/{profile_id}/plan/medicines/skip",
        kit["token"],
        403,
        "NotTheirsToSetUp",
    )
    await refused(deployment, "GET", f"/profiles/{uuid.uuid4()}/plan", his, 403, "NoKey")


async def test_a_narrow_key_writing_a_fact_never_trips_the_plan(deployment: Deployment) -> None:
    """The eager close runs under the writer's key. A helper's key — the medicines and the face
    of the graph — does not open the plan: the hook steps aside, and the fact lands."""
    mei, profile_id, _ = await _closed(deployment)
    async with deployment.sessions() as session:
        async with unit_of_work(session):
            chief = await resolve_key_context(
                session,
                region=Region.SG,
                person_id=uuid.UUID(mei["person_id"]),
                profile_id=uuid.UUID(profile_id),
            )
            helper = replace(
                chief, scopes=frozenset({Scope.PROFILE, Scope.MEDICINES}), role=KeyRole.HELPER
            )
            medicine = (await current_facts(session, context=chief, subject="medicine"))[0]
            await close_prompts_on_fact(session, helper, medicine)
            view = await current_plan(session, context=chief)
            assert [p.gap for p in view.prompts] == PLAN_GAPS
        await session.commit()


async def test_later_sends_a_prompt_to_the_back_of_the_week_then_retires_it(
    deployment: Deployment,
) -> None:
    """docs/gaps-and-unlocks.md §4: Later defers it, and it is asked once more; a second Later
    retires it from the week, kept in the plan for the caregiver's list."""
    mei, profile_id, _ = await _closed(deployment)
    her = mei["token"]
    path = f"/profiles/{profile_id}/plan"
    once = await call(deployment, "POST", f"{path}/later", her, 200, json={"gap_id": "bp_numbers"})
    bp = next(p for p in once["prompts"] if p["prompt"] == "bp_numbers")
    assert (bp["status"], bp["deferred"], bp["tier"], bp["capture"]) == ("pending", 1, 1, "photo")
    assert bp["due_local"] == "2026-09-11T07:30:00+08:00"  # the morning after day seven
    assert [p["prompt"] for p in once["prompts"]][-1] == "bp_numbers"
    morning = await call(
        deployment, "GET", path, her, 200, params={"at": FIRST_MORNING.isoformat()}
    )
    assert morning["due"] == []
    twice = await call(deployment, "POST", f"{path}/later", her, 200, json={"gap_id": "bp_numbers"})
    bp = next(p for p in twice["prompts"] if p["prompt"] == "bp_numbers")
    assert (bp["status"], bp["deferred"]) == ("skipped", 2) and bp["skipped_at"]
    await refused(
        deployment,
        "POST",
        f"{path}/later",
        her,
        409,
        "PromptAlreadySettled",
        json={"gap_id": "bp_numbers"},
    )
    await refused(
        deployment,
        "POST",
        f"{path}/later",
        her,
        404,
        "NoSuchPrompt",
        json={"gap_id": "no_such_gap"},
    )
    kinds = {p["prompt"]: p["capture"] for p in twice["prompts"]}
    assert kinds["insurance"] == "photo"
