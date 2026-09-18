""""Or just tell me" (docs/onboarding.html): free text tagged into the word cloud's own
condition codes by RE-04's `TopicTagger`, a red word turned away before a tagger ever sees it.

`app.onboarding.tell_me.tell_me` is the pure function; `POST /onboarding/tell-me` is public,
like the cloud itself.
"""

from __future__ import annotations

from app.delivery.recommend.topics import FixtureTagger
from app.onboarding.conditions import graph
from app.onboarding.tell_me import tell_me
from tests.conftest import Deployment


def test_ordinary_words_tag_the_clouds_own_codes() -> None:
    told = tell_me("I have high blood pressure and take tablets for it")
    assert told.red_flag is False
    assert "high_blood_pressure" in told.conditions
    assert all(code in graph().conditions for code in told.conditions)


def test_a_sensitive_word_names_no_condition_at_all() -> None:
    told = tell_me("I have been thinking about suicide")
    assert told.red_flag is True
    assert told.conditions == ()


def test_a_sensitive_word_wins_even_beside_an_ordinary_one() -> None:
    # He also names his blood pressure, but the red word still stops every pill.
    told = tell_me("I am pregnant and my blood pressure is high")
    assert told.red_flag is True
    assert told.conditions == ()


def test_nothing_the_catalogue_knows_tags_nothing() -> None:
    told = tell_me("just checking in today")
    assert told == tell_me("just checking in today")
    assert told.red_flag is False
    assert told.conditions == ()


def test_a_topic_outside_the_condition_family_is_left_out() -> None:
    # A medicine topic (RE-04's generic families) is not one of the cloud's own words, so it
    # is never handed back as a condition code to pre-pick.
    told = tell_me("I take amlodipine every morning")
    assert all(code in graph().conditions for code in told.conditions)


def test_a_custom_tagger_is_honoured() -> None:
    told = tell_me("some words a fixture answers", tagger=FixtureTagger({}))
    assert told.conditions == () and told.red_flag is False


async def test_the_route_is_public_and_echoes_no_text(deployment: Deployment) -> None:
    answer = await deployment.client.post("/onboarding/tell-me", json={"text": "my sugar is high"})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body == {"conditions": ["diabetes"], "red_flag": False}


async def test_the_route_turns_away_a_red_word(deployment: Deployment) -> None:
    answer = await deployment.client.post(
        "/onboarding/tell-me", json={"text": "he hit me and I am afraid at home"}
    )
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"conditions": [], "red_flag": True}


async def test_empty_text_is_refused(deployment: Deployment) -> None:
    answer = await deployment.client.post("/onboarding/tell-me", json={"text": ""})
    assert answer.status_code == 422
