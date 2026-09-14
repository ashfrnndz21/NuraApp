"""Registration: one account per phone number, pinned to the region that registered it."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.service import AlreadyRegistered, register_person
from app.regions import OutOfRegion, Region
from app.settings import MissingSetting, Settings, load_settings


async def test_two_siblings_setting_up_from_one_number_get_one_account(sg: AsyncSession) -> None:
    first = await register_person(
        sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    again = await register_person(
        sg, region=Region.SG, display_name="Pa (again)", phone_e164="+6591110001"
    )
    assert again.id == first.id
    assert again.display_name == "Pa"


async def test_an_account_keeps_the_region_it_registered_in(sg: AsyncSession) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    assert pa.region is Region.SG
    with pytest.raises(OutOfRegion):
        await register_person(
            sg, region=Region.MY, display_name="Pa", phone_e164="+6591110001"
        )


async def test_an_email_belongs_to_one_account(sg: AsyncSession) -> None:
    await register_person(sg, region=Region.SG, display_name="Ash", email="ash@example.com")
    with pytest.raises(AlreadyRegistered):
        await register_person(sg, region=Region.SG, display_name="Ash", email="ash@example.com")


def test_a_deployment_that_cannot_name_its_region_does_not_start() -> None:
    with pytest.raises(MissingSetting):
        load_settings({"NURA_DATABASE_URL": "postgresql+asyncpg://localhost/nura"})
    assert load_settings(
        {"NURA_REGION": "MY", "NURA_DATABASE_URL": "postgresql+asyncpg://localhost/nura"}
    ) == Settings(region=Region.MY, database_url="postgresql+asyncpg://localhost/nura")
