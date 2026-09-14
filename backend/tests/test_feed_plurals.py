"""A count agrees with its noun in every feed line (plain words): never "1 times", "1 days",
"1 people". Each template has its one-form in every language, looked up by `counted`."""

from __future__ import annotations

from typing import Any

from app.delivery.strings import (
    CAREGIVER_DUTY_LINES,
    CAREGIVER_DUTY_LINES_ONE,
    counted,
    render,
)
from app.safety.plain_words import verify
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment

LANGUAGES = ("en", "ms", "zh")
TABLET = {"en": "your blood pressure tablet", "ms": "ubat darah tinggi", "zh": "降压药"}


def _story(language: str, count: int) -> tuple[str, ...]:
    return render("story_count", language, body=(counted("story_count", count),), count=count).body


def _reorder_why(language: str, days: int) -> str:
    return render(
        "reorder",
        language,
        body=(),
        why=counted("reorder", days),
        medicine=TABLET[language],
        days=days,
    ).why


def test_the_story_count_says_1_time_and_3_times() -> None:
    assert _story("en", 1)[0] == "You have written your blood pressure down 1 time."
    assert _story("en", 3)[0] == "You have written your blood pressure down 3 times."


def test_the_reorder_why_says_1_day_and_5_days() -> None:
    assert _reorder_why("en", 1) == "You have about 1 day of your blood pressure tablet left."
    assert _reorder_why("en", 5) == "You have about 5 days of your blood pressure tablet left."


def test_the_caregiver_duty_line_says_1_person_and_2_people() -> None:
    assert (
        CAREGIVER_DUTY_LINES_ONE[0].format(name="Pa")
        == "1 person holds a key to Pa's record today."
    )
    assert (
        CAREGIVER_DUTY_LINES[0].format(count=2, name="Pa")
        == "2 people hold a key to Pa's record today."
    )


def test_every_language_has_both_forms_and_they_pass_plain_words() -> None:
    for language in LANGUAGES:
        for count in (1, 2, 7):
            lines = [*_story(language, count), _reorder_why(language, count)]
            for line in lines:
                assert "{" not in line, line
                failures = [f for f in verify(line, language, "line") if f.severity == "fail"]
                assert not failures, (language, line, failures)
            if language == "en":
                assert (
                    not any(f"{count} times" in line or f"{count} days" in line for line in lines)
                    or count != 1
                )


async def _first_pages(deployment: Deployment, profile_id: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(3):
        params = {"cursor": cursor} if cursor else {}
        page = (
            await deployment.client.get(
                f"/profiles/{profile_id}/feed", params=params, headers=bearer(token)
            )
        ).json()
        items.extend(page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    return items


async def test_one_blood_pressure_makes_the_story_card_say_1_time(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591230001")
    profile_id = await own_profile(deployment, pa)
    written = await deployment.client.post(
        f"/profiles/{profile_id}/readings",
        json={"systolic": 138, "diastolic": 84},
        headers=bearer(pa["token"]),
    )
    assert written.status_code == 201, written.text
    items = await _first_pages(deployment, profile_id, pa["token"])
    count = next(item for item in items if item["headline"] == "The number that only goes up")
    assert count["body"][0] == "You have written your blood pressure down 1 time."
    assert not any("1 times" in line for item in items for line in item["body"] + item["voice"])
