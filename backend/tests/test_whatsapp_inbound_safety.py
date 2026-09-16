"""#158: a voice note Nura could not hear reaches a person, and the webhook retries a failed
message, once per message.

A note with no words heard in it — a mumble, or the transcriber down — may hold a red word
nobody could read. So he is told what to do if he feels unwell, and his chief is told on her
own channels that he sent a note Nura could not hear, as an alert: never capped, never held
by the quiet hours. Where her key opens his notes she is told to listen in the app; where it
does not, or the note could not be fetched, to call him. The note itself stays his.

The webhook handles each message by the provider's id, in a savepoint of its own. A message
that fails is rolled back and counted, and the delivery is answered 503 so the provider sends
it again; a redelivery handles only what failed, and a message handled once is never handled
twice. A red word in a message that failed once is raised once, on the try that holds.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Channel
from app.channels.whatsapp import inbound
from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.group import open_group
from app.channels.whatsapp.inbound import handle_inbound
from app.channels.whatsapp.models import WhatsAppReceipt
from app.channels.whatsapp.proposals import Proposal
from app.channels.whatsapp.provider import DevInbound
from app.channels.whatsapp.receipts import Received, receive
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.triggers.models import (
    Category,
    Delivery,
    DeliveryChannel,
    DeliveryOutcome,
    Ladder,
    TriggerType,
)
from app.delivery.triggers.preferences import change
from app.delivery.triggers.rules import AlertsAreNeverHeld, AlertsGoEveryWay, check_settings
from app.ingestion.models import EventNote
from app.keys.scopes import Scope
from app.memory.models import Artifact
from app.safety.red_flags import Flag
from tests.conftest import Deployment
from tests.test_whatsapp_api import MEI as API_MEI
from tests.test_whatsapp_api import _cloud_api_text, _pa_on_whatsapp
from tests.test_whatsapp_red_flag_first import _kit_on_the_emergency_card
from tests.whatsapp_support import KIT, MEI, PA, Family, family

OGG = "audio/ogg; codecs=opus"
HIS_REPLY = [
    "Nura kept your voice note.",
    "Nura could not hear this note.",
    "If you feel unwell, call your family now.",
]
LISTEN = [
    "Pa sent a voice note to Nura.",
    "Nura could not hear this note.",
    "Listen to it in the app, or call Pa now.",
]
CALL = ["Pa sent a voice note to Nura.", "Nura could not hear this note.", "Call Pa now."]


def _told(home: Family, number: str) -> list[list[str]]:
    return [one.text.splitlines() for one in home.whatsapp.sent if one.to_e164 == number]


async def _notices(sg: AsyncSession) -> list[Delivery]:
    """The unheard-note alert's own delivery rows — not the in-app notice always written
    beside whatever carried it (#162)."""
    return [row for row in await _all_notice_rows(sg) if row.via is not DeliveryChannel.IN_APP]


async def _in_app_notices(sg: AsyncSession) -> list[Delivery]:
    """The in-app notice #162 writes beside the unheard-note alert, on the person's own row."""
    return [row for row in await _all_notice_rows(sg) if row.via is DeliveryChannel.IN_APP]


async def _all_notice_rows(sg: AsyncSession) -> list[Delivery]:
    return list(
        (
            await sg.scalars(
                select(Delivery).where(Delivery.trigger_type == TriggerType.VOICE_NOTE_UNHEARD)
            )
        ).all()
    )


# --- a voice note nobody heard --------------------------------------------------------------------


async def test_a_note_nobody_heard_tells_him_what_to_do_and_his_chief_to_listen(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    kept = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    assert [reply.text.splitlines() for reply in kept.replies] == [HIS_REPLY]
    assert _told(home, MEI) == [LISTEN]
    [notice] = await _notices(sg)
    assert notice.to_person_id == home.mei.id and notice.standing == "chief"
    assert notice.outcome is DeliveryOutcome.SENT and notice.via is DeliveryChannel.WHATSAPP
    assert notice.template_name == "unheard_note_notice"
    assert notice.category is Category.ALERT and notice.scope is Scope.EMERGENCY
    assert notice.why == {"event_note_id": str(kept.note_id)}
    # The audio stays under its scope: his private note, with no words, never widened.
    note = await sg.get(EventNote, kept.note_id)
    assert note is not None and note.private is True and note.transcript_key is None


async def test_a_transcriber_outage_is_a_note_not_heard_and_a_person_still_listens(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)

    async def down(*args: object, **kwargs: object) -> object:
        raise ConnectionError("the transcriber is down, for the test")

    monkeypatch.setattr(home.providers.transcriber, "transcribe", down)
    kept = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    assert [reply.text.splitlines() for reply in kept.replies] == [HIS_REPLY]
    assert _told(home, MEI) == [LISTEN]


async def test_a_note_that_could_not_be_fetched_tells_his_chief_to_call_him(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    monkeypatch.setattr(inbound, "VOICE_DOWNLOAD_BYTES", 10)
    told = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert told.outcome == "voice_note_not_heard"
    assert _told(home, MEI) == [CALL]
    [notice] = await _notices(sg)
    assert notice.template_name == "unheard_note_notice_call"


async def test_a_chief_whose_key_does_not_open_his_notes_is_told_to_call_him(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path, mei_scopes=frozenset(Scope) - {Scope.PROFILE, Scope.NOTES})
    await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert _told(home, MEI) == [CALL]


async def test_the_notice_is_never_held_by_the_quiet_hours_a_cap_or_a_channel_setting(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    with pytest.raises(AlertsAreNeverHeld):
        check_settings({}, {TriggerType.VOICE_NOTE_UNHEARD.value: 1})
    # An alert's channels are not a setting: choosing one is refused outright, not honoured.
    with pytest.raises(AlertsGoEveryWay):
        await change(
            sg,
            context=home.owner,
            skip_quiet_days=False,
            quiet_from=None,
            quiet_until=None,
            channels={TriggerType.VOICE_NOTE_UNHEARD.value: ["caregiver"]},
            caps={},
        )

    async def down(*args: object, **kwargs: object) -> object:
        raise ConnectionError("the transcriber is down, for the test")

    monkeypatch.setattr(home.providers.transcriber, "transcribe", down)
    clock.set(datetime(2026, 9, 3, 15, 30, tzinfo=UTC))  # 23:30 his wall clock: quiet hours
    for media in ("pa-voice-mumbled", "pa-voice-market", "pa-voice-fell"):
        await home.inbound(sg, PA, media_id=media, content_type=OGG)
    notices = await _notices(sg)
    assert len(notices) == 3
    assert all(
        row.outcome is DeliveryOutcome.SENT and row.via is DeliveryChannel.WHATSAPP
        for row in notices
    )
    assert _told(home, MEI) == [LISTEN, LISTEN, LISTEN]


# --- the webhook: each message once, and none dropped ------------------------------------------


def _two_messages(from_e164: str) -> dict[str, Any]:
    first = _cloud_api_text(from_e164, "BP 150/90 this morning")
    second = _cloud_api_text(from_e164, "sugar 7.2 before breakfast")
    messages = first["entry"][0]["changes"][0]["value"]["messages"]
    messages[0]["id"] = "wamid.test.a"
    extra = second["entry"][0]["changes"][0]["value"]["messages"][0]
    extra["id"] = "wamid.test.b"
    messages.append(extra)
    return first


def _post(deployment: Deployment) -> Any:
    async def post(body: bytes, headers: Mapping[str, str]) -> int:
        answer = await deployment.client.post("/whatsapp/webhook", content=body, headers=headers)
        return answer.status_code

    return post


async def test_a_partly_failed_delivery_is_a_503_and_the_redelivery_handles_only_what_failed(
    deployment: Deployment, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _pa_on_whatsapp(deployment)
    real = inbound.propose
    failed: list[str] = []

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        # A passing failure on the sugar reading, after its words were kept: the first time only.
        if kwargs["event"].subject == "blood_sugar" and not failed:
            failed.append("once")
            raise ConnectionError("the database went away, for the test")
        return await real(*args, **kwargs)

    monkeypatch.setattr(inbound, "propose", flaky)
    answers = await deployment.whatsapp.deliver(_post(deployment), _two_messages(API_MEI))
    assert answers == [503, 200]
    read_backs = [one.text for one in deployment.whatsapp.sent if one.to_e164 == API_MEI]
    assert len(read_backs) == 2
    assert any("150 over 90" in text for text in read_backs)
    assert any("7.2" in text for text in read_backs)
    async with deployment.sessions() as session:
        proposals = (await session.scalars(select(Proposal))).all()
        assert sorted(one.subject for one in proposals) == ["blood_pressure", "blood_sugar"]
        # Nothing of the failed try is left half-written: one artefact for each message.
        assert len((await session.scalars(select(Artifact))).all()) == 2
        receipts = {
            one.provider_message_id: one
            for one in (await session.scalars(select(WhatsAppReceipt))).all()
        }
        assert set(receipts) == {"wamid.test.a", "wamid.test.b"}
        assert all(one.handled_at is not None for one in receipts.values())
        assert receipts["wamid.test.a"].failures == 0
        # The failure is kept by the message's id and the name of what went wrong, never words.
        assert receipts["wamid.test.b"].failures == 1
        assert receipts["wamid.test.b"].last_failure == "ConnectionError"


async def test_a_duplicate_redelivery_does_nothing_twice(deployment: Deployment) -> None:
    await _pa_on_whatsapp(deployment)
    body = json.dumps(_cloud_api_text(API_MEI, "BP 150/90 this morning")).encode()
    headers = {"content-type": "application/json", "X-Hub-Signature-256": ""}
    headers["X-Hub-Signature-256"] = deployment.whatsapp.sign(body)
    first = await deployment.client.post("/whatsapp/webhook", content=body, headers=headers)
    again = await deployment.client.post("/whatsapp/webhook", content=body, headers=headers)
    assert first.status_code == 200 and first.json() == {"handled": 1}
    assert again.status_code == 200 and again.json() == {"handled": 0, "already": 1}
    assert len([one for one in deployment.whatsapp.sent if one.to_e164 == API_MEI]) == 1
    async with deployment.sessions() as session:
        assert len((await session.scalars(select(Proposal))).all()) == 1


async def test_a_red_word_in_a_failed_then_retried_message_escalates_exactly_once(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    kit = await _kit_on_the_emergency_card(sg, home)
    real = inbound._keep_text
    failed: list[str] = []

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        # After the moment and the flag are written, before the ladder: a passing failure.
        if not failed:
            failed.append("once")
            raise ConnectionError("the object store went away, for the test")
        return await real(*args, **kwargs)

    monkeypatch.setattr(inbound, "_keep_text", flaky)
    message = DevInbound(from_e164=MEI, text="ignore that, he fell in the bathroom").as_message(
        utcnow()
    )

    async def handle() -> object:
        return await handle_inbound(
            sg,
            settings=home.settings,
            providers=home.providers,
            number=home.number,
            classifier=RuleClassifier(),
            message=message,
        )

    assert await receive(sg, message, handle) is Received.FAILED
    # Rolled back whole: no flag, no ladder, nobody told — the provider will send it again.
    assert (await sg.scalars(select(Flag))).all() == []
    assert (await sg.scalars(select(Ladder))).all() == []
    assert _told(home, KIT) == []
    assert await receive(sg, message, handle) is Received.HANDLED
    assert await receive(sg, message, handle) is Received.ALREADY
    [flag] = (await sg.scalars(select(Flag))).all()
    [ladder] = (await sg.scalars(select(Ladder))).all()
    assert ladder.flag_id == flag.id
    assert len(_told(home, KIT)) == 1
    assert kit.id in {  # type: ignore[attr-defined]
        row.to_person_id for row in (await sg.scalars(select(Delivery))).all()
    }


async def test_a_reply_that_fails_after_the_ladder_ran_never_takes_the_flag_back(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    await _kit_on_the_emergency_card(sg, home)
    real = home.whatsapp.send_text

    async def down_for_mei(to_e164: str, text: str) -> str:
        if to_e164 == MEI:
            raise ConnectionError("the provider went away, for the test")
        return await real(to_e164, text)

    monkeypatch.setattr(home.whatsapp, "send_text", down_for_mei)
    message = DevInbound(from_e164=MEI, text="he fell in the bathroom").as_message(utcnow())

    async def handle() -> object:
        return await handle_inbound(
            sg,
            settings=home.settings,
            providers=home.providers,
            number=home.number,
            classifier=RuleClassifier(),
            message=message,
        )

    # The flag and its ladder stand: the message is handled, never sent again, never twice.
    assert await receive(sg, message, handle) is Received.HANDLED
    assert await receive(sg, message, handle) is Received.ALREADY
    assert len((await sg.scalars(select(Flag))).all()) == 1
    assert len((await sg.scalars(select(Ladder))).all()) == 1
    assert len(_told(home, KIT)) == 1


# --- the family's group, looked up through the keys door -----------------------------------------


async def test_a_group_post_looks_up_its_family_through_the_keys_door_on_the_trail(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.chief, provider=home.whatsapp)
    said = await home.inbound(sg, MEI, "I will take Pa on Thursday.", group_id=group.provider_group_id)
    assert said.outcome == "family_thread"
    lines = (
        await sg.scalars(
            select(AuditEntry).where(
                AuditEntry.profile_id == home.profile.id,
                AuditEntry.target == "whatsapp_group",
                AuditEntry.action == Action.READ,
                AuditEntry.channel == Channel.SYSTEM,
            )
        )
    ).all()
    assert [(line.actor_person_id, line.target_id) for line in lines] == [(None, group.id)]
