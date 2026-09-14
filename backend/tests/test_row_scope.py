"""Security: a row is read under the scope it was written under (artefacts, events, facts).

The rule (CLAUDE.md): every read of profile data goes through the keys module with a key
context, and a key reaches only the scopes it holds. Scope used to be checked per table — the
scope the caller named — so rows of different kinds, written under different scopes into one
table, leaked across:

1. The family's WhatsApp messages (E19) and the questions asked of Nura (E03) are MESSAGE
   artefacts written under FAMILY and ASK, and any read of the artefact table under RECORDS
   returned them: a key holding the record only read them by reference.
2. `GET /profiles/{id}/facts` with no subject returned the medicine and reading facts to a key
   holding the record only.

The first two tests are those leaks. The rest is the property that closes the class: over a
profile holding one row of every kind, for every preset role and for a key narrowed to each
single scope, every read route under `/profiles/{id}/` and every service that returns rows
answers with rows of the key's scopes only, and names what it withholds rather than dropping
it in silence. The routes are a registry the test walks, so a new route must opt in:
`test_every_profile_route_is_in_the_matrix` fails for a route under `/profiles/{id}/` that is
in neither registry.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.channels.whatsapp.models import MessageKind, WhatsAppMessage
from app.clock import now
from app.db import take_keepers
from app.delivery.feed.models import FeedItem
from app.keys.context import KeyContext, OutOfScope, resolve_key_context
from app.keys.repository import scoped_new
from app.keys.scopes import ALL_SCOPES, ROLE_SCOPES, KeyRole, Scope, scope_for_subject
from app.memory.episodic import (
    NoSuchArtifact,
    NoSuchEvent,
    OnlyTheFamilyHears,
    record_event,
    require_artifact,
    require_event,
)
from app.memory.models import (
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    EpisodeKind,
    Event,
    EventKind,
    Fact,
    ProviderKind,
    SourceChannel,
)
from app.memory.semantic import assert_fact, current_facts
from app.memory.spine import add_provider
from app.memory.timeline import gather
from app.memory.working import open_episode
from app.regions import Region
from app.safety.red_flags import Flag
from app.search.ask import Mode, recall
from tests.api import bearer, let_in, own_profile, register_by_phone
from tests.capture_support import agree_to_recording, b64, confirm, decide, photo
from tests.conftest import Deployment
from tests.consult_audio import CONSULT, CONTENT_TYPE, DURATION_S, placeholder_consult
from tests.medicines_support import add, label
from tests.medicines_support import let_in as cut_key
from tests.paper import LIPID_PANEL, PNG_SIGNATURE
from tests.test_migration import _in_order, _load
from tests.timeline_support import artefact, book, hang_on_episode, reading
from tests.visits import ROUTINE, transcript
from tests.whatsapp_support import MEI, family

PA = "+6591110001"
KIT = "+6593300001"
EVERY_PART = sorted(scope.value for scope in Scope if scope is not Scope.PROFILE)
FACT_SCOPES = (Scope.READINGS, Scope.MEDICINES, Scope.RECORDS)


# --- the two leaks ----------------------------------------------------------------------------


async def test_a_key_holding_the_record_only_cannot_read_the_familys_messages_or_questions(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """Leak 1. A family message (FAMILY) and a question asked of Nura (ASK) are MESSAGE
    artefacts; a read of the artefact table under RECORDS, by a key holding RECORDS only,
    returned both. Now neither is there for it, by any read, and nothing else moved."""
    home = await family(sg, tmp_path)
    told = await home.inbound(sg, MEI, "who is taking him on Thursday?")
    assert told.outcome == "coordination" and told.artifact_id is not None
    asked = await recall(
        sg,
        context=home.owner,
        question="what was my blood pressure",
        mode=Mode.TEXT,
        retriever=home.providers.retriever,
        store=home.providers.object_store,
    )
    records_only = await cut_key(
        sg, home.owner, phone=KIT, name="Kit", role=KeyRole.CAREGIVER, scopes={Scope.RECORDS}
    )
    assert records_only.scopes == {Scope.PROFILE, Scope.RECORDS}

    seen = {a.id for a in await audited_read(sg, Artifact, records_only, Scope.RECORDS)}
    assert told.artifact_id not in seen and asked.question_artifact_id not in seen
    for hidden in (told.artifact_id, asked.question_artifact_id):
        with pytest.raises(NoSuchArtifact):
            await require_artifact(sg, context=records_only, artifact_id=hidden)
    events = await audited_read(sg, Event, records_only, Scope.RECORDS)
    assert [e for e in events if e.kind is EventKind.MESSAGE] == []

    # The owner reads both; a key holding the family scope reads the family's message and
    # not the question, which is the ask scope's.
    everything = {a.id for a in await audited_read(sg, Artifact, home.owner, Scope.RECORDS)}
    assert {told.artifact_id, asked.question_artifact_id} <= everything
    family_key = await cut_key(
        sg,
        home.owner,
        phone="+6593300002",
        name="Lin",
        role=KeyRole.CHIEF,
        scopes={Scope.RECORDS, Scope.FAMILY},
    )
    theirs = {a.id for a in await audited_read(sg, Artifact, family_key, Scope.RECORDS)}
    assert told.artifact_id in theirs and asked.question_artifact_id not in theirs


async def test_the_whole_record_read_of_the_facts_returns_only_the_parts_the_key_holds(
    deployment: Deployment,
) -> None:
    """Leak 2. `GET /facts` with no subject returned the medicine and the reading facts to a
    key holding RECORDS only. Now it returns the record's facts, and the medicines and the
    readings go to the keys that hold them."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    typed = await deployment.client.post(
        f"/profiles/{profile_id}/readings", json={"systolic": 146, "diastolic": 90}, headers=his
    )
    assert typed.status_code == 201, typed.text
    card = await deployment.client.post(
        f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL), headers=his
    )
    assert card.status_code == 201, card.text
    done = await confirm(deployment, pa["token"], profile_id, card.json(), decide(card.json()))
    assert done.status_code == 200, done.text
    async with deployment.sessions() as session:
        owner = await _context(session, pa, profile_id)
        await add(session, owner, label("amlodipine", "5 mg"))
        await session.commit()
    kit = await _holder(deployment, pa, profile_id, KIT, "caregiver", ["records"])

    everything = await deployment.client.get(f"/profiles/{profile_id}/facts", headers=his)
    assert {f["subject"] for f in everything.json()} >= {
        "blood_pressure",
        "medication",
        "lipid_panel",
    }
    theirs = await deployment.client.get(f"/profiles/{profile_id}/facts", headers=bearer(kit.token))
    assert theirs.status_code == 200, theirs.text
    assert {f["subject"] for f in theirs.json()} == {"lipid_panel"}
    for subject in ("medication", "blood_pressure"):
        refused = await deployment.client.get(
            f"/profiles/{profile_id}/facts", params={"subject": subject}, headers=bearer(kit.token)
        )
        assert refused.status_code == 403, refused.text

    # The service says the same thing the route does.
    async with deployment.sessions() as session:
        records_only = await _context(session, {"person_id": str(kit.person_id)}, profile_id)
        facts = await current_facts(session, context=records_only)
        assert {scope_for_subject(f.subject) for f in facts} == {Scope.RECORDS}
        await session.commit()


async def test_a_fact_whose_artefact_the_key_cannot_see_is_shown_with_the_artefact_withheld(
    deployment: Deployment,
) -> None:
    """A fact is shown under its own scope; the artefact it cites is shown only under the
    artefact's. A helper holds the medicines and not the record, so she reads the medicine
    fact and is told, by name, that the label photo it rests on is withheld — never its id."""
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    async with deployment.sessions() as session:
        owner = await _context(session, pa, profile_id)
        added = await add(session, owner, label("amlodipine", "5 mg"))
        await session.commit()
    helper = await _holder(
        deployment, pa, profile_id, KIT, "helper", ["medicines", "emergency", "send"]
    )

    his = await deployment.client.get(
        f"/profiles/{profile_id}/facts",
        params={"subject": "medication"},
        headers=bearer(pa["token"]),
    )
    [fact] = his.json()
    assert fact["artifact_id"] == str(added.line.source_artifact_id) and fact["withheld"] == []
    hers = await deployment.client.get(
        f"/profiles/{profile_id}/facts",
        params={"subject": "medication"},
        headers=bearer(helper.token),
    )
    [seen] = hers.json()
    assert seen["fact_id"] == fact["fact_id"] and seen["value"] == fact["value"]
    assert seen["artifact_id"] is None and seen["withheld"] == ["artifact"]


async def test_no_caller_names_the_scope_a_row_is_written_under(sg: AsyncSession) -> None:
    """The scope of the write is the row's written scope. A caller cannot pass another."""
    owner = await _pa(sg)
    with pytest.raises(TypeError):
        scoped_new(Artifact, owner, Scope.RECORDS, written_scope=Scope.FAMILY)
    row = scoped_new(Event, owner, Scope.MEDICINES, kind=EventKind.DOSE_TAKEN)
    assert row.written_scope is Scope.MEDICINES


async def test_a_reading_is_written_under_the_readings_scope(sg: AsyncSession) -> None:
    """The moment a reading was taken is the readings' part, as the timeline always read it;
    it is now written there, so the row says so itself."""
    owner = await _pa(sg)
    taken = await record_event(
        sg,
        context=owner,
        kind=EventKind.READING,
        occurred_at=now(),
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    visit = await record_event(
        sg,
        context=owner,
        kind=EventKind.VISIT,
        occurred_at=now(),
        label="clinic visit",
        source_channel=SourceChannel.APP,
    )
    assert (taken.written_scope, visit.written_scope) == (Scope.READINGS, Scope.RECORDS)


# --- the oracle: which scope each row sits under, from what the test knows of how it came in ---


def expected_artifact_scope(artifact: Artifact, whatsapp: dict[uuid.UUID, MessageKind]) -> Scope:
    """The migration's backfill rules, written independently: the scope a row of this kind,
    from this source, is written under."""
    if artifact.kind is ArtifactKind.MESSAGE:
        if artifact.storage_key.startswith("questions/"):
            return Scope.ASK
        kind = whatsapp.get(artifact.id)
        if kind is MessageKind.COORDINATION:
            return Scope.FAMILY
        if kind is MessageKind.RED_FLAG:
            return Scope.EMERGENCY
        return Scope.RECORDS if kind is not None else Scope.FAMILY
    if artifact.kind is ArtifactKind.TRANSCRIPT:
        return Scope.VISITS
    if artifact.kind is ArtifactKind.VOICE and artifact.storage_key.startswith("consults/"):
        # A consult recording (E02-05): the visits' part, like its transcript.
        return Scope.VISITS
    if artifact.kind is ArtifactKind.PHOTO and artifact.storage_key.startswith("family-photos/"):
        # A photo the family shared in the thread (E12-02, E21-05): the family's part.
        return Scope.FAMILY
    return Scope.RECORDS


def expected_event_scope(
    event: Event, flagged: set[uuid.UUID], artifacts: dict[uuid.UUID, Scope]
) -> Scope:
    if event.kind is EventKind.READING:
        return Scope.READINGS
    if event.kind is EventKind.DOSE_TAKEN:
        return Scope.MEDICINES
    if event.kind is EventKind.MESSAGE:
        return artifacts.get(event.artifact_id, Scope.FAMILY) if event.artifact_id else Scope.FAMILY
    if (
        event.kind is EventKind.SYMPTOM
        and event.source_channel is SourceChannel.WHATSAPP
        and event.artifact_id is None
        and event.id in flagged
    ):
        return Scope.EMERGENCY
    return Scope.RECORDS


# --- the seeded profile ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Holder:
    name: str
    token: str
    person_id: uuid.UUID
    scopes: frozenset[Scope]


@dataclass
class Seeded:
    profile_id: str
    owner: Holder
    scopes: dict[str, Scope] = field(default_factory=dict)
    """Every artefact, event and fact id on the profile, to the scope it sits under."""
    kinds: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    """A fact or event id, to the artefact and the event it cites."""
    params: dict[str, list[str]] = field(default_factory=dict)
    written: dict[str, Scope | None] = field(default_factory=dict)
    """What each artefact and event row itself says it was written under."""
    card: set[str] = field(default_factory=set)
    """The facts the emergency card's projection reads under EMERGENCY (ADR 0002)."""


async def _context(session: AsyncSession, who: dict[str, str], profile_id: str) -> KeyContext:
    return await resolve_key_context(
        session,
        region=Region.SG,
        person_id=uuid.UUID(who["person_id"]),
        profile_id=uuid.UUID(profile_id),
    )


async def _pa(session: AsyncSession) -> KeyContext:
    from tests.medicines_support import pa

    return await pa(session)


async def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


async def _holder(
    deployment: Deployment,
    owner: dict[str, str],
    profile_id: str,
    phone: str,
    role: str,
    scopes: list[str],
    *,
    preset: bool = False,
) -> Holder:
    """Register this number, let it in to these parts, and cut it a key: the role's preset,
    or narrowed to the parts."""
    who = await register_by_phone(deployment, phone, f"{role} {phone[-3:]}")
    await let_in(deployment, owner, profile_id, phone, scopes)
    body: dict[str, Any] = {"holder_phone_e164": phone, "role": role}
    if not preset:
        body["scopes"] = scopes
    key = await _ok(
        await deployment.client.post(
            f"/profiles/{profile_id}/keys", json=body, headers=bearer(owner["token"])
        ),
        201,
    )
    return Holder(
        name=f"{role}{'' if preset else ':' + ','.join(scopes)}",
        token=who["token"],
        person_id=uuid.UUID(who["person_id"]),
        scopes=frozenset(Scope(s) for s in key["scopes"]),
    )


async def _seed(deployment: Deployment) -> Seeded:
    """One row of every kind: artefacts of every kind and source, events of every kind,
    facts of every subject family, the family's messages and a question — each written
    through the path the app writes it by."""
    client = deployment.client
    pa = await register_by_phone(deployment, PA, "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    await register_by_phone(deployment, MEI, "Mei")
    await let_in(deployment, pa, profile_id, MEI, EVERY_PART)
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/keys",
            json={"holder_phone_e164": MEI, "role": "chief"},
            headers=his,
        ),
        201,
    )
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/consents/whatsapp",
            json={"language": "en", "captured_via": "app"},
            headers=his,
        ),
        201,
    )
    # WhatsApp: the family's business (FAMILY), a fall (EMERGENCY), a reading she reports
    # and says yes to (RECORDS message, READINGS moment and fact).
    outcomes = []
    for said in (
        "who is taking him on Thursday?",
        "he fell in the bathroom",
        "BP 150/90 this morning",
        "yes",
    ):
        heard = await _ok(
            await client.post("/dev/whatsapp/inbound", json={"from_e164": MEI, "text": said})
        )
        outcomes.append(heard["outcome"])
    assert outcomes[0] == "coordination" and outcomes[1].startswith("red_flag"), outcomes
    assert outcomes[2:] == ["proposal", "confirmed"], outcomes
    # The app: a question (ASK), a photo read and confirmed, a feeling, a typed reading.
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/ask",
            json={"question": "what was my blood pressure", "mode": "text"},
            headers=his,
        )
    )
    card = await _ok(
        await client.post(f"/profiles/{profile_id}/photos", json=photo(LIPID_PANEL), headers=his),
        201,
    )
    await _ok(await confirm(deployment, pa["token"], profile_id, card, decide(card)))
    felt = await _ok(
        await client.post(f"/profiles/{profile_id}/feelings", json={"word": "dizzy"}, headers=his),
        201,
    )
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/readings", json={"systolic": 146, "diastolic": 90}, headers=his
        ),
        201,
    )

    async with deployment.sessions() as session:
        owner = await _context(session, pa, profile_id)
        moment = now()
        tan = await add_provider(
            session, context=owner, name="Dr Tan", kind=ProviderKind.DOCTOR, region=Region.SG
        )
        illness = await open_episode(
            session,
            context=owner,
            kind=EpisodeKind.ILLNESS,
            label="chest infection",
            opened_at=moment - timedelta(days=4),
        )
        checkup = await book(
            session,
            owner,
            tan,
            moment - timedelta(days=10),
            "check-up",
            steps=(AppointmentStatus.CONFIRMED, AppointmentStatus.ATTENDED),
        )
        next_visit = await book(
            session, owner, tan, moment + timedelta(days=7), "see Dr Tan", episode_id=illness.id
        )
        # An artefact of every kind the app keeps, hung off the illness.
        kept = [
            await artefact(session, owner, kind=kind)
            for kind in (
                ArtifactKind.PHOTO,
                ArtifactKind.PDF,
                ArtifactKind.VOICE,
                ArtifactKind.READING,
                ArtifactKind.SCREENSHOT,
            )
        ]
        # And the family's message and the question, hung there by the owner, who reads both:
        # a key that holds neither must not reach them through the illness.
        messages = list(
            await session.scalars(
                select(Artifact).where(
                    Artifact.profile_id == owner.profile_id, Artifact.kind == ArtifactKind.MESSAGE
                )
            )
        )
        for each in [*kept, *messages]:
            await hang_on_episode(session, owner, each, illness)
        # Events of every kind the record writes, on the illness.
        for kind, said in (
            (EventKind.VISIT, "clinic visit"),
            (EventKind.DISCHARGE, "hospital letter"),
            (EventKind.ENGAGEMENT, "card seen"),
            (EventKind.SYMPTOM, "tired"),
        ):
            await record_event(
                session,
                context=owner,
                kind=kind,
                occurred_at=moment - timedelta(hours=1),
                label=said,
                source_channel=SourceChannel.APP,
                episode_id=illness.id,
            )
        await reading(session, owner, 138, 84, moment - timedelta(days=1), illness.id)
        # Facts of every subject family: the record's, a reading resting on a photo, a
        # medicine on its label photo, a preference, and a fact resting on the family's
        # message — shown under its own scope, its artefact withheld from a key without FAMILY.
        photo_row = kept[0]
        await assert_fact(
            session,
            context=owner,
            subject="reading:weight",
            attribute="value",
            value=68.5,
            unit="kg",
            confidence=0.9,
            artifact_id=photo_row.id,
            episode_id=illness.id,
        )
        await assert_fact(
            session,
            context=owner,
            subject="declined",
            attribute="card",
            value="walking",
            confidence=0.9,
            artifact_id=photo_row.id,
        )
        # The emergency card's projection (ADR 0002): a clinician's word on a condition — a
        # sugar one, which the shaky-and-sweaty rule reads as the system — an allergy and a
        # blood type, all under the record's scope.
        for subject, attribute, value in (
            ("diabetes", "control", "watch"),
            ("penicillin", "allergy", "rash"),
            ("blood_type", "group", "O+"),
        ):
            await assert_fact(
                session,
                context=owner,
                subject=subject,
                attribute=attribute,
                value=value,
                confidence=0.9,
                artifact_id=photo_row.id,
            )
        family_message = next(m for m in messages if m.storage_key.startswith("messages/"))
        await assert_fact(
            session,
            context=owner,
            subject="who_to_tell",
            attribute="name",
            value="Mei",
            confidence=0.9,
            artifact_id=family_message.id,
            episode_id=illness.id,
        )
        medicine = await add(session, owner, label("amlodipine", "5 mg"))
        await session.commit()
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/medicines/{medicine.line.id}/taken", json={}, headers=his
        ),
        201,
    )
    # The feeling tap's answer (E17): a note read against the new medicine, a RECORDS row that
    # cites a MEDICINES line — withheld, by count, from a key that holds the record only.
    await _ok(
        await client.post(
            f"/profiles/{profile_id}/feelings/{felt['tap_id']}/answer",
            json={"answer": "yesterday"},
            headers=his,
        ),
        201,
    )

    # A visit's transcript (E05): a consult, kept under the visits scope, on his agreement
    # to Nura listening at the visit (ADR 0003).
    await agree_to_recording(deployment, pa, profile_id)
    kept_transcript = await client.post(
        f"/profiles/{profile_id}/appointments/{next_visit.id}/transcript",
        json={"data": b64(transcript(ROUTINE).encode()), "captured_at": "2026-09-03T07:00:00Z"},
        headers=his,
    )
    assert kept_transcript.status_code in (200, 201), kept_transcript.text
    # A consult recording (E02-05): its voice and its transcript, under the visits scope.
    recorded = await client.post(
        f"/profiles/{profile_id}/appointments/{next_visit.id}/recording",
        content=placeholder_consult(CONSULT),
        params={"duration_s": DURATION_S},
        headers={**his, "Content-Type": CONTENT_TYPE},
    )
    assert recorded.status_code == 201, recorded.text
    consult_voice = recorded.json()["recording"]["artifact_id"]

    # A photo shared with the family (E12-02), with his yes to his story (E21-05): the
    # family's part, its bytes read through the thread.
    shared = await _ok(
        await client.post(
            f"/profiles/{profile_id}/thread/photos",
            json={
                "data": b64(PNG_SIGNATURE + b"nura-family-photo-placeholder"),
                "content_type": "image/png",
                "caption": "Lunch on Sunday.",
                "on_his_feed": True,
            },
            headers=his,
        ),
        201,
    )

    # Today's top three (E11-02), composed as he opens it: the cards the voice route plays.
    today = await client.get(f"/profiles/{profile_id}/feed/today", headers=his)
    assert today.status_code == 200, today.text
    feed_items = sorted({o["item_id"] for o in _objects(today.json()) if "item_id" in o})

    seeded = Seeded(
        profile_id=profile_id,
        owner=Holder("owner", pa["token"], uuid.UUID(pa["person_id"]), frozenset(ALL_SCOPES)),
    )
    async with deployment.sessions() as session:
        pid = uuid.UUID(profile_id)
        whatsapp = {
            row.artifact_id: row.kind
            for row in await session.scalars(
                select(WhatsAppMessage).where(WhatsAppMessage.profile_id == pid)
            )
            if row.artifact_id is not None
        }
        flagged = {
            f.event_id for f in await session.scalars(select(Flag).where(Flag.profile_id == pid))
        }
        artifacts = list(await session.scalars(select(Artifact).where(Artifact.profile_id == pid)))
        artifact_scopes = {a.id: expected_artifact_scope(a, whatsapp) for a in artifacts}
        for a in artifacts:
            seeded.scopes[str(a.id)] = artifact_scopes[a.id]
            seeded.kinds[str(a.id)] = f"artifact({a.kind.value})"
            seeded.written[str(a.id)] = getattr(a, "written_scope", None)
        events = list(await session.scalars(select(Event).where(Event.profile_id == pid)))
        for e in events:
            seeded.scopes[str(e.id)] = expected_event_scope(e, flagged, artifact_scopes)
            seeded.kinds[str(e.id)] = f"event({e.kind.value})"
            seeded.provenance[str(e.id)] = (_str(e.artifact_id), None)
            seeded.written[str(e.id)] = getattr(e, "written_scope", None)
        # The feed's cards (E11): each is of the scope of what it says, and a card of a scope
        # the key does not hold is neither listed nor spoken to it.
        for item in await session.scalars(select(FeedItem).where(FeedItem.profile_id == pid)):
            seeded.scopes[str(item.id)] = item.scope
            seeded.kinds[str(item.id)] = f"feed_item({item.type.value})"
        for f in await session.scalars(select(Fact).where(Fact.profile_id == pid)):
            seeded.scopes[str(f.id)] = scope_for_subject(f.subject)
            seeded.kinds[str(f.id)] = f"fact({f.subject})"
            seeded.provenance[str(f.id)] = (_str(f.artifact_id), _str(f.event_id))
            if f.attribute in ("control", "allergy") or f.subject in ("blood_type", "person"):
                seeded.card.add(str(f.id))
        seeded.params = {
            "event_id": [str(e.id) for e in events],
            "episode_id": [str(illness.id)],
            "appointment_id": [str(next_visit.id), str(checkup.id)],
            "analyte": ["ldl", "total_cholesterol", "blood_pressure"],
            "provider_id": [str(tan.id)],
            "line_id": [str(medicine.line.id)],
            "card_id": [card["card_id"]],
            "note_id": [str(uuid.uuid4())],
            "job_id": [str(uuid.uuid4())],
            "item_id": feed_items or [str(uuid.uuid4())],
            "artifact_id": [consult_voice],
            "photo_id": [shared["photo"]["photo_id"]],
        }
    return seeded


def _str(value: uuid.UUID | None) -> str | None:
    return None if value is None else str(value)


async def _holders(deployment: Deployment, seeded: Seeded) -> list[Holder]:
    """The owner; a key of every preset role; and a caregiver and a chief narrowed to each
    single part."""
    owner = {"token": seeded.owner.token, "person_id": str(seeded.owner.person_id)}
    holders = [seeded.owner]
    number = iter(range(100, 999))
    for role in KeyRole:
        parts = sorted(s.value for s in ROLE_SCOPES[role] if s is not Scope.PROFILE)
        holders.append(
            await _holder(
                deployment,
                owner,
                seeded.profile_id,
                f"+65934{next(number):05d}",
                role.value,
                parts,
                preset=True,
            )
        )
    for role in (KeyRole.CAREGIVER, KeyRole.CHIEF):
        for part in EVERY_PART:
            holders.append(
                await _holder(
                    deployment,
                    owner,
                    seeded.profile_id,
                    f"+65934{next(number):05d}",
                    role.value,
                    [part],
                )
            )
    return holders


# --- the registry of routes --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Walk:
    """How the matrix calls one read route. `each` names a path parameter walked over every
    seeded value; `params`/`json` are the query and body; `variants` more query strings."""

    method: str
    path: str
    params: dict[str, str] = field(default_factory=dict)
    json: dict[str, Any] | None = None
    variants: tuple[dict[str, str], ...] = ()
    card: bool = False
    """The emergency card: EMERGENCY's one fixed projection (ADR 0002). The facts it reads
    are the card's own scope, not a leak; anything past ADR 0002's list is."""
    button: bool = False
    """The not-feeling-well button and the symptom log: the safety rules read the record as
    the system (`red_flags._system_read`), and nothing they read reaches the caller."""


P = "/profiles/{profile_id}"

READ_ROUTES: tuple[Walk, ...] = (
    Walk("GET", P),
    Walk("GET", f"{P}/stewardship"),
    Walk("GET", f"{P}/keys"),
    Walk("GET", f"{P}/consents"),
    Walk("GET", f"{P}/audit", params={"limit": "500"}),
    Walk("GET", f"{P}/notes"),
    Walk("GET", f"{P}/state"),
    Walk("GET", f"{P}/review-cards"),
    Walk("GET", f"{P}/review-cards/{{card_id}}"),
    Walk(
        "GET",
        f"{P}/facts",
        variants=tuple(
            {"subject": s}
            for s in (
                "medication",
                "blood_pressure",
                "reading:weight",
                "lipid_panel",
                "who_to_tell",
                "declined",
                "feeling",
            )
        ),
    ),
    Walk("GET", f"{P}/events/{{event_id}}/notes"),
    Walk("GET", f"{P}/events/{{event_id}}/notes/{{note_id}}/content"),
    Walk("GET", f"{P}/feed"),
    Walk("GET", f"{P}/feed/cached"),
    Walk("GET", f"{P}/feed/today"),
    Walk("GET", f"{P}/feed/{{item_id}}/voice"),
    Walk("GET", f"{P}/delivery-settings"),
    Walk("GET", f"{P}/deliveries"),
    Walk("GET", f"{P}/sources"),
    Walk("GET", f"{P}/search-jobs"),
    Walk("GET", f"{P}/search-jobs/{{job_id}}"),
    Walk("GET", f"{P}/medicines"),
    Walk("GET", f"{P}/medicines/history"),
    Walk("GET", f"{P}/medicines/interactions"),
    Walk("GET", f"{P}/medicines/today"),
    Walk("GET", f"{P}/medicines/{{line_id}}/story"),
    Walk("GET", f"{P}/medicines/{{line_id}}/story/voice"),
    Walk("GET", f"{P}/whatsapp/thread"),
    Walk("GET", f"{P}/timeline"),
    Walk("GET", f"{P}/episodes/{{episode_id}}"),
    Walk("GET", f"{P}/providers"),
    Walk("GET", f"{P}/providers/{{provider_id}}"),
    Walk("GET", f"{P}/changes"),
    Walk("POST", f"{P}/ask", json={"question": "what papers do I have", "mode": "text"}),
    Walk("GET", f"{P}/grants"),
    Walk("GET", f"{P}/helpers"),
    Walk("GET", f"{P}/thread"),
    Walk("GET", f"{P}/thread/digest", params={"since": "2026-08-01T00:00:00Z"}),
    Walk("GET", f"{P}/roster"),
    Walk("GET", f"{P}/roster/on-duty"),
    Walk("GET", f"{P}/tasks"),
    Walk("GET", f"{P}/trail"),
    Walk("GET", f"{P}/privacy"),
    Walk("GET", f"{P}/pushes"),
    Walk("GET", f"{P}/documents"),
    Walk("GET", f"{P}/proud"),
    Walk("GET", f"{P}/emergency-card", card=True),
    Walk("GET", f"{P}/emergency-card.html", card=True),
    Walk("GET", f"{P}/symptoms", params={"since": "2026-08-01T00:00:00Z"}),
    Walk("POST", f"{P}/not-feeling-well", json={"words": "he is shaky and sweaty"}, button=True),
    Walk("POST", f"{P}/symptoms", json={"words": "he is shaky and sweaty"}, button=True),
    Walk("GET", f"{P}/appointments"),
    Walk("GET", f"{P}/appointments/{{appointment_id}}/brief"),
    Walk("GET", f"{P}/appointments/{{appointment_id}}/questions"),
    Walk("GET", f"{P}/appointments/{{appointment_id}}/summaries"),
    Walk("GET", f"{P}/appointments/{{appointment_id}}/logistics"),
    Walk("GET", f"{P}/appointments/{{appointment_id}}/recording/notice"),
    Walk("GET", f"{P}/appointments/{{appointment_id}}/recordings"),
    Walk("GET", f"{P}/artifacts/{{artifact_id}}/clip", params={"start": "19.8", "end": "28.9"}),
    Walk("POST", f"{P}/transcripts/search", json={"words": "water pill"}),
    Walk("GET", f"{P}/thread/photos/{{photo_id}}/content"),
    Walk("GET", f"{P}/memos"),
    Walk("GET", f"{P}/proposals"),
    Walk("GET", f"{P}/routine"),
    Walk("GET", f"{P}/trends/{{analyte}}"),
    Walk("GET", f"{P}/settings"),
    Walk("GET", f"{P}/biography"),
    Walk("GET", f"{P}/plan"),
    Walk("GET", f"{P}/feelings/cloud"),
    Walk("GET", f"{P}/feelings/notes"),
    Walk("GET", f"{P}/nudges/plan"),
    Walk("GET", f"{P}/nudge-metrics"),
    Walk("GET", f"{P}/me-summary"),
)
"""Every route under `/profiles/{id}/` that answers with rows of the profile."""

NOT_WALKED: dict[tuple[str, str], str] = {
    ("POST", f"{P}/confirmations"): "mints a yes for a draft the caller sends; returns its id",
    ("POST", f"{P}/claim"): "the patient claims his graph; returns the profile row",
    ("POST", f"{P}/keys"): "cuts a key; returns the key",
    ("DELETE", f"{P}/keys/{{key_id}}"): "closes a key; returns the key",
    ("PUT", f"{P}/keys/{{key_id}}"): "narrows a key; returns the key",
    ("POST", f"{P}/consents/sharing"): "writes an agreement; returns it",
    (
        "POST",
        f"{P}/consents/sharing/preview",
    ): "renders the words of an agreement the caller sends; returns no rows",
    ("POST", f"{P}/consents/whatsapp"): "writes an agreement; returns it",
    ("POST", f"{P}/consents/recording"): "writes an agreement; returns it",
    ("POST", f"{P}/notes"): "writes his own note; returns it",
    ("POST", f"{P}/readings"): "writes a reading; returns the event and fact it wrote",
    ("POST", f"{P}/photos"): "keeps a photo; returns its card",
    ("POST", f"{P}/imports"): "keeps a PDF; returns its card",
    ("POST", f"{P}/readings/photo"): "keeps a photo of a machine; returns its card",
    (
        "POST",
        f"{P}/review-cards/{{card_id}}/fields/{{field_id}}/type",
    ): "types a field; returns the card",
    (
        "POST",
        f"{P}/review-cards/{{card_id}}/confirm",
    ): "writes what the card says; returns what it wrote",
    ("POST", f"{P}/events/{{event_id}}/notes"): "writes a note on an event; returns it",
    ("POST", f"{P}/feed/{{item_id}}/engagement"): "writes what he did with a card",
    ("POST", f"{P}/search-jobs"): "starts a search; returns the job",
    ("POST", f"{P}/feelings"): "writes a feeling; returns the event and flag it wrote",
    ("POST", f"{P}/medicines/draft"): "plans a medicine from a label the caller sends",
    ("POST", f"{P}/medicines"): "writes a medicine; returns the line",
    ("POST", f"{P}/medicines/{{line_id}}/taken"): "writes a dose taken; returns it",
    ("POST", f"{P}/episodes"): "opens an episode; returns it",
    ("POST", f"{P}/episodes/{{episode_id}}/attach"): "hangs a paper; returns the attachment",
    ("POST", f"{P}/appointments"): "books a visit; returns it",
    ("POST", f"{P}/appointments/{{appointment_id}}/status"): "moves a visit; returns it",
    (
        "POST",
        f"{P}/appointments/{{appointment_id}}/attach",
    ): "hangs a paper; returns the attachment",
    ("POST", f"{P}/providers"): "adds a provider; returns it",
    ("POST", f"{P}/providers/{{provider_id}}/notes"): "writes the chief's line; returns it",
    ("POST", f"{P}/thread"): "posts to the family thread; returns the entry",
    ("POST", f"{P}/roster"): "adds a roster slot; returns it",
    ("DELETE", f"{P}/roster/{{slot_id}}"): "removes a roster slot",
    ("POST", f"{P}/tasks"): "adds a task; returns it",
    ("POST", f"{P}/tasks/{{task_id}}/done"): "closes a task; returns it",
    ("POST", f"{P}/privacy"): "marks a part only-me; returns the mark",
    ("POST", f"{P}/privacy/{{scope}}/lift"): "lifts an only-me mark; returns it",
    ("POST", f"{P}/pushes/preview"): "renders a push from a template the caller names",
    ("POST", f"{P}/pushes"): "schedules a push; returns it",
    ("POST", f"{P}/documents"): "keeps a document; returns the document list, as GET does",
    ("POST", f"{P}/appointments/{{appointment_id}}/questions"): "changes a question on a yes",
    (
        "POST",
        f"{P}/appointments/{{appointment_id}}/transcript",
    ): "keeps a transcript; returns its card",
    ("POST", f"{P}/appointments/{{appointment_id}}/recording"): (
        "keeps a consult recording; returns what it kept and its card"
    ),
    ("POST", f"{P}/appointments/{{appointment_id}}/driver"): "gives the drive on a yes; returns the task",
    ("POST", f"{P}/appointments/{{appointment_id}}/summary/{{summary_id}}/confirm"): (
        "writes what the summary card says; returns what it wrote"
    ),
    ("PUT", f"{P}/routine"): "sets his routine on a yes; returns it",
    ("POST", f"{P}/connectors/calendar"): "connects a calendar; returns the connector",
    ("POST", f"{P}/connectors/{{connector_id}}/scan"): "scans a calendar; returns what it proposes",
    ("POST", f"{P}/proposals/{{proposal_id}}/accept"): "books a proposed visit on a yes",
    ("POST", f"{P}/proposals/{{proposal_id}}/dismiss"): "dismisses a proposed visit",
    ("PUT", f"{P}/settings"): "sets his settings on a yes; returns them",
    ("POST", f"{P}/biography"): "starts the biography session; returns it",
    ("POST", f"{P}/biography/papers"): "keeps a paper for the biography; returns its card",
    ("POST", f"{P}/biography/read-back"): "reads back what he said, for his yes",
    ("POST", f"{P}/biography/questions"): "answers a biography question on a yes",
    ("POST", f"{P}/biography/close"): "closes the biography session",
    ("POST", f"{P}/plan/later"): "moves the first-week plan to later",
    ("POST", f"{P}/plan/{{prompt}}/skip"): "skips one prompt of the plan",
    ("PUT", f"{P}/delivery-settings"): "sets how Nura reaches him on a yes; returns them",
    ("POST", f"{P}/ladders/{{ladder_id}}/acknowledge"): "says I have got it; closes the ladder",
    ("POST", f"{P}/feelings/{{tap_id}}/answer"): "answers a tap; returns the note it wrote",
    ("POST", f"{P}/nudges/plan"): "hands the day's nudge to delivery; returns it",
    ("POST", f"{P}/nudges/{{nudge_id}}/response"): "writes what he did with a nudge",
    ("POST", f"{P}/thread/photos"): "shares a photo with the family; returns the entry",
    ("POST", f"{P}/thread/photos/{{photo_id}}/take-back"): "takes a photo back; returns it",
}
"""Every other route under `/profiles/{id}/`, and why it is not walked: it writes, and
answers with what the caller wrote."""


def _profile_routes() -> Iterator[tuple[str, str]]:
    """Every (method, path) the app serves under `/profiles/{profile_id}`, found two ways that
    do not depend on how a FastAPI version keeps an included router: walking the routes
    recursively through included routers and mounts, and reading the OpenAPI paths. The
    `/api` twin of a route (`app.channels.api.API_PREFIX`) is the same route."""
    from app.channels.api import API_PREFIX, create_app
    from tests.whatsapp_support import deployment as whatsapp_deployment

    settings, providers = whatsapp_deployment(Path("."))
    app = create_app(settings, None, providers)  # type: ignore[arg-type]

    def walk(routes: Any, prefix: str = "") -> Iterator[tuple[str, str]]:
        for route in routes:
            path = getattr(route, "path", "") or ""
            methods = getattr(route, "methods", None)
            inner = getattr(route, "routes", None)
            if inner is None and getattr(route, "router", None) is not None:
                inner = getattr(route.router, "routes", None)
            if methods:
                for method in set(methods) - {"HEAD", "OPTIONS"}:
                    yield method, prefix + path
            elif inner is not None:
                yield from walk(inner, prefix + (getattr(route, "prefix", "") or path))

    found = set(walk(app.routes))
    for path, operations in app.openapi().get("paths", {}).items():
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                found.add((method.upper(), path))
    for method, path in sorted(found):
        if path.startswith(API_PREFIX + "/"):
            path = path[len(API_PREFIX) :]
        if path == P or path.startswith(P + "/"):
            yield method, path


def test_every_profile_route_is_in_the_matrix() -> None:
    walked = {(w.method, w.path) for w in READ_ROUTES}
    routes = set(_profile_routes())
    # An enumeration that found nothing would call every route stale: say so plainly instead.
    assert ("GET", f"{P}/facts") in routes and len(routes) > 50, sorted(routes)
    missing = sorted(routes - walked - set(NOT_WALKED))
    assert missing == [], f"add these to READ_ROUTES (or, for a write, NOT_WALKED): {missing}"
    assert not walked & set(NOT_WALKED)
    # A GET is a read: it is walked, never excused.
    assert [r for r in NOT_WALKED if r[0] == "GET"] == []
    stale = sorted((walked | set(NOT_WALKED)) - routes)
    assert stale == [], f"these routes no longer exist: {stale}"


# --- the matrix ---------------------------------------------------------------------------------

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _strings(body: Any) -> Iterator[str]:
    if isinstance(body, str):
        yield body
    elif isinstance(body, dict):
        for key, value in body.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(body, list):
        for value in body:
            yield from _strings(value)


def _objects(body: Any) -> Iterator[dict[str, Any]]:
    if isinstance(body, dict):
        yield body
        for value in body.values():
            yield from _objects(value)
    elif isinstance(body, list):
        for value in body:
            yield from _objects(value)


CARD_FIELDS = frozenset(
    {
        # Whose card, rendered from which State, when, in which words.
        "card_id",
        "profile_id",
        "state_id",
        "rendered_at",
        "name",
        "language",
        "spoken_language",
        "lines",
        "emergency_number",
        # ADR 0002's projection: conditions by a clinician's control word, allergies, blood
        # type, birth year as a decade band, the active medicines and the high-risk ones, the
        # active chiefs to call, the providers, the date of the last blood-pressure reading.
        "conditions",
        "allergies",
        "blood_type",
        "age_band",
        "medicines",
        "high_risk",
        "contacts",
        "clinic",
        "last_reading_at",
    }
)
NOT_ON_THE_CARD = (
    "146",
    "138",
    "68.5",
    "cholesterol",
    "ldl",
    "walking",
    "chest infection",
    "check-up",
)
"""Seeded values the card must never carry: reading numbers, a lab value, a preference, an
episode, a visit."""
CONDITION_WORDS = ("diabetes", "sugar sickness", "penicillin")
MEDICINE_WORDS = ("amlodipine",)
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T[0-9:.+Z-]+")


def _text(body: Any) -> str:
    raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return _STAMP.sub("", _UUID.sub("", raw)).lower()


def _check(
    where: str,
    holder: Holder,
    body: Any,
    seeded: Seeded,
    seen: set[str],
    problems: list[str],
    walk: Walk | None = None,
) -> None:
    """Every seeded row a response names is of a scope the holder holds, and every fact or
    event whose artefact or event it may not follow says so by name."""
    on_the_card = walk is not None and walk.card and Scope.EMERGENCY in holder.scopes
    for found in {m for s in _strings(body) for m in _UUID.findall(s)}:
        scope = seeded.scopes.get(found)
        if scope is None:
            continue
        seen.add(found)
        if on_the_card and found in seeded.card:
            continue
        if scope not in holder.scopes:
            problems.append(
                f"{holder.name} {where}: {seeded.kinds[found]} {found} sits under {scope}"
            )
    for obj in _objects(body):
        # An object that shows a fact's or an event's provenance: it carries the row's id and
        # the artefact it came from. One that only names a fact (a medicine's line) shows none.
        if not {"artifact_id", "source_artifact_id"} & set(obj) or "fact_ids" in obj:
            continue
        own = obj.get("fact_id") or obj.get("event_id")
        if not isinstance(own, str) or own not in seeded.provenance:
            continue
        artifact_id, event_id = seeded.provenance[own]
        named = obj.get("withheld", [])
        for what, ref in (("artifact", artifact_id), ("event", event_id)):
            hidden = ref is not None and seeded.scopes.get(ref, Scope.PROFILE) not in holder.scopes
            if hidden and what not in named:
                problems.append(
                    f"{holder.name} {where}: {seeded.kinds[own]} {own} drops its {what} in silence"
                )
    if walk is not None and walk.card:
        text = _text(body)
        for value in NOT_ON_THE_CARD:
            if value in text:
                problems.append(f"{holder.name} {where}: the card carries {value!r}")
        if isinstance(body, dict) and not set(body) <= CARD_FIELDS:
            problems.append(
                f"{holder.name} {where}: the card carries {sorted(set(body) - CARD_FIELDS)}"
            )
    if walk is not None and walk.button:
        text = _text(body)
        if Scope.RECORDS not in holder.scopes:
            problems.extend(
                f"{holder.name} {where}: the system's read reached the caller: {word!r}"
                for word in CONDITION_WORDS
                if word in text
            )
        if Scope.MEDICINES not in holder.scopes:
            problems.extend(
                f"{holder.name} {where}: the system's read reached the caller: {word!r}"
                for word in MEDICINE_WORDS
                if word in text
            )


async def _walk(
    deployment: Deployment, holder: Holder, seeded: Seeded, seen: set[str], problems: list[str]
) -> None:
    for walk in READ_ROUTES:
        path = walk.path.replace("{profile_id}", seeded.profile_id)
        names = re.findall(r"{(\w+)}", path)
        combos: list[dict[str, str]] = [{}]
        for name in names:
            combos = [{**c, name: value} for c in combos for value in seeded.params[name]]
        for combo in combos:
            url = path.format(**combo)
            for params in (walk.params, *walk.variants):
                response = await deployment.client.request(
                    walk.method, url, params=params, json=walk.json, headers=bearer(holder.token)
                )
                where = f"{walk.method} {walk.path}{'?' + str(params) if params else ''}"
                if response.status_code >= 500:
                    problems.append(f"{holder.name} {where}: {response.status_code}")
                elif response.status_code < 300 and response.content:
                    kind = response.headers.get("content-type", "")
                    # Audio names nothing: a spoken twin answers for the card it speaks, a clip
                    # (E03-05) for the recording it is cut from.
                    body = (
                        {"spoken": list(combo.values())}
                        if kind.startswith(("audio/", "image/"))
                        else response.text
                        if kind.startswith("text/html")
                        else response.json()
                    )
                    _check(where, holder, body, seeded, seen, problems, walk)


async def _services(
    deployment: Deployment, holder: Holder, seeded: Seeded, seen: set[str], problems: list[str]
) -> None:
    """The same property one layer down: every read of the three tables, every door."""
    held = holder.scopes

    def outside(where: str, rows: Any) -> None:
        for row in rows:
            scope = seeded.scopes.get(str(row.id))
            if scope is not None:
                seen.add(str(row.id))
            if scope is not None and scope not in held:
                problems.append(f"{holder.name} {where}: {seeded.kinds[str(row.id)]} under {scope}")

    async with deployment.sessions() as session:
        context = await _context(session, {"person_id": str(holder.person_id)}, seeded.profile_id)
        for door in sorted(held):
            # The artefacts and events carry the scope each row was written under, so every
            # read of them, through any door, returns rows of the key's scopes only. A fact's
            # scope is its subject's, and the readers of facts narrow by it (below); the door
            # of the fact table stays the caller's, for EMERGENCY's card (ADR 0002).
            for model in (Artifact, Event):
                outside(
                    f"audited_read({model.__name__}, {door})",
                    await audited_read(session, model, context, door),
                )
        for ident, scope in seeded.scopes.items():
            kind = seeded.kinds[ident]
            try:
                if kind.startswith("artifact"):
                    await require_artifact(session, context=context, artifact_id=uuid.UUID(ident))
                elif kind.startswith("event"):
                    await require_event(session, context=context, event_id=uuid.UUID(ident))
                else:
                    continue
            except (NoSuchArtifact, NoSuchEvent, OutOfScope, OnlyTheFamilyHears):
                continue
            if scope not in held:
                problems.append(f"{holder.name} require: {kind} {ident} under {scope}")
        if Scope.RECORDS in held:
            outside("current_facts()", await current_facts(session, context=context))
            found = await gather(session, context=context)
            outside("gather", [*found.artifacts.values(), *found.events, *found.facts])
        for subject in (
            "medication",
            "blood_pressure",
            "reading:weight",
            "lipid_panel",
            "who_to_tell",
        ):
            if scope_for_subject(subject) in held:
                outside(
                    f"current_facts({subject})",
                    await current_facts(session, context=context, subject=subject),
                )
        # The refusals above were written down; a test is its own channel and drops the replay.
        take_keepers(session)
        await session.commit()


async def test_every_read_returns_rows_of_the_keys_scopes_only_and_names_what_it_withholds(
    deployment: Deployment,
) -> None:
    seeded = await _seed(deployment)
    holders = await _holders(deployment, seeded)
    problems: list[str] = []

    # Every artefact and event row says the scope it was written under, and it is the scope
    # the path that wrote it writes under.
    for ident, written in seeded.written.items():
        if written != seeded.scopes[ident]:
            problems.append(
                f"{seeded.kinds[ident]} {ident} says {written}, was written under {seeded.scopes[ident]}"
            )

    seen_by: dict[str, set[str]] = {}
    for holder in holders:
        seen: set[str] = set()
        await _walk(deployment, holder, seeded, seen, problems)
        await _services(deployment, holder, seeded, seen, problems)
        seen_by[holder.name] = seen

    # Not vacuous: the owner's walk — the routes and the services — reaches rows of every scope
    # the leaks were about. No route shows a tablet's moment by id; the doors do.
    reached = {(seeded.kinds[i].split("(")[0], seeded.scopes[i]) for i in seen_by["owner"]}
    for wanted in (
        ("artifact", Scope.RECORDS),
        ("artifact", Scope.FAMILY),
        ("artifact", Scope.ASK),
        ("artifact", Scope.EMERGENCY),
        ("artifact", Scope.VISITS),
        ("event", Scope.RECORDS),
        ("event", Scope.READINGS),
        ("event", Scope.MEDICINES),
        ("fact", Scope.RECORDS),
        ("fact", Scope.READINGS),
        ("fact", Scope.MEDICINES),
    ):
        assert wanted in reached, f"the owner's walk never reached a {wanted[0]} under {wanted[1]}"
    assert any(kind == "feed_item" for kind, _ in reached), "the owner's walk never reached a card"
    assert problems == [], "\n".join(sorted(set(problems)))


def test_only_the_emergency_card_reads_across_written_scopes() -> None:
    """ADR 0002's projection is the one read not narrowed by the scope a row was written
    under. Anything else reaching for it is a new leak, and fails here."""
    import app

    root = Path(app.__file__).resolve().parent
    callers = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if re.search(r"\b(audited_projection_read|scoped_projection)\b", path.read_text())
    )
    assert callers == ["audit/access.py", "keys/repository.py", "safety/emergency_card.py"]


RAW_READS = re.compile(
    r"(?<![\w.])select\(\s*(Fact|Artifact|Event)\b"
    r"|\.get\(\s*(Fact|Artifact|Event)\s*,"
    r"|\bmodel\s*=\s*(Fact|Artifact|Event)\b"
)
APPROVED_RAW_READS = {
    "safety/red_flags.py": (
        "the safety rules' own read of the record as the system (`_system_read`, ADR 0002): "
        "nothing it reads reaches the caller, only whether a flag is held back"
    ),
}


def test_no_raw_read_of_the_row_scoped_tables_outside_the_approved_readers() -> None:
    """Artefacts, events and facts are read through the doors, which narrow them by the scope
    each row sits under; the raw reads that need no key — a keeper replaying its own write,
    the kind of an artefact a rule looks at — live in `app/memory`, where the scope is. A raw
    `select`, `session.get` or raw reader of the three tables anywhere else fails here."""
    import app

    root = Path(app.__file__).resolve().parent
    found: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        where = str(path.relative_to(root))
        if where.startswith("memory/"):
            continue
        source = path.read_text()
        lines = [source[: m.start()].count("\n") + 1 for m in RAW_READS.finditer(source)]
        if lines:
            found[where] = lines
    assert set(found) == set(APPROVED_RAW_READS), found


# --- the migration's backfill ---------------------------------------------------------------------

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _fill(connection: Connection, table: str, **values: Any) -> None:
    """Insert one row, every NOT NULL column the test does not care about filled with
    something of its type. Foreign keys are off on this engine: only the columns matter."""
    for column in inspect(connection).get_columns(table):
        if column["name"] in values or column["nullable"]:
            continue
        kind = str(column["type"]).upper()
        values[column["name"]] = (
            uuid.uuid4().hex
            if "CHAR(32)" in kind
            else now()
            if "DATE" in kind
            else 0
            if "INT" in kind or "FLOAT" in kind or "BOOL" in kind
            else "{}"
            if "JSON" in kind
            else "x"
        )
    names = ", ".join(values)
    marks = ", ".join(f":{name}" for name in values)
    connection.execute(text(f"INSERT INTO {table} ({names}) VALUES ({marks})"), values)


def test_the_migration_backfills_the_written_scope_from_what_is_known() -> None:
    revisions = {m.revision: m for m in map(_load, sorted(VERSIONS.glob("*.py")))}
    ordered = _in_order(revisions)
    row_scope: ModuleType = revisions["0019_row_scope"]
    before = [m for m in ordered if m is not row_scope]
    engine = create_engine("sqlite+pysqlite://")
    with engine.begin() as connection:
        for migration in before:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
        profile = uuid.uuid4().hex
        ids: dict[str, str] = {}

        def artifact(name: str, kind: str, key: str, source: str) -> str:
            ids[name] = uuid.uuid4().hex
            _fill(
                connection,
                "artifact",
                id=ids[name],
                profile_id=profile,
                kind=kind,
                storage_key=key,
                source_channel=source,
                region="SG",
            )
            return ids[name]

        def event(name: str, kind: str, source: str = "app", artifact_id: str | None = None) -> str:
            ids[name] = uuid.uuid4().hex
            _fill(
                connection,
                "event",
                id=ids[name],
                profile_id=profile,
                kind=kind,
                source_channel=source,
                artifact_id=artifact_id,
            )
            return ids[name]

        question = artifact("question", "message", f"questions/{profile}/q", "app")
        coordination = artifact("coordination", "message", f"messages/{profile}/c", "whatsapp")
        fall = artifact("fall", "message", f"messages/{profile}/f", "whatsapp")
        health = artifact("health", "message", f"messages/{profile}/h", "whatsapp")
        artifact("stray", "message", f"messages/{profile}/s", "whatsapp")
        artifact("photo", "photo", f"photos/{profile}/p", "app")
        artifact("pdf", "pdf", f"imports/{profile}/d", "whatsapp")
        artifact("transcript", "transcript", f"transcripts/{profile}/t", "app")
        for name, kind, fact in (
            ("coordination", "coordination", coordination),
            ("fall", "red_flag", fall),
            ("health", "health_event", health),
        ):
            _fill(
                connection,
                "whatsapp_message",
                profile_id=profile,
                kind=kind,
                artifact_id=fact,
                direction="inbound",
            )
        event("reading", "reading")
        event("dose", "dose_taken")
        event("family", "message", "whatsapp", coordination)
        event("stray_message", "message", "whatsapp")
        moment = event("moment", "symptom", "whatsapp")
        _fill(connection, "red_flag", profile_id=profile, event_id=moment)
        tapped = event("tapped", "symptom", "app")
        _fill(connection, "red_flag", profile_id=profile, event_id=tapped)
        event("check_in", "symptom", "whatsapp", health)
        event("visit", "visit")
        event("discharge", "discharge")
        event("engagement", "engagement")
        assert question

        # A card composed before row scope, someone's engagement with it, and the page cache.
        card = uuid.uuid4().hex
        _fill(connection, "feed_item", id=card, profile_id=profile)
        _fill(
            connection, "feed_engagement", profile_id=profile, item_id=card, event_id=ids["visit"]
        )
        _fill(connection, "feed_page", profile_id=profile)

        with Operations.context(MigrationContext.configure(connection)):
            row_scope.upgrade()
        # The cards are gone, to be rendered again under the new rules; the event under the
        # engagement stays on the record.
        for table in ("feed_item", "feed_engagement", "feed_page"):
            assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table
        assert (
            connection.execute(
                text("SELECT count(*) FROM event WHERE id = :id"), {"id": ids["visit"]}
            ).scalar()
            == 1
        )
        written = {
            row.id: row.written_scope
            for table in ("artifact", "event")
            for row in connection.execute(text(f"SELECT id, written_scope FROM {table}"))
        }
        assert {name: written[ident] for name, ident in ids.items()} == {
            "question": "ask",
            "coordination": "family",
            "fall": "emergency",
            "health": "records",
            "stray": "family",
            "photo": "records",
            "pdf": "records",
            "transcript": "visits",
            "reading": "readings",
            "dose": "medicines",
            "family": "family",
            "stray_message": "family",
            "moment": "emergency",
            "tapped": "records",
            "check_in": "records",
            "visit": "records",
            "discharge": "records",
            "engagement": "records",
        }
        built = inspect(connection)
        for table in ("artifact", "event"):
            [column] = [c for c in built.get_columns(table) if c["name"] == "written_scope"]
            assert column["nullable"] is False
        with Operations.context(MigrationContext.configure(connection)):
            row_scope.downgrade()
        assert "written_scope" not in {
            c["name"] for c in inspect(connection).get_columns("artifact")
        }
    engine.dispose()
