"""The sign-in SMS and the capture messages are in his language (#127).

#125 wrote the Malay and Chinese lines in `app.channels.strings`. These check that the line
sent is the one in his language: the sign-in SMS in the language picked on the sign-in
screen, else the one his number's profile speaks, else English; the capture messages in the
language of his settings (E01, in State). A language Nura has no lines in falls back to
English, and one the sign-in screen does not offer is refused at the door.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.channels.strings import TEXT
from app.clock import FrozenClock
from app.identity.models import Profile
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import pdf, photo, voice
from tests.conftest import Deployment
from tests.onboarding_support import SETTINGS
from tests.paper import CLINIC_SLIP, RECEIPT
from tests.voice_notes import MUMBLED

PA = "+6591270001"
LANGUAGES = ["en", "ms", "zh"]
FIRST_LINE = {
    "en": "Your Nura code is {code}.",
    "ms": "Kod Nura anda ialah {code}.",
    "zh": "您的 Nura 验证码是 {code}。",
}
"""Each language's first line, written out so the test is not the catalogue against itself."""
AFTER_THE_SLIP = datetime(2026, 9, 14, 4, 0, tzinfo=UTC)


async def _ask(deployment: Deployment, language: str | None = None) -> list[str]:
    """Ask for a sign-in code for Pa's number; the lines of the message the phone got."""
    body = {"phone_e164": PA} | ({} if language is None else {"language": language})
    started = await deployment.client.post("/auth/phone/start", json=body)
    assert started.status_code == 202, started.text
    return deployment.sender.last_message(PA).splitlines()


def _sms(deployment: Deployment, language: str) -> list[str]:
    code = deployment.sender.last_code(PA)
    return [line.format(code=code) for line in TEXT[language]["phone_code_self"]]


async def _speaks(deployment: Deployment, profile_id: str, language: str) -> None:
    """Set the profile's language behind the API's back: one Nura has no lines in."""
    async with deployment.sessions() as session:
        await session.execute(
            update(Profile).where(Profile.id == uuid.UUID(profile_id)).values(language=language)
        )
        await session.commit()


# --- the sign-in SMS ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_sign_in_sms_is_in_the_language_picked_on_the_screen(
    deployment: Deployment, language: str
) -> None:
    sent = await _ask(deployment, language)
    assert sent == _sms(deployment, language)
    assert sent[0] == FIRST_LINE[language].format(code=deployment.sender.last_code(PA))


@pytest.mark.parametrize("language", LANGUAGES)
async def test_with_nothing_picked_the_sms_is_in_his_profiles_language(
    deployment: Deployment, language: str
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    await own_profile(deployment, pa, language=language)
    assert await _ask(deployment) == _sms(deployment, language)


async def test_the_language_picked_on_the_screen_wins_over_his_profiles(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    await own_profile(deployment, pa, language="ms")
    assert await _ask(deployment, "zh") == _sms(deployment, "zh")


async def test_a_number_nura_does_not_know_is_sent_english(deployment: Deployment) -> None:
    assert await _ask(deployment) == _sms(deployment, "en")


async def test_a_profile_language_with_no_sms_falls_back_to_english(
    deployment: Deployment,
) -> None:
    pa = await register_by_phone(deployment, PA, "Pa")
    await _speaks(deployment, await own_profile(deployment, pa, language="ms"), "ta")
    assert await _ask(deployment) == _sms(deployment, "en")


async def test_a_language_the_sign_in_screen_does_not_offer_is_refused_at_the_door(
    deployment: Deployment,
) -> None:
    for unknown in ("fr", "ta", "en-SG", "EN", ""):
        refused = await deployment.client.post(
            "/auth/phone/start", json={"phone_e164": PA, "language": unknown}
        )
        assert refused.status_code == 422, (unknown, refused.text)
    with pytest.raises(KeyError):
        deployment.sender.last_message(PA)


# --- the capture messages ----------------------------------------------------------------------


async def _capture(deployment: Deployment, profile_id: str, his: dict[str, str]) -> list[list[str]]:
    """A clinic slip with a field Nura cannot read, a receipt sent as a paper, and a voice note
    nothing was heard in: the three lines the capture routes say about them."""
    slip = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(CLINIC_SLIP, hint="clinic_slip"), headers=his
    )
    assert slip.status_code == 201, slip.text
    (frequency,) = [f for f in slip.json()["fields"] if f["attribute"] == "frequency"]
    receipt = await deployment.client.post(
        f"/profiles/{profile_id}/imports", json=pdf(RECEIPT, source="email"), headers=his
    )
    assert receipt.status_code == 201, receipt.text
    reading = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 138, "diastolic": 84}, headers=his
    )
    assert reading.status_code == 201, reading.text
    note = await deployment.client.post(
        f"/profiles/{profile_id}/events/{reading.json()['event_id']}/notes",
        json=voice(MUMBLED),
        headers=his,
    )
    assert note.status_code == 201, note.text
    return [frequency["prompt"], receipt.json()["notice"], note.json()["notice"]]


def _capture_lines(language: str) -> list[list[str]]:
    keys = ("could_not_read", "not_a_health_paper", "could_not_hear")
    return [list(TEXT[language][key]) for key in keys]


@pytest.mark.parametrize("language", LANGUAGES)
async def test_the_capture_messages_are_in_the_language_of_his_settings(
    deployment: Deployment, clock: FrozenClock, language: str
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    saved = await deployment.client.put(
        f"/profiles/{profile_id}/settings", json={**SETTINGS, "language": language}, headers=his
    )
    assert saved.status_code == 200, saved.text
    assert await _capture(deployment, profile_id, his) == _capture_lines(language)


async def test_capture_messages_in_a_language_with_no_lines_fall_back_to_english(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(AFTER_THE_SLIP)
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="ms")
    await _speaks(deployment, profile_id, "ta")
    assert await _capture(deployment, profile_id, bearer(pa["token"])) == _capture_lines("en")
