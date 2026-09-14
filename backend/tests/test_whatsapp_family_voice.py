"""E11-01: the family's group on WhatsApp, and voice notes from Pa.

    WhatsApp surface: cards, voice notes, Taken replies, family thread, inbound.

The family's group mirrors the family thread (E12-02). Who is in it is who reads the thread —
the patient and every live key holding the family's part — worked out from the keys each
time, never stored: a key closed is a person out of it. A message posted there lands in the
thread in its poster's name; a message from anyone else is not taken in and nobody is answered
in the group; a message written in the app's thread is said in the group. A red word in the
group still takes the red-flag path first, whoever says it.

A voice note Pa sends is fetched from the (fixture) provider and heard by the region's
transcriber before anything else, so a red word in it is found first — before "ignore" and
before his agreement to WhatsApp is checked. It is kept as his own note (ADR 0003: his own
voice, so no recording consent), private to him and a chief preset to his notes, and recall
finds it. Nobody else's voice note is kept. No call is made to Meta: the provider is the
fixture.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.group import members_of, mirror_to_group, open_group, sync_group
from app.consent.models import Consent, ConsentPurpose
from app.family.thread import post_message, read_thread
from app.ingestion.models import EventNote, NoteKind
from app.ingestion.transcribe import FixtureTranscriber
from app.keys.grants import revoke_key
from app.keys.scopes import KeyRole, Scope
from app.memory.models import Artifact, ArtifactKind, Fact, SourceChannel
from app.regions import OutOfRegion, Region
from app.safety.red_flags import Flag
from app.search.ask import Mode, recall
from tests.medicines_support import let_in as cut_key
from tests.voice_notes import VOICE
from tests.whatsapp_support import KIT, MEI, PA, SITI, family

OGG = "audio/ogg; codecs=opus"


async def test_the_family_group_is_who_reads_the_thread_and_a_message_there_lands_in_it(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    await cut_key(sg, home.owner, phone=KIT, name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS, Scope.READINGS})
    await cut_key(sg, home.owner, phone=SITI, name="Siti", role=KeyRole.HELPER, scopes={Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND})

    group, members = await open_group(sg, context=home.chief, provider=home.whatsapp)
    gid = group.provider_group_id
    assert [(m.name, m.is_patient) for m in members] == [("Pa", True), ("Mei", False)]
    assert home.whatsapp.groups[gid] == tuple(sorted({PA, MEI}))
    again, _ = await open_group(sg, context=home.owner, provider=home.whatsapp)
    assert again.id == group.id  # one group per family

    # Mei, in the group: into the family thread, in her name; nobody is answered there.
    said = await home.inbound(sg, MEI, "I will take Pa on Thursday.", group_id=gid)
    assert said.outcome == "family_thread" and said.thread_message_id is not None
    assert said.replies == ()
    page, _ = await read_thread(sg, context=home.owner)
    assert [(e.text, e.author_person_id) for e in page] == [("I will take Pa on Thursday.", home.mei.id)]
    assert not list(await sg.scalars(select(Fact).where(Fact.profile_id == home.profile.id)))

    # Kit's key does not read the family, nor Siti's: not members, not taken in, not answered.
    for number in (KIT, SITI):
        ignored = await home.inbound(sg, number, "Is he OK today?", group_id=gid)
        assert ignored.outcome == "ignored" and ignored.replies == ()
    page, _ = await read_thread(sg, context=home.owner)
    assert len(page) == 1

    # A red word in the group takes the red-flag path first, member or not.
    flagged = await home.inbound(sg, SITI, "He fell in the kitchen just now", group_id=gid)
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None
    # A stranger, or a group this number does not keep: nothing kept, nothing said.
    assert (await home.inbound(sg, "+6599990001", "hello", group_id=gid)).outcome == "ignored"
    assert (await home.inbound(sg, MEI, "hello", group_id="group.fixture.other")).outcome == "ignored"

    # The app's thread, mirrored out: said in the group, in her name.
    entry = await post_message(sg, context=home.chief, text="The doctor moved it to 3 pm.")
    assert await mirror_to_group(sg, context=home.chief, provider=home.whatsapp, message=entry)
    [out] = [sent for sent in home.whatsapp.sent if sent.group_id == gid]
    assert out.text == "Mei wrote in the family thread:\nThe doctor moved it to 3 pm."

    # Her key closed: out of the group at once; her next message there is not taken in.
    assert home.chief.key_id is not None
    await revoke_key(sg, context=home.owner, key_id=home.chief.key_id)
    await sync_group(sg, context=home.owner, provider=home.whatsapp)
    assert home.whatsapp.groups[gid] == (PA,)
    assert [m.name for m in await members_of(sg, context=home.owner)] == ["Pa"]
    late = await home.inbound(sg, MEI, "Still here?", group_id=gid)
    assert late.outcome == "ignored"


async def test_a_group_is_opened_only_by_him_or_his_chief_on_his_agreement_to_whatsapp(
    sg: AsyncSession, tmp_path: Path
) -> None:
    from app.channels.whatsapp.group import NotTheirsToOpen
    from app.consent.service import NoConsent
    from app.keys.context import resolve_key_context

    home = await family(sg, tmp_path, whatsapp_consent=False)
    with pytest.raises(NoConsent):
        await open_group(sg, context=home.owner, provider=home.whatsapp)
    kit = await cut_key(sg, home.owner, phone=KIT, name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS, Scope.FAMILY})
    with pytest.raises(NotTheirsToOpen):
        await open_group(sg, context=kit, provider=home.whatsapp)
    assert home.whatsapp.groups == {}
    assert resolve_key_context is not None


async def test_pas_voice_note_is_heard_in_the_region_and_kept_as_his_own_note(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    kept = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None and kept.artifact_id is not None
    assert [r.text for r in kept.replies] == ["Nura kept your voice note."]

    note = await sg.get(EventNote, kept.note_id)
    assert note is not None and note.kind is NoteKind.VOICE and note.private is True
    assert note.transcript_language == "en" and note.transcript_key is not None
    voice = await sg.get(Artifact, kept.artifact_id)
    assert voice is not None and voice.kind is ArtifactKind.VOICE
    assert voice.source_channel is SourceChannel.WHATSAPP and voice.storage_key.startswith("voice/")
    # His own voice: no recording consent asked or on file (ADR 0003), and never a fact.
    purposes = {c.purpose for c in await sg.scalars(select(Consent).where(Consent.profile_id == home.profile.id))}
    assert ConsentPurpose.RECORDING not in purposes
    assert not list(await sg.scalars(select(Fact).where(Fact.profile_id == home.profile.id)))

    # Recall finds it: his, and his chief's, whose key opens his notes.
    for context, line in ((home.owner, "You left a note on Thursday 3 September."), (home.chief, "Pa left a note on Thursday 3 September.")):
        answer = await recall(
            sg,
            context=context,
            question="what did I say about the market",
            mode=Mode.TEXT,
            retriever=home.providers.retriever,
            store=home.providers.object_store,
        )
        found = [l for l in answer.lines if any(c.kind == "event_note" for c in l.cites)]
        assert [l.text for l in found] == [line]
    kit = await cut_key(sg, home.owner, phone=KIT, name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS, Scope.READINGS, Scope.ASK})
    theirs = await recall(
        sg,
        context=kit,
        question="what did Pa say about the market",
        mode=Mode.TEXT,
        retriever=home.providers.retriever,
        store=home.providers.object_store,
    )
    assert not [l for l in theirs.lines if any(c.kind == "event_note" for c in l.cites)]


async def test_a_voice_note_nothing_was_heard_in_is_kept_and_says_so(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    kept = await home.inbound(sg, PA, media_id="pa-voice-mumbled", content_type=OGG)
    assert kept.outcome == "voice_note" and kept.note_id is not None
    assert [r.text for r in kept.replies] == ["Nura kept your voice note.\nNura could not hear this note."]
    note = await sg.get(EventNote, kept.note_id)
    assert note is not None and note.transcript_key is None


async def test_a_red_word_in_his_voice_note_is_a_flag_first_and_the_note_is_still_his(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    flagged = await home.inbound(sg, PA, media_id="pa-voice-fell", content_type=OGG)
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None
    assert flagged.note_id is not None
    flag = await sg.get(Flag, flagged.flag_id)
    assert flag is not None and flag.feeling.value == "fall"


async def test_without_his_agreement_to_whatsapp_a_red_word_in_his_voice_is_still_raised(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path, whatsapp_consent=False)
    flagged = await home.inbound(sg, PA, media_id="pa-voice-fell", content_type=OGG)
    assert flagged.flag_id is not None
    # Raised on the word alone: nothing of the message is kept, his voice note least of all.
    assert not list(await sg.scalars(select(EventNote).where(EventNote.profile_id == home.profile.id)))
    plain = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert plain.outcome == "refused" and plain.note_id is None


async def test_nobody_elses_voice_note_is_kept(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, media_id="pa-voice-market", content_type=OGG)
    assert handled.outcome == "other" and handled.note_id is None
    assert not list(await sg.scalars(select(EventNote).where(EventNote.profile_id == home.profile.id)))


async def test_a_voice_note_is_heard_in_the_region_or_not_at_all(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    home.providers = replace(home.providers, transcriber=FixtureTranscriber(VOICE, Region.MY))
    with pytest.raises(OutOfRegion):
        await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert not list(await sg.scalars(select(EventNote).where(EventNote.profile_id == home.profile.id)))


def test_the_webhook_reads_a_voice_note_as_media_to_fetch_and_hear() -> None:
    from app.channels.whatsapp.provider import FixtureProvider

    provider = FixtureProvider(secret="s")
    [message] = provider.parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "6591110001",
                                        "id": "wamid.voice.1",
                                        "timestamp": "1757000000",
                                        "type": "audio",
                                        "audio": {"id": "pa-voice-market", "mime_type": OGG, "voice": True},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert (message.from_e164, message.media_id, message.content_type, message.text) == (
        PA,
        "pa-voice-market",
        OGG,
        None,
    )


# --- the privacy and clinical-safety review's fixes ----------------------------------------------


async def test_a_flag_in_his_voice_note_stands_when_keeping_the_note_is_refused(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag, its moment and its ladder are never taken back by a refusal to keep the note:
    the note is kept in a savepoint of its own, and he is not told "not understood"."""
    from app.channels.whatsapp import inbound
    from app.errors import Refusal

    class NotKept(Refusal):
        """The note could not be kept."""

    async def refuse(*args: object, **kwargs: object) -> None:
        raise NotKept("refused, for the test")

    home = await family(sg, tmp_path)
    monkeypatch.setattr(inbound, "keep_voice_message", refuse)
    flagged = await home.inbound(sg, PA, media_id="pa-voice-fell", content_type=OGG)
    assert flagged.outcome == "red_flag" and flagged.flag_id is not None and flagged.note_id is None
    assert await sg.get(Flag, flagged.flag_id) is not None
    assert not any("did not understand" in r.text for r in flagged.replies)


async def test_the_group_follows_only_me_and_his_agreement(sg: AsyncSession, tmp_path: Path) -> None:
    from app.consent.models import ConsentChannel
    from app.consent.service import revoke_consent
    from tests.timeline_support import keep_only_me

    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.chief, provider=home.whatsapp)
    gid = group.provider_group_id
    assert home.whatsapp.groups[gid] == tuple(sorted({PA, MEI}))
    # He keeps the family's part to himself: nobody else is in the group.
    await keep_only_me(sg, home.owner, Scope.FAMILY)
    await sync_group(sg, context=home.owner, provider=home.whatsapp)
    assert home.whatsapp.groups[gid] == (PA,)
    # His agreement to WhatsApp withdrawn: the group is emptied.
    await revoke_consent(
        sg, context=home.owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP
    )
    await sync_group(sg, context=home.owner, provider=home.whatsapp)
    assert home.whatsapp.groups[gid] == ()


async def test_a_photo_in_the_group_is_never_one_of_his_papers(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.chief, provider=home.whatsapp)
    shared = await home.inbound(
        sg, MEI, media_id="grandkids-photo", content_type="image/jpeg", group_id=group.provider_group_id
    )
    assert shared.outcome == "ignored" and shared.review_card_id is None
    assert not list(await sg.scalars(select(Artifact).where(Artifact.profile_id == home.profile.id)))


async def test_his_ok_is_a_check_in_answer_only_while_a_check_in_is_open(
    sg: AsyncSession, tmp_path: Path
) -> None:
    from app.channels.whatsapp.outbound.level0 import run_feeling_check_in

    home = await family(sg, tmp_path)
    stray = await home.inbound(sg, PA, "OK")
    assert stray.outcome == "nothing_open" and stray.fact_id is None
    await run_feeling_check_in(
        sg, settings=home.settings, providers=home.providers, number=home.number, profile_id=home.profile.id
    )
    answered = await home.inbound(sg, PA, "OK")
    assert answered.outcome == "check_in_answer" and answered.fact_id is not None
    again = await home.inbound(sg, PA, "OK")
    assert again.outcome == "nothing_open"


async def test_a_voice_note_that_could_not_be_fetched_is_told_to_him(
    sg: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.channels.whatsapp import inbound

    home = await family(sg, tmp_path)
    monkeypatch.setattr(inbound, "VOICE_DOWNLOAD_BYTES", 10)
    told = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    assert told.outcome == "voice_note_not_heard" and told.note_id is None
    assert [r.text for r in told.replies] == [
        "Nura could not hear your voice note.\nIf you feel unwell, call your family now."
    ]


async def test_his_private_voice_notes_moment_is_the_notes_own(sg: AsyncSession, tmp_path: Path) -> None:
    from app.memory.models import Event

    home = await family(sg, tmp_path)
    kept = await home.inbound(sg, PA, media_id="pa-voice-market", content_type=OGG)
    note = await sg.get(EventNote, kept.note_id)
    assert note is not None
    moment = await sg.get(Event, note.event_id)
    assert moment is not None and moment.written_scope is Scope.NOTES
