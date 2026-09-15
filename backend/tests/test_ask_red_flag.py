"""A red word typed into Ask or search (D1: the bar on top of his Today) takes the red-flag path
before anything is looked up, exactly as the same word tapped on the feeling cloud; a question
with no red word is answered as before."""

from __future__ import annotations

from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6598760431"


async def test_a_red_word_in_a_question_takes_the_red_flag_path_first(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    client = deployment.client

    red = await client.post(
        f"/profiles/{profile_id}/ask", json={"question": "My chest is tight"}, headers=his
    )
    assert red.status_code == 200, red.text
    flagged = red.json()["red_flag"]
    assert flagged is not None
    assert flagged["red_flag"] is True
    assert flagged["lines"]

    plain = await client.post(
        f"/profiles/{profile_id}/ask", json={"question": "what was my blood pressure"}, headers=his
    )
    assert plain.status_code == 200, plain.text
    assert plain.json()["red_flag"] is None
