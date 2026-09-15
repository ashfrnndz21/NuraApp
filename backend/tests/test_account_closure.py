"""Closing an account (#143): what stops at once, what a red flag keeps, undo, and erasure.

Pa closes his account on his yes to exactly the lines he was shown. At once: nobody opens his
profile — Mei's key, Siti's, his own reads — the agreement to keep his papers is withdrawn,
every push subscription under the profile is revoked, and the delivery engine sends nothing
more about him. One thing is never hidden: a red flag raised before the closing is still carried
to his family. Within the window his yes undoes it all. After the window the erasure deletes
every row of the profile and every object it kept, and leaves only what the PDPA data map says
must outlive it: the consent rows, archived with the one record that says the graph was erased,
and his sign-in account.
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import tests.delivery_support as ds
from app.clock import FrozenClock
from app.consent.models import Consent, ConsentChannel, ConsentPurpose
from app.consent.service import RecordConsent, active_consents
from app.consent.texts import current_version
from app.db import as_utc, utcnow
from app.delivery.push import b64url
from app.delivery.subscriptions import subscribe
from app.delivery.triggers.models import DeliveryOutcome, Ladder, PushSubscription, TriggerType
from app.identity.closing import (
    OBJECT_KINDS,
    GraphEraser,
    NotTheirsToClose,
    TooLateToUndo,
    answerable_while_closing,
    close_account,
    close_draft_for,
    profile_tables,
    run_erasures,
    undo_closure,
)
from app.identity.closure_models import AccountClosure, ErasureRecord
from app.identity.doors import doors_for
from app.identity.models import LoginSession, Person, Profile
from app.ingestion.objects import LocalObjectStore
from app.keys.confirm import confirm
from app.keys.context import AccountClosing, resolve_key_context
from app.keys.scopes import Scope
from app.memory.models import Artifact, ArtifactKind, SourceChannel
from app.regions import Region
from app.safety.red_flags import Flag
from app.settings import MissingSetting, load_settings
from tests.api import bearer, own_profile, register_by_phone
from tests.conftest import Deployment
from tests.delivery_support import MEI, PA, Home, home
from tests.test_triggers import _rows, _run, at

APP = Path(__file__).resolve().parents[1] / "app"
DAYS = 30


async def _close(sg: AsyncSession, h: Home) -> AccountClosure:
    draft = await close_draft_for(sg, context=h.owner, language="en", retention_days=DAYS)
    yes = await confirm(sg, h.owner, draft)
    return await close_account(
        sg, context=h.owner, confirmation_id=yes.id, language="en", retention_days=DAYS
    )


async def _phone_for(sg: AsyncSession, h: Home, person: Person) -> None:
    login = LoginSession(
        region=Region.SG,
        person_id=person.id,
        token_hash=uuid.uuid4().hex * 2,
        expires_at=utcnow() + timedelta(days=30),
    )
    sg.add(login)
    await sg.flush()
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    key = ec.generate_private_key(ec.SECP256R1())
    await subscribe(
        sg,
        context=await h.ctx(sg, person),
        login_id=login.id,
        endpoint=f"https://push.example.test/{uuid.uuid4().hex}",
        p256dh=b64url(key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
        auth=b64url(uuid.uuid4().bytes),
    )


async def _opens(sg: AsyncSession, h: Home, person: Person) -> bool:
    try:
        await resolve_key_context(
            sg, region=Region.SG, person_id=person.id, profile_id=h.owner.profile_id
        )
    except AccountClosing:
        return False
    return True


async def test_closing_stops_every_delivery_and_every_key_at_once(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    await _phone_for(sg, h, h.mei)
    # Before: the morning card and the reorder go.
    before = await _run(sg, h, clock, at(10))
    assert _rows(before, TriggerType.REORDER)
    closure = await _close(sg, h)
    # The window runs to the end of the day his papers are said to go, on his wall clock.
    ends = as_utc(closure.delete_after).astimezone(ZoneInfo("Asia/Singapore"))
    assert (ends.hour, ends.minute) == (0, 0)
    assert (
        timedelta(days=DAYS)
        <= as_utc(closure.delete_after) - as_utc(closure.requested_at)
        <= timedelta(days=DAYS + 1)
    )
    # At once: nobody opens his profile — not Mei, not Siti, not Pa himself.
    for person in (h.pa, h.mei, h.siti):
        assert not await _opens(sg, h, person), person.display_name
    # Keeping his papers is withdrawn, on the record; every push under the profile revoked.
    held = [
        c
        for c in await active_consents(sg, context=h.owner)
        if c.purpose is ConsentPurpose.HOLD_HEALTH_RECORD
    ]
    assert held == []
    devices = (await sg.execute(select(PushSubscription))).scalars().all()
    assert devices and all(device.revoked_at is not None for device in devices)
    # And nothing more goes out about him: the next morning, nothing at all.
    for hour in (7, 8, 10, 18):
        assert (await _run(sg, h, clock, at(hour, day=15))).sent == ()


async def test_a_red_flag_raised_before_the_closing_is_still_carried_to_the_family(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """The safety rule of #143: a suspension never hides an unacknowledged red flag from the day
    it was raised. Pa falls at 09:00 and Mei, on duty, is told at once; he closes his account a
    minute later; at 09:06 nobody has answered, and the next rung still goes, to Siti. Nothing
    else goes: not the morning card, not a nudge."""
    clock.set(at(9))
    h = await home(sg, tmp_path)
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    assert handled.outcome == "red_flag" and handled.flag_id is not None
    clock.set(at(9, 1))
    await _close(sg, h)
    later = await _run(sg, h, clock, at(9, 6))
    assert [
        (s.delivery.trigger_type, s.delivery.to_person_id, s.delivery.outcome) for s in later.sent
    ] == [(TriggerType.FLAG, h.siti.id, DeliveryOutcome.SENT)]
    # And once the ladder has run its rungs, nothing more goes.
    assert (await _run(sg, h, clock, at(9, 30))).sent == ()


async def test_a_message_after_the_closing_gets_one_fixed_line_with_who_to_call(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """After the closing, Pa's "I fell" and Mei's "he fell" each get one fixed line that says
    who to call. Nothing is kept, nothing is raised, and nobody is told through Nura."""
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await _close(sg, h)
    for who, words in (
        (PA, "I fell in the bathroom"),
        (MEI, "he fell in the bathroom"),
        (PA, "Taken"),
    ):
        handled = await h.inbound(sg, who, words)
        assert handled.outcome == "closing" and handled.flag_id is None, (who, words)
        assert handled.stranger_reply is not None and "995" in handled.stranger_reply
    assert {one.to_e164 for one in h.whatsapp.sent} == {PA, MEI}
    assert (await sg.execute(select(Flag))).scalars().all() == []


async def test_his_yes_within_the_window_undoes_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    await _close(sg, h)
    clock.set(at(9, day=20))  # six days on, well inside the window
    owner = await resolve_key_context(
        sg, region=Region.SG, person_id=h.pa.id, profile_id=h.owner.profile_id, while_closing=True
    )
    words = RecordConsent(
        text_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
        language="en",
        captured_via=ConsentChannel.APP,
    )
    await undo_closure(sg, context=owner, consent=words)
    for person in (h.pa, h.mei, h.siti):
        assert await _opens(sg, h, person), person.display_name
    held = [
        c
        for c in await active_consents(sg, context=h.owner)
        if c.purpose is ConsentPurpose.HOLD_HEALTH_RECORD
    ]
    assert len(held) == 1
    assert (await _run(sg, h, clock, at(10, day=21))).sent != ()


async def test_after_the_window_nothing_of_his_remains_but_the_record_of_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(6))
    h = await home(sg, tmp_path, quantity=2)
    await _phone_for(sg, h, h.mei)
    await _run(sg, h, clock, at(10))  # deliveries, ladders, audit lines: all of it his
    store = h.via.providers.object_store
    assert isinstance(store, LocalObjectStore)
    profile_id = h.owner.profile_id
    await store.put(f"voice/{profile_id}/fixture/abc", b"a card, said")
    await store.put(f"photos/{profile_id}/label", b"a label")
    # Evidence for a documented basis sits at a key its caller chose, outside his prefixes.
    await store.put("evidence/lpa-of-pa.pdf", b"the power of attorney")
    sg.add(
        Artifact(
            profile_id=profile_id,
            kind=ArtifactKind.PDF,
            storage_key="evidence/lpa-of-pa.pdf",
            content_type="application/pdf",
            sha256="0" * 64,
            captured_at=utcnow(),
            source_channel=SourceChannel.APP,
            region=Region.SG,
            written_scope=Scope.RECORDS,
        )
    )
    await store.put("evidence/someone-elses.pdf", b"not his")
    other = uuid.uuid4()
    await store.put(f"photos/{other}/theirs", b"another profile's bytes")
    for key in (f"photos/{other}/theirs", "Not A Key!"):
        sg.add(
            Artifact(
                profile_id=profile_id,
                kind=ArtifactKind.PDF,
                storage_key=key,
                content_type="application/pdf",
                sha256="1" * 64,
                captured_at=utcnow(),
                source_channel=SourceChannel.APP,
                region=Region.SG,
                written_scope=Scope.RECORDS,
            )
        )
    await sg.flush()
    closure = await _close(sg, h)
    too_early = await run_erasures(
        sg, eraser=GraphEraser(store), at=utcnow() + timedelta(days=DAYS - 1)
    )
    assert too_early == []
    clock.set(as_utc(closure.delete_after) + timedelta(minutes=1))
    owner = await resolve_key_context(
        sg, region=Region.SG, person_id=h.pa.id, profile_id=profile_id, while_closing=True
    )
    with pytest.raises(TooLateToUndo):
        await undo_closure(
            sg,
            context=owner,
            consent=RecordConsent(
                text_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
                language="en",
                captured_via=ConsentChannel.APP,
            ),
        )
    [erased] = await run_erasures(sg, eraser=GraphEraser(store))
    # No row of the profile is left, in any table of profile data, nor the profile itself.
    for table in profile_tables():
        count = await sg.scalar(
            select(func.count()).select_from(table).where(table.c.profile_id == profile_id)
        )
        assert count == 0, table.name
    assert await sg.get(Profile, profile_id) is None
    # No object of his, under any kind.
    root = store.root
    assert [p for kind in OBJECT_KINDS for p in (root / kind / str(profile_id)).rglob("*")] == []
    assert not (root / "evidence" / "lpa-of-pa.pdf").exists()
    assert (root / "evidence" / "someone-elses.pdf").exists()
    # Under another profile's own prefix: its bytes stay. A key no store keeps: counted.
    assert (root / "photos" / str(other) / "theirs").exists()
    # What stays: the one record, with every consent row archived, and his sign-in account.
    [kept] = (await sg.execute(select(ErasureRecord))).scalars().all()
    assert kept.id == erased.id and kept.profile_id == profile_id
    assert {row["purpose"] for row in kept.consents} >= {"hold_health_record", "share_with_family"}
    assert all(row["profile_id"] == str(profile_id) for row in kept.consents)
    assert kept.removed["unremovable_keys"] == 1
    assert kept.removed["objects"] >= 3 and kept.removed.get("delivery", 0) > 0
    assert (await sg.execute(select(Consent))).scalars().all() == []
    assert await sg.get(Person, h.pa.id) is not None


async def test_only_the_owner_closes_his_account(sg: AsyncSession, tmp_path: Path) -> None:
    h = await home(sg, tmp_path)
    with pytest.raises(NotTheirsToClose):
        await close_draft_for(
            sg, context=await h.ctx(sg, h.mei), language="en", retention_days=DAYS
        )


def test_every_kind_of_stored_object_is_erased() -> None:
    """Every `<kind>/{profile_id}` key the app writes is a kind the erasure takes."""
    written = set()
    for path in APP.rglob("*.py"):
        written |= set(re.findall(r'f"([a-z_-]+)/\{[a-z_.]*profile_id\}', path.read_text()))
    assert written and written <= set(OBJECT_KINDS), written - set(OBJECT_KINDS)


def test_the_window_is_thirty_days_unless_set_and_at_least_one() -> None:
    env = {"NURA_REGION": "SG", "NURA_DATABASE_URL": "sqlite+aiosqlite://"}
    assert load_settings(env).account_retention_days == 30
    assert load_settings({**env, "NURA_ACCOUNT_RETENTION_DAYS": "45"}).account_retention_days == 45
    for bad in ("0", "abc", "-3"):
        with pytest.raises(MissingSetting):
            load_settings({**env, "NURA_ACCOUNT_RETENTION_DAYS": bad})


# --- over HTTP ---------------------------------------------------------------------------------


async def test_closing_and_undoing_over_http(deployment: Deployment) -> None:
    pa = await register_by_phone(deployment, "+6591430001", "Pa")
    profile_id = await own_profile(deployment, pa, language="en")
    his = bearer(pa["token"])
    base = f"/profiles/{profile_id}"
    shown = await deployment.client.post(
        f"{base}/closure/preview", json={"language": "en"}, headers=his
    )
    assert shown.status_code == 200, shown.text
    lines = shown.json()["lines"]
    assert lines[0] == "Nura will stop keeping your papers."
    assert lines[1] == "Nobody can open them from now on, not even you."
    assert lines[2] == "Nura will not remind you about your medicines."
    assert lines[4] == "If you are unwell, call 995."
    assert re.match(r"Your papers will be deleted after \w+day \d+ \w+\.", lines[5])
    yes = await deployment.client.post(
        f"{base}/confirmations", json={"subject": "close_account", "language": "en"}, headers=his
    )
    assert yes.status_code == 201, yes.text
    closed = await deployment.client.post(
        f"{base}/closure",
        json={"confirmation_id": yes.json()["confirmation_id"], "language": "en"},
        headers=his,
    )
    assert closed.status_code == 201 and closed.json()["closing"] is True
    # Suspended: his own reads are refused by name; the closing and his undo stay open to him.
    refused = await deployment.client.get(base, headers=his)
    assert refused.status_code == 403 and refused.json() == {"refusal": "AccountClosing"}
    status = await deployment.client.get(f"{base}/closure", headers=his)
    assert status.status_code == 200 and status.json()["closing"] is True
    # His own record stays his to read in the window: every agreement, and his trail.
    agreed = await deployment.client.get(f"{base}/consents", headers=his)
    assert agreed.status_code == 200 and any(
        c["purpose"] == "hold_health_record" for c in agreed.json()
    )
    assert (await deployment.client.get(f"{base}/trail", headers=his)).status_code == 200
    undone = await deployment.client.post(
        f"{base}/closure/undo",
        json={
            "wording_version": current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
            "language": "en",
        },
        headers=his,
    )
    assert undone.status_code == 200 and undone.json()["closing"] is False
    assert (await deployment.client.get(base, headers=his)).status_code == 200
    # A yes to other words (a closing shown in Malay) does not close it.
    other = await deployment.client.post(
        f"{base}/confirmations", json={"subject": "close_account", "language": "ms"}, headers=his
    )
    wrong = await deployment.client.post(
        f"{base}/closure",
        json={"confirmation_id": other.json()["confirmation_id"], "language": "en"},
        headers=his,
    )
    assert wrong.status_code == 400 and wrong.json() == {"refusal": "NotWhatWasConfirmed"}


async def test_his_familys_doors_still_open_and_his_closing_one_is_listed_by_id(
    sg: AsyncSession, tmp_path: Path
) -> None:
    h = await home(sg, tmp_path)
    await _close(sg, h)
    for person in (h.mei, h.pa):
        doors = await doors_for(sg, region=Region.SG, person=person)
        assert doors.closing == [h.owner.profile_id], person.display_name
        assert doors.own is None and doors.invited == [] and doors.stewarding == []


async def test_a_yes_on_whatsapp_still_answers_a_flag_raised_before_the_closing(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Pa falls at 09:00 and Mei is told; he closes a minute later; her "yes" at 09:02 is
    that flag's answer, so at 09:06 the ladder asks nobody else."""
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await h.inbound(sg, PA, "I fell in the bathroom")
    clock.set(at(9, 1))
    await _close(sg, h)
    clock.set(at(9, 2))
    said = await h.inbound(sg, MEI, "Yes")
    assert said.outcome == "flag_acknowledged"
    assert h.sent_to(h.mei)[-1].startswith("Thank you, you have it now.")
    assert (await _run(sg, h, clock, at(9, 6))).sent == ()


async def test_the_ack_route_answers_only_a_flag_raised_before_the_closing(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(at(9))
    h = await home(sg, tmp_path)
    handled = await h.inbound(sg, PA, "I fell in the bathroom")
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == handled.flag_id))).one()
    clock.set(at(9, 1))
    await _close(sg, h)
    mei = await resolve_key_context(
        sg, region=Region.SG, person_id=h.mei.id, profile_id=h.owner.profile_id, while_closing=True
    )
    await answerable_while_closing(sg, context=mei, ladder_id=ladder.id)
    with pytest.raises(AccountClosing):
        await answerable_while_closing(sg, context=mei, ladder_id=uuid.uuid4())


async def test_a_red_word_about_a_closing_family_is_never_raised_on_another(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """Mei holds keys to Pa's papers and to Ma's. She last wrote about Pa; Pa closes his
    account; her "he fell" gets the fixed line with who to call, and nothing is raised on Ma."""
    clock.set(at(9))
    h = await home(sg, tmp_path)
    await h.inbound(sg, MEI, "Pa had a good breakfast")
    ma = await ds.register_person(
        sg, region=Region.SG, display_name="Ma", phone_e164="+6593330051", language="en"
    )
    ma_profile = await ds.create_own_profile(
        sg, region=Region.SG, owner=ma, consent=ds.OPENING_CONSENT, language="en"
    )
    ma_owner = await resolve_key_context(
        sg, region=Region.SG, person_id=ma.id, profile_id=ma_profile.id
    )
    everything = frozenset(ds.Scope) - {ds.Scope.PROFILE}
    await ds.agree_to_family_sharing(
        sg, ma_owner, h.mei, scopes=everything, relationship="daughter"
    )
    await ds.grant_key(sg, context=ma_owner, holder=h.mei, role=ds.KeyRole.CHIEF, scopes=everything)
    clock.set(at(9, 5))
    await _close(sg, h)
    said = await h.inbound(sg, MEI, "he fell in the bathroom")
    assert said.outcome == "closing" and said.flag_id is None
    assert (await sg.execute(select(Flag))).scalars().all() == []
