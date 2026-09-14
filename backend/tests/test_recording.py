"""The recording consent pattern (E16-02): the notice, and the gate on the RECORDING consent.

    Acceptance: doctor notified aloud or by printed notice; consent stored.

The notice is spoken in the patient's language and passes docs/plain-words.md; `may_record`
refuses when the RECORDING consent is withheld, withdrawn, or given to older words, and every
refusal is on the trail; the steps the code names are the steps the document names.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import ConsentRevoked, ConsentWithheld, grant_consent, revoke_consent
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.scopes import KeyRole, Scope
from app.regions import Region
from app.safety.boundary import LANGUAGES
from app.safety.plain_words import verify
from app.safety.recording import (
    CHECKLIST,
    PRINTED_NOTICE,
    SPOKEN_NOTICE,
    WHEN_NO,
    may_record,
    printed_notice,
    recording_notice,
    when_no,
)
from tests.medicines_support import let_in
from tests.support import OPENING_CONSENT, refused_unit

DOCUMENT = Path(__file__).resolve().parents[2] / "docs" / "trust" / "recording-consent.md"


async def _pa(session: AsyncSession, language: str = "en") -> KeyContext:
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(
        session, region=Region.SG, owner=pa, consent=OPENING_CONSENT, language=language
    )
    return await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )


def test_the_notice_is_spoken_in_his_language_and_names_the_doctor() -> None:
    assert recording_notice("en", doctor="Dr Tan").splitlines() == [
        "Nura is about to listen and keep what is said.",
        "Only you and the family you choose can hear it.",
        "Is that OK, Dr Tan?",
    ]
    assert recording_notice("ms").splitlines()[-1] == "Boleh, doktor anda?"
    assert recording_notice("zh", doctor="Dr Tan").splitlines()[-1] == "Dr Tan，可以吗？"
    assert recording_notice("ta") == recording_notice("en")
    assert printed_notice("en").splitlines()[0] == "This patient uses Nura."
    assert when_no("en", who="Ash").splitlines() == [
        "Nura does not keep this visit.",
        "Ash will write the notes by hand.",
    ]


def test_every_notice_passes_plain_words_in_every_language() -> None:
    failures = [
        (which, language, finding.problem)
        for which, catalogue in (
            ("spoken", SPOKEN_NOTICE),
            ("printed", PRINTED_NOTICE),
            ("no", WHEN_NO),
        )
        for language in LANGUAGES
        for line in catalogue[language]
        for finding in verify(line.format(doctor="Dr Tan", who="Ash"), language)
        if finding.severity != "note"
    ]
    assert failures == []


async def test_no_recording_without_the_recording_consent_in_force(sg: AsyncSession) -> None:
    owner = await _pa(sg)
    async with refused_unit(sg, ConsentWithheld):
        await may_record(sg, owner)
    trail = await read_audit(sg, context=owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.action is Action.READ
        and e.scope is Scope.VISITS
        and e.refused_because == "ConsentWithheld"
        for e in trail
    )

    agreed = await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    allowed = await may_record(sg, owner)
    assert allowed.consent_id == agreed.id and allowed.purpose is ConsentPurpose.RECORDING

    await revoke_consent(
        sg, context=owner, purpose=ConsentPurpose.RECORDING, captured_via=ConsentChannel.APP
    )
    with pytest.raises(ConsentRevoked):
        await may_record(sg, owner)


async def test_the_gate_is_asked_under_the_visits_scope(sg: AsyncSession) -> None:
    """A helper with a key to the medicines alone cannot start a recording, and cannot learn
    from the gate whether the patient agreed to one."""
    owner = await _pa(sg)
    await grant_consent(
        sg,
        context=owner,
        purpose=ConsentPurpose.RECORDING,
        captured_via=ConsentChannel.APP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    helper = await let_in(
        sg,
        owner,
        phone="+6591110003",
        name="Auntie",
        role=KeyRole.HELPER,
        scopes={Scope.MEDICINES},
    )
    with pytest.raises(OutOfScope):
        await may_record(sg, helper)
    daughter = await let_in(
        sg,
        owner,
        phone="+6591110002",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.VISITS},
    )
    assert (await may_record(sg, daughter)).purpose is ConsentPurpose.RECORDING


def test_the_checklist_in_the_code_is_the_checklist_in_the_document() -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    for step in CHECKLIST:
        assert f"`{step}`" in document, step
    assert CHECKLIST[0] == "recording_consent_in_force"
