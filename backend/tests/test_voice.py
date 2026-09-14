"""E11-04: every card's spoken twin, as audio, under thirty seconds.

The `Voice` port says a card's voice lines; the fixture is silence exactly as long as the
lines would take at his pace. English, Malay and Mandarin now; Hokkien and Tamil at T2. The
twin is a derived cache in the region's object store, keyed by what was said — never an
artefact — so the second play is a read. A WhatsApp voice note uses the same port, inside the
24-hour window only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.models import MessageKind, WhatsAppMessage
from app.channels.whatsapp.outbound.level0 import run_morning
from app.channels.whatsapp.outbound.send import OutsideTheWindow, send_voice_note
from app.delivery.voice import (
    MAX_SECONDS,
    FixtureVoice,
    NoVoiceFor,
    TooLongToSay,
    seconds_to_say,
    voiced,
    wav_seconds,
)
from app.ingestion.objects import LocalObjectStore
from app.memory.models import Artifact
from app.regions import OutOfRegion, Region
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_feed_api import _caregiver_key, _feed, _reading
from tests.whatsapp_support import PA, family

MEI = "+6591119902"


async def test_the_fixture_says_a_card_as_silence_of_the_right_length() -> None:
    voice = FixtureVoice()
    lines = "Your blood pressure today was 138 over 84.\nIt is in your blood pressure book."
    said = await voice.speak(lines, "en")
    assert said.content_type == "audio/wav" and said.language == "en"
    assert said.duration_seconds == seconds_to_say(lines, "en") == wav_seconds(said.audio)
    assert said.duration_seconds < MAX_SECONDS
    assert (await voice.speak(lines, "en")).audio == said.audio
    for language in ("ms", "zh"):
        assert (await voice.speak("您今天的血压是138比84。", language)).duration_seconds > 0


async def test_hokkien_and_tamil_wait_for_t2_and_a_long_note_is_refused(tmp_path: Path) -> None:
    voice = FixtureVoice()
    for later in ("nan", "ta"):
        with pytest.raises(NoVoiceFor):
            await voice.speak("Hello.", later)
    store = LocalObjectStore(tmp_path, Region.SG)
    import uuid

    with pytest.raises(TooLongToSay):
        await voiced(
            store,
            voice,
            profile_id=uuid.uuid4(),
            region=Region.SG,
            lines=["This line is one of many lines that together run far too long."] * 12,
            language="en",
        )


async def test_the_twin_is_kept_by_digest_in_the_regions_store_never_as_an_artefact(
    sg: AsyncSession, tmp_path: Path
) -> None:
    import uuid

    voice = FixtureVoice()
    store = LocalObjectStore(tmp_path, Region.SG)
    profile_id = uuid.uuid4()
    lines = ["Your tablets for today are on your list."]
    first = await voiced(store, voice, profile_id=profile_id, region=Region.SG, lines=lines, language="en")
    again = await voiced(store, voice, profile_id=profile_id, region=Region.SG, lines=lines, language="en")
    assert not first.cached and again.cached and again.spoken.audio == first.spoken.audio
    assert first.key.startswith(f"voice/{profile_id}/")
    assert (tmp_path / "SG" / first.key).is_file()
    assert (await sg.scalars(select(Artifact))).all() == []
    with pytest.raises(OutOfRegion):
        await voiced(
            LocalObjectStore(tmp_path, Region.MY),
            voice,
            profile_id=profile_id,
            region=Region.SG,
            lines=lines,
            language="en",
        )


async def test_any_card_is_played_on_request_in_its_language_under_thirty_seconds(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = pa["token"]
    await _reading(deployment, profile_id, his, 138, 84)
    page = await _feed(deployment, profile_id, his)
    for item in page["items"]:
        played = await deployment.client.get(
            f"/profiles/{profile_id}/feed/{item['item_id']}/voice", headers=bearer(his)
        )
        assert played.status_code == 200, played.text
        assert played.headers["content-type"] == "audio/wav"
        assert float(played.headers["x-duration-seconds"]) < MAX_SECONDS
    reading = next(item for item in page["items"] if item["type"] == "reading")
    url = f"/profiles/{profile_id}/feed/{reading['item_id']}/voice"
    again = await deployment.client.get(url, headers=bearer(his))
    assert again.headers["x-voice-cache"] == "hit"
    assert again.headers["cache-control"] == "private"
    # No audio for this card in that language: 404, and the phone says it with its own voice.
    refused = await deployment.client.get(url, params={"language": "zh"}, headers=bearer(his))
    assert refused.status_code == 404 and refused.json()["refusal"] == "NotInThatLanguage"
    later = await deployment.client.get(url, params={"language": "ta"}, headers=bearer(his))
    assert later.status_code == 404 and later.json()["refusal"] == "NoVoiceFor"
    # A key that does not cover the readings does not hear the reading card.
    mei = await register_by_phone(deployment, MEI, "Mei")
    await _caregiver_key(deployment, pa, profile_id, MEI, ["medicines", "emergency"])
    hers = await deployment.client.get(url, headers=bearer(mei["token"]))
    assert hers.status_code == 403 and hers.json()["refusal"] == "OutOfScope"


async def test_a_whatsapp_voice_note_uses_the_same_port_inside_the_window_only(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    lines = ["Your tablets for today are on your list."]
    with pytest.raises(OutsideTheWindow):
        await send_voice_note(
            sg,
            context=home.owner,
            to_person=home.pa,
            lines=lines,
            provider=home.providers.whatsapp,
            voice=home.providers.voice,
            store=home.providers.object_store,
        )
    await home.inbound(sg, PA, "hello")
    sent = await send_voice_note(
        sg,
        context=home.owner,
        to_person=home.pa,
        lines=lines,
        provider=home.providers.whatsapp,
        voice=home.providers.voice,
        store=home.providers.object_store,
    )
    assert sent.kind == "audio" and home.whatsapp.sent[-1].kind == "audio"
    row = await sg.get(WhatsAppMessage, sent.message_id)
    assert row is not None and row.kind is MessageKind.VOICE_NOTE


async def test_the_morning_card_is_followed_by_its_voice_twin_inside_the_window(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    await home.inbound(sg, PA, "hello")
    await run_morning(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    kinds = [one.kind for one in home.whatsapp.sent if one.to_e164 == PA]
    assert kinds[-2:] == ["text", "audio"]


async def test_the_audio_is_said_from_the_voice_script_and_kept_under_its_digest(
    tmp_path: Path,
) -> None:
    """E22-03's voice script is what is said, and its digest is the key: the same words and
    pauses, the same audio, wherever the card appears."""
    import uuid

    from app.language.voice_script import script_for

    voice = FixtureVoice()
    store = LocalObjectStore(tmp_path, Region.SG)
    profile_id = uuid.uuid4()
    lines = ["Your blood pressure today was 138 over 84.", "It is in your blood pressure book."]
    said = await voiced(
        store, voice, profile_id=profile_id, region=Region.SG, lines=lines, language="en"
    )
    script = script_for(lines, "en")
    assert said.key == f"voice/{profile_id}/{voice.name}/{script.digest}"
    assert "one hundred and thirty-eight over eighty-four" in script.spoken()
    assert said.spoken.duration_seconds == seconds_to_say(script.spoken(), "en")
