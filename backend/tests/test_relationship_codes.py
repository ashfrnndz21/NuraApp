"""Who someone is to him is a code, said in each reader's language (#137's review).

The doors take one of a closed set of codes — never words — and the backend says it to
whoever reads it: in the words of an agreement, on the claim, on the stewardship."""

from __future__ import annotations

from app.clock import FrozenClock
from app.family.relationships import RELATIONSHIP_WORDS, Relationship, relationship_words
from app.safety.plain_words import verify
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.family_support import MONDAY
from tests.test_doors import _for_someone

PA, MEI = "+6591116601", "+6592226602"


async def test_the_words_of_letting_someone_in_say_the_code_in_their_language(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    pa = await register_by_phone(deployment, PA, "Pa", "en")
    profile_id = await own_profile(deployment, pa, display_name="Pa", language="en")
    body = {
        "holder_phone_e164": MEI,
        "holder_display_name": "Mei",
        "scopes": ["medicines"],
        "role": "caregiver",
        "window": "always",
        "relationship": "daughter",
    }
    said = {}
    for language in ("en", "ms", "zh"):
        preview = await deployment.client.post(
            f"/profiles/{profile_id}/consents/sharing/preview",
            json={**body, "language": language},
            headers=bearer(pa["token"]),
        )
        assert preview.status_code == 200, preview.text
        said[language] = preview.json()["lines"][0]
    assert "Mei, your daughter," in said["en"]
    assert "Mei, anak perempuan anda," in said["ms"]
    assert "Mei（您的女儿）" in said["zh"]
    # Words are not a code: the doors take the closed set and nothing else.
    for words in ("your daughter", "anak perempuan", "Father"):
        typed = await deployment.client.post(
            f"/profiles/{profile_id}/consents/sharing/preview",
            json={**body, "relationship": words, "language": "en"},
            headers=bearer(pa["token"]),
        )
        assert typed.status_code == 422, words


async def test_the_claim_and_the_stewardship_say_who_set_it_up_in_the_readers_words(
    deployment: Deployment, clock: FrozenClock
) -> None:
    clock.set(MONDAY)
    mei = await register_by_phone(deployment, MEI, "Mei", "en")
    made = await deployment.client.post(
        "/profiles/for-someone",
        json=_for_someone(PA, relationship="daughter"),
        headers=bearer(mei["token"]),
    )
    assert made.status_code == 201, made.text
    profile_id = made.json()["profile_id"]
    held = await deployment.client.get(
        f"/profiles/{profile_id}/stewardship",
        params={"language": "zh"},
        headers=bearer(mei["token"]),
    )
    assert held.status_code == 200, held.text
    assert (held.json()["relationship"], held.json()["relationship_words"]) == (
        "daughter",
        "您的女儿",
    )

    pa = await register_by_phone(deployment, PA, "Pa", "ms")
    for language, words in (("en", "your daughter"), ("ms", "anak perempuan anda")):
        offers = await deployment.client.get(
            "/profiles/mine/claimable", params={"language": language}, headers=bearer(pa["token"])
        )
        assert offers.status_code == 200, offers.text
        (offer,) = offers.json()
        assert (offer["relationship"], offer["relationship_words"]) == ("daughter", words)


def test_every_code_is_said_in_every_language_in_plain_words() -> None:
    for language in ("en", "ms", "zh"):
        assert set(RELATIONSHIP_WORDS[language]) == set(Relationship)
        for code in Relationship:
            words = relationship_words(code.value, language)
            assert words is not None
            assert [f for f in verify(words, language, "phrase") if f.severity == "fail"] == []
    # Anything outside the set — a row the migration could not place — is "other", never an error.
    assert relationship_words("cousin twice removed", "en") == "someone you know"
    assert relationship_words(None, "en") is None
    assert relationship_words("son", "ta") == "your son"
