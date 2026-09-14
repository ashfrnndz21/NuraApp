"""Who may give consent on whose behalf and with what behind it, who may withdraw it, what
the wording catalogue promises, and how each of those lands in the trail."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import NotOnThisProfile, person_display_name
from app.audit.models import Action, Channel, Outcome
from app.audit.trail import read_audit
from app.consent import texts
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
    versions,
    what_words,
    wording,
)
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import Region
from tests.support import OPENING_CONSENT, agree_to_family_sharing

GIVEN_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)

# Every wording on file, by (purpose, version, language, region), as a sha256 of the text.
# Editing shipped words fails this test; the only way to change what a person is asked to
# agree to is a new version, appended below the old one.
SHIPPED_WORDS: dict[tuple[str, str, str, str | None], str] = {
    ('hold_health_record', '1', 'en', 'SG'): (
        "49a23d71f800544127a27ae5bbce682edd543da1dab102a9da1005e0a46544a5"
    ),
    ('hold_health_record', '1', 'en', 'MY'): (
        "a2533c02ce7cc2f5bb2123798166ebbcbe4f18c950ce549d958093cfc32098c5"
    ),
    ('hold_health_record', '1', 'ms', 'SG'): (
        "a8287f1d2c29bd7e440c4adc60400c8050ebcd51cddeed6d7b49f0bcbb945b7d"
    ),
    ('hold_health_record', '1', 'ms', 'MY'): (
        "3fdaa22c1ed01f70ec176365af21ed4436cf5cb36669e6be6acf257d9c26f26e"
    ),
    ('hold_health_record', '1', 'zh', 'SG'): (
        "444d8b6c645eeecf40ab9671708551cc399e58401a5b265daf775d3c10d188d9"
    ),
    ('hold_health_record', '1', 'zh', 'MY'): (
        "a060e60e2a2357f63aba4370a254bfc60b0f3c901d56d0c5685a740d5c97bd18"
    ),
    ('share_with_family', '1', 'en', None): (
        "ef22011a7d39e10bae9b0290acc235434b53573e0590042d574e86cc0e7632a2"
    ),
    ('share_with_family', '2', 'en', None): (
        "ca896f4ad6fdca185bc908d3dc34be45912dc34cc71a999d4d8990c0da978941"
    ),
    ('share_with_family', '2', 'ms', None): (
        "657def7f76caf31c8e2607c831e42d72218ebc96daa056f3a47b40d1b13aeca4"
    ),
    ('share_with_family', '2', 'zh', None): (
        "2e17babab0b454e878d1bc2ccbfbf448a6e6c04e3f513f3aed7c6218d9692abe"
    ),
    ('recording', '1', 'en', None): (
        "af91a7ccfe04bd97ea9dbb9a4dd27c4e3898fad9fa55f00a1197e17ec38362f6"
    ),
    ('recording', '1', 'ms', None): (
        "fdf7e49d20213844e819091d1e31f5f6ddf76a3e65670b15f2494437cf208243"
    ),
    ('recording', '1', 'zh', None): (
        "30bb26e0237f58e4b2790bf767b10853bb316f7624b0eec86997f8e82ba992f9"
    ),
    ('whatsapp', '1', 'en', None): (
        "97e9159f56aa1da1828deab95308dd1a6302fe5a948942c0ba6b53c3406f9c24"
    ),
    ('whatsapp', '1', 'ms', None): (
        "5f8f02058ff1f848e6fcdecdd76ffe957b84c29ff11b6e96229a80ee16447886"
    ),
    ('whatsapp', '1', 'zh', None): (
        "2037a41ac7a4d5a23a23d4658fb2dc739b9602476fee07aeca0e303e7f7d263e"
    ),
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _pa_and_his_son(session: AsyncSession) -> tuple[KeyContext, KeyContext]:
    """Pa opens his graph, agrees to share with his son and names him chief."""
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(
        session, region=Region.SG, owner=pa, consent=OPENING_CONSENT, now=GIVEN_AT
    )
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    son = await register_person(
        session, region=Region.SG, display_name="Son", phone_e164="+6591110004"
    )
    await agree_to_family_sharing(session, owner, son, now=GIVEN_AT)
    await grant_key(session, context=owner, holder=son, role=KeyRole.CHIEF, now=GIVEN_AT)
    chief = await resolve_key_context(
        session, region=Region.SG, person_id=son.id, profile_id=profile.id
    )
    return owner, chief


async def _letter(session: AsyncSession, context: KeyContext) -> Artifact:
    """A doctor's letter, or an LPA, as a PDF on the profile."""
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
        now=GIVEN_AT,
    )


# --- the wording catalogue ----------------------------------------------------------------


def test_every_purpose_has_current_wording_in_english_malay_and_chinese_for_both_regions() -> None:
    for purpose in ConsentPurpose:
        for region in Region:
            for language in ("en", "ms", "zh"):  # Tamil is a follow-up
                assert wording(purpose, current_version(purpose), language, region) is not None
    keys = [(text.purpose, text.version, text.language, text.region) for text in texts.TEXTS]
    assert len(keys) == len(set(keys))
    assert {text.language for text in texts.TEXTS} <= set(LANGUAGES)


def test_the_sharing_words_name_the_person_and_the_parts() -> None:
    for language in ("en", "ms", "zh"):
        assert set(SCOPE_WORDS[language]) == set(Scope) - {Scope.PROFILE}
    assert what_words({Scope.MEDICINES}, "en") == "medicines"
    assert what_words({Scope.MEDICINES, Scope.VISITS}, "en") == "medicines and visits to the doctor"
    assert what_words({Scope.RECORDS, Scope.MEDICINES, Scope.NOTES}, "en") == (
        "medicines, papers and private notes"
    )
    assert what_words((), "en") == "papers"
    assert what_words({Scope.MEDICINES, Scope.VISITS}, "zh") == "药物和看医生的记录"


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
        lines = basis_lines(basis, "Ash", "Pa")
        assert (lines == []) == (basis is ConsentBasis.OWNER)
        assert all(line.count(". ") == 0 for line in lines), "one idea per line"
    assert set(CHANNEL_WORDS) == set(ConsentChannel)
    assert set(REGION_NAMES) == set(Region)


# --- who may give it, and in which words -------------------------------------------------


async def test_the_owner_consents_for_himself_and_only_on_his_own_basis(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)
    with pytest.raises(NotTheirConsentToGive):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.LPA,
            language="en",
            now=GIVEN_AT + timedelta(days=1),
        )
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.action, e.target, e.refused_because) for e in refused] == [
        (Action.WRITE, Consent.__tablename__, "NotTheirConsentToGive")
    ]


async def test_a_chief_consents_for_pa_only_on_a_proxy_basis_with_the_document_behind_it(
    sg: AsyncSession,
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
    by_proxy = await grant_consent(
        sg,
        context=chief,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.PAPER,
        basis=ConsentBasis.MEDICAL_LETTER,
        language="en",
        basis_artifact_id=letter.id,
        now=GIVEN_AT + timedelta(days=1),
    )
    assert by_proxy.person_id == chief.person_id
    assert by_proxy.basis is ConsentBasis.MEDICAL_LETTER
    assert by_proxy.basis_artifact_id == letter.id

    # It stands for the profile, whoever asks.
    held = await require_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        scope=Scope.VISITS,
        now=GIVEN_AT + timedelta(days=2),
    )
    assert held.consent_id == by_proxy.id

    # And the record says who gave it and on what basis.
    record = await export_consent_record(sg, context=owner)
    entry = next(e for e in record.document["consents"] if e["id"] == str(by_proxy.id))
    assert entry["given_by"] == "Son" and entry["basis"] == "medical_letter"
    page = record.rendered.body.decode()
    assert "- Son said yes on paper on Tuesday 15 September 2026." in page
    assert "  Son said yes for you.\n  A doctor's letter says Son may decide for you." in page


async def test_a_spoken_agreement_names_who_heard_it(sg: AsyncSession) -> None:
    owner, chief = await _pa_and_his_son(sg)
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )
    with pytest.raises(NoSuchWitness):
        await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.WHATSAPP,
            captured_via=ConsentChannel.VERBAL_WITNESSED,
            basis=ConsentBasis.VERBAL_RECORDED,
            language="en",
        )
    with pytest.raises(NoSuchWitness):
        await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.WHATSAPP,
            captured_via=ConsentChannel.VERBAL_WITNESSED,
            basis=ConsentBasis.VERBAL_RECORDED,
            language="en",
            witness_person_id=stranger.id,
        )
    # The chief who heard it may be the witness; the recording, when there is one, is on the profile.
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
        now=GIVEN_AT,
    )
    spoken = await grant_consent(
        sg,
        context=chief,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.VERBAL_WITNESSED,
        basis=ConsentBasis.VERBAL_RECORDED,
        language="en",
        witness_person_id=chief.person_id,
        basis_artifact_id=recording.id,
    )
    assert spoken.witness_person_id == chief.person_id
    assert spoken.basis_artifact_id == recording.id
    page = (await export_consent_record(sg, context=owner)).rendered.body.decode()
    assert "  You said yes out loud.\n  Son wrote it down here.\n  Nura kept what you said." in page
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
            sharing=Sharing(holder=son, scopes=frozenset({Scope.MEDICINES})),
        )
    with pytest.raises(NoHolderNamed):
        await require_consent(
            sg, context=owner, purpose=ConsentPurpose.SHARE_WITH_PERSON, scope=Scope.FAMILY
        )


async def test_a_consent_is_recorded_only_in_words_that_are_on_file_in_that_language(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = await _pa_and_his_son(sg)

    # Tamil is a language Nura speaks, but its words are not on file yet.
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


async def test_a_caregiver_can_neither_give_nor_withdraw_consent(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await agree_to_family_sharing(sg, owner, daughter)
    await grant_key(sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER)
    held = await resolve_key_context(
        sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
    )
    with pytest.raises(OutOfScope):
        await grant_consent(
            sg,
            context=held,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.VERBAL_RECORDED,
            language="en",
            now=GIVEN_AT + timedelta(days=1),
        )
    with pytest.raises(OutOfScope):
        await revoke_consent(
            sg,
            context=held,
            purpose=ConsentPurpose.SHARE_WITH_PERSON,
            captured_via=ConsentChannel.APP,
            holder_person_id=daughter.id,
            now=GIVEN_AT + timedelta(days=2),
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
    siti = await register_person(sg, region=Region.SG, display_name="Siti", phone_e164="+6591110003")
    await agree_to_family_sharing(sg, owner, siti)
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


async def test_the_trail_records_where_each_consent_was_captured(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=GIVEN_AT + timedelta(days=1),
    )
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.PAPER,
        basis=ConsentBasis.OWNER,
        language="en",
        now=GIVEN_AT + timedelta(days=2),
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


async def test_only_the_owner_stops_sharing_with_someone(sg: AsyncSession) -> None:
    """A chief closes one key with revoke_key; withdrawing the consent behind it is Pa's."""
    owner, chief = await _pa_and_his_son(sg)
    with pytest.raises(NotTheirConsentToWithdraw):
        await revoke_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.SHARE_WITH_PERSON,
            captured_via=ConsentChannel.APP,
            holder_person_id=chief.person_id,
            now=GIVEN_AT + timedelta(days=1),
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


async def test_a_withdrawal_is_written_on_the_channel_it_came_from(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=GIVEN_AT + timedelta(days=1),
    )
    await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        now=GIVEN_AT + timedelta(days=2),
    )
    withdrawal = next(
        entry
        for entry in await read_audit(sg, context=owner, action=Action.WRITE)
        if entry.target == Consent.__tablename__
    )
    assert withdrawal.channel is Channel.WHATSAPP and withdrawal.rows == 1


async def test_withdrawing_closes_every_version_still_open(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = await _pa_and_his_son(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=GIVEN_AT,
    )
    newer = ConsentText(ConsentPurpose.WHATSAPP, "2", "en", "Newer words.")
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, newer))
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
        now=GIVEN_AT + timedelta(hours=1),
    )
    closed = await revoke_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.APP,
        now=GIVEN_AT + timedelta(days=1),
    )
    assert sorted(c.text_version for c in closed) == ["1", "2"]
    still_open = await active_consents(sg, context=owner, now=GIVEN_AT + timedelta(days=2))
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
