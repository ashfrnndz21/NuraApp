"""The sharing preview (W3 onboarding's invite, on E12's consent): the words the owner reads
before he lets someone in are the words the consent keeps, word for word; the preview writes
nothing but its READ; a person let in by phone is named by the owner, never by the account the
number may already be, and that typed name gives way to the person's own when he signs in."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.audit.models import Action, AuditEntry, Outcome
from app.consent.models import Consent, ConsentPurpose
from app.identity.models import Person
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.test_doors import _mei_sets_up_pa

PA = "+6591130001"
MEI = "+6591130002"
NEW_NUMBER = "+6591130003"
PARTS = ["medicines", "visits"]
EVERYTHING = [
    "medicines",
    "visits",
    "readings",
    "records",
    "notes",
    "money",
    "family",
    "emergency",
    "ask",
    "send",
]


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    pa = await register_by_phone(deployment, PA, display_name="Pa")
    return pa, await own_profile(deployment, pa)


def _ask(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "holder_phone_e164": MEI,
        "holder_display_name": "Mei",
        "scopes": PARTS,
        "relationship": "daughter",
        "language": "en",
    }
    body.update(overrides)
    return body


async def _preview(deployment: Deployment, token: str, profile_id: str, **overrides: object):  # type: ignore[no-untyped-def]
    return await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing/preview",
        json=_ask(**overrides),
        headers=bearer(token),
    )


async def _agree(deployment: Deployment, token: str, profile_id: str, **overrides: object):  # type: ignore[no-untyped-def]
    return await deployment.client.post(
        f"/profiles/{profile_id}/consents/sharing",
        json={**_ask(**overrides), "captured_via": "app"},
        headers=bearer(token),
    )


async def _refused(deployment: Deployment, profile_id: str) -> list[str]:
    """The refusals on his trail, by name, oldest first."""
    async with deployment.sessions() as db:
        found = await db.scalars(
            select(AuditEntry.refused_because)
            .where(
                AuditEntry.profile_id == uuid.UUID(profile_id),
                AuditEntry.outcome == Outcome.REFUSED,
            )
            .order_by(AuditEntry.at)
        )
        return [name for name in found if name is not None]


async def _person(deployment: Deployment, phone: str) -> Person | None:
    async with deployment.sessions() as db:
        found: Person | None = await db.scalar(select(Person).where(Person.phone_e164 == phone))
        return found


@pytest.mark.parametrize("language", ["en", "ms", "zh"])
async def test_the_preview_is_the_words_the_consent_keeps(
    deployment: Deployment, language: str
) -> None:
    pa, profile_id = await _pa(deployment)
    shown = await _preview(deployment, pa["token"], profile_id, language=language)
    assert shown.status_code == 200, shown.text
    preview = shown.json()
    agreed = await _agree(
        deployment,
        pa["token"],
        profile_id,
        language=language,
        wording_version=preview["wording_version"],
    )
    assert agreed.status_code == 201, agreed.text
    assert agreed.json()["wording_text"].split("\n") == preview["lines"]
    assert agreed.json()["text_version"] == preview["wording_version"]


async def test_the_preview_writes_nothing_but_its_read(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)

    async def reads() -> int:
        async with deployment.sessions() as db:
            counted: int = (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditEntry)
                    .where(
                        AuditEntry.profile_id == uuid.UUID(profile_id),
                        AuditEntry.action == Action.READ,
                        AuditEntry.target == "consent",
                        AuditEntry.outcome == Outcome.ALLOWED,
                    )
                )
                or 0
            )
            return counted

    before = await reads()
    shown = await _preview(
        deployment,
        pa["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Ah Kow",
    )
    assert shown.status_code == 200, shown.text
    assert await reads() == before + 1
    assert await _person(deployment, NEW_NUMBER) is None
    async with deployment.sessions() as db:
        shares = await db.scalar(
            select(func.count())
            .select_from(Consent)
            .where(Consent.purpose == ConsentPurpose.SHARE_WITH_PERSON)
        )
    assert shares == 0


@pytest.mark.parametrize("name", [None, "", "   "])
async def test_a_person_let_in_by_phone_needs_a_name(
    deployment: Deployment, name: str | None
) -> None:
    pa, profile_id = await _pa(deployment)
    shown = await _preview(
        deployment, pa["token"], profile_id, holder_phone_e164=NEW_NUMBER, holder_display_name=name
    )
    assert shown.status_code == 400
    assert shown.json() == {"refusal": "HolderNeedsAName"}
    agreed = await _agree(
        deployment, pa["token"], profile_id, holder_phone_e164=NEW_NUMBER, holder_display_name=name
    )
    assert agreed.status_code == 400
    assert agreed.json() == {"refusal": "HolderNeedsAName"}
    assert await _person(deployment, NEW_NUMBER) is None
    # Both refusals are on his trail (#156): the preview's, and the agreement's past its door.
    assert await _refused(deployment, profile_id) == ["HolderNeedsAName", "HolderNeedsAName"]


async def test_a_person_who_is_nobody_here_is_refused_on_his_trail(
    deployment: Deployment,
) -> None:
    """#156: an id that names nobody in this region is refused, by the preview and by the
    agreement alike, and each refusal is written on the owner's trail."""
    pa, profile_id = await _pa(deployment)
    nobody = {"holder_phone_e164": None, "holder_person_id": str(uuid.uuid4())}
    shown = await _preview(deployment, pa["token"], profile_id, **nobody)
    assert shown.status_code == 403
    assert shown.json() == {"refusal": "NoSuchHolder"}
    agreed = await _agree(deployment, pa["token"], profile_id, **nobody)
    assert agreed.status_code == 403
    assert agreed.json() == {"refusal": "NoSuchHolder"}
    assert await _refused(deployment, profile_id) == ["NoSuchHolder", "NoSuchHolder"]


async def test_the_words_use_the_name_he_typed_never_the_accounts(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    await register_by_phone(deployment, MEI, display_name="Mei Ling Tan")
    shown = await _preview(deployment, pa["token"], profile_id)
    text = "\n".join(shown.json()["lines"])
    assert "Mei" in text
    assert "Ling" not in text
    agreed = await _agree(deployment, pa["token"], profile_id)
    assert agreed.status_code == 201, agreed.text
    assert "Ling" not in agreed.json()["wording_text"]
    mei = await _person(deployment, MEI)
    assert mei is not None
    assert (mei.display_name, mei.named_by_person_id) == ("Mei Ling Tan", None)


async def test_the_typed_name_gives_way_to_the_persons_own(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    agreed = await _agree(
        deployment,
        pa["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Ah Kow",
    )
    assert agreed.status_code == 201, agreed.text
    placeholder = await _person(deployment, NEW_NUMBER)
    assert placeholder is not None
    assert (placeholder.display_name, placeholder.named_by_person_id) == (
        "Ah Kow",
        uuid.UUID(pa["person_id"]),
    )

    await register_by_phone(deployment, NEW_NUMBER)  # signing in without a name keeps it
    still = await _person(deployment, NEW_NUMBER)
    assert still is not None and still.display_name == "Ah Kow"

    await register_by_phone(deployment, NEW_NUMBER, display_name="Tan Ah Kow")
    his = await _person(deployment, NEW_NUMBER)
    assert his is not None
    assert (his.display_name, his.named_by_person_id) == ("Tan Ah Kow", None)

    await register_by_phone(deployment, NEW_NUMBER, display_name="Someone Else")
    kept = await _person(deployment, NEW_NUMBER)
    assert kept is not None and kept.display_name == "Tan Ah Kow"


async def test_the_steward_setting_up_for_him_previews(deployment: Deployment) -> None:
    mei, profile_id = await _mei_sets_up_pa(deployment)
    shown = await _preview(
        deployment,
        mei["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Siti",
        relationship="helper",
    )
    assert shown.status_code == 200, shown.text


async def test_a_chief_key_does_not_preview_words_it_cannot_give(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    await let_in(
        deployment,
        pa,
        profile_id,
        MEI,
        EVERYTHING,
        relationship="daughter",
        holder_display_name="Mei",
        role="chief",
    )
    key = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "chief"},
        headers=bearer(pa["token"]),
    )
    assert key.status_code == 201, key.text
    mei = await register_by_phone(deployment, MEI, display_name="Mei")
    refused = await _preview(
        deployment,
        mei["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Siti",
    )
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "NotTheirConsentToGive"}


BROTHER = "+6591130004"


async def test_a_refused_caller_leaves_no_account_behind(deployment: Deployment) -> None:
    pa, profile_id = await _pa(deployment)
    # A caregiver's key has no family scope: refused at the door.
    await let_in(
        deployment,
        pa,
        profile_id,
        MEI,
        ["medicines"],
        relationship="daughter",
        holder_display_name="Mei",
        role="caregiver",
    )
    carer = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": MEI, "role": "caregiver", "scopes": ["medicines"]},
        headers=bearer(pa["token"]),
    )
    assert carer.status_code == 201, carer.text
    mei = await register_by_phone(deployment, MEI, display_name="Mei")
    refused = await _agree(
        deployment,
        mei["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Siti",
    )
    assert refused.status_code == 403
    assert refused.json()["refusal"] == "OutOfScope"
    assert await _person(deployment, NEW_NUMBER) is None

    # A chief holds the family scope, but this route is the owner's own yes: refused too.
    await let_in(
        deployment,
        pa,
        profile_id,
        BROTHER,
        EVERYTHING,
        relationship="son",
        holder_display_name="Kit",
        role="chief",
    )
    chief = await deployment.client.post(
        f"/profiles/{profile_id}/keys",
        json={"holder_phone_e164": BROTHER, "role": "chief"},
        headers=bearer(pa["token"]),
    )
    assert chief.status_code == 201, chief.text
    kit = await register_by_phone(deployment, BROTHER, display_name="Kit")
    refused = await _agree(
        deployment,
        kit["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Siti",
    )
    assert refused.status_code == 403
    assert refused.json() == {"refusal": "NotTheirConsentToGive"}
    assert await _person(deployment, NEW_NUMBER) is None

    # Both refusals are on the owner's trail, and the owner himself still can.
    async with deployment.sessions() as db:
        refusals = (
            await db.scalars(
                select(AuditEntry.refused_because).where(
                    AuditEntry.profile_id == uuid.UUID(profile_id),
                    AuditEntry.outcome == Outcome.REFUSED,
                )
            )
        ).all()
    assert {"OutOfScope", "NotTheirConsentToGive"} <= set(refusals)
    agreed = await _agree(
        deployment,
        pa["token"],
        profile_id,
        holder_phone_e164=NEW_NUMBER,
        holder_display_name="Siti",
    )
    assert agreed.status_code == 201, agreed.text
