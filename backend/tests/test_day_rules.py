"""The two rules that close his day (E11-01, E19-03): the check-in and the family notice.

Their properties one at a time, on the frozen clock over `run_due` and the fixtures: the
check-in at his check-in time from his settings, else at ten as the nudge planner has it; each
once a day, never late, never in the quiet hours; by the recipient's own channels; neither on
a day with an open red flag; the check-in not asked twice in a day (he already said how he
is, or the day's nudge asked it); the notice a count of only what the chief's key opens, and
only on a day something was written down.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.db import as_utc
from app.delivery.triggers.day import A_FLAG_IS_OPEN, HE_SAID_TODAY, THE_NUDGE_ASKED
from app.delivery.triggers.deliver import Firing, Recipient, open_run, write
from app.delivery.triggers.engine import Report, run_due
from app.delivery.triggers.ladder import PATIENT
from app.delivery.triggers.models import Delivery, DeliveryChannel, DeliveryOutcome, TriggerType
from app.delivery.triggers.preferences import change
from app.identity.service import register_person
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope, scope_for_subject
from app.memory.semantic import current_facts
from app.regions import Region
from tests.delivery_support import KIT, MEI, PA, Home, home
from tests.feelings_support import check_in_setting
from tests.support import agree_to_family_sharing

SGT = ZoneInfo("Asia/Singapore")
CHECK_IN = TriggerType.CHECK_IN
NOTICE = TriggerType.FAMILY_NOTICE
ASKED = "How are you feeling today?"


def at(hour: int, minute: int = 0, day: int = 14) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=SGT).astimezone(UTC)


async def _run(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime) -> Report:
    clock.set(when)
    return await run_due(sg, via=h.via, profile_id=h.owner.profile_id, at=when)


def _rows(report: Report, kind: TriggerType) -> list[Delivery]:
    return [sent.delivery for sent in report.sent if sent.delivery.trigger_type is kind]


def _asked(h: Home) -> list[str]:
    return [text for text in h.sent_to(h.pa) if ASKED in text]


def _notices(h: Home, phone: str) -> list[str]:
    return [one.text for one in h.whatsapp.sent if one.to_e164 == phone and one.text.startswith("Nura wrote down")]


async def _he_says(sg: AsyncSession, h: Home, clock: FrozenClock, when: datetime, text: str) -> None:
    clock.set(when)
    handled = await h.inbound(sg, PA, text)
    assert handled.outcome == "check_in_answer", handled


# --- the check-in ------------------------------------------------------------------------------


async def test_the_check_in_goes_at_his_check_in_time_from_his_settings_once_a_day(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await check_in_setting(sg, h.owner, "18:00")

    assert not _rows(await _run(sg, h, clock, at(17, 59)), CHECK_IN)
    [asked] = _rows(await _run(sg, h, clock, at(18)), CHECK_IN)
    assert asked.outcome is DeliveryOutcome.SENT and asked.to_person_id == h.pa.id
    assert asked.via is DeliveryChannel.WHATSAPP and asked.template_name == "feeling_check_in"
    assert asked.rule == "check_in_time_reached" and asked.why == {"check_in_at": "18:00"}
    assert h.sent_to(h.pa)[-1].splitlines() == [
        "Hello Pa, this is Nura.",
        ASKED,
        "Answer OK, tired or pain.",
    ]
    # Once a day: the runs after it that day write nothing more.
    assert not _rows(await _run(sg, h, clock, at(18, 5)), CHECK_IN)
    assert not _rows(await _run(sg, h, clock, at(20, 30)), CHECK_IN)
    assert len(_asked(h)) == 1
    # The next day, at the same time, again.
    [again] = _rows(await _run(sg, h, clock, at(18, 1, day=15)), CHECK_IN)
    assert again.outcome is DeliveryOutcome.SENT and again.day == "2026-09-15"


async def test_before_he_says_a_time_he_is_asked_at_ten_and_never_late(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    # Three hours after ten, a check-in that did not go is dropped, not sent late.
    assert not _rows(await _run(sg, h, clock, at(13, 1)), CHECK_IN)
    assert not _rows(await _run(sg, h, clock, at(9, 59, day=15)), CHECK_IN)
    [asked] = _rows(await _run(sg, h, clock, at(10, day=15)), CHECK_IN)
    assert asked.outcome is DeliveryOutcome.SENT and asked.why == {"check_in_at": "10:00"}


async def test_he_is_asked_once_a_day_not_again_after_he_said_or_the_nudge_asked(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await check_in_setting(sg, h.owner, "18:00")
    # He said how he is at noon, of his own accord: the evening does not ask again.
    await _he_says(sg, h, clock, at(12), "tired")
    [held] = _rows(await _run(sg, h, clock, at(18)), CHECK_IN)
    assert (held.outcome, held.reason) == (DeliveryOutcome.SKIPPED, HE_SAID_TODAY)
    assert not _rows(await _run(sg, h, clock, at(18, 30)), CHECK_IN)  # written once

    # The next day the day's smart nudge was the check-in (E17-03): it is not asked twice.
    clock.set(at(17, day=15))
    run = await open_run(sg, via=h.via, profile_id=h.owner.profile_id, at=at(17, day=15))
    await write(
        run,
        Firing(type=TriggerType.NUDGE, dedupe_key="nudge:check-in", why={"kind": "check_in"}),
        Recipient(h.pa, PATIENT),
        DeliveryOutcome.SENT,
        via=DeliveryChannel.WHATSAPP,
    )
    [held] = _rows(await _run(sg, h, clock, at(18, day=15)), CHECK_IN)
    assert (held.outcome, held.reason) == (DeliveryOutcome.SKIPPED, THE_NUDGE_ASKED)
    assert _asked(h) == []


async def test_the_quiet_hours_hold_the_check_in_and_the_hold_is_written_once(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await check_in_setting(sg, h.owner, "18:00")
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=time(17),
        quiet_until=time(7),
        channels={},
        caps={},
    )
    [held] = _rows(await _run(sg, h, clock, at(18)), CHECK_IN)
    assert (held.outcome, held.reason) == (DeliveryOutcome.QUIET, "quiet hours")
    assert not _rows(await _run(sg, h, clock, at(19)), CHECK_IN)
    assert _asked(h) == []


# --- the family notice ---------------------------------------------------------------------------


async def test_the_notice_goes_to_each_chief_in_the_evening_by_her_own_channels_once(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    h.push.register(h.mei.id)  # Mei has the app on her phone
    await _he_says(sg, h, clock, at(12), "tired")

    assert not _rows(await _run(sg, h, clock, at(19, 59)), NOTICE)
    [notice] = _rows(await _run(sg, h, clock, at(20)), NOTICE)
    # Her own list: the app first, where she has a device; nothing said in the push.
    assert (notice.to_person_id, notice.standing) == (h.mei.id, "chief")
    assert (notice.outcome, notice.via, notice.rule) == (
        DeliveryOutcome.SENT,
        DeliveryChannel.APP_PUSH,
        "evening_family_notice",
    )
    # (Her phone also hears the breakfast tablet's ladder, which nobody answered here.)
    [pushed] = [one for one in h.push.sent if one.ref == str(notice.id)]
    assert pushed.person_id == h.mei.id and "tired" not in pushed.text
    assert not _rows(await _run(sg, h, clock, at(20, 30)), NOTICE)
    # Not to him, and not to the helper: the notice is a chief's.
    assert not [row for row in _rows(await _run(sg, h, clock, at(21)), NOTICE)]
    assert not any(text.startswith("Nura wrote down") for text in h.sent_to(h.siti))

    # The next day the family asked for WhatsApp for the notice: her list, not the type's.
    await change(
        sg,
        context=h.owner,
        skip_quiet_days=False,
        quiet_from=None,
        quiet_until=None,
        channels={"family_notice": ["whatsapp"]},
        caps={},
    )
    await _he_says(sg, h, clock, at(12, day=15), "tired")
    [notice] = _rows(await _run(sg, h, clock, at(20, day=15)), NOTICE)
    assert (notice.outcome, notice.via, notice.template_name) == (
        DeliveryOutcome.SENT,
        DeliveryChannel.WHATSAPP,
        "family_digest",
    )
    assert len(_notices(h, MEI)) == 1


async def test_the_notice_counts_only_what_her_key_opens(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    # Kit, a son, a chief over the family list and the readings only.
    kit = await register_person(
        sg, region=Region.SG, display_name="Kit", phone_e164=KIT, language="en"
    )
    narrow = frozenset({Scope.FAMILY, Scope.READINGS})
    await agree_to_family_sharing(sg, h.owner, kit, scopes=narrow, relationship="son")
    await grant_key(sg, context=h.owner, holder=kit, role=KeyRole.CHIEF, scopes=narrow)
    # Today: a feeling of his (the record) and a blood pressure Mei sent and confirmed.
    await _he_says(sg, h, clock, at(12), "tired")
    clock.set(at(12, 5))
    assert (await h.inbound(sg, MEI, "BP 150/90 this morning")).outcome == "proposal"
    assert (await h.inbound(sg, MEI, "yes")).outcome == "confirmed"

    clock.set(at(20))
    week = [
        fact
        for fact in await current_facts(sg, context=h.owner)
        if as_utc(fact.asserted_at) > at(20) - timedelta(days=7)
    ]
    kits = [fact for fact in week if scope_for_subject(fact.subject) in narrow]
    assert 0 < len(kits) < len(week)

    sent = {row.to_person_id: row for row in _rows(await _run(sg, h, clock, at(20)), NOTICE)}
    assert set(sent) == {h.mei.id, kit.id}
    assert sent[kit.id].why == {"count": len(kits), "days": 7}
    assert sent[h.mei.id].why == {"count": len(week), "days": 7}
    assert _notices(h, KIT) == [
        f"Nura wrote down {len(kits)} things about Pa this week.\nYou can read them in the app."
    ]
    assert _notices(h, MEI) == [
        f"Nura wrote down {len(week)} things about Pa this week.\nYou can read them in the app."
    ]


async def test_no_notice_on_a_day_nothing_was_written_down(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await _he_says(sg, h, clock, at(12), "tired")
    assert _rows(await _run(sg, h, clock, at(20)), NOTICE)
    # Tuesday: nothing new, so nothing to tell her; the week's count is not said again.
    assert not _rows(await _run(sg, h, clock, at(20, day=15)), NOTICE)
    assert len(_notices(h, MEI)) == 1


# --- a red flag ------------------------------------------------------------------------------


async def test_neither_goes_on_a_day_with_an_open_red_flag(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    await check_in_setting(sg, h.owner, "18:00")
    clock.set(at(12))
    await h.inbound(sg, MEI, "he fell in the bathroom")

    [held] = _rows(await _run(sg, h, clock, at(18)), CHECK_IN)
    assert (held.outcome, held.reason) == (DeliveryOutcome.SKIPPED, A_FLAG_IS_OPEN)
    assert not _rows(await _run(sg, h, clock, at(18, 30)), CHECK_IN)  # written once
    notices = _rows(await _run(sg, h, clock, at(20)), NOTICE)
    assert [(row.to_person_id, row.outcome, row.reason) for row in notices] == [
        (h.mei.id, DeliveryOutcome.SKIPPED, A_FLAG_IS_OPEN)
    ]
    assert _asked(h) == [] and _notices(h, MEI) == []

    # The next evening the flag is out of its day: he is asked again.
    [asked] = _rows(await _run(sg, h, clock, at(18, day=15)), CHECK_IN)
    assert asked.outcome is DeliveryOutcome.SENT
