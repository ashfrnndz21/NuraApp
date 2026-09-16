"""E12-06: the push composer with preview and scheduling.

    Chief sees exactly what Dad will see; sends at a State-appropriate time.

The preview is the lines in his language through the verifier; a memo in red words is
refused with the findings; the yes binds to the lines; the scheduled row names its State;
nothing is sent here.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.drugs.fixture import FixtureRegistry
from app.family.common import NotAChief, NotPlainWords
from app.family.models import PushChannel
from app.family.pushes import (
    BadWindow,
    MessageNamesAMedicine,
    MissingSlot,
    NoSuchTemplate,
    preview_push,
    push_draft,
    pushes,
    schedule_push,
)
from app.family.strings import PUSH_TEMPLATES, TEMPLATE_SLOTS
from app.keys.confirm import NotWhatWasConfirmed, confirm
from app.state.service import current_state
from tests.family_support import MONDAY, household


async def test_the_preview_is_exactly_what_pa_will_see_in_his_language(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg, language="ms")
    mei = await h.ctx(sg, h.mei)
    preview = await preview_push(
        sg, context=mei, template_id="pickup", slots={"who": "Mei", "when": "pukul 9"}
    )
    assert preview.language == "ms"
    assert preview.lines == ["Mei akan ambil anda pada pukul 9.", "Bawa buku tekanan darah anda."]
    assert preview.notes == []
    english = await preview_push(
        sg,
        context=mei,
        template_id="pickup",
        slots={"who": "Mei", "when": "9 in the morning"},
        language="en",
    )
    assert english.lines == [
        "Mei will pick you up at 9 in the morning.",
        "Bring your blood pressure book.",
    ]
    with pytest.raises(MissingSlot):
        await preview_push(sg, context=mei, template_id="pickup", slots={"who": "Mei"})
    with pytest.raises(NoSuchTemplate):
        await preview_push(sg, context=mei, template_id="stop_the_water_pill", slots={})
    assert set(TEMPLATE_SLOTS) == set(PUSH_TEMPLATES["en"]) == set(PUSH_TEMPLATES["ms"])
    assert set(PUSH_TEMPLATES["zh"]) == set(PUSH_TEMPLATES["en"])


async def test_a_memo_in_red_words_is_refused_with_the_findings(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    with pytest.raises(NotPlainWords) as refused:
        await preview_push(
            sg, context=mei, memo_lines=["You missed your walk again.", "Recheck on the 29th."]
        )
    assert any("rule 11" in f for f in refused.value.findings)
    assert any("rule 12" in f for f in refused.value.findings)
    fine = await preview_push(
        sg, context=mei, memo_lines=["Mei will call you at 6.", "It is not a worry."]
    )
    assert fine.lines == ["Mei will call you at 6.", "It is not a worry."]
    kit = await h.ctx(sg, h.kit)
    with pytest.raises(NotAChief):
        await preview_push(sg, context=kit, template_id="drink_water", slots={})
    pa = await h.ctx(sg, h.pa)
    names = {
        e.refused_because for e in await read_audit(sg, context=pa) if e.outcome is Outcome.REFUSED
    }
    assert {"NotPlainWords", "NotAChief"} <= names


async def test_a_message_to_him_names_no_medicine_and_no_dose(
    sg: AsyncSession, clock: FrozenClock, tmp_path: Path
) -> None:
    """#164: his medicine reminders come only from his confirmed list. No template names a
    medicine, and a memo or a slot that names one — or a dose — is refused, the way a note
    about a clinic that names one is (E03-03), before anything is kept."""
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    registry = FixtureRegistry.load()
    assert "water_pill_morning" not in TEMPLATE_SLOTS
    for words in PUSH_TEMPLATES.values():
        assert "water_pill_morning" not in words
    refused = [
        {"memo_lines": ["Nura says the water pill is at 8.", "Take it with breakfast."]},
        {"memo_lines": ["Take your amlodipine now."]},
        {"memo_lines": ["Makan 2 biji selepas sarapan."]},
        {"memo_lines": ["早餐后吃两片药。"]},
        {"memo_lines": ["Bring your Lipitor."]},
        {"template_id": "call_you", "slots": {"who": "Mei", "when": "after your 5 mg"}},
    ]
    for asked in refused:
        with pytest.raises(MessageNamesAMedicine):
            await preview_push(sg, context=mei, registry=registry, **asked)  # type: ignore[arg-type]
    fine = await preview_push(
        sg, context=mei, registry=registry, memo_lines=["Mei will call you at 6."]
    )
    assert fine.lines == ["Mei will call you at 6."]
    pa = await h.ctx(sg, h.pa)
    names = {
        e.refused_because for e in await read_audit(sg, context=pa) if e.outcome is Outcome.REFUSED
    }
    assert "MessageNamesAMedicine" in names


async def test_the_yes_binds_to_the_lines_and_the_row_names_its_state(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg, language="ms")
    mei = await h.ctx(sg, h.mei)
    send_at, expires_at = MONDAY + timedelta(hours=8), MONDAY + timedelta(hours=12)

    preview = await preview_push(
        sg, context=mei, template_id="pickup", slots={"who": "Mei", "when": "pukul 9"}
    )
    yes = await confirm(
        sg,
        mei,
        push_draft(preview, send_at=send_at, channel=PushChannel.WHATSAPP, expires_at=expires_at),
    )
    # The same yes offered for other lines, or another moment, is refused.
    with pytest.raises(NotWhatWasConfirmed):
        await schedule_push(
            sg,
            context=mei,
            send_at=send_at,
            channel=PushChannel.WHATSAPP,
            expires_at=expires_at,
            confirmation_id=yes.id,
            template_id="pickup",
            slots={"who": "Mei", "when": "pukul 10"},
        )
    with pytest.raises(NotWhatWasConfirmed):
        await schedule_push(
            sg,
            context=mei,
            send_at=send_at + timedelta(hours=1),
            channel=PushChannel.WHATSAPP,
            expires_at=expires_at,
            confirmation_id=yes.id,
            template_id="pickup",
            slots={"who": "Mei", "when": "pukul 9"},
        )
    scheduled = await schedule_push(
        sg,
        context=mei,
        send_at=send_at,
        channel=PushChannel.WHATSAPP,
        expires_at=expires_at,
        confirmation_id=yes.id,
        template_id="pickup",
        slots={"who": "Mei", "when": "pukul 9"},
    )
    assert scheduled.lines == preview.lines and scheduled.language == "ms"
    assert scheduled.via_channel is PushChannel.WHATSAPP
    assert scheduled.state_id == (await current_state(sg, context=mei)).id
    assert scheduled.composed_by_person_id == h.mei.id
    assert [p.id for p in await pushes(sg, context=mei)] == [scheduled.id]

    with pytest.raises(BadWindow):
        await schedule_push(
            sg,
            context=mei,
            send_at=send_at,
            channel=PushChannel.APP,
            expires_at=send_at,
            confirmation_id=yes.id,
            template_id="drink_water",
        )
