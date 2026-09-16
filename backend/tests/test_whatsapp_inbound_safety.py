"""#158 and #173: a voice note Nura could not hear reaches a person, whoever sent it; a
channel that failed falls through to the next; and the webhook retries a failed message,
once per message.

A note with no words heard in it — a mumble, or the transcriber down — may hold a red word
nobody could read. So the sender is told, and the chief is told on her own channels, as an
alert: never capped, never held by the quiet hours, and climbing a ladder if nobody says they
have it. Where her key opens his notes she is told to listen in the app; where it does not,
or the note could not be fetched, to call him. The note itself stays his.

That holds for anyone who holds a key, not only for him (#173). The helper's note is not
kept — it may carry other people's voices — and the notice names who actually sent it, never
saying it was his; his line, what to do if he feels unwell, is said to him alone. On a
profile whose patient has not agreed to WhatsApp nothing of the note is kept and the sender
gets one fixed line, and his family is still told, through the app.

A WhatsApp send that fails with a network error falls through to the app push, and for an
alert the notice on the family page is written whatever carried it.

The webhook handles each message by the provider's id, in a savepoint of its own, and claims
its receipt row before the handler runs, so two copies of one delivery at the same instant
are one handling and the second is a clean duplicate. A message that fails is rolled back and
counted, and the delivery is answered 503 so the provider sends it again; a redelivery
handles only what failed, and a message handled once is never handled twice. A red word in a
message that failed once is raised once, on the try that holds.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Channel
from app.channels.whatsapp import inbound, receipts
from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.group import open_group
from app.channels.whatsapp.inbound import Handled, handle_inbound
from app.channels.whatsapp.models import WhatsAppReceipt
from app.channels.whatsapp.proposals import Proposal
from app.channels.whatsapp.provider import DevInbound
from app.channels.whatsapp.receipts import Received, receive
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.push import FixturePush
from app.delivery.triggers import ladder as ladder_module
from app.delivery.triggers.deliver import Via
from app.delivery.triggers.engine import run_due
from app.delivery.triggers.ladder import NotOnTheLadder, acknowledge_flag
from app.delivery.triggers.models import (
    Category,
    Delivery,
    DeliveryChannel,
    DeliveryOutcome,
    Ladder,
    Subject,
    TriggerType,
)
from app.delivery.triggers.preferences import change
from app.delivery.triggers.rules import AlertsAreNeverHeld, AlertsGoEveryWay, check_settings
from app.identity.models import Person
from app.identity.service import register_person
from app.ingestion.models import EventNote
from app.keys.grants import grant_key
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.memory.models import Artifact
from app.regions import Region
from app.safety.red_flags import Flag
from tests.conftest import Deployment
from tests.support import agree_to_family_sharing
from tests.test_whatsapp_api import MEI as API_MEI
from tests.test_whatsapp_api import _cloud_api_text, _pa_on_whatsapp
from tests.test_whatsapp_red_flag_first import _kit_on_the_emergency_card
from tests.whatsapp_support import KIT, MEI, PA, SITI, Family, family

OGG = "audio/ogg; codecs=opus"
HIS_REPLY = [
    "Nura kept your voice note.",
    "Nura could not hear this note.",
    "Mei knows now.",
    "If you feel unwell, call your family now.",
]
HIS_REPLY_ALONE = [
    "Nura kept your voice note.",
    "Nura could not hear this note.",
    "If you feel unwell, call your family now.",
]
NOT_FETCHED = [
    "Nura could not hear your voice note.",
    "Mei knows now.",
    "If you feel unwell, call your family now.",
]
HER_REPLY = [
    "Nura could not hear your voice note.",
    "Mei knows now.",
    "Please write what you said.",
]
FROM_SITI = [
    "Siti sent a voice note to Nura about Pa.",
    "Nura could not hear this note.",
    "Call Siti now.",
]
LISTEN = [
    "Pa sent a voice note to Nura.",
    "Nura could not hear this note.",
    "Listen to it in the app, or call Pa now.",
]
CALL = ["Pa sent a voice note to Nura.", "Nura could not hear this note.", "Call Pa now."]


def _told(home: Family, number: str) -> list[list[str]]:
    return [one.text.splitlines() for one in home.whatsapp.sent if one.to_e164 == number]


def _said(handled: Handled) -> list[list[str]]:
    return [reply.text.splitlines() for reply in handled.replies]


async def _every_notice(sg: AsyncSession) -> list[Delivery]:
    """Every row this trigger wrote, by any channel and none: nothing at all means this."""
    return list(
        (
            await sg.scalars(
                select(Delivery).where(Delivery.trigger_type == TriggerType.VOICE_NOTE_UNHEARD)
            )
        ).all()
    )


async def _notices(sg: AsyncSession) -> list[Delivery]:
    """What carried the notice to her phone. An alert also writes the notice on her family
    page beside whatever carried it (#162), which is not what these tests are about."""
    return [row for row in await _every_notice(sg) if row.via is not DeliveryChannel.IN_APP]


async def _page_notices(sg: AsyncSession) -> list[Delivery]:
    """The notice on her family page, written whatever carried it (#162)."""
    return [row for row in await _every_notice(sg) if row.via is DeliveryChannel.IN_APP]


async def _by_channel(sg: AsyncSession, channel: DeliveryChannel) -> list[Delivery]:
    return [row for row in await _every_notice(sg) if row.via is channel]


async def _siti_the_helper(sg: AsyncSession, home: Family) -> Person:
    """The domestic helper, with the emergency card and the medicines, as her key is set."""
    siti = await register_person(sg, region=Region.SG, display_name="Siti", phone_e164=SITI)
    scopes = ROLE_SCOPES[KeyRole.HELPER]
    await agree_to_family_sharing(sg, home.owner, siti, scopes=scopes, relationship="helper")
    await grant_key(sg, context=home.owner, holder=siti, role=KeyRole.HELPER, scopes=scopes)
    return siti


# --- a voice note nobody heard --------------------------------------------------------------------


async def test_a_note_nobody_heard_tells_him_what_to_do_and_his_chief_to_listen(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    kept = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    # His reply names who the notice actually reached, and only once it has gone (#173).
    assert _said(kept) == [HIS_REPLY]
    assert _told(home, MEI) == [LISTEN]
    [notice] = await _by_channel(sg, DeliveryChannel.WHATSAPP)
    assert notice.to_person_id == home.mei.id and notice.standing == "chief"
    assert notice.outcome is DeliveryOutcome.SENT
    assert notice.template_name == "unheard_note_notice"
    assert notice.category is Category.ALERT and notice.scope is Scope.EMERGENCY
    assert notice.why == {"ladder_id": ANY, "rung": 3, "action": ANY}
    # An alert is written on her family page too, whatever else carried it (#169).
    assert [row.outcome for row in await _by_channel(sg, DeliveryChannel.IN_APP)] == [
        DeliveryOutcome.SENT
    ]
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
    assert _said(kept) == [HIS_REPLY]
    assert _told(home, MEI) == [LISTEN]


async def test_a_note_that_could_not_be_fetched_tells_his_chief_to_call_him(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    monkeypatch.setattr(inbound, "VOICE_DOWNLOAD_BYTES", 10)
    told = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert told.outcome == "voice_note_not_heard"
    assert _said(told) == [NOT_FETCHED]
    assert _told(home, MEI) == [CALL]
    [notice] = await _by_channel(sg, DeliveryChannel.WHATSAPP)
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
    # A setting that would send it only to the caregiver is refused for an alert (#162), so
    # there is no way to leave this notice with nowhere to go.
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
    notices = await _by_channel(sg, DeliveryChannel.WHATSAPP)
    assert len(notices) == 3
    assert all(row.outcome is DeliveryOutcome.SENT for row in notices)
    assert _told(home, MEI) == [LISTEN, LISTEN, LISTEN]


# --- anyone's unheard note, and one on a profile with no WhatsApp agreement (#173) ---------------


async def test_the_helpers_unheard_note_tells_his_chief_and_never_says_his_line(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    await _siti_the_helper(sg, home)
    told = await home.inbound(sg, SITI, media_id="pa-voice-mumbled", content_type=OGG)
    assert told.outcome == "voice_note_not_heard"
    # Her note is not kept — it may carry other people's voices — and there is nothing to
    # listen to. The notice names who actually sent it: it is never said to be his.
    assert (await sg.scalars(select(EventNote))).all() == []
    assert _told(home, MEI) == [FROM_SITI]
    # What to do if *he* feels unwell is his line, and is said to nobody else.
    assert _said(told) == [HER_REPLY]
    [notice] = await _by_channel(sg, DeliveryChannel.WHATSAPP)
    assert notice.to_person_id == home.mei.id and notice.category is Category.ALERT
    assert notice.template_name == "unheard_note_notice_from"
    [ladder] = (await sg.scalars(select(Ladder))).all()
    assert ladder.note_id is None and ladder.note_from_person_id is not None


async def test_a_red_word_in_the_helpers_voice_note_is_still_read_first(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    await _siti_the_helper(sg, home)
    flagged = await home.inbound(sg, SITI, media_id="pa-voice-fell", content_type=OGG)
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None
    # A note whose words were heard is a flag, not an unheard note: nobody is told twice.
    assert await _every_notice(sg) == []


async def test_a_voice_note_in_the_familys_group_is_the_familys_and_pages_nobody(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.chief, provider=home.whatsapp)
    posted = await home.inbound(
        sg,
        MEI,
        media_id="pa-voice-mumbled",
        content_type=OGG,
        group_id=group.provider_group_id,
    )
    # The group is where the family talk to each other: a note nobody could hear there is
    # not kept and never an alert, the way a photo posted there is not one of his papers.
    assert posted.outcome == "ignored"
    assert await _every_notice(sg) == []
    assert (await sg.scalars(select(EventNote))).all() == []
    # A red word said in the group is still a flag, read before any of that.
    flagged = await home.inbound(
        sg, MEI, media_id="pa-voice-fell", content_type=OGG, group_id=group.provider_group_id
    )
    assert flagged.outcome == "red_flag"


async def test_a_group_note_without_his_whatsapp_agreement_pages_nobody_either(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # He stopped WhatsApp; the family group he opened before that is still there. A note
    # nobody could hear posted in it is still the family's, not an alert about him (#173).
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.chief, provider=home.whatsapp)

    async def stopped(*args: object, **kwargs: object) -> bool:
        return False

    monkeypatch.setattr(inbound, "_whatsapp_agreed", stopped)
    posted = await home.inbound(
        sg,
        MEI,
        media_id="pa-voice-mumbled",
        content_type=OGG,
        group_id=group.provider_group_id,
    )
    assert posted.outcome == "ignored"
    assert await _every_notice(sg) == []
    assert (await sg.scalars(select(Ladder))).all() == []


async def test_a_notice_that_cannot_say_who_sent_the_note_never_guesses_it_was_his(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    siti = await _siti_the_helper(sg, home)
    push = FixturePush()
    push.register(home.mei.id)
    object.__setattr__(home.providers, "push", push)
    real = ladder_module.Run.person

    async def missing(run: Any, person_id: Any) -> Any:
        # Her row has gone between the note arriving and the notice being written.
        return None if person_id == siti.id else await real(run, person_id)

    monkeypatch.setattr(ladder_module.Run, "person", missing)
    told = await home.inbound(sg, SITI, media_id="pa-voice-mumbled", content_type=OGG)
    assert told.outcome == "voice_note_not_heard"
    # Saying "Pa sent a voice note" would be a claim about him that is not true, so nothing
    # goes on WhatsApp; the push and the notice on her family page still do.
    assert _told(home, MEI) == []
    assert [one.person_id for one in push.sent] == [home.mei.id]
    assert [row.outcome for row in await _by_channel(sg, DeliveryChannel.IN_APP)] == [
        DeliveryOutcome.SENT
    ]


async def test_an_unheard_note_without_his_whatsapp_agreement_still_tells_a_person(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path, whatsapp_consent=False)
    push = FixturePush()
    push.register(home.mei.id)
    object.__setattr__(home.providers, "push", push)
    told = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert told.outcome == "voice_note_unheard_unagreed"
    # Nothing of the note is kept, and the sender gets one fixed line with who to call.
    assert (await sg.scalars(select(EventNote))).all() == []
    assert (await sg.scalars(select(Artifact))).all() == []
    assert _told(home, PA) == [
        [
            "Nura could not hear your voice note.",
            "Nura did not keep this note.",
            "If it cannot wait, call 995 now.",
        ]
    ]
    # A person is still told — but through the app, not on the WhatsApp he never agreed to:
    # a red flag is the one thing his family is sent there without his agreement (#163).
    assert _told(home, MEI) == []
    assert [one.person_id for one in push.sent] == [home.mei.id]
    assert [row.outcome for row in await _by_channel(sg, DeliveryChannel.IN_APP)] == [
        DeliveryOutcome.SENT
    ]
    assert [row.passed_over for row in await _by_channel(sg, DeliveryChannel.APP_PUSH)] == [
        ["whatsapp: not agreed"]
    ]


async def test_a_door_that_says_no_to_the_telling_leaves_his_note_and_his_reply(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)

    async def refused(*args: object, **kwargs: object) -> object:
        raise NotOnTheLadder("no ladder here, for the test")

    # A refusal is a decision, not a failure: nothing is sent again, and his note stands.
    monkeypatch.setattr(inbound, "unheard_ladder", refused)
    kept = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    assert await sg.get(EventNote, kept.note_id) is not None
    # One reply, and it says nothing about who knows: nobody was told.
    assert _said(kept) == [HIS_REPLY_ALONE]
    assert await _every_notice(sg) == []


async def test_a_telling_that_failed_is_not_a_200_and_the_message_comes_again(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    down: list[str] = []

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        if not down:
            down.append("once")
            raise ConnectionError("the ladder's database went away, for the test")
        return await ladder_module.unheard_ladder(*args, **kwargs)

    monkeypatch.setattr(inbound, "unheard_ladder", flaky)
    message = DevInbound(from_e164=PA, media_id="pa-voice-mumbled", content_type=OGG).as_message(
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

    # Not a refusal: a note nobody could hear never ends in a 200 with nobody told. Nothing
    # of the message is kept and nothing was said, so the retry tells him once, not twice.
    assert await receive(sg, message, handle) is Received.FAILED
    assert (await sg.scalars(select(EventNote))).all() == []
    assert _told(home, PA) == [] and _told(home, MEI) == []
    assert await receive(sg, message, handle) is Received.HANDLED
    assert _told(home, PA) == [HIS_REPLY]
    assert _told(home, MEI) == [LISTEN]
    assert await receive(sg, message, handle) is Received.ALREADY
    assert len(_told(home, PA)) == 1 and len(_told(home, MEI)) == 1


# --- the notice climbs, and one person's word stops it (#173) ------------------------------------


async def test_the_unheard_notice_climbs_when_the_chief_does_not_say_she_has_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home = await family(sg, tmp_path)
    await _kit_on_the_emergency_card(sg, home)
    clock.set(datetime(2026, 9, 3, 2, 0, tzinfo=UTC))
    await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert _told(home, MEI) == [LISTEN] and _told(home, KIT) == []
    [ladder] = (await sg.scalars(select(Ladder))).all()
    assert ladder.subject is Subject.UNHEARD_NOTE and ladder.is_open
    assert ladder.note_id is not None
    # Nobody has said they have it six minutes on: the next rung is asked.
    clock.set(datetime(2026, 9, 3, 2, 6, tzinfo=UTC))
    await run_due(sg, via=Via(home.settings, home.providers, home.number), profile_id=home.profile.id)
    assert _told(home, KIT) == [CALL]


async def test_saying_i_have_it_stops_the_unheard_notice(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home = await family(sg, tmp_path)
    await _kit_on_the_emergency_card(sg, home)
    clock.set(datetime(2026, 9, 3, 2, 0, tzinfo=UTC))
    await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    stopped = await acknowledge_flag(sg, context=home.chief)
    assert stopped is not None and stopped.subject is Subject.UNHEARD_NOTE
    assert stopped.acknowledged_by_person_id == home.mei.id
    clock.set(datetime(2026, 9, 3, 2, 6, tzinfo=UTC))
    await run_due(sg, via=Via(home.settings, home.providers, home.number), profile_id=home.profile.id)
    assert _told(home, KIT) == []


# --- a channel that failed falls through to the next one (#173) ----------------------------------


async def test_a_whatsapp_send_that_fails_falls_through_to_push_and_the_notice(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    push = FixturePush()
    push.register(home.mei.id)
    object.__setattr__(home.providers, "push", push)

    async def down(*args: object, **kwargs: object) -> str:
        raise ConnectionError("the provider went away, for the test")

    # The notice to her goes as a template: she has written nothing, so no window is open.
    monkeypatch.setattr(home.whatsapp, "send_template", down)
    kept = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    # WhatsApp did not carry it, so the next channel did — and the notice on her family page
    # is written whatever carried it (#169), on a send error as much as on a refusal.
    assert _told(home, MEI) == []
    assert [one.person_id for one in push.sent] == [home.mei.id]
    [pushed] = await _by_channel(sg, DeliveryChannel.APP_PUSH)
    assert pushed.outcome is DeliveryOutcome.SENT and pushed.to_person_id == home.mei.id
    # What went wrong is on the row by the name of its class, never by its words.
    assert pushed.passed_over == ["whatsapp: ConnectionError"]
    assert [row.outcome for row in await _by_channel(sg, DeliveryChannel.IN_APP)] == [
        DeliveryOutcome.SENT
    ]


async def test_a_notice_meta_has_not_approved_yet_falls_through_to_push_and_the_page(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    push = FixturePush()
    push.register(home.mei.id)
    object.__setattr__(home.providers, "push", push)
    # The unheard-note notices are pending Meta's approval: until a deployment's number
    # carries them, the send door refuses them and the notice goes by the app instead.
    home.number = replace(
        home.number,
        templates=tuple(
            name for name in home.number.templates if not name.startswith("unheard_note_notice")
        ),
    )
    kept = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    assert _told(home, MEI) == []
    assert [one.person_id for one in push.sent] == [home.mei.id]
    [pushed] = await _by_channel(sg, DeliveryChannel.APP_PUSH)
    assert pushed.passed_over == ["whatsapp: TemplateNotApproved"]
    assert [row.outcome for row in await _by_channel(sg, DeliveryChannel.IN_APP)] == [
        DeliveryOutcome.SENT
    ]


async def test_a_red_flag_whose_every_channel_failed_still_writes_the_notice(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)

    async def down(*args: object, **kwargs: object) -> str:
        raise ConnectionError("the provider went away, for the test")

    monkeypatch.setattr(home.whatsapp, "send_template", down)
    flagged = await home.inbound(sg, PA, "I fell in the bathroom")
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None
    rows = [
        row
        for row in (await sg.scalars(select(Delivery))).all()
        if row.trigger_type is TriggerType.FLAG and row.to_person_id == home.mei.id
    ]
    # Nothing reached her phone, and that is written down beside the notice on her page.
    assert {(row.via, row.outcome) for row in rows} == {
        (None, DeliveryOutcome.NO_CHANNEL),
        (DeliveryChannel.IN_APP, DeliveryOutcome.SENT),
    }
    # The flag stands whatever the provider did, and so does its ladder.
    assert len((await sg.scalars(select(Flag))).all()) == 1
    assert len((await sg.scalars(select(Ladder))).all()) == 1


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


async def test_two_copies_of_one_delivery_at_the_same_instant_are_one_handling(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The receipt row is claimed before the handler runs (#173), so of two copies of one
    delivery arriving at the same instant exactly one runs it. The other loses the race on
    the unique constraint and is answered as the duplicate it is, not with a 500."""
    home = await family(sg, tmp_path)
    message = DevInbound(from_e164=MEI, text="BP 150/90 this morning").as_message(utcnow())
    ran: list[str] = []

    async def handle() -> object:
        ran.append("once")
        return await handle_inbound(
            sg,
            settings=home.settings,
            providers=home.providers,
            number=home.number,
            classifier=RuleClassifier(),
            message=message,
        )

    assert await receive(sg, message, handle) is Received.HANDLED

    async def nothing_yet(*args: object, **kwargs: object) -> None:
        # The copy that lost the race has not seen the other's row: its insert is what decides.
        return None

    monkeypatch.setattr(receipts, "_receipt", nothing_yet)
    assert await receive(sg, message, handle) is Received.ALREADY
    assert ran == ["once"]
    assert len((await sg.scalars(select(Proposal))).all()) == 1
    [receipt] = (await sg.scalars(select(WhatsAppReceipt))).all()
    assert receipt.handled_at is not None and receipt.failures == 0


async def test_a_message_that_failed_keeps_its_claimed_row_and_is_tried_again(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = await family(sg, tmp_path)
    message = DevInbound(from_e164=MEI, text="BP 150/90 this morning").as_message(utcnow())
    real = inbound.propose
    failed: list[str] = []

    async def flaky(*args: Any, **kwargs: Any) -> Any:
        if not failed:
            failed.append("once")
            raise ConnectionError("the database went away, for the test")
        return await real(*args, **kwargs)

    monkeypatch.setattr(inbound, "propose", flaky)

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
    [receipt] = (await sg.scalars(select(WhatsAppReceipt))).all()
    assert receipt.handled_at is None and receipt.failures == 1
    # The claim stands and says nothing was done: the provider's next delivery tries it again.
    assert await receive(sg, message, handle) is Received.HANDLED
    assert len((await sg.scalars(select(Proposal))).all()) == 1



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
