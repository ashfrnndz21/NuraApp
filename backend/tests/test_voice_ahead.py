"""E22-03: a card's audio is made when the card is made, not on its first play.

The spoken twin (E11-04) is said through the one voice port and kept in the region's store
under the digest of the card's voice script. `refresh` now says each new card as it makes it,
under that same digest, so the first play of the card reads the stored audio. The provider is
still the fixture (silence as long as the lines): a real speech provider is outside Nura.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import utcnow
from app.delivery.feed.compose import refresh
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.search import Engine
from app.delivery.feed.twin import spoken_twin
from app.delivery.voice import MAX_SECONDS, FixtureVoice, Spoken, cache_key, seconds_to_say
from app.ingestion.objects import LocalObjectStore
from app.language.voice_script import script_for
from app.regions import Region
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import FEED, Deployment
from tests.medicines_support import REGISTRY
from tests.visits import pa, reading

ENGINE = Engine(
    searcher=FixtureSearcher(FEED), compressor=FixtureCompressor(FEED), registry=REGISTRY
)


class Counting:
    """The fixture voice, counting what it is asked to say."""

    name = "fixture"

    def __init__(self) -> None:
        self.said: list[str] = []
        self._voice = FixtureVoice()

    async def speak(self, text: str, language: str) -> Spoken:
        self.said.append(text)
        return await self._voice.speak(text, language)


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
