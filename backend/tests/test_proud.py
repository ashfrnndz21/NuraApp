"""E17-04: the number that only goes up, on Me.

The acceptance line: it never decreases, and there is no streak language. The number is W1's
(`GET /profiles/{id}/proud`: days with a DOSE_TAKEN event); the Me page says it in his words.
"""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import FrozenClock
from app.delivery.nudges.strings import recognition_lines
from app.medicines.service import proud_days, record_dose_taken
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.family_support import household
from tests.feelings_support import new_medicine


async def test_the_number_never_goes_down_whatever_the_days_bring(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    home = await household(sg)
    owner = await home.ctx(sg, home.pa)
    siti = await home.ctx(sg, home.siti)
    added = await new_medicine(sg, owner)
    seen = [(await proud_days(sg, context=owner)).days]

    async def count() -> None:
        seen.append((await proud_days(sg, context=owner)).days)

    await record_dose_taken(sg, context=owner, line_id=added.line.id)
    await record_dose_taken(sg, context=owner, line_id=added.line.id)
    await count()  # two taps on one day are one day
    clock.step(timedelta(days=1))
    await record_dose_taken(sg, context=siti, line_id=added.line.id)
    await count()  # the helper's "given" is his tablet taken
    clock.step(timedelta(days=5))
    await count()  # quiet days take nothing away
    changed = await new_medicine(sg, owner, dose="2 tab OD")
    await count()  # a dose change keeps every day already counted
    await record_dose_taken(sg, context=owner, line_id=changed.line.id)
    await count()
    clock.step(timedelta(days=40))
    await count()
    assert seen == [0, 1, 2, 2, 2, 3, 3]
    assert all(later >= earlier for earlier, later in pairwise(seen))


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
def test_the_me_page_says_it_without_streak_words(language: str) -> None:
    for count in (0, 1, 2, 41):
        lines = recognition_lines(count, language)
        text = " ".join(lines).lower()
        for word in ("streak", "in a row", "row", "missed", "lost", "break", "berturut", "连续"):
            assert word not in text, (count, lines)
    assert recognition_lines(41, "en") == (
        "Nura counts 41 days with your tablets taken.",
        "This number only goes up.",
    )


async def test_the_me_page_over_http(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591310001", "Pa")
    profile_id = await own_profile(deployment, pa)
    his = bearer(pa["token"])
    proud = await deployment.client.get(f"/profiles/{profile_id}/proud", headers=his)
    assert proud.status_code == 200 and proud.json()["days"] == 0
    me = await deployment.client.get(f"/profiles/{profile_id}/me-summary", headers=his)
    assert me.status_code == 200, me.text
    assert me.json()["proud_days"] == 0 and me.json()["name"] == "Pa"
    assert me.json()["lines"] == [
        "Nura counts the days with your tablets taken.",
        "This number only goes up.",
    ]
    stranger = await register_by_phone(deployment, "+6591310002", "Someone")
    refused = await deployment.client.get(
        f"/profiles/{profile_id}/me-summary", headers=bearer(stranger["token"])
    )
    assert refused.status_code == 403 and refused.json() == {"refusal": "NoKey"}
