"""The feed's caregiver duty card asks the roster (E12-03 → E21): who is on duty by the
roster leads the card and is who does the next thing; with no roster, the key holders stand."""

from __future__ import annotations

from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.feed.compose import refresh
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.feed.models import CardType
from app.delivery.feed.search import Engine
from app.delivery.strings import CAREGIVER_DUTY_WHY, CAREGIVER_ROSTER_WHY
from app.drugs.fixture import FixtureRegistry
from app.family.roster import add_slot
from app.keys.scopes import KeyRole
from tests.conftest import FEED
from tests.family_support import MONDAY, household

ENGINE = Engine(
    searcher=FixtureSearcher(FEED),
    compressor=FixtureCompressor(FEED),
    registry=FixtureRegistry.load(),
)


async def test_with_no_roster_the_duty_card_counts_the_key_holders(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    _, made = await refresh(sg, context=mei, engine=ENGINE)
    duty = next(item for item in made if item.type is CardType.DUTY)
    assert duty.body[0] == "3 people hold a key to Pa's record today."
    assert duty.body[1] == "Nobody is on the roster for now; add a slot under Family."
    assert "on duty" not in " ".join(duty.body)
    assert duty.why["plain"] == CAREGIVER_DUTY_WHY


async def test_with_a_roster_the_duty_card_names_who_is_on_duty_now(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    clock.set(MONDAY)  # Monday 10:00 on Pa's wall
    h = await household(sg)
    mei = await h.ctx(sg, h.mei)
    await add_slot(
        sg,
        context=mei,
        person_id=h.kit.id,
        role=KeyRole.CAREGIVER,
        weekdays=[0, 1, 2, 3, 4],
        from_time=time(8, 0),
        to_time=time(20, 0),
    )
    _, made = await refresh(sg, context=mei, engine=ENGINE)
    duty = next(item for item in made if item.type is CardType.DUTY)
    assert duty.body[0] == "Kit is on duty for Pa right now, by the roster."
    assert duty.body[1:] == ["3 people hold a key to Pa's record today."]
    assert duty.why["plain"] == CAREGIVER_ROSTER_WHY
