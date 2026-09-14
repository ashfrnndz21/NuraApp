"""Who may give consent on whose behalf, who may withdraw it, what the wording catalogue
promises, and how each of those lands in the trail."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Channel, Outcome
from app.audit.trail import read_audit
from app.consent import texts
from app.consent.export import (
    CHANNEL_WORDS,
    PURPOSE_TITLES,
    REGION_NAMES,
    PlainTextRenderer,
    basis_words,
    export_consent_record,
)
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import (
    NoConsentToWithdraw,
    NotTheirConsentToGive,
    NotTheirConsentToWithdraw,
    WordingNotOnFile,
    active_consents,
    grant_consent,
    require_consent,
    revoke_consent,
)
from app.consent.texts import ConsentText, current_version, versions, wording
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.grants import grant_key
from app.keys.scopes import KeyRole, Scope
from app.regions import Region
from tests.support import OPENING_CONSENT

GIVEN_AT = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)


async def _pa_and_his_son(session: AsyncSession) -> tuple[KeyContext, KeyContext]:
    """Pa opens his graph, agrees to family sharing and names his son chief."""
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa, consent=OPENING_CONSENT)
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    await grant_consent(
        session,
        context=owner,
        purpose=ConsentPurpose.SHARE_WITH_FAMILY,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        now=GIVEN_AT,
    )
    son = await register_person(
        session, region=Region.SG, display_name="Son", phone_e164="+6591110004"
    )
    await grant_key(
        session, context=owner, holder=son, role=KeyRole.CHIEF, basis="owner_consent",
        now=GIVEN_AT,
    )
    chief = await resolve_key_context(
        session, region=Region.SG, person_id=son.id, profile_id=profile.id
    )
    return owner, chief


# --- the wording catalogue ----------------------------------------------------------------


def test_every_purpose_has_current_english_wording_in_both_regions() -> None:
    for purpose in ConsentPurpose:
        for region in Region:
            assert wording(purpose, current_version(purpose), "en", region) is not None
    keys = [(text.purpose, text.version, text.language, text.region) for text in texts.TEXTS]
    assert len(keys) == len(set(keys))


def test_words_that_name_the_country_have_a_twin_per_region() -> None:
    purpose, version = ConsentPurpose.HOLD_HEALTH_RECORD, "1"
    assert wording(purpose, version, "en", Region.SG) == (
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They never leave Singapore."
    )
    assert wording(purpose, version, "en", Region.MY) == (
        "Nura keeps your papers, your medicines and your blood pressure book. "
        "They never leave Malaysia."
    )


def test_the_current_version_is_the_last_one_appended(monkeypatch: pytest.MonkeyPatch) -> None:
    before = versions(ConsentPurpose.WHATSAPP)
    newer = ConsentText(ConsentPurpose.WHATSAPP, "10", "en", "Newer words.")
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, newer))
    # Appended last is current, whatever the strings would sort to.
    assert versions(ConsentPurpose.WHATSAPP) == [*before, "10"]
    assert current_version(ConsentPurpose.WHATSAPP) == "10"


def test_wording_nobody_was_ever_shown_is_unknown() -> None:
    current = current_version(ConsentPurpose.WHATSAPP)
    assert wording(ConsentPurpose.WHATSAPP, "not-a-version", "en", Region.SG) is None
    assert wording(ConsentPurpose.WHATSAPP, current, "xx", Region.SG) is None


def test_the_record_can_put_words_to_every_purpose_basis_channel_and_region() -> None:
    assert set(PURPOSE_TITLES) == set(ConsentPurpose)
    for basis in ConsentBasis:
        line = basis_words(basis, "Ash", "Pa")
        assert (line is None) == (basis is ConsentBasis.OWNER)
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
            now=GIVEN_AT + timedelta(days=1),
        )
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.action, e.target, e.refused_because) for e in refused] == [
        (Action.WRITE, Consent.__tablename__, "NotTheirConsentToGive")
    ]


async def test_a_chief_consents_for_pa_only_on_a_recorded_proxy_basis(sg: AsyncSession) -> None:
    owner, chief = await _pa_and_his_son(sg)

    with pytest.raises(NotTheirConsentToGive):
        await grant_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
        )

    by_proxy = await grant_consent(
        sg,
        context=chief,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.PAPER,
        basis=ConsentBasis.MEDICAL_LETTER,
        now=GIVEN_AT + timedelta(days=1),
    )
    assert by_proxy.person_id == chief.person_id
    assert by_proxy.basis is ConsentBasis.MEDICAL_LETTER

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
    assert "- Son agreed to this for Pa on paper on Tuesday 15 September 2026." in page
    assert "  A doctor's letter says Son may decide for Pa." in page


async def test_a_consent_is_recorded_only_in_words_that_are_on_file_in_that_language(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _ = await _pa_and_his_son(sg)

    with pytest.raises(WordingNotOnFile):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            language="zh",
        )
    with pytest.raises(WordingNotOnFile):
        await grant_consent(
            sg,
            context=owner,
            purpose=ConsentPurpose.RECORDING,
            captured_via=ConsentChannel.APP,
            basis=ConsentBasis.OWNER,
            text_version="0",
        )

    # Once the words exist in his language, the record shows those words, not the English.
    in_chinese = ConsentText(
        ConsentPurpose.RECORDING, current_version(ConsentPurpose.RECORDING), "zh", "中文的说明。"
    )
    monkeypatch.setattr(texts, "TEXTS", (*texts.TEXTS, in_chinese))
    given = await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="zh",
    )
    assert given.language == "zh"
    record = await export_consent_record(sg, context=owner)
    entry = next(e for e in record.document["consents"] if e["id"] == str(given.id))
    assert entry["wording"] == "中文的说明。" and entry["language_name"] == "Chinese"
    assert "  These are the words Pa read, in Chinese:\n  \"中文的说明。\"" in record.rendered.body.decode()


async def test_a_caregiver_can_neither_give_nor_withdraw_consent(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)
    daughter = await register_person(
        sg, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await grant_key(
        sg, context=owner, holder=daughter, role=KeyRole.CAREGIVER, basis="owner_consent"
    )
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
            now=GIVEN_AT + timedelta(days=1),
        )
    with pytest.raises(OutOfScope):
        await revoke_consent(
            sg,
            context=held,
            purpose=ConsentPurpose.SHARE_WITH_FAMILY,
            captured_via=ConsentChannel.APP,
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
    await grant_key(sg, context=owner, holder=siti, role=KeyRole.HELPER, basis="owner_consent")
    helper = await resolve_key_context(
        sg, region=Region.SG, person_id=siti.id, profile_id=owner.profile_id
    )
    with pytest.raises(OutOfScope):
        await require_consent(
            sg, context=helper, purpose=ConsentPurpose.RECORDING, scope=Scope.VISITS
        )
    # A helper may send on WhatsApp, so a helper may ask whether WhatsApp is agreed to.
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
    )
    assert await require_consent(
        sg, context=helper, purpose=ConsentPurpose.WHATSAPP, scope=Scope.SEND,
        channel=Channel.WHATSAPP,
    )


# --- the trail says where the agreement came from ----------------------------------------


async def test_the_trail_records_where_each_consent_was_captured(sg: AsyncSession) -> None:
    owner, _ = await _pa_and_his_son(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        now=GIVEN_AT + timedelta(days=1),
    )
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.PAPER,
        basis=ConsentBasis.OWNER,
        now=GIVEN_AT + timedelta(days=2),
    )
    writes = [
        entry
        for entry in await read_audit(sg, context=owner, action=Action.WRITE)
        if entry.target == Consent.__tablename__
    ]
    # Newest first: the paper form was entered in the app; the WhatsApp one came from there;
    # then family sharing and the opening consent, both in the app.
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
        await revoke_consent(sg, context=owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP)
    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert [(e.action, e.refused_because) for e in refused] == [
        (Action.WRITE, "NoConsentToWithdraw")
    ]


async def test_only_the_owner_stops_sharing_with_his_family(sg: AsyncSession) -> None:
    """A chief closes one key with revoke_key; stopping it all, his own key included, is Pa's."""
    owner, chief = await _pa_and_his_son(sg)
    with pytest.raises(NotTheirConsentToWithdraw):
        await revoke_consent(
            sg,
            context=chief,
            purpose=ConsentPurpose.SHARE_WITH_FAMILY,
            captured_via=ConsentChannel.APP,
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
        now=GIVEN_AT + timedelta(hours=1),
    )
    closed = await revoke_consent(sg, context=owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP, now=GIVEN_AT + timedelta(days=1)
    )
    assert sorted(c.text_version for c in closed) == ["1", "2"]
    still_open = await active_consents(sg, context=owner, now=GIVEN_AT + timedelta(days=2))
    assert [c.purpose for c in still_open] == [
        ConsentPurpose.HOLD_HEALTH_RECORD,
        ConsentPurpose.SHARE_WITH_FAMILY,
    ]


async def test_withdrawing_something_other_than_family_sharing_leaves_the_keys(
    sg: AsyncSession,
) -> None:
    owner, chief = await _pa_and_his_son(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
    )
    await revoke_consent(sg, context=owner, purpose=ConsentPurpose.WHATSAPP, captured_via=ConsentChannel.APP)
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
    assert record.rendered.body == b"2 consents"  # keeping the record, and sharing it

    plain = await export_consent_record(sg, context=owner, renderer=PlainTextRenderer())
    assert plain.rendered.body.decode().startswith("# What you agreed to")
