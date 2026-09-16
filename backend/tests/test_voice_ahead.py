"""E22-03: a card's audio is made when the card is made, not on its first play.

The spoken twin (E11-04) is said through the one voice port and kept in the region's store
under the digest of the card's voice script. `refresh` now says each new card as it makes it,
under that same digest, so the first play of the card reads the stored audio. The provider is
still the fixture (silence as long as the lines): a real speech provider is outside Nura.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.db import utcnow
from app.delivery.feed.compose import VOICE_TARGET, _say_ahead, refresh
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.items import Why, create_item
from app.delivery.feed.models import CardType, DeliverTo
from app.delivery.feed.search import Engine
from app.delivery.feed.twin import spoken_twin
from app.delivery.strings import Lines
from app.delivery.voice import MAX_SECONDS, FixtureVoice, Spoken, cache_key, seconds_to_say
from app.ingestion.objects import LocalObjectStore
from app.keys.scopes import Scope
from app.language.voice_script import VoiceScript, script_for
from app.regions import Region
from app.state.service import current_state
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import FEED, Deployment
from tests.medicines_support import REGISTRY
from tests.visits import pa, reading

ENGINE = Engine(
    searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
)
MONDAY = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


class Counting:
    """The fixture voice, counting what it is asked to say."""

    name = "fixture"

    def __init__(self) -> None:
        self.said: list[str] = []
        self._voice = FixtureVoice()

    async def speak(self, script: VoiceScript) -> Spoken:
        self.said.append(script.spoken())
        return await self._voice.speak(script)


async def test_each_card_is_said_once_as_it_is_made_and_its_first_play_reads_the_store(
    sg: AsyncSession, tmp_path: Path
) -> None:
    context = await pa(sg, language="en")
    await reading(sg, context, when=utcnow())
    store = LocalObjectStore(tmp_path, Region.SG)
    voice = Counting()
    engine = replace(ENGINE, voice=voice, store=store)

    _, made = await refresh(sg, context=context, engine=engine)
    sayable = [
        item
        for item in made
        if seconds_to_say(
            script_for(item.voice or item.body, item.language, boundary=item.boundary).spoken(),
            item.language,
        )
        <= MAX_SECONDS
    ]
    assert sayable and len(voice.said) == len(sayable)
    for item in sayable:
        digest = script_for(item.voice or item.body, item.language, boundary=item.boundary).digest
        assert store.path_of(cache_key(context.profile_id, voice.name, digest)).is_file()
        twin = await spoken_twin(sg, context=context, item_id=item.id, voice=voice, store=store)
        assert twin.cached
    assert len(voice.said) == len(sayable)  # the plays were reads

    _, again = await refresh(sg, context=context, engine=engine)
    assert again == [] and len(voice.said) == len(sayable)


async def test_over_http_the_first_play_of_a_new_card_is_a_read(deployment: Deployment) -> None:
    pa_ = await register_by_phone(deployment, "+6591510001", "Pa")
    profile_id = await own_profile(deployment, pa_, display_name="Pa", language="en")
    his = bearer(pa_["token"])
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=his
    )
    assert posted.status_code == 201, posted.text
    page = await deployment.client.get(f"/profiles/{profile_id}/feed", headers=his)
    [card] = [c for c in page.json()["items"] if c["type"] == "reading"]
    played = await deployment.client.get(
        f"/profiles/{profile_id}/feed/{card['item_id']}/voice", headers=his
    )
    assert played.status_code == 200 and played.headers["x-voice-cache"] == "hit"


async def test_a_card_is_prerendered_in_each_of_en_ms_and_zh_within_a_minute_of_the_frozen_clock(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """E22-03's acceptance, "audio within a minute of creation", held to the frozen clock
    rather than wall time: the card's audio already stands, under its digest, at the very
    moment `refresh` returns it — before any time at all has passed on his clock — in each
    of the three languages T1 says a card in."""
    store = LocalObjectStore(tmp_path, Region.SG)
    for index, language in enumerate(("en", "ms", "zh")):
        voice = Counting()
        engine = replace(ENGINE, voice=voice, store=store)
        context = await pa(sg, language=language, phone=f"+65911102{index:02d}")
        made_at = clock.now()
        await reading(sg, context, when=made_at)

        _, made = await refresh(sg, context=context, engine=engine)
        [item] = [one for one in made if one.type is CardType.READING]
        assert item.language == language
        assert item.created_at == made_at

        digest = script_for(item.voice or item.body, item.language, boundary=item.boundary).digest
        assert store.path_of(cache_key(context.profile_id, voice.name, digest)).is_file()
        said_ahead = len(voice.said)  # every card `refresh` made was said ahead, not on a play

        twin = await spoken_twin(sg, context=context, item_id=item.id, voice=voice, store=store)
        assert twin.cached and len(voice.said) == said_ahead  # the play was a read
        # Nothing moved the clock between the card being made and its audio being ready: the
        # gap is zero, which is under a minute on any clock, frozen or not.
        assert clock.now() == made_at


class Breaking:
    """A voice that cannot say a script in one language: what a provider outage looks like."""

    name = "fixture"

    def __init__(self, fails_language: str) -> None:
        self._voice = FixtureVoice()
        self._fails_language = fails_language

    async def speak(self, script: VoiceScript) -> Spoken:
        if script.language == self._fails_language:
            raise RuntimeError("speech provider unavailable")
        return await self._voice.speak(script)


async def test_a_prerender_failure_is_on_the_trail_and_never_costs_him_the_card(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The second gap E22-03 closes: a render that fails at creation does not unmake the
    card, and is not swallowed — it is written to the trail under `VOICE_TARGET`, the way
    any other refused write is, so the gap between the card and its twin is visible to
    whoever reads it back, not just to a log line."""
    context = await pa(sg, language="en")
    await reading(sg, context, when=utcnow())
    store = LocalObjectStore(tmp_path, Region.SG)
    engine = replace(ENGINE, voice=Breaking("en"), store=store)

    _, made = await refresh(sg, context=context, engine=engine)
    reading_card = next(item for item in made if item.type is CardType.READING)
    digest = script_for(
        reading_card.voice or reading_card.body,
        reading_card.language,
        boundary=reading_card.boundary,
    ).digest
    assert not store.path_of(cache_key(context.profile_id, "fixture", digest)).is_file()

    trail = await read_audit(sg, context=context, action=Action.WRITE, scope=Scope.READINGS)
    failed = [
        entry
        for entry in trail
        if entry.target == VOICE_TARGET
        and entry.target_id == reading_card.id
        and entry.outcome is Outcome.REFUSED
    ]
    assert failed and failed[0].refused_because == "RuntimeError"

    # The route falls back to rendering on request exactly as it does today: asked now,
    # through a voice that is working, the card is still said.
    twin = await spoken_twin(
        sg, context=context, item_id=reading_card.id, voice=FixtureVoice(), store=store
    )
    assert not twin.cached
    assert store.path_of(cache_key(context.profile_id, "fixture", digest)).is_file()


async def test_a_corrected_cards_audio_is_never_the_stale_digest(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """A `FeedItem` row is never edited (`app.db.frozen`): a card whose words were wrong is
    superseded by a new row with the corrected words, never rewritten in place. Its voice
    script digest is a function of those words, so the corrected card renders under a digest
    of its own — the wrong card's audio is never in its way to be served stale."""
    context = await pa(sg, language="en")
    state = await current_state(sg, context=context)
    store = LocalObjectStore(tmp_path, Region.SG)
    engine = replace(ENGINE, voice=FixtureVoice(), store=store)

    def _lines(text: str) -> Lines:
        return Lines(
            language="en",
            headline="Your blood pressure today",
            body=(text,),
            voice=(text,),
            why="You took your blood pressure today.",
        )

    wrong = await create_item(
        sg,
        context=context,
        state=state,
        type=CardType.READING,
        lines=_lines("Your blood pressure today was 138 over 84."),
        why=Why(kind="reading", plain="You took your blood pressure today."),
        scope=Scope.READINGS,
        deliver_to=DeliverTo.PATIENT,
        day="2026-09-14",
        dedupe_key="reading:wrong",
        expires_at=MONDAY,
    )
    fixed = await create_item(
        sg,
        context=context,
        state=state,
        type=CardType.READING,
        lines=_lines("Your blood pressure today was 140 over 85."),
        why=Why(kind="reading", plain="You took your blood pressure today."),
        scope=Scope.READINGS,
        deliver_to=DeliverTo.PATIENT,
        day="2026-09-14",
        dedupe_key="reading:fixed",
        expires_at=MONDAY,
    )
    await _say_ahead(sg, engine, context, [wrong, fixed])

    wrong_digest = script_for(wrong.voice, wrong.language).digest
    fixed_digest = script_for(fixed.voice, fixed.language).digest
    assert wrong_digest != fixed_digest

    wrong_twin = await spoken_twin(
        sg, context=context, item_id=wrong.id, voice=FixtureVoice(), store=store
    )
    fixed_twin = await spoken_twin(
        sg, context=context, item_id=fixed.id, voice=FixtureVoice(), store=store
    )
    # Each card's play reads back its own digest's slot, never the other's: the corrected
    # card was never at risk of the wrong one's stale bytes, by construction.
    assert wrong_twin.cached and fixed_twin.cached
    assert wrong_twin.key != fixed_twin.key
    assert wrong_twin.key.endswith(wrong_digest) and fixed_twin.key.endswith(fixed_digest)
