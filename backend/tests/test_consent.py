"""Who may give consent on whose behalf and with what behind it, who may withdraw it, what
the wording catalogue promises, and how each of those lands in the trail."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock as app_clock
from app.audit.access import NotOnThisProfile, person_display_name
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import read_audit
from app.clock import FrozenClock
from app.consent import export, texts
from app.consent.export import (
    CHANNEL_WORDS,
    PURPOSE_TITLES,
    REGION_NAMES,
    PlainTextRenderer,
    basis_lines,
    export_consent_record,
)
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import (
    NoConsentToWithdraw,
    NoHolderNamed,
    NoSuchWitness,
    NotAgreedPerPerson,
    NothingBehindTheBasis,
    NotTheirConsentToGive,
    NotTheirConsentToWithdraw,
    Sharing,
    WordingNotOnFile,
    active_consents,
    grant_consent,
    require_consent,
    revoke_consent,
)
from app.consent.texts import (
    LANGUAGES,
    SCOPE_WORDS,
    ConsentText,
    current_version,
    named_words,
    versions,
    what_lines,
    wording,
)
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, KeyWindow, Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, Recording, SourceChannel
from app.regions import Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing, agree_to_recording

GIVEN_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)

# Every wording on file, by (purpose, version, language, region), as a sha256 of the text.
# Editing shipped words fails this test; the only way to change what a person is asked to
# agree to is a new version, appended below the old one.
SHIPPED_WORDS: dict[tuple[str, str, str, str | None], str] = {
    ("hold_health_record", "1", "en", "SG"): (
        "2aea4af78b13a6fdae529b78d1928ff776c5e67bf6e71ba71e34ea48dc02dbf5"
    ),
    ("hold_health_record", "1", "en", "MY"): (
        "63d5b2baeda85fc14284d3457a23928c4c1a0dba749e270002511fbe1840a025"
    ),
    ("hold_health_record", "1", "ms", "SG"): (
        "b009031c9853727a5b02f550187b931e6fcf626f10143faae3a84738e0a1a51f"
    ),
    ("hold_health_record", "1", "ms", "MY"): (
        "0aba6a356b3c07edcd145ad1a64338fbb33c663e652fdbbd55b8645bf5ff9953"
    ),
    ("hold_health_record", "1", "zh", "SG"): (
        "bdec731b3823f2610e38c7d4701971af27bcc389ccb7bcb1fe516af6184df23a"
    ),
    ("hold_health_record", "1", "zh", "MY"): (
        "fc2658c5698e33f0816d9e2eee07e7894bb9e52b930a8b3be68fd9c3fc2af254"
    ),
    ("share_with_family", "1", "en", None): (
        "ef22011a7d39e10bae9b0290acc235434b53573e0590042d574e86cc0e7632a2"
    ),
    ("share_with_family", "2", "en", None): (
        "e2b00d6b1f5072de1d8fc9a3848263de7dd26d41c2377fea7b726ceda0645db0"
    ),
    ("share_with_family", "2", "ms", None): (
        "da5308c6de39947d364fc14432aaf1a7b433bfb6a1585388aa1a0bc7e052d5be"
    ),
    ("share_with_family", "2", "zh", None): (
        "939138cd82fb2d96f9197f221f4a960785d235556908a86e384d6a8c4020bc25"
    ),
    ("share_with_family", "3", "en", None): (
        "f9d77a31e2d3313880d992caf6c5f3646e7a765aae59d9a41d808c3cd5d03464"
    ),
    ("share_with_family", "3", "ms", None): (
        "61f6dd3fa0e43f63c55e3e557138031437503cefd0be208a35ac5c58a27d3ac4"
    ),
    ("share_with_family", "3", "zh", None): (
        "04311f36d040d104e666602f210d89cba383597b851a473273303cbf0ea248eb"
    ),
    ("recording", "1", "en", None): (
        "198f6e974300bd444db2daac51b432a39ddf297f6367cca507712040fb2387dc"
    ),
    ("recording", "1", "ms", None): (
        "1c46a6e298b9f1adc84819a2b2b0989e713352cac13adfbed8129ef256c86870"
    ),
    ("recording", "1", "zh", None): (
        "1bca2bf9b2e3f6cc062def6511c5ab1f2e5657762305caf5540fee98b378487b"
    ),
    ("whatsapp", "1", "en", None): (
        "1283a808cf6d595478dea88539a79a780b501a10e57a52e3a2ecff8c7cea1ed7"
    ),
    ("whatsapp", "1", "ms", None): (
        "12fbab219fbba2bae475b3abc7413b46fb3af3ce4d6f1f0ab79d86b6c50dc0ee"
    ),
    ("whatsapp", "1", "zh", None): (
        "a957b200988658c0da126071b6131cd5fb76a8bee528e24de7ba09f81fcf37e7"
    ),
    ("calendar", "1", "en", None): (
        "98914d5acd8bebbb0d5247644ff80343193ed8d74ebf514a28db6e5dba2384f3"
    ),
    ("calendar", "1", "ms", None): (
        "633cd7218f0fd2523a2117f8909a829bb672e481fb304e3854cd89778b551146"
    ),
    ("calendar", "1", "zh", None): (
        "d4fa59aa40cdd26345edf3ad60a260c49329938faa73cdae71c01fd4a1b5d97d"
    ),
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _pa_and_his_son(session: AsyncSession) -> tuple[KeyContext, KeyContext]:
    """Pa opens his graph, agrees to share with his son and names him chief."""
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    cast(FrozenClock, app_clock.current()).set(GIVEN_AT)
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    son = await register_person(
        session, region=Region.SG, display_name="Son", phone_e164="+6591110004"
    )
    await agree_to_family_sharing(session, owner, son, role=KeyRole.CHIEF)
    await grant_key(session, context=owner, holder=son, role=KeyRole.CHIEF)
    chief = await resolve_key_context(
        session, region=Region.SG, person_id=son.id, profile_id=profile.id
    )
    return owner, chief


async def _letter(session: AsyncSession, context: KeyContext) -> Artifact:
    """A doctor's letter, or an LPA, as a PDF on the profile."""
    cast(FrozenClock, app_clock.current()).set(GIVEN_AT)
    return await store_artifact(
        session,
        context=context,
        kind=ArtifactKind.PDF,
        storage_key="sg/profiles/pa/letter.pdf",
        content_type="application/pdf",
        sha256="c" * 64,
        captured_at=GIVEN_AT,
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )


# --- the wording catalogue ----------------------------------------------------------------


def test_every_purpose_has_current_wording_in_every_language_nura_speaks() -> None:
    assert set(LANGUAGES) == {"en", "ms", "zh"}  # Tamil joins when its words are on file
    for purpose in ConsentPurpose:
        for region in Region:
            for language in LANGUAGES:
                assert wording(purpose, current_version(purpose), language, region) is not None
    keys = [(text.purpose, text.version, text.language, text.region) for text in texts.TEXTS]
    assert len(keys) == len(set(keys))
    assert {text.language for text in texts.TEXTS} <= set(LANGUAGES)


def test_the_sharing_words_name_the_person_and_list_the_parts() -> None:
    for language in ("en", "ms", "zh"):
        assert set(SCOPE_WORDS[language]) == set(Scope) - {Scope.PROFILE}
    assert what_lines({Scope.MEDICINES}, "en") == ["your medicines"]
    assert what_lines({Scope.RECORDS, Scope.MEDICINES, Scope.NOTES}, "en") == [
        "your medicines",
        "your papers",
        "your private notes",
    ]
    assert what_lines((), "en") == ["your papers"]
    assert what_lines({Scope.MEDICINES, Scope.VISITS}, "zh") == ["您的药", "您看医生的记录"]
    # Who they are to him is said the way each language says it, or not at all.
    assert named_words("Ash", None, "zh") == "Ash"
    # The relationship is a code (`app.family.relationships`), said in each language's words.
    assert named_words("Ash", "daughter", "en") == "Ash, your daughter,"
    assert named_words("Ash", "daughter", "ms") == "Ash, anak perempuan anda,"
    assert named_words("Ash", "daughter", "zh") == "Ash（您的女儿）"


def test_shipped_words_are_never_edited_only_appended() -> None:
    on_file = {
        (t.purpose.value, t.version, t.language, t.region.value if t.region else None): _digest(
            t.summary
        )
        for t in texts.TEXTS
    }
    assert on_file == SHIPPED_WORDS


def test_words_that_name_the_country_have_a_twin_per_region() -> None:
    purpose, version = ConsentPurpose.HOLD_HEALTH_RECORD, "1"
    sg_words = wording(purpose, version, "en", Region.SG)
    my_words = wording(purpose, version, "en", Region.MY)
    assert sg_words is not None and "They never leave Singapore." in sg_words
    assert my_words is not None and "They never leave Malaysia." in my_words
    assert sg_words.replace("Singapore", "Malaysia") == my_words


def test_the_current_version_is_the_last_one_appended(monkeypatch: pytest.MonkeyPatch) -> None:
    before = versions(ConsentPurpose.WHATSAPP)
    newer = ConsentText(ConsentPurpose.WHATSAPP, "10", "en", "Newer words.")
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, newer))
    # Appended last is current, whatever the strings would sort to.
    assert versions(ConsentPurpose.WHATSAPP) == [*before, "10"]
    assert current_version(ConsentPurpose.WHATSAPP) == "10"


def test_wording_nobody_was_ever_shown_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    current = current_version(ConsentPurpose.WHATSAPP)
    assert wording(ConsentPurpose.WHATSAPP, "not-a-version", "en", Region.SG) is None
    # A language Nura does not speak has no words, even if the catalogue held some.
    stray = ConsentText(ConsentPurpose.WHATSAPP, current, "xx", "Words in no language.")
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, stray))
    assert wording(ConsentPurpose.WHATSAPP, current, "xx", Region.SG) is None


def test_the_record_can_put_words_to_every_purpose_basis_channel_and_region() -> None:
    assert set(PURPOSE_TITLES) == set(ConsentPurpose)
    for basis in ConsentBasis:
        lines = basis_lines(
            basis, giver="Ash", patient="Pa", patients="Pa's", witness="Mei", recording_kept=True
        )
        assert (lines == []) == (basis is ConsentBasis.OWNER)
        assert all(line.count(". ") == 0 for line in lines), "one idea per line"
    spoken = basis_lines(
        ConsentBasis.VERBAL_RECORDED,
        giver="Ash",
        patient="Pa",
        patients="Pa's",
        witness="Mei",
        recording_kept=True,
    )
    assert spoken == [
        "Pa said yes out loud.",
        "Mei was there and heard Pa say it.",
        "Ash wrote it down here.",
        "Nura kept the recording.",
    ]
    assert set(CHANNEL_WORDS) == set(ConsentChannel)
    assert set(REGION_NAMES) == set(Region)


# --- who may give it, and in which words -------------------------------------------------


async def test_the_owner_consents_for_himself_and_only_on_his_own_basis(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    with pytest.raises(NotTheirConsentToGive):
        clock.set(GIVEN_AT + timedelta(days=1))
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.LPA,
            language="en",
        )
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.action, e.target, e.refused_because) for e in refused] == [
        (Action.WRITE, Consent.__tablename__, "NotTheirConsentToGive")
    ]


async def test_a_chief_consents_for_pa_only_on_a_proxy_basis_with_the_document_behind_it(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, chief = await _pa_and_his_son(sg)

    with pytest.raises(NotTheirConsentToGive):
        await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="en",
        )
    # A bare "doctor's letter" is a claim, not a basis.
    with pytest.raises(NothingBehindTheBasis):
        await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.PAPER,
            basis=ConsentBasis.MEDICAL_LETTER,
            language="en",
        )
    # And a letter on some other profile is no letter at all.
    with pytest.raises(NothingBehindTheBasis):
        await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.PAPER,
            basis=ConsentBasis.MEDICAL_LETTER,
            language="en",
            basis_artifact_id=owner.profile_id,
        )

    letter = await _letter(sg, chief)
    clock.set(GIVEN_AT + timedelta(days=1))
    by_proxy = await grant_consent(
        sg,
        context=chief,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.PAPER,
        basis=ConsentBasis.MEDICAL_LETTER,
        language="en",
        basis_artifact_id=letter.id,
    )
    assert by_proxy.person_id == chief.person_id
    assert by_proxy.basis is ConsentBasis.MEDICAL_LETTER
    assert by_proxy.basis_artifact_id == letter.id

    # It stands for the profile, whoever asks.
    clock.set(GIVEN_AT + timedelta(days=2))
    held = await require_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        scope=Scope.VISITS,
    )
    assert held.consent_id == by_proxy.id

    # And the record says who gave it and on what basis.
    record = await export_consent_record(sg, context=owner)
    entry = next(e for e in record.document["consents"] if e["id"] == str(by_proxy.id))
    assert entry["given_by"] == "Son" and entry["basis"] == "medical_letter"
    page = record.rendered.body.decode()
    assert "- Son said yes on paper on Tuesday 15 September 2026." in page
    assert "  Son said yes for you.\n  A doctor's letter says Son may decide for you." in page


async def test_a_spoken_agreement_needs_someone_else_who_heard_it_and_the_recording(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, chief = await _pa_and_his_son(sg)
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await agree_to_family_sharing(sg, owner, daughter, role=KeyRole.CAREGIVER)
    await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    clock.set(GIVEN_AT)
    # A recording of his spoken yes carries the witness's voice as well as his: a recording of
    # other people, which rests on the RECORDING consent (E16-02, ADR 0003).
    await agree_to_recording(sg, owner)
    recording = await store_artifact(
        sg,
        context=chief,
        kind=ArtifactKind.VOICE,
        storage_key="sg/profiles/pa/said-yes.m4a",
        content_type="audio/mp4",
        sha256="d" * 64,
        captured_at=GIVEN_AT,
        source_channel=SourceChannel.APP,
        region=Region.SG,
        recording=Recording.CONSULT,
    )

    async def spoken(witness: object, artifact: object) -> Consent:
        return await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.WHATSAPP,
            captured_via=ConsentChannel.VERBAL_WITNESSED,
            basis=ConsentBasis.VERBAL_RECORDED,
            language="en",
            witness_person_id=witness,  # type: ignore[arg-type]
            basis_artifact_id=artifact,  # type: ignore[arg-type]
        )

    # No witness; the chief naming himself; a witness with no key here; no recording.
    with pytest.raises(NoSuchWitness):
        await spoken(None, recording.id)
    with pytest.raises(NoSuchWitness):
        await spoken(chief.person_id, recording.id)
    with pytest.raises(NoSuchWitness):
        await spoken(stranger.id, recording.id)
    with pytest.raises(NothingBehindTheBasis):
        await spoken(daughter.id, None)
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert sorted(e.refused_because for e in refused) == sorted(
        [
            "NothingBehindTheBasis",
            "NoSuchWitness",
            "NoSuchWitness",
            "NoSuchWitness",
        ]
    )

    given = await spoken(daughter.id, recording.id)
    assert given.witness_person_id == daughter.id
    assert given.basis_artifact_id == recording.id
    record = await export_consent_record(sg, context=owner)
    entry = next(e for e in record.document["consents"] if e["id"] == str(given.id))
    assert entry["witness"] == "Daughter" and entry["recording_kept"] is True
    assert str(recording.id) not in str(entry)  # yes or no, never the artefact's id
    page = record.rendered.body.decode()
    assert (
        "  You said yes out loud.\n"
        "  Daughter was there and heard you say it.\n"
        "  Son wrote it down here.\n"
        "  Nura kept the recording."
    ) in page
    assert "said yes for you" not in page


async def test_sharing_names_a_person_and_the_other_purposes_name_nobody(
    sg: AsyncSession,
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    with pytest.raises(NoHolderNamed):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.SHARE_WITH_PERSON,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="en",
        )
    son = await register_person(sg, region=Region.SG, display_name="Son", phone_e164="+6591110004")
    with pytest.raises(NotAgreedPerPerson):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.WHATSAPP,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="en",
            sharing=Sharing(
                holder=son, scopes=frozenset({Scope.MEDICINES}), role=KeyRole.CAREGIVER, window=KeyWindow.ALWAYS
            ),
        )
    with pytest.raises(NoHolderNamed):
        await require_consent(
            sg, context=owner, purpose=ConsentPurpose.SHARE_WITH_PERSON, scope=Scope.FAMILY
        )


async def test_a_consent_is_recorded_only_in_words_that_are_on_file_in_that_language(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = await _pa_and_his_son(sg)

    # Tamil is not offered until its words are on file.
    assert "ta" not in LANGUAGES
    with pytest.raises(WordingNotOnFile):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="ta",
        )
    with pytest.raises(WordingNotOnFile):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="en",
            text_version="0",
        )

    # Once the words exist in his language, the row keeps those words and the page shows them.
    in_tamil = ConsentText(
        ConsentPurpose.RECORDING, current_version(ConsentPurpose.RECORDING), "ta", "தமிழ் வார்த்தைகள்."
    )
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, in_tamil))
    monkeypatch.setattr(texts, "LANGUAGES", {**texts.LANGUAGES, "ta": "Tamil"})
    monkeypatch.setattr(export, "LANGUAGES", texts.LANGUAGES)
    given = await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="ta",
    )
    assert given.language == "ta" and given.wording_text == "தமிழ் வார்த்தைகள்."
    record = await export_consent_record(sg, context=owner)
    entry = next(e for e in record.document["consents"] if e["id"] == str(given.id))
    assert entry["wording"] == "தமிழ் வார்த்தைகள்." and entry["language_name"] == "Tamil"
    assert "  These are the words you read in Tamil:\n  தமிழ் வார்த்தைகள்." in (
        record.rendered.body.decode()
    )


async def test_a_caregiver_can_neither_give_nor_withdraw_consent(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await agree_to_family_sharing(sg, owner, daughter, role=KeyRole.CAREGIVER)
    await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
    )
    with pytest.raises(OutOfScope):
        clock.set(GIVEN_AT + timedelta(days=1))
        await grant_consent(
            sg,
            context=held,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.VERBAL_RECORDED,
            language="en",
        )
    with pytest.raises(OutOfScope):
        clock.set(GIVEN_AT + timedelta(days=2))
        await revoke_consent(
            sg,
            context=held,
            purpose=ConsentPurpose.SHARE_WITH_PERSON,
            captured_via=ConsentChannel.APP,
            holder_person_id=daughter.id,
        )

    # Both reaches are in the trail Pa reads, newest first.
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(entry.actor_person_id, entry.action, entry.target) for entry in refused] == [
        (daughter.id, Action.READ, Consent.__tablename__),
        (daughter.id, Action.WRITE, Consent.__tablename__),
    ]


async def test_a_gate_is_only_open_to_someone_the_act_itself_is_open_to(sg: AsyncSession) -> None:
    """The consent check runs under the scope of the act it guards, never wider."""
    owner, _ = await _pa_and_his_son(sg)
    siti = await register_person(
        sg, region=Region.SG, display_name="Siti", phone_e164="+6591110003"
    )
    await agree_to_family_sharing(sg, owner, siti, role=KeyRole.HELPER)
    await grant_key(sg, context=owner, holder=siti, role=KeyRole.HELPER)
    helper = await resolve_key_context(
        sg, region=Region.SG, person_id=siti.id, profile_id=owner.profile_id
    )
    with pytest.raises(OutOfScope):
        await require_consent(
            sg, context=helper, purpose=ConsentPurpose.RECORDING, scope=Scope.VISITS
        )
    # A helper's key covers no more than the words let him see, and the profile row.
    assert helper.scopes <= {Scope.PROFILE, Scope.MEDICINES, Scope.EMERGENCY, Scope.SEND}
    # A helper may send on WhatsApp, so a helper may ask whether WhatsApp is agreed to.
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    assert await require_consent(
        sg,
        context=helper,
        purpose=ConsentPurpose.WHATSAPP,
        scope=Scope.SEND,
        channel=Channel.WHATSAPP,
    )


# --- the names on the page come through the doors ---------------------------------------


async def test_a_name_is_given_only_for_someone_on_the_profile(sg: AsyncSession) -> None:
    owner, chief = await _pa_and_his_son(sg)
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )
    assert await person_display_name(sg, owner, owner.person_id) == "Pa"
    assert await person_display_name(sg, chief, chief.person_id) == "Son"
    with pytest.raises(NotOnThisProfile):
        await person_display_name(sg, owner, stranger.id)
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.scope, e.target, e.refused_because) for e in refused] == [
        (Scope.FAMILY, "person", "NotOnThisProfile")
    ]


# --- the trail says where the agreement came from ----------------------------------------


async def test_the_trail_records_where_each_consent_was_captured(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    clock.set(GIVEN_AT + timedelta(days=1))
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    clock.set(GIVEN_AT + timedelta(days=2))
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.PAPER,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    writes = [
        entry
        for entry in await read_audit(sg, context=owner, action=Action.WRITE)
        if entry.target == Consent.__tablename__
    ]
    # Newest first: the paper form was entered in the app; the WhatsApp one came from there;
    # then sharing with his son and the opening consent, both in the app.
    assert [entry.channel for entry in writes] == [
        Channel.APP,
        Channel.WHATSAPP,
        Channel.APP,
        Channel.APP,
    ]


# --- withdrawing ------------------------------------------------------------------------


async def test_withdrawing_what_was_never_given_is_refused_and_written_down(
    sg: AsyncSession,
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    with pytest.raises(NoConsentToWithdraw):
        await revoke_consent(
            sg, context=owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP
        )
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.action, e.refused_because) for e in refused] == [
        (Action.WRITE, "NoConsentToWithdraw")
    ]


async def test_only_the_owner_stops_sharing_with_someone(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    """A chief closes one key with revoke_key; withdrawing the consent behind it is Pa's."""
    owner, chief = await _pa_and_his_son(sg)
    with pytest.raises(NotTheirConsentToWithdraw):
        clock.set(GIVEN_AT + timedelta(days=1))
        await revoke_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.SHARE_WITH_PERSON,
            captured_via=ConsentChannel.APP,
            holder_person_id=chief.person_id,
        )
    # The chief still holds his key, and Pa sees the attempt.
    still = await resolve_key_context(
        sg, region=Region.SG, person_id=chief.person_id, profile_id=owner.profile_id
    )
    assert still.key_id == chief.key_id
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.actor_person_id, e.refused_because) for e in refused] == [
        (chief.person_id, "NotTheirConsentToWithdraw")
    ]


async def test_a_withdrawal_is_written_on_the_channel_it_came_from(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    clock.set(GIVEN_AT + timedelta(days=1))
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    clock.set(GIVEN_AT + timedelta(days=2))
    await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
    )
    withdrawal = next(
        entry
        for entry in await read_audit(sg, context=owner, action=Action.WRITE)
        if entry.target == Consent.__tablename__
    )
    assert withdrawal.channel is Channel.WHATSAPP and withdrawal.rows == 1


async def test_withdrawing_closes_every_version_still_open(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch, clock: FrozenClock
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    clock.set(GIVEN_AT)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    newer = ConsentText(ConsentPurpose.WHATSAPP, "2", "en", "Newer words.")
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, newer))
    clock.set(GIVEN_AT + timedelta(hours=1))
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    clock.set(GIVEN_AT + timedelta(days=1))
    closed = await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.APP,
    )
    assert sorted(c.text_version for c in closed) == ["1", "2"]
    still_open = await active_consents(sg, context=owner, at=GIVEN_AT + timedelta(days=2))
    assert [c.purpose for c in still_open] == [
        ConsentPurpose.HOLD_HEALTH_RECORD,
        ConsentPurpose.SHARE_WITH_PERSON,
    ]


async def test_withdrawing_something_other_than_sharing_leaves_the_keys(
    sg: AsyncSession,
) -> None:
    owner, chief = await _pa_and_his_son(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    await revoke_consent(
        sg, context=owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP
    )
    still = await resolve_key_context(
        sg, region=Region.SG, person_id=chief.person_id, profile_id=owner.profile_id
    )
    assert still.key_id == chief.key_id


# --- the renderer is a seam ---------------------------------------------------------------


async def test_the_export_takes_any_renderer(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)

    class Counting:
        media_type = "text/plain"

        def render(self, document: dict[str, object]) -> bytes:
            consents = document["consents"]
            assert isinstance(consents, list)
            return f"{len(consents)} consents".encode()

    record = await export_consent_record(sg, context=owner, renderer=Counting())
    assert record.rendered.media_type == "text/plain"
    assert record.rendered.body == b"2 consents"  # keeping the record, and sharing with his son

    plain = await export_consent_record(sg, context=owner, renderer=PlainTextRenderer())
    assert plain.rendered.body.decode().startswith("# What you said yes to")
