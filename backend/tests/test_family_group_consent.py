"""The family's WhatsApp group under #143: each member's own yes, and a withdrawal at once.

Everyone in the family's group sees everyone's number, so nobody but the patient is put in it
without their own yes at the key-accept step, and their no takes them out. The patient is in
it while his agreement to WhatsApp is in force: it is his agreement to be messaged there, and
his withdrawing it takes him out — only him. Withdrawing a sharing agreement closes the keys
it rested on, and takes the holder out. Each of these sets the group where it happens, in
the same step, not at its next use. A closing account empties the group and mirrors nothing;
his yes within the window puts everyone who said yes back.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.whatsapp.group import (
    members_of,
    mirror_to_group,
    open_group,
    sync_group,
    withdraw,
)
from app.channels.whatsapp.opt_in import record_opt_in
from app.clock import FrozenClock
from app.consent.models import ConsentChannel, ConsentPurpose
from app.consent.opt_in_words import OPT_IN_VERSION
from app.consent.service import RecordConsent
from app.consent.texts import current_version
from app.family.thread import post_message
from app.identity.closing import close_account, close_draft_for, undo_closure
from app.keys.confirm import confirm
from app.keys.context import resolve_key_context
from app.regions import Region
from tests.whatsapp_support import MEI, PA, Family, family

API = Path(__file__).resolve().parents[1] / "app" / "channels" / "api"
MORNING = dt.datetime(2026, 9, 14, 1, 0, tzinfo=dt.UTC)


async def _answers(sg: AsyncSession, home: Family, *, group: bool) -> None:
    await record_opt_in(
        sg,
        context=home.chief,
        messages=True,
        joins_group=group,
        wording_version=OPT_IN_VERSION,
        language="en",
    )
    await sync_group(sg, context=home.chief, provider=home.whatsapp)  # as the route does


async def test_nobody_but_him_is_in_the_group_without_their_own_yes(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(MORNING)
    home = await family(sg, tmp_path, group_yes=False)
    group, members = await open_group(sg, context=home.owner, provider=home.whatsapp)
    gid = group.provider_group_id
    # Mei's key reads the family thread, but she has not said yes: only Pa is in it.
    assert [m.name for m in members] == ["Pa"] and home.whatsapp.groups[gid] == (PA,)
    clock.set(MORNING + dt.timedelta(minutes=1))
    await _answers(sg, home, group=True)
    assert home.whatsapp.groups[gid] == tuple(sorted({PA, MEI}))
    # Her no takes her out, at once.
    clock.set(MORNING + dt.timedelta(minutes=2))
    await _answers(sg, home, group=False)
    assert home.whatsapp.groups[gid] == (PA,)


async def test_his_stopping_whatsapp_takes_only_him_out_and_at_once(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.chief, provider=home.whatsapp)
    gid = group.provider_group_id
    assert home.whatsapp.groups[gid] == tuple(sorted({PA, MEI}))
    await withdraw(
        sg,
        context=home.owner,
        provider=home.whatsapp,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.APP,
    )
    assert home.whatsapp.groups[gid] == (MEI,)
    assert [m.name for m in await members_of(sg, context=home.owner)] == ["Mei"]
    # The family still hears the family thread there: it is theirs, on their own yes.
    entry = await post_message(sg, context=home.chief, text="I will bring lunch.")
    assert await mirror_to_group(sg, context=home.chief, provider=home.whatsapp, message=entry)


async def test_withdrawing_her_sharing_agreement_takes_her_out_at_once(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.owner, provider=home.whatsapp)
    gid = group.provider_group_id
    await withdraw(
        sg,
        context=home.owner,
        provider=home.whatsapp,
        purpose=ConsentPurpose.SHARE_WITH_PERSON,
        captured_via=ConsentChannel.APP,
        holder_person_id=home.mei.id,
    )
    assert home.whatsapp.groups[gid] == (PA,)
    late = await home.inbound(sg, MEI, "Still here?", group_id=gid)
    assert late.outcome == "ignored"


async def test_a_closing_account_empties_the_group_and_his_yes_puts_them_back(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    clock.set(MORNING)
    home = await family(sg, tmp_path)
    group, _ = await open_group(sg, context=home.owner, provider=home.whatsapp)
    gid = group.provider_group_id
    draft = await close_draft_for(sg, context=home.owner, language="en", retention_days=30)
    yes = await confirm(sg, home.owner, draft)
    await close_account(
        sg, context=home.owner, confirmation_id=yes.id, language="en", retention_days=30
    )
    await sync_group(sg, context=home.owner, provider=home.whatsapp)  # as the route does
    assert home.whatsapp.groups[gid] == ()
    entry_words = "The doctor moved it to 3 pm."
    before = len(home.whatsapp.sent)
    assert (await home.inbound(sg, MEI, entry_words, group_id=gid)).outcome == "ignored"
    # A red word that still arrives there is answered to her alone, with who to call.
    flagged = await home.inbound(sg, MEI, "He fell in the kitchen just now", group_id=gid)
    assert flagged.outcome == "closing" and flagged.flag_id is None
    said = home.whatsapp.sent[before:]
    assert [(one.to_e164, one.group_id) for one in said] == [(MEI, None)]
    assert "995" in said[0].text
    # His yes within the window: everyone who said yes is back, now.
    clock.set(MORNING + dt.timedelta(days=3))
    owner = await resolve_key_context(
        sg, region=Region.SG, person_id=home.pa.id, profile_id=home.profile.id, while_closing=True
    )
    await undo_closure(
        sg,
        context=owner,
        consent=RecordConsent(
            text_version=current_version(ConsentPurpose.HOLD_HEALTH_RECORD),
            language="en",
            captured_via=ConsentChannel.APP,
        ),
    )
    await sync_group(sg, context=owner, provider=home.whatsapp)  # as the route does
    assert home.whatsapp.groups[gid] == tuple(sorted({PA, MEI}))


# Whatever changes who reads the family thread, or whether the patient may be messaged.
CHANGES_WHO_IS_IN = {
    "revoke_key",
    "grant_key",
    "close_account",
    "undo_closure",
    "record_opt_in",
    "mark_only_me",
    "lift_only_me",
}


def _calls(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            func = inner.func
            names.add(func.id if isinstance(func, ast.Name) else getattr(func, "attr", ""))
    return names


def test_every_route_that_changes_who_is_in_the_group_sets_it_in_the_same_step() -> None:
    """Held to the code: a route that closes or cuts a key, closes or reopens the account,
    takes an answer at the key-accept step, or keeps the family "only me" also sets the
    group; no route withdraws an agreement but through `withdraw`, which sets it too; and
    his yes to WhatsApp puts him back in it."""
    missing: list[str] = []
    for path in sorted(API.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            calls = _calls(node)
            if "revoke_consent" in calls:
                missing.append(f"{path.name}:{node.name} withdraws without `withdraw`")
            if calls & CHANGES_WHO_IS_IN and not calls & {"sync_group", "withdraw"}:
                missing.append(f"{path.name}:{node.name} {sorted(calls & CHANGES_WHO_IS_IN)}")
            if node.name == "agree_to_whatsapp" and "sync_group" not in calls:
                missing.append(f"{path.name}:{node.name} does not put him back in the group")
    assert missing == []
