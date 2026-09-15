"""The numbers and words the redesigned Today and Home read from the backend (D1).

    GET /profiles/{id}/medicines/now   the one big number on his Today, and what it counts
    GET /profiles/{id}/state           the posture as a word and a line, and its drivers
    GET /profiles/{id}/changes         each line with the tone of its dot

The client composes no sentence about his record: the hero's number and words, the State's
word, line and chips, and the colour of each dot in "What changed" all come from here.
"""

from __future__ import annotations

from typing import Any

from app.channels.state_words import said
from app.medicines.service import Slot, due_now
from app.state.models import Dimension, Posture
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

PA = "+6591110001"


def _slot(anchor: str, *, taken: bool = False, due: bool = False, missed: bool = False) -> Slot:
    return Slot(
        line=None,  # type: ignore[arg-type]  # the count reads the moments, never the line
        anchor=anchor,
        card="",
        taken=taken,
        taken_label="Taken",
        due_now=due,
        missed=missed,
    )


def test_the_hero_counts_the_tablets_due_at_the_moment_that_is_open() -> None:
    slots = [_slot("breakfast", due=True), _slot("breakfast", due=True), _slot("dinner")]
    found = due_now(slots, "en")
    assert found is not None
    assert (found.count, found.anchor, found.words) == (2, "breakfast", "medicines with breakfast")


def test_with_nothing_open_the_hero_counts_the_next_moment_still_to_come() -> None:
    slots = [
        _slot("breakfast", taken=True),
        _slot("lunch", missed=True),
        _slot("dinner"),
        _slot("bed"),
    ]
    found = due_now(slots, "en")
    assert found is not None
    assert (found.count, found.anchor, found.words) == (1, "dinner", "medicine with dinner")
    assert due_now(slots, "ms") == found.__class__(1, "dinner", "ubat bersama makan malam")
    assert due_now(slots, "zh") == found.__class__(1, "dinner", "种药，晚餐时吃")


def test_with_everything_taken_or_passed_there_is_no_number() -> None:
    assert due_now([_slot("breakfast", taken=True), _slot("bed", missed=True)], "en") is None
    assert due_now([], "en") is None


def test_the_state_is_said_in_his_language_naming_only_what_it_has_words_for() -> None:
    dimensions: dict[Dimension, Any] = {
        Dimension.CLINICAL: {
            "because": [
                {"posture": "watch", "subject": "hypertension", "fact_id": "f1"},
                {"posture": "watch", "subject": "a_code_nobody_has_words_for", "fact_id": "f2"},
                {"posture": "act", "episode_id": "e1", "episode_kind": "admission"},
            ]
        },
        Dimension.SITUATIONAL: {"because": [], "phase": "before_visit"},
        Dimension.FAMILY: None,  # a dimension this key does not read
    }
    english = said(Posture.ACT, dimensions, "en")
    assert english.word == "One thing today"
    assert english.line == "There is one thing for you to do today."
    assert [(d.key, d.text, d.tone) for d in english.drivers] == [
        ("subject:hypertension", "Blood pressure", "watch"),
        ("episode:admission", "In hospital", "act"),
        ("phase:before_visit", "A visit this week", None),
    ]
    malay = said(Posture.ACT, dimensions, "ms")
    assert malay.word == "Satu perkara hari ini"
    assert [d.text for d in malay.drivers] == ["Tekanan darah", "Di hospital", "Lawatan minggu ini"]
    steady = said(Posture.STABLE, {Dimension.SITUATIONAL: {"phase": "steady"}}, "xx")
    assert (steady.word, steady.line, steady.drivers) == ("Steady", "Nothing needs you today.", ())


async def test_the_routes_answer_with_the_words_and_numbers(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    client = deployment.client

    state = await client.get(f"/profiles/{profile_id}/state", headers=his)
    assert state.status_code == 200, state.text
    body = state.json()
    assert (body["word"], body["line"], body["drivers"]) == (
        "Steady",
        "Nothing needs you today.",
        [],
    )
    chinese = (await client.get(f"/profiles/{profile_id}/state?language=zh", headers=his)).json()
    assert (chinese["word"], chinese["line"]) == ("平稳", "今天没有需要您处理的事。")

    # No medicines: no number, no words — never a zero he did not earn.
    now = await client.get(f"/profiles/{profile_id}/medicines/now", headers=his)
    assert now.status_code == 200, now.text
    assert now.json() == {"count": None, "anchor": None, "words": None}

    changes = await client.get(f"/profiles/{profile_id}/changes", headers=his)
    assert changes.status_code == 200, changes.text
    lines = changes.json()["lines"]
    assert lines and all("tone" in line for line in lines)
    assert lines[0]["section"] == "look" and lines[0]["tone"] is None
