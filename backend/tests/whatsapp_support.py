"""One family on WhatsApp, for the service tests: Pa owns his profile, Mei is his chief.

Pa has agreed to WhatsApp (unless a test says otherwise), so the number may keep a thread
with him and send him his morning card. Everything runs on the fixture provider, which sends
into a list and serves media from `tests/fixtures/whatsapp/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.api.deps import Providers
from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.config import BusinessNumber, business_number_for
from app.channels.whatsapp.inbound import Handled, handle_inbound
from app.channels.whatsapp.provider import DevInbound, FixtureProvider
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import grant_consent
from app.db import utcnow
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.drugs.fixture import FixtureRegistry
from app.identity.models import Person, Profile
from app.identity.providers import LoggingCodeSender
from app.identity.service import create_own_profile, register_person
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.keys.context import KeyContext, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.reasoning.ranges import FixtureRanges
from app.regions import Region
from app.settings import Settings
from tests.conftest import FEED, WHATSAPP_FIXTURES, WHATSAPP_SECRET
from tests.paper import PAPER
from tests.support import OPENING_CONSENT, agree_to_family_sharing
from tests.voice_notes import VOICE

PA = "+6591110001"
MEI = "+6591110002"
KIT = "+6591110003"
SITI = "+6591110004"


@dataclass(slots=True)
class Family:
    settings: Settings
    providers: Providers
    number: BusinessNumber
    pa: Person
    profile: Profile
    owner: KeyContext
    mei: Person
    chief: KeyContext

    @property
    def whatsapp(self) -> FixtureProvider:
        assert isinstance(self.providers.whatsapp, FixtureProvider)
        return self.providers.whatsapp

    async def inbound(
        self,
        session: AsyncSession,
        from_e164: str,
        text: str | None = None,
        *,
        media_id: str | None = None,
        content_type: str | None = None,
        group_id: str | None = None,
    ) -> Handled:
        message = DevInbound(
            from_e164=from_e164,
            text=text,
            media_id=media_id,
            content_type=content_type,
            group_id=group_id,
        ).as_message(utcnow())
        return await handle_inbound(
            session,
            settings=self.settings,
            providers=self.providers,
            number=self.number,
            classifier=RuleClassifier(),
            message=message,
        )


def deployment(tmp_path: Path, region: Region = Region.SG) -> tuple[Settings, Providers]:
    settings = Settings(
        region=region,
        database_url="sqlite+aiosqlite://",
        dev_code_sender=True,
        whatsapp_dev_secret=WHATSAPP_SECRET,
    )
    providers = Providers(
        code_sender=LoggingCodeSender(),
        object_store=LocalObjectStore(tmp_path, region),
        extractor=FixtureExtractor(PAPER),
        transcriber=FixtureTranscriber(VOICE, region),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=FixtureRegistry.load(),
        whatsapp=FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES),
        reference_ranges=FixtureRanges.load(),
    )
    return settings, providers


async def family(
    session: AsyncSession,
    tmp_path: Path,
    *,
    whatsapp_consent: bool = True,
    mei_scopes: frozenset[Scope] | None = None,
    mei_role: KeyRole = KeyRole.CHIEF,
) -> Family:
    settings, providers = deployment(tmp_path)
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164=PA, language="en"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    mei = await register_person(
        session, region=Region.SG, display_name="Mei", phone_e164=MEI, language="en"
    )
    scopes = mei_scopes if mei_scopes is not None else frozenset(Scope) - {Scope.PROFILE}
    await agree_to_family_sharing(session, owner, mei, scopes=scopes, relationship="your daughter")
    await grant_key(session, context=owner, holder=mei, role=mei_role, scopes=scopes)
    chief = await resolve_key_context(
        session, region=Region.SG, person_id=mei.id, profile_id=profile.id
    )
    if whatsapp_consent:
        await grant_consent(
            session,
            context=owner,
            purpose=ConsentPurpose.WHATSAPP,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="en",
        )
    return Family(
        settings=settings,
        providers=providers,
        number=business_number_for(settings),
        pa=pa,
        profile=profile,
        owner=owner,
        mei=mei,
        chief=chief,
    )
