"""The recording consent pattern (E16-02): the notice, and the gate on the RECORDING consent.

    Acceptance: doctor notified aloud or by printed notice; consent stored.

The notice is spoken in the patient's language and passes docs/plain-words.md; with no doctor
named it addresses the doctor plainly, never "your doctor"; `may_record` refuses when the
RECORDING consent is withheld, withdrawn, or given to older words, and when the key cannot
keep what the room was told would be kept; `store_artifact` refuses a VOICE artefact without
that consent whoever writes it; every refusal is on the trail; the steps the code names are
the steps the document names.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Outcome
from app.audit.trail import read_audit
from app.consent.models import ConsentChannel, ConsentPurpose
from app.consent.service import ConsentRevoked, ConsentWithheld, revoke_consent
from app.db import utcnow
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import store_artifact
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import Region
from app.safety.boundary import LANGUAGES
from app.safety.plain_words import verify
from app.safety.recording import (
    CHECKLIST,
    PRINTED_NOTICE,
    SPOKEN_NOTICE,
    VOCATIVE_LINE,
    WHEN_NO,
    may_record,
    printed_notice,
    recording_notice,
    when_no,
)
from tests.medicines_support import let_in
from tests.support import OPENING_CONSENT, agree_to_recording, refused_unit

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


async def _voice(session: AsyncSession, context: KeyContext, kind: ArtifactKind = ArtifactKind.VOICE) -> Artifact:
    digest = uuid.uuid4().hex + uuid.uuid4().hex
    return await store_artifact(
        session,
        context=context,
        kind=kind,
        storage_key=f"sg/{context.profile_id}/{digest}",
        content_type="audio/mp4" if kind is ArtifactKind.VOICE else "image/jpeg",
        sha256=digest,
        captured_at=utcnow(),
        source_channel=SourceChannel.APP,
        region=Region.SG,
    )


def test_the_notice_is_spoken_in_his_language_and_names_the_doctor() -> None:
    assert recording_notice("en", doctor="Dr Tan").splitlines() == [
        "Nura will listen now.",
        "Nura keeps what you and Dr Tan say.",
        "Only you and those you let in can hear it.",
        "Is that OK, Dr Tan?",
    ]
    assert recording_notice("zh", doctor="Dr Tan").splitlines()[-1] == "Dr Tan，可以吗？"
    assert recording_notice("ta") == recording_notice("en")
    assert printed_notice("en").splitlines()[0] == "This patient uses Nura."
    assert when_no("en", who="Ash").splitlines() == [
        "Nura will not listen today.",
        "Ash will write the notes by hand.",
    ]


def test_with_no_doctor_named_the_last_line_addresses_the_doctor_plainly() -> None:
    """A form of address is never "your doctor": that is not something anyone says to a
    person's face in a clinic room."""
    for language, last in (
        ("en", "Is that OK, doctor?"),
        ("ms", "Boleh ya, doktor?"),
        ("zh", "医生，可以吗？"),
    ):
        lines = recording_notice(language).splitlines()
        assert lines[-1] == last == VOCATIVE_LINE[language], language
        assert "your doctor" not in lines[-1] and "doktor anda" not in lines[-1]
        assert "您的医生" not in lines[-1]
    assert recording_notice("en").splitlines()[1] == "Nura keeps what you and your doctor say."


def test_every_notice_passes_plain_words_in_every_language() -> None:
    failures = [
        (which, language, finding.problem)
        for which, catalogue in (
            ("spoken", SPOKEN_NOTICE),
            ("printed", PRINTED_NOTICE),
            ("no", WHEN_NO),
            ("vocative", {code: (line,) for code, line in VOCATIVE_LINE.items()}),
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

    agreed = await agree_to_recording(sg, owner)
    allowed = await may_record(sg, owner)
    assert allowed.consent_id == agreed.id and allowed.purpose is ConsentPurpose.RECORDING

    await revoke_consent(
        sg, context=owner, purpose=ConsentPurpose.RECORDING, captured_via=ConsentChannel.APP
    )
    with pytest.raises(ConsentRevoked):
        await may_record(sg, owner)


async def test_the_gate_needs_the_visit_and_the_place_the_recording_goes(sg: AsyncSession) -> None:
    """A helper with a key to the medicines alone cannot start a recording, and cannot learn
    from the gate whether the patient agreed to one. A viewer holds visits and not records:
    the room must not be told "Nura will listen now" and then find nothing was kept, so the
    gate refuses her too, and the refusal is on the trail as a refused write of an artefact."""
    owner = await _pa(sg)
    await agree_to_recording(sg, owner)
    helper = await let_in(
        sg, owner, phone="+6591110003", name="Auntie", role=KeyRole.HELPER, scopes={Scope.MEDICINES}
    )
    with pytest.raises(OutOfScope):
        await may_record(sg, helper)
    viewer = await let_in(
        sg,
        owner,
        phone="+6591110004",
        name="Uncle",
        role=KeyRole.VIEWER,
        scopes={Scope.VISITS, Scope.MEDICINES},
    )
    async with refused_unit(sg, OutOfScope):
        await may_record(sg, viewer)
    trail = await read_audit(sg, context=owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.action is Action.WRITE
        and e.scope is Scope.RECORDS
        and e.target == "artifact"
        and e.refused_because == "OutOfScope"
        and e.actor_person_id == viewer.person_id
        for e in trail
    )
    daughter = await let_in(
        sg,
        owner,
        phone="+6591110002",
        name="Mei",
        role=KeyRole.CAREGIVER,
        scopes={Scope.VISITS, Scope.RECORDS},
    )
    assert (await may_record(sg, daughter)).purpose is ConsentPurpose.RECORDING
    await _voice(sg, daughter)


async def test_the_store_refuses_a_voice_without_the_consent_whoever_writes_it(
    sg: AsyncSession,
) -> None:
    """Where the bytes enter: `store_artifact` asks for the RECORDING consent on every VOICE
    artefact, so a writer that never asked the gate cannot keep a recording either. A photo
    rests on the consent to hold the record alone."""
    owner = await _pa(sg)
    await _voice(sg, owner, ArtifactKind.PHOTO)
    async with refused_unit(sg, ConsentWithheld):
        await _voice(sg, owner)
    trail = await read_audit(sg, context=owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.scope is Scope.RECORDS
        and e.refused_because == "ConsentWithheld"
        for e in trail
    )
    await agree_to_recording(sg, owner)
    kept = await _voice(sg, owner)
    assert kept.kind is ArtifactKind.VOICE
    await revoke_consent(
        sg, context=owner, purpose=ConsentPurpose.RECORDING, captured_via=ConsentChannel.APP
    )
    with pytest.raises(ConsentRevoked):
        await _voice(sg, owner)


def test_the_checklist_in_the_code_is_the_checklist_in_the_document() -> None:
    document = DOCUMENT.read_text(encoding="utf-8")
    for step in CHECKLIST:
        assert f"`{step}`" in document, step
    assert CHECKLIST[:2] == ("recording_consent_in_force", "records_scope_held")
    for language in LANGUAGES:
        for line in (*SPOKEN_NOTICE[language], *PRINTED_NOTICE[language], *WHEN_NO[language]):
            assert line.replace("{doctor}", "Dr Tan").replace("{who}", "Ash") in document, line
