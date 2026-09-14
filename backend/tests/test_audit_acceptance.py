"""E00-07 acceptance.

    Any access to patient data is queryable by patient and chief.

One test per clause: that every read, write and share lands in the trail, that the patient
can query it, that his chief can query the same, and that nobody else can. The last test is
the other half of the promise: the trail says what was touched and never what it said.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import record_share
from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.audit.trail import NotTheirsToRead, read_audit
from app.db import take_keepers, utcnow
from app.identity.models import Person, Profile
from app.identity.service import create_own_profile, register_person
from app.keys.context import KeyContext, NoKey, OutOfScope, resolve_key_context
from app.keys.grants import grant_key, revoke_key
from app.keys.scopes import KeyRole, Scope
from app.regions import OutOfRegion, Region
from tests.support import Note, add_note, read_notes, refused_unit

PRIVATE = "Pa keeps this one to himself."
WATER_PILL = "The water pill is at 8 in the morning."


async def _pa_and_his_daughter(
    session: AsyncSession,
) -> tuple[Profile, KeyContext, Person, KeyContext]:
    """Pa opens his graph and cuts his daughter a caregiver key, as in E00-01."""
    pa = await register_person(
        session, region=Region.SG, display_name="Pa", phone_e164="+6591110001"
    )
    profile = await create_own_profile(session, region=Region.SG, owner=pa)
    owner = await resolve_key_context(
        session, region=Region.SG, person_id=pa.id, profile_id=profile.id
    )
    daughter = await register_person(
        session, region=Region.SG, display_name="Daughter", phone_e164="+6591110002"
    )
    await grant_key(
        session,
        context=owner,
        holder=daughter,
        role=KeyRole.CAREGIVER,
        scopes=[Scope.MEDICINES, Scope.VISITS, Scope.SEND],
        basis="owner_consent",
    )
    held = await resolve_key_context(
        session, region=Region.SG, person_id=daughter.id, profile_id=profile.id
    )
    return profile, owner, daughter, held


# --- any access is written down --------------------------------------------------------


async def test_every_read_write_and_share_of_patient_data_is_queryable_by_the_patient(
    sg: AsyncSession,
) -> None:
    profile, owner, daughter, held = await _pa_and_his_daughter(sg)

    await add_note(sg, owner, scope=Scope.MEDICINES, body=WATER_PILL)
    read = await read_notes(sg, held, scope=Scope.MEDICINES)
    assert [note.body for note in read] == [WATER_PILL]

    await record_share(
        sg,
        context=held,
        scope=Scope.MEDICINES,
        target="medicine_list",
        channel=Channel.SHARE_LINK,
        shared_with_label="Dr Tan's clinic",
    )

    trail = await read_audit(sg, context=owner)
    touched = [(entry.actor_person_id, entry.action, entry.scope, entry.target) for entry in trail]

    # The write Pa made himself, the read his daughter made, and the copy she sent out.
    assert (owner.person_id, Action.WRITE, Scope.MEDICINES, Note.__tablename__) in touched
    assert (daughter.id, Action.READ, Scope.MEDICINES, Note.__tablename__) in touched
    assert (daughter.id, Action.SHARE, Scope.MEDICINES, "medicine_list") in touched

    # Every entry names the profile it touched and how the person reached it.
    assert {entry.profile_id for entry in trail} == {profile.id}
    her = next(entry for entry in trail if entry.action is Action.SHARE)
    assert her.actor_role is KeyRole.CAREGIVER
    assert her.key_id == held.key_id
    assert her.shared_with_label == "Dr Tan's clinic"
    assert her.channel is Channel.SHARE_LINK

    his = next(entry for entry in trail if entry.action is Action.WRITE)
    assert his.actor_role is None and his.key_id is None  # the owner holds no key: it is his


async def test_a_refused_reach_is_written_down_so_the_patient_sees_it(sg: AsyncSession) -> None:
    _, owner, daughter, held = await _pa_and_his_daughter(sg)
    await add_note(sg, owner, scope=Scope.NOTES, body=PRIVATE)

    with pytest.raises(OutOfScope):
        await read_notes(sg, held, scope=Scope.NOTES)

    refused = [
        entry for entry in await read_audit(sg, context=owner) if entry.outcome is Outcome.REFUSED
    ]
    assert len(refused) == 1
    assert refused[0].actor_person_id == daughter.id
    assert refused[0].scope is Scope.NOTES
    assert refused[0].refused_because == "OutOfScope"
    assert refused[0].rows == 0

    # A refusal is a refusal: she still holds nothing of what is in the note.
    assert [note.body for note in await read_notes(sg, held, scope=Scope.MEDICINES)] == []


async def test_cutting_a_key_is_written_down_as_a_share_of_the_graph(sg: AsyncSession) -> None:
    _, owner, daughter, _ = await _pa_and_his_daughter(sg)

    shares = [
        entry for entry in await read_audit(sg, context=owner) if entry.action is Action.SHARE
    ]
    assert [(entry.target, entry.shared_with_person_id) for entry in shares] == [
        ("key", daughter.id)
    ]
    assert shares[0].scope is Scope.FAMILY


# --- queryable by patient and chief ------------------------------------------------------


async def test_the_patient_and_his_chief_read_the_trail_and_no_other_holder_can(
    sg: AsyncSession,
) -> None:
    _, owner, _, held = await _pa_and_his_daughter(sg)
    son = await register_person(sg, region=Region.SG, display_name="Son", phone_e164="+6591110004")
    await grant_key(sg, context=owner, holder=son, role=KeyRole.CHIEF, basis="owner_consent")
    chief = await resolve_key_context(
        sg, region=Region.SG, person_id=son.id, profile_id=held.profile_id
    )

    await add_note(sg, owner, scope=Scope.MEDICINES, body=WATER_PILL)
    await read_notes(sg, held, scope=Scope.MEDICINES)

    by_patient = await read_audit(sg, context=owner)
    by_chief = await read_audit(sg, context=chief)
    # The chief sees the same accesses the patient sees, his own read of the trail aside.
    assert {entry.id for entry in by_patient} <= {entry.id for entry in by_chief}
    assert len(by_patient) >= 3

    # The caregiver holds a key to the medicines, not to the record of who read them.
    with pytest.raises(NotTheirsToRead):
        await read_audit(sg, context=held)

    # And her attempt is itself in the trail the patient reads.
    attempts = [
        entry
        for entry in await read_audit(sg, context=owner)
        if entry.target == "audit_entry" and entry.outcome is Outcome.REFUSED
    ]
    assert [entry.actor_person_id for entry in attempts] == [held.person_id]


async def test_the_patient_narrows_the_trail_by_person_action_scope_and_day(
    sg: AsyncSession,
) -> None:
    _, owner, daughter, held = await _pa_and_his_daughter(sg)
    # Three days after the key was cut, so the entries the grant itself wrote fall before them.
    day_one = utcnow() + timedelta(days=1)
    await add_note(sg, owner, scope=Scope.MEDICINES, body=WATER_PILL, now=day_one)
    await read_notes(sg, held, scope=Scope.MEDICINES, now=day_one + timedelta(days=1))
    await read_notes(sg, held, scope=Scope.VISITS, now=day_one + timedelta(days=2))

    by_her = await read_audit(sg, context=owner, actor_person_id=daughter.id)
    assert {entry.action for entry in by_her} == {Action.READ}

    reads = await read_audit(sg, context=owner, action=Action.READ, scope=Scope.MEDICINES)
    assert [entry.actor_person_id for entry in reads] == [daughter.id]

    since_day_two = await read_audit(sg, context=owner, since=day_one + timedelta(days=1))
    assert len(since_day_two) == 2

    # Newest first, so the owner's screen opens on what just happened.
    newest = await read_audit(sg, context=owner)
    assert [entry.at for entry in newest] == sorted((entry.at for entry in newest), reverse=True)


# --- what was touched, never what it said ------------------------------------------------


async def test_the_trail_says_what_was_touched_and_never_what_it_said(sg: AsyncSession) -> None:
    _, owner, _, held = await _pa_and_his_daughter(sg)
    await add_note(sg, owner, scope=Scope.NOTES, body=PRIVATE)
    with pytest.raises(OutOfScope):
        await read_notes(sg, held, scope=Scope.NOTES)

    for entry in await read_audit(sg, context=owner):
        written = " ".join(str(value) for value in vars(entry).values() if isinstance(value, str))
        assert PRIVATE not in written
        assert WATER_PILL not in written


async def test_a_stranger_writes_nothing_into_a_graph_he_holds_no_key_to(
    sg: AsyncSession,
) -> None:
    _, owner, _, _ = await _pa_and_his_daughter(sg)
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )
    before = len(await read_audit(sg, context=owner))

    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=stranger.id, profile_id=owner.profile_id
        )

    # Nothing new but the owner's own read of the trail: a person with no key cannot put a
    # line into someone else's record, not even a line about himself.
    after = await read_audit(sg, context=owner)
    assert stranger.id not in {entry.actor_person_id for entry in after}
    assert len(after) == before + 1


async def test_a_helper_whose_key_was_closed_is_refused_and_the_patient_sees_it(
    sg: AsyncSession,
) -> None:
    _, owner, daughter, held = await _pa_and_his_daughter(sg)
    assert held.key_id is not None
    await revoke_key(sg, context=owner, key_id=held.key_id)
    before = len(await read_audit(sg, context=owner))

    with pytest.raises(NoKey):
        await resolve_key_context(
            sg, region=Region.SG, person_id=daughter.id, profile_id=owner.profile_id
        )

    # She held a key once, so the profile knows her: the reaching is written down.
    after = await read_audit(sg, context=owner)
    assert len(after) == before + 2
    refused = [entry for entry in after if entry.outcome is Outcome.REFUSED]
    assert [(e.actor_person_id, e.refused_because, e.key_id, e.actor_role) for e in refused] == [
        (daughter.id, "NoKey", None, None)
    ]


async def test_a_stranger_cannot_learn_that_a_profile_exists_or_where_it_is_pinned(
    sg: AsyncSession,
) -> None:
    pa = await register_person(sg, region=Region.SG, display_name="Pa", phone_e164="+6591110001")
    here = await create_own_profile(sg, region=Region.SG, owner=pa)
    ma = await register_person(sg, region=Region.SG, display_name="Ma", phone_e164="+6591110002")
    astray = Profile(region=Region.MY, display_name="Ma", owner_person_id=ma.id)
    sg.add(astray)
    await sg.flush()
    stranger = await register_person(
        sg, region=Region.SG, display_name="Someone", phone_e164="+6591110099"
    )

    # Missing, here, or pinned elsewhere: the same refusal, in the same words, and no line.
    for profile_id in (uuid.uuid4(), here.id, astray.id):
        with pytest.raises(NoKey) as refused:
            await resolve_key_context(
                sg, region=Region.SG, person_id=stranger.id, profile_id=profile_id
            )
        assert "MY" not in str(refused.value) and "held in" not in str(refused.value)
    lines = (
        await sg.scalars(select(AuditEntry).where(AuditEntry.profile_id.in_([here.id, astray.id])))
    ).all()
    assert lines == []

    # The owner, whom the profile knows, is told the real reason and is written down.
    with pytest.raises(OutOfRegion):
        await resolve_key_context(sg, region=Region.SG, person_id=ma.id, profile_id=astray.id)
    lines = (await sg.scalars(select(AuditEntry).where(AuditEntry.profile_id == astray.id))).all()
    assert [(e.refused_because, e.actor_person_id) for e in lines] == [("OutOfRegion", ma.id)]


# --- a refused line outlives the unit of work that was refused ------------------------------


async def test_a_refused_line_survives_the_rollback_the_refusal_causes(sg: AsyncSession) -> None:
    _, owner, _, held = await _pa_and_his_daughter(sg)
    before = len(await read_audit(sg, context=owner))

    async with refused_unit(sg, OutOfScope):
        # An allowed write in the same unit, and its line, go down with the refusal.
        await add_note(sg, owner, scope=Scope.NOTES, body=PRIVATE)
        await read_notes(sg, held, scope=Scope.NOTES)

    assert await read_notes(sg, owner, scope=Scope.NOTES) == []
    after = await read_audit(sg, context=owner)
    assert [e.refused_because for e in after if e.outcome is Outcome.REFUSED] == ["OutOfScope"]
    # ...the refusal, the owner's read of his own empty notes, and this read of the trail.
    assert len(after) == before + 3
    assert not any(e.action is Action.WRITE and e.target == Note.__tablename__ for e in after)
    # The keepers were replayed and dropped; a unit that succeeds has none to replay.
    assert take_keepers(sg) == []
