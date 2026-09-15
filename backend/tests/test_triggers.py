"""E00-05, E11-05, E11-10: the trigger engine, the channels and caps per type, the morning.

`run_due(profile, at)` evaluates every trigger for one profile at one moment and writes one
`Delivery` per attempt, each naming its rule. No persona receives more than the configured
cap per day; an alert has no cap and no quiet hours; each type goes by its configured
channel; the morning card goes at his breakfast, once a day, by WhatsApp; a pattern is a
count, never a diagnosis; a family message comes due and reaches him.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry
from app.clock import FrozenClock
from app.delivery.push import FixturePush
from app.delivery.strings import PUSH_LINE
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.models import (
    Delivery,
    DeliveryChannel,
    DeliveryOutcome,
    TriggerKind,
    TriggerType,
)
from app.delivery.triggers.preferences import change
from app.delivery.triggers.rules import RULES, AlertsAreNeverHeld, NotASetting, check_settings
from app.family.models import PushChannel, ScheduledPush
from app.ingestion.models import DocumentKind, ReviewCard
from app.keys.scopes import Scope
from app.onboarding.gaps import BY_CODE
from app.onboarding.plan import current_plan, make_plan
from app.onboarding.settings import SettingsValues, save_settings
from app.onboarding.words import prompt as prompt_words
from app.routines.breakfast import breakfast_time
from app.routines.service import due_now
from app.state.service import render_from_state
from tests.delivery_support import PA, Home, home
from tests.medicines_support import add, artefact, label

SGT = ZoneInfo("Asia/Singapore")


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _rows(report: Report, kind: TriggerType) -> list[Delivery]:
    return [sent.delivery for sent in report.sent if sent.delivery.trigger_type is kind]


# --- the morning card (E11-10) -----------------------------------------------------------------


async def test_the_morning_card_goes_at_breakfast_once_a_day_by_whatsapp(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    # Nobody has said when he has breakfast: the one breakfast time's default, 07:30.
    assert _rows(await _run(sg, h, clock, at(6, 50)), TriggerType.MORNING) == []
    report = await _run(sg, h, clock, at(7, 31))
    [card] = _rows(report, TriggerType.MORNING)
    assert card.outcome is DeliveryOutcome.SENT and card.via is DeliveryChannel.WHATSAPP
    assert card.template_name == "morning_card" and card.rule == "breakfast_anchor_reached"
    assert card.trigger_kind is TriggerKind.RULE and card.why["breakfast_at"] == "07:30"
    text = h.sent_to(h.pa)[-1].splitlines()
    assert text[:3] == [
        "Good morning, Pa, this is Nura.",
        "Today is Monday 14 September.",
        "Take 1 tablet of your blood pressure tablet with breakfast.",
    ]
    assert _rows(await _run(sg, h, clock, at(7, 45)), TriggerType.MORNING) == []
    # The next day, once again; three hours after breakfast it is dropped, never sent late.
    assert _rows(await _run(sg, h, clock, at(10, 31, day=15)), TriggerType.MORNING) == []
    assert len(_rows(await _run(sg, h, clock, at(7, 35, day=16)), TriggerType.MORNING)) == 1
    # A delivery that reached him is a SHARE on the trail, under the scope it spoke of.
    shares = (
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.action == Action.SHARE, AuditEntry.target == "delivery"
            )
        )
    ).all()
    assert h.pa.id in {entry.shared_with_person_id for entry in shares}
    for entry in shares:
        assert entry.target_id is not None
        row = await sg.get(Delivery, entry.target_id)
        assert row is not None and row.outcome is DeliveryOutcome.SENT
        assert row.to_person_id == entry.shared_with_person_id and row.scope is entry.scope


async def test_there_is_one_breakfast_time(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """His settings say breakfast is at 07:30: the routine's breakfast, the first week's
    prompt and the morning card are all at 07:30. He changes it to 08:15: all three move."""
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await save_settings(
        sg, context=h.owner, values=SettingsValues(language="en", breakfast_time=time(7, 30))
    )
    await make_plan(sg, context=h.owner, session_id=None, gaps=[BY_CODE["weight"]], breakfast=None)

    async def shared(day: int, hour: int, minute: int) -> None:
        assert await breakfast_time(sg, context=h.owner) == time(hour, minute)
        due = await due_now(sg, context=h.owner, at=at(hour, minute, day=day))
        assert due is not None and due.anchor == "breakfast" and due.at == time(hour, minute)
        view = await current_plan(sg, context=h.owner)
        assert view.due_of(view.prompts[0]).astimezone(SGT).time() == time(hour, minute)
        early = at(hour, minute, day=day) - timedelta(minutes=1)
        assert _rows(await _run(sg, h, clock, early), TriggerType.MORNING) == []
        [card] = _rows(await _run(sg, h, clock, at(hour, minute, day=day)), TriggerType.MORNING)
        assert card.outcome is DeliveryOutcome.SENT
        assert card.why["breakfast_at"] == f"{hour:02d}:{minute:02d}"
        assert (
            _rows(
                report_after := await _run(sg, h, clock, at(hour, minute, day=day)),
                TriggerType.MORNING,
            )
            == []
        )
        assert report_after.day == f"2026-09-{day}"

    await shared(15, 7, 30)
    await save_settings(
        sg, context=h.owner, values=SettingsValues(language="en", breakfast_time=time(8, 15))
    )
    await shared(16, 8, 15)


async def test_a_quiet_day_is_skipped_only_when_he_asked(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    from app.delivery.triggers.deliver import Via
    from tests.whatsapp_support import family

    clock.set(at(6))
    fam = await family(sg, tmp_path)
    via = Via.of(fam.settings, fam.providers)
    first = await run_due(sg, via=via, profile_id=fam.profile.id, at=at(7, 31))
    [sent] = [s.delivery for s in first.sent if s.delivery.trigger_type is TriggerType.MORNING]
    assert sent.outcome is DeliveryOutcome.SENT and sent.why["quiet_day"] is True
    await change(
        sg,
        context=fam.owner,
        skip_quiet_days=True,
        quiet_from=None,
        quiet_until=None,
        channels={},
        caps={},
    )
    clock.set(at(7, 31, day=15))
    second = await run_due(sg, via=via, profile_id=fam.profile.id, at=at(7, 31, day=15))
    [held] = [s.delivery for s in second.sent if s.delivery.trigger_type is TriggerType.MORNING]
    assert held.outcome is DeliveryOutcome.SKIPPED and held.reason == "a quiet day, as asked"


# --- rules, caps and quiet hours (E00-05) ------------------------------------------------------------


async def test_the_reorder_date_reached_tells_the_one_on_duty_capped_the_second_time(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    [sent] = _rows(await _run(sg, h, clock, at(10)), TriggerType.REORDER)
    assert sent.to_person_id == h.mei.id and sent.standing == "on_duty"
    assert sent.outcome is DeliveryOutcome.SENT and sent.rule == "reorder_date_reached"
    assert h.sent_to(h.mei)[-1].splitlines() == [
        "Pa's tablets are running low.",
        "Pa's blood pressure tablet runs out on Wednesday 16 September.",
        "Can you order more for Pa?",
    ]
    [held] = _rows(await _run(sg, h, clock, at(12)), TriggerType.REORDER)
    assert held.outcome is DeliveryOutcome.CAPPED and held.reason == "once a day"
    # The hold is written down once; nothing more that day.
    assert _rows(await _run(sg, h, clock, at(14)), TriggerType.REORDER) == []
    # 22:30 the next day: the quiet hours hold it, and it waits for the morning.
    [quiet] = _rows(await _run(sg, h, clock, at(22, 30, day=15)), TriggerType.REORDER)
    assert quiet.outcome is DeliveryOutcome.QUIET
    [again] = _rows(await _run(sg, h, clock, at(10, day=16)), TriggerType.REORDER)
    assert again.outcome is DeliveryOutcome.SENT


async def test_no_one_receives_more_than_the_configured_cap_a_day(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    await add(sg, h.owner, label("metformin", "500 mg", "1 tab OM", quantity=2))
    rows = _rows(await _run(sg, h, clock, at(10)), TriggerType.REORDER)
    assert sorted(row.outcome for row in rows) == [DeliveryOutcome.CAPPED, DeliveryOutcome.SENT]
    capped = next(row for row in rows if row.outcome is DeliveryOutcome.CAPPED)
    assert capped.reason == "1 a day"
    # The family raises the cap for reorders; the next day both go.
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=None,
        quiet_until=None,
        channels={},
        caps={"reorder": 2},
    )
    rows = _rows(await _run(sg, h, clock, at(10, day=15)), TriggerType.REORDER)
    assert [row.outcome for row in rows] == [DeliveryOutcome.SENT, DeliveryOutcome.SENT]


def test_an_alert_is_never_capped_and_a_setting_is_checked() -> None:
    assert RULES[TriggerType.FLAG].cap is None and RULES[TriggerType.FLAG].quiet is False
    with pytest.raises(AlertsAreNeverHeld):
        check_settings({}, {"flag": 3})
    with pytest.raises(NotASetting):
        check_settings({"reorder": ["pigeon"]}, {})
    with pytest.raises(NotASetting):
        check_settings({"reorder": ["whatsapp", "whatsapp"]}, {})
    with pytest.raises(NotASetting):
        check_settings({}, {"reorder": 0})
    assert check_settings({"reorder": ["app_push"]}, {"morning": 1}) == (
        {"reorder": ["app_push"]},
        {"morning": 1},
    )


# --- channels (E11-05) ----------------------------------------------------------------------------------


async def test_each_type_goes_by_its_configured_channel(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=None,
        quiet_until=None,
        channels={"reorder": ["app_push", "whatsapp"]},
        caps={},
    )
    # Mei has no device yet: the app push falls through to WhatsApp, and the row says why.
    [first] = _rows(await _run(sg, h, clock, at(10)), TriggerType.REORDER)
    assert first.via is DeliveryChannel.WHATSAPP and first.passed_over == ["app_push: no device"]
    # With a device, the next day's reorder is an app push: one line, no health content.
    assert isinstance(h.via.providers.push, FixturePush)
    h.push.register(h.mei.id)
    [second] = _rows(await _run(sg, h, clock, at(10, day=15)), TriggerType.REORDER)
    assert second.via is DeliveryChannel.APP_PUSH and second.template_name is None
    assert second.passed_over == []
    # Every push is the one content-free line, and only to the person with a device.
    assert h.push.sent and {one.text for one in h.push.sent} == {PUSH_LINE["en"]}
    assert {one.person_id for one in h.push.sent} == {h.mei.id}


async def test_when_he_cannot_be_reached_the_caregiver_on_duty_is(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    h.pa.phone_e164 = None
    await sg.flush()
    [rung] = _rows(await _run(sg, h, clock, at(8, 31)), TriggerType.DOSE)
    assert rung.via is DeliveryChannel.CAREGIVER and rung.to_person_id == h.mei.id
    assert rung.for_person_id == h.pa.id and rung.reason == "for the patient"
    assert rung.passed_over == ["app_push: no device", "whatsapp: no number"]
    assert h.sent_to(h.mei)[-1].splitlines()[0] == (
        "Pa has not said Taken for Pa's blood pressure tablet with breakfast yet."
    )
    assert h.whatsapp.sent[-1].to_e164 != PA


# --- the pattern and the events ----------------------------------------------------------------------------


async def test_three_untapped_tablets_in_a_week_are_a_count_for_the_one_on_duty(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6, day=12))
    h = await home(sg, tmp_path)
    [counted] = _rows(await _run(sg, h, clock, at(10)), TriggerType.DOSES_UNTAPPED)
    assert counted.trigger_kind is TriggerKind.PATTERN and counted.to_person_id == h.mei.id
    assert counted.why["count"] == 3 and counted.why["days"] == 7
    assert counted.rule == "three_untapped_doses_in_seven_days"
    assert h.sent_to(h.mei)[-1].splitlines() == [
        "Pa did not say Taken 3 times this week.",
        "This is a count, not a worry.",
        "You can see which ones in the app.",
    ]
    # Once a week.
    assert _rows(await _run(sg, h, clock, at(10, day=15)), TriggerType.DOSES_UNTAPPED) == []


async def test_a_paper_waiting_for_a_yes_tells_the_chief_there_are_papers(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    photo = await artefact(sg, h.owner)
    from app.audit.access import audited_write

    await audited_write(
        sg,
        ReviewCard,
        h.owner,
        Scope.RECORDS,
        artifact_id=photo.id,
        document_kind=DocumentKind.LAB_REPORT,
    )
    [told] = _rows(await _run(sg, h, clock, at(11)), TriggerType.PAPERS)
    assert told.to_person_id == h.mei.id and told.trigger_kind is TriggerKind.EVENT
    assert h.sent_to(h.mei)[-1].splitlines() == [
        "New papers for Pa are waiting for your yes.",
        "You can check them in the app.",
    ]


async def test_a_family_message_comes_due_and_reaches_him(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    mei = await h.ctx(sg, h.mei)
    await render_from_state(
        sg,
        ScheduledPush,
        mei,
        Scope.SEND,
        composed_by_person_id=h.mei.id,
        composed_at=at(6),
        language="en",
        template_id=None,
        lines=["Mei will pick you up at 9.", "Bring your blood pressure book."],
        send_at=at(8),
        via_channel=PushChannel.WHATSAPP,
        expires_at=at(20),
    )
    assert _rows(await _run(sg, h, clock, at(7, 59)), TriggerType.FAMILY_MESSAGE) == []
    [sent] = _rows(await _run(sg, h, clock, at(8, 1)), TriggerType.FAMILY_MESSAGE)
    assert sent.outcome is DeliveryOutcome.SENT and sent.template_name == "family_note"
    assert h.sent_to(h.pa)[-1].splitlines() == [
        "Mei sent you a message.",
        "Mei will pick you up at 9.",
        "Bring your blood pressure book.",
    ]
    assert _rows(await _run(sg, h, clock, at(9)), TriggerType.FAMILY_MESSAGE) == []


async def test_every_row_names_its_rule(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6, day=12))
    h = await home(sg, tmp_path, quantity=2)
    for when in (at(7, 31), at(9, 31), at(10, 5), at(11), at(22, 30)):
        await _run(sg, h, clock, when)
    rows = (await sg.scalars(select(Delivery))).all()
    assert rows and {row.rule for row in rows} <= {rule.rule for rule in RULES.values()}
    assert all(row.rule == RULES[row.trigger_type].rule for row in rows)
    assert timedelta(0) <= rows[-1].recorded_at - rows[0].recorded_at


async def test_the_first_week_prompt_is_one_line_of_the_morning_card(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """E01-04's prompt due today rides the morning card as one line, and is an event trigger
    of its own, logged with its rule — once a day, under the card's one a day."""
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await make_plan(sg, context=h.owner, session_id=None, gaps=[BY_CODE["weight"]], breakfast=None)
    words = prompt_words("weight", "en", None)
    assert words is not None
    report = await _run(sg, h, clock, at(7, 31, day=15))
    [card] = _rows(report, TriggerType.MORNING)
    [along] = _rows(report, TriggerType.FIRST_WEEK_PROMPT)
    assert card.outcome is DeliveryOutcome.SENT
    assert along.outcome is DeliveryOutcome.SENT and along.trigger_kind is TriggerKind.EVENT
    assert along.rule == "first_week_prompt_due" and along.reason == "in the morning card"
    assert along.message_id == card.message_id and along.why["gap"] == "weight"
    assert words.action in h.sent_to(h.pa)[-1].splitlines()
    assert _rows(await _run(sg, h, clock, at(7, 50, day=15)), TriggerType.FIRST_WEEK_PROMPT) == []


async def test_the_nudge_goes_at_its_time_and_one_cap_says_how_many_a_day(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """E17's planner hands the day's nudge over and the engine sends it from its time, by the
    one cap on nudges a day (`caps.nudge`, one unless the family sets it): the planner hands
    over by that number and the engine sends by it, so there is no second cap."""
    from app.db import as_utc
    from app.delivery.nudges.engine import hand_over, plan_nudges
    from app.family.thread import post_message
    from tests.feelings_support import REGISTRY

    clock.set(at(9))
    h = await home(sg, tmp_path)
    caps = {"skip_quiet_days": False, "quiet_from": None, "quiet_until": None, "channels": {}}
    await change(sg, context=h.owner, **caps, caps={"nudge": 2})
    _, first = await hand_over(sg, context=h.owner, registry=REGISTRY)
    # Mei writes to the family: the day has a second nudge to offer (presence).
    await post_message(sg, context=await h.ctx(sg, h.mei), text="See you on Saturday, Pa.")
    _, second = await hand_over(sg, context=h.owner, registry=REGISTRY)
    early = as_utc(first.send_after) - timedelta(minutes=1)
    assert _rows(await _run(sg, h, clock, early), TriggerType.NUDGE) == []
    # The family lowers the cap to one: the engine sends the better one and holds the other.
    await change(sg, context=h.owner, **caps, caps={"nudge": 1})
    due = max(as_utc(first.send_after), as_utc(second.send_after)) + timedelta(minutes=1)
    rows = {
        row.why["nudge_id"]: row for row in _rows(await _run(sg, h, clock, due), TriggerType.NUDGE)
    }
    sent, held = rows[str(first.id)], rows[str(second.id)]
    assert sent.outcome is DeliveryOutcome.SENT and sent.rule == "nudge_handed_over"
    assert sent.template_name == "nudge" and sent.why["kind"] == first.kind.value
    assert held.outcome is DeliveryOutcome.CAPPED
    assert _rows(await _run(sg, h, clock, due + timedelta(minutes=5)), TriggerType.NUDGE) == []
    # The planner hands over no more that day, by the same number.
    assert (await plan_nudges(sg, context=h.owner, registry=REGISTRY)).drafts == ()


async def test_he_is_spoken_to_in_the_language_his_settings_say(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """One settings read for how to reach him (`reach_of`): his settings say Malay and
    breakfast at 07:30 while his profile still says English. The morning card is in Malay at
    07:30, and #132's capture lines ask the same read."""
    from app.channels.api.capture import capture_language
    from app.identity.models import Profile
    from app.onboarding.settings import his_language

    clock.set(at(6))
    h = await home(sg, tmp_path)
    await save_settings(
        sg, context=h.owner, values=SettingsValues(language="ms", breakfast_time=time(7, 30))
    )
    profile = await sg.get(Profile, h.owner.profile_id)
    assert profile is not None
    profile.language = "en"
    await sg.flush()
    assert await his_language(sg, context=h.owner) == "ms"
    assert await capture_language(sg, h.owner) == "ms"
    assert await breakfast_time(sg, context=h.owner) == time(7, 30)
    [card] = _rows(await _run(sg, h, clock, at(7, 31)), TriggerType.MORNING)
    assert card.outcome is DeliveryOutcome.SENT
    [sent] = [one for one in h.whatsapp.sent if one.template_name == "morning_card"]
    assert sent.language == "ms"


async def test_a_nudge_he_answered_in_the_app_is_not_sent_again(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """W7: the web shows the day's nudge and he answers it there. Delivery then does not send
    him the same nudge: the row says it was skipped, answered in the app."""
    from app.db import as_utc
    from app.delivery.nudges.engine import hand_over, respond
    from app.delivery.nudges.models import ResponseKind
    from tests.feelings_support import REGISTRY

    clock.set(at(9))
    h = await home(sg, tmp_path)
    _, nudge = await hand_over(sg, context=h.owner, registry=REGISTRY)
    await respond(sg, context=h.owner, nudge_id=nudge.id, kind=ResponseKind.DISMISSED)
    due = as_utc(nudge.send_after) + timedelta(minutes=1)
    [row] = _rows(await _run(sg, h, clock, due), TriggerType.NUDGE)
    assert row.outcome is DeliveryOutcome.SKIPPED and row.reason == "answered in the app"
    assert [one for one in h.whatsapp.sent if one.template_name == "nudge"] == []
    assert _rows(await _run(sg, h, clock, due + timedelta(minutes=5)), TriggerType.NUDGE) == []
