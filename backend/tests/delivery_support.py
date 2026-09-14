"""The channels a service test sends through, and the household every E11 test starts from.

`via_for(region)` is what a route would pass: a dev run's settings, the fixture providers (the
WhatsApp fixture keeps every send in a list, the push fixture reaches only registered people,
the voice fixture says a card as silence of the right length) and the business number.

`home(...)` is Pa (his own profile, WhatsApp agreed, in English), on amlodipine at breakfast
from a label with 30 tablets dispensed; Mei his daughter and chief; Siti the helper (medicines,
emergency, send), in Malay; and the roster: Mei on duty every day but a slot the test can
change. Every key rests on Pa's own consent, as in checkpoint 4.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.api.deps import Providers
from app.channels.whatsapp.classifier import RuleClassifier
from app.channels.whatsapp.inbound import Handled, handle_inbound
from app.channels.whatsapp.provider import DevInbound, FixtureProvider
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import grant_consent
from app.db import utcnow
from app.delivery.feed.compress import FixtureCompressor, FixtureSearcher
from app.delivery.push import FixturePush
from app.delivery.triggers.deliver import Via
from app.delivery.voice import FixtureVoice
from app.drugs.fixture import FixtureRegistry
from app.family.roster import add_slot
from app.identity.models import Person
from app.identity.providers import LoggingCodeSender
from app.identity.service import create_own_profile, register_person
from app.ingestion.extract import FixtureExtractor
from app.ingestion.objects import LocalObjectStore
from app.ingestion.transcribe import FixtureTranscriber
from app.keys.context import KeyContext, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import ROLE_SCOPES, KeyRole, Scope
from app.medicines.models import MedicationLine
from app.reasoning.visits.summary import FixtureSummariser
from app.regions import Region
from app.settings import Settings
from tests.conftest import FEED, VISITS, WHATSAPP_FIXTURES, WHATSAPP_SECRET
from tests.medicines_support import add, label
from tests.paper import PAPER
from tests.support import OPENING_CONSENT, agree_to_family_sharing
from tests.voice_notes import VOICE

PA = "+6591110051"
MEI = "+6592220051"
SITI = "+6597770051"
KIT = "+6595550051"


def via_for(region: Region = Region.SG, root: Path | None = None) -> Via:
    """A dev run's channels for one region: fixtures all the way, nothing leaves the process."""
    settings = Settings(
        region=region,
        database_url="sqlite+aiosqlite://",
        dev_code_sender=True,
        whatsapp_dev_secret=WHATSAPP_SECRET,
    )
    store_root = root or Path(tempfile.mkdtemp(prefix="nura-delivery-"))
    providers = Providers(
        code_sender=LoggingCodeSender(),
        object_store=LocalObjectStore(store_root, region),
        extractor=FixtureExtractor(PAPER),
        summariser=FixtureSummariser(VISITS),
        transcriber=FixtureTranscriber(VOICE, region),
        searcher=FixtureSearcher(FEED),
        compressor=FixtureCompressor(FEED),
        drug_registry=FixtureRegistry.load(),
        whatsapp=FixtureProvider(secret=WHATSAPP_SECRET, fixtures=WHATSAPP_FIXTURES),
        voice=FixtureVoice(),
        push=FixturePush(),
    )
    return Via.of(settings, providers)


@dataclass(slots=True)
class Home:
    via: Via
    owner: KeyContext
    pa: Person
    mei: Person
    siti: Person
    line: MedicationLine

    @property
    def whatsapp(self) -> FixtureProvider:
        assert isinstance(self.via.providers.whatsapp, FixtureProvider)
        return self.via.providers.whatsapp

    @property
    def push(self) -> FixturePush:
        assert isinstance(self.via.providers.push, FixturePush)
        return self.via.providers.push

    async def ctx(self, session: AsyncSession, person: Person) -> KeyContext:
        return await resolve_key_context(
            session, region=Region.SG, person_id=person.id, profile_id=self.owner.profile_id
        )

    async def inbound(self, session: AsyncSession, from_e164: str, text: str) -> Handled:
        """A message to the number, through the webhook's own path, at the clock's moment."""
        return await handle_inbound(
            session,
            settings=self.via.settings,
            providers=self.via.providers,
            number=self.via.number,
            classifier=RuleClassifier(),
            message=DevInbound(from_e164=from_e164, text=text).as_message(utcnow()),
        )

    def sent_to(self, person: Person) -> list[str]:
        """The words each WhatsApp message to this person said, oldest first."""
        return [one.text for one in self.whatsapp.sent if one.to_e164 == person.phone_e164]


async def home(
    session: AsyncSession,
    tmp_path: Path,
    *,
    whatsapp: bool = True,
    quantity: int = 30,
    roster: bool = True,
) -> Home:
    via = via_for(Region.SG, tmp_path)
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164=PA, language="en"
    )
    profile = await create_own_profile(
        session, region=Region.SG, owner=pa, consent=OPENING_CONSENT, language="en"
    )
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    mei = await register_person(
        session, region=Region.SG, display_name="Mei", phone_e164=MEI, language="en"
    )
    siti = await register_person(
        session, region=Region.SG, display_name="Siti", phone_e164=SITI, language="ms"
    )
    everything = frozenset(Scope) - {Scope.PROFILE}
    await agree_to_family_sharing(session, owner, mei, scopes=everything, relationship="daughter")
    await grant_key(session, context=owner, holder=mei, role=KeyRole.CHIEF, scopes=everything)
    helper = ROLE_SCOPES[KeyRole.HELPER]
    await agree_to_family_sharing(session, owner, siti, scopes=helper, relationship="helper")
    await grant_key(session, context=owner, holder=siti, role=KeyRole.HELPER)
    if whatsapp:
        await grant_consent(
            session,
            context=owner,
            purpose=ConsentPurpose.WHATSAPP,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="en",
        )
    if roster:
        await add_slot(
            session,
            context=owner,
            person_id=mei.id,
            role=KeyRole.CHIEF,
            from_time=time(6, 0),
            to_time=time(23, 0),
            weekdays=list(range(7)),
        )
    made = await add(session, owner, label("amlodipine", "5 mg", "1 tab OM", quantity=quantity))
    assert made.line is not None
    return Home(via=via, owner=owner, pa=pa, mei=mei, siti=siti, line=made.line)
