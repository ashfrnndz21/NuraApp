"""Templates wait for Meta (E11, the review of #121): outside a dev run a pending template is
refused on the trail (`TemplateNotApproved`) and a delivery tries its next channel; a red flag
never waits on it — the approved notice goes when a variant is still pending."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.audit.trail import read_audit
from app.channels.whatsapp.config import business_number_for
from app.channels.whatsapp.outbound.send import TemplateNotApproved, send
from app.clock import FrozenClock
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.engine import run_due
from app.delivery.triggers.ladder import escalate_flag
from app.delivery.triggers.models import DeliveryOutcome, TriggerType
from app.memory.models import SourceChannel
from app.regions import Region
from app.safety.red_flags import Feeling, raise_flag, record_the_moment
from app.settings import Settings
from app.state.service import current_state
from tests.delivery_support import home
from tests.support import refused_unit
from tests.whatsapp_support import MEI, family

SGT = ZoneInfo("Asia/Singapore")
LIVE = business_number_for(Settings(region=Region.SG, database_url="sqlite://", dev_code_sender=False))
"""A deployment's number: E19's six approved, E11's nine pending."""


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 14, hour, minute, tzinfo=SGT).astimezone(UTC)


async def test_a_pending_template_is_refused_outside_a_dev_run_and_written_down(
    sg: AsyncSession, tmp_path: Path
) -> None:
    fam = await family(sg, tmp_path)
    state = await current_state(sg, context=fam.owner)
    async with refused_unit(sg, TemplateNotApproved):
        await send(
            sg,
            context=fam.owner,
            to_person=fam.pa,
            kind="dose_reminder",
            params={"name": "Pa", "medicine": "your blood pressure tablet", "anchor": "with breakfast"},
            provider=fam.providers.whatsapp,
            number=LIVE,
            state=state,
        )
    assert fam.whatsapp.sent == []
    trail = await read_audit(sg, context=fam.owner)
    assert any(
        entry.action is Action.SHARE and entry.refused_because == "TemplateNotApproved"
        for entry in trail
    )


async def test_the_ladder_tries_its_next_channel_when_a_template_is_pending(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path)
    live = Via(settings=h.via.settings, providers=h.via.providers, number=LIVE)
    clock.set(at(8, 31))
    report = await run_due(sg, via=live, profile_id=h.owner.profile_id, at=at(8, 31))
    [rung] = [s.delivery for s in report.sent if s.delivery.trigger_type is TriggerType.DOSE]
    assert rung.outcome is DeliveryOutcome.NO_CHANNEL
    assert rung.passed_over == [
        "app_push: no device",
        "whatsapp: TemplateNotApproved",
        "caregiver: TemplateNotApproved",
    ]


async def test_his_own_flag_says_his_name_where_approved_and_never_waits_on_meta(
    sg: AsyncSession, tmp_path: Path
) -> None:
    for number, second in ((None, "Pa is not feeling well."), (LIVE, "Pa said Pa is not well.")):
        fam = await family(sg, tmp_path / (number.phone_e164 if number else "dev"))
        said = await record_the_moment(
            sg,
            context=fam.owner,
            feeling=Feeling.FALL,
            occurred_at=datetime.now(UTC),
            source_channel=SourceChannel.APP,
        )
        flag = await raise_flag(sg, context=fam.owner, feeling=Feeling.FALL, event_id=said.id)
        via = Via(settings=fam.settings, providers=fam.providers, number=number or fam.number)
        escalated = await escalate_flag(sg, fam.owner, flag, via=via)
        assert escalated.told == (fam.mei.id,)
        assert fam.whatsapp.sent[-1].to_e164 == MEI
        assert fam.whatsapp.sent[-1].text.splitlines()[1] == second
        await sg.rollback()
