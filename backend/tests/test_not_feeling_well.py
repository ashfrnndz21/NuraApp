"""E13-02: the not-feeling-well button.

    Three steps; guidance is rest, call clinic or go now; family notified.

A red-flag word writes the Flag before anything else (structurally: it is the first allowed
write on the trail after the artefact that holds his words), notices go to the right people,
the posture is ACT and the card's first line is the call line. A non-red-flag with a dose not
taken says to ask before he takes it and never says how much. Voice goes through the fixture
transcriber; every line is verified; a Malaysian profile is told 999.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.clock import FrozenClock
from app.db import utcnow
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.medicines.service import record_dose_taken
from app.memory.models import Artifact, ArtifactKind, Fact
from app.regions import Region
from app.safety.models import Flag, Notice, NoticeKind, WhatToDoCard, WhatToDoKind
from app.safety.not_feeling_well import (
    ANCHOR_HOURS,
    NothingSaid,
    SaidTwice,
    not_feeling_well,
    notice_lines,
)
from app.safety.red_flags import RedFlag
from app.safety.symptoms import Symptom
from app.state.models import Posture
from app.state.service import current_state
from tests.safety_support import (
    REGISTRY,
    TRANSCRIBER,
    assert_plain,
    first_write_of,
    let_in,
    pa,
    sugar_tablet,
    trail,
    water_pill,
)
from tests.voice import CHEST_PAIN, CONTENT_TYPE, TIRED_TODAY, UNHEARD, placeholder_voice

FORBIDDEN = ("mg", "tablet", "stop", "start", "double", "half", "skip")
"""Words no what-to-do card may carry: a dose, or advice about a medicine."""


async def _household(session: AsyncSession, *, region: Region = Region.SG):
    """Pa on the water pill (breakfast, not yet tapped), Mei chief, Lin emergency-only, Siti
    helper (holds EMERGENCY), Kit a viewer narrowed to visits (does not)."""
    sg = region is Region.SG
    owner = await pa(session, region=region, phone="+6591110041" if sg else "+60121110041")
    await water_pill(session, owner)
    mei = await let_in(
        session, owner, phone="+6592220041" if sg else "+60122220041", name="Mei", role=KeyRole.CHIEF
    )
    lin = await let_in(
        session, owner, phone="+6594440041" if sg else "+60124440041", name="Lin", role=KeyRole.EMERGENCY
    )
    siti = await let_in(
        session, owner, phone="+6596660041" if sg else "+60126660041", name="Siti", role=KeyRole.HELPER, language="ms"
    )
    kit = await let_in(
        session,
        owner,
        phone="+6593330041" if sg else "+60123330041",
        name="Kit",
        role=KeyRole.VIEWER,
        scopes={Scope.VISITS},
    )
    return owner, mei, lin, siti, kit


_verified = assert_plain


async def _press(session: AsyncSession, context, **said):
    return await not_feeling_well(
        session,
        context=context,
        store=_Store(),
        transcriber=TRANSCRIBER,
        registry=REGISTRY,
        **said,
    )


class _Store:
    """An object store for the service tests: bytes kept in memory, pinned to the region."""

    region = Region.SG

    def __init__(self) -> None:
        self.kept: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.kept[key] = data

    async def get(self, key: str) -> bytes:
        return self.kept[key]


async def test_a_red_flag_writes_the_flag_first_tells_the_family_and_the_first_line_is_the_call(
    sg: AsyncSession,
) -> None:
    owner, mei, lin, siti, kit = await _household(sg)
    done = await _press(sg, owner, words="I have chest pain since just now")

    assert done.kind is WhatToDoKind.RED_FLAG
    assert done.red_flags == [RedFlag.CHEST_PAIN] and done.posture is Posture.ACT
    assert [line.text for line in done.lines] == ["Call Mei now.", "Call 995 now.", "Mei knows."]
    _verified(done.lines)

    # The flag is the first thing written after the artefact that holds his words: between
    # that artefact's line and the flag's there is no other write, and every notice, event,
    # fact and card of this press comes after it.
    lines = await trail(sg, owner.profile_id)
    flag_at = first_write_of(lines, "flag")
    assert flag_at > 0
    writes_before = [
        line for line in lines[:flag_at] if line.action.value == "write" and line.outcome.value == "allowed"
    ]
    assert writes_before[-1].target == "artifact" and writes_before[-1].target_id == done.artifact_id
    for later in ("notice", "event", "fact", "what_to_do_card"):
        at = first_write_of(lines, later, after=flag_at)
        assert at > flag_at, (later, at, flag_at)
    flag = await sg.get(Flag, done.flag_id)
    assert flag is not None and flag.code == "chest_pain" and flag.posture is Posture.ACT
    artifact = await sg.get(Artifact, flag.artifact_id)
    assert artifact is not None and artifact.kind is ArtifactKind.MESSAGE
    assert artifact.id == done.artifact_id

    # Everyone with EMERGENCY is told, the presser is not, and a key narrowed past it is not.
    assert set(done.notified_person_ids) == {mei.person_id, lin.person_id, siti.person_id}
    assert kit.person_id not in done.notified_person_ids
    notices = {n.to_person_id: n for n in done.notices if n.kind is NoticeKind.FAMILY_ALERT}
    assert notice_lines(notices[mei.person_id], patient="Pa") == [
        "Pa is not feeling well.",
        "Pa said: 'chest pain'.",
        "Call Pa now.",
        "This one we do not wait for.",
    ]
    # Siti reads Malay: the same notice in her words, the code said in her language.
    malay = notice_lines(notices[siti.person_id], patient="Pa")
    assert malay[1] == "Pa kata: 'sakit dada'."
    _verified(malay, "ms")
    assert all(n.flag_id == done.flag_id and n.slots == {"words": "chest_pain", "heard": True} for n in notices.values())
    assert done.check_in_at is None  # a red flag is the call, not a check-in later

    # The moment is on the record: a SYMPTOM event, the fact on the artefact, the posture.
    facts = (await sg.scalars(select(Fact).where(Fact.profile_id == owner.profile_id))).all()
    reported = next(f for f in facts if f.subject == "symptom")
    assert reported.artifact_id == done.artifact_id and reported.event_id == done.event_id
    assert reported.value["red_flags"] == ["chest_pain"] and reported.value["via"] == "typed"
    feeling = next(f for f in facts if f.subject == "feeling")
    assert feeling.value == "act" and feeling.event_id == done.event_id
    assert feeling.valid_to is not None
    state = await current_state(sg, context=owner)
    assert state.posture is Posture.ACT and state.id == done.state_id
    card = await sg.get(WhatToDoCard, done.card_id)
    assert card is not None and card.state_id == state.id and card.flag_id == done.flag_id


async def test_a_red_flag_by_voice_goes_through_the_transcriber(sg: AsyncSession) -> None:
    owner, *_ = await _household(sg)
    done = await _press(sg, owner, audio=placeholder_voice(CHEST_PAIN), content_type=CONTENT_TYPE)
    assert done.by_voice and done.heard and done.transcript_confidence == 0.94
    assert done.kind is WhatToDoKind.RED_FLAG and done.lines[0].text == "Call Mei now."
    artifact = await sg.get(Artifact, done.artifact_id)
    assert artifact is not None and artifact.kind is ArtifactKind.VOICE
    assert artifact.content_type == "audio/m4a"
    fact = await sg.get(Fact, done.fact_id)
    assert fact is not None and fact.confidence == 0.94 and fact.value["via"] == "voice"


async def test_a_dose_not_taken_says_ask_before_you_take_it_and_never_how_much(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, mei, *_ = await _household(sg)
    # 08:00 UTC is 16:00 in Singapore: breakfast has passed and the water pill was not tapped.
    assert utcnow().hour == 8 and ANCHOR_HOURS
    done = await _press(sg, owner, words="tired today")

    assert done.kind is WhatToDoKind.MISSED_DOSE and done.missed_medicine == "the water pill"
    assert done.red_flags == [] and done.symptoms == [Symptom.TIRED]
    texts = [line.text for line in done.lines]
    assert texts[:2] == ["You have not taken the water pill today.", "Ask Mei before you take it."]
    assert texts[-1] == "Nura will ask you again in 2 hours."
    for text in texts:
        assert not any(word in text.lower() for word in FORBIDDEN), text
    _verified(done.lines)
    assert done.posture is Posture.WATCH
    assert done.check_in_at == utcnow() + timedelta(hours=2)
    check_in = [n for n in done.notices if n.kind is NoticeKind.CHECK_IN]
    assert len(check_in) == 1 and check_in[0].to_person_id == owner.person_id
    assert check_in[0].deliver_after == done.check_in_at
    assert notice_lines(check_in[0], patient="Pa") == ["How do you feel now?"]
    told = {n.to_person_id: n for n in done.notices if n.kind is NoticeKind.FAMILY_ALERT}
    assert notice_lines(told[mei.person_id], patient="Pa") == [
        "Pa is not feeling well.",
        "Pa said: 'tired'.",
        "Pa has not taken the water pill today.",
        "Please call Pa today.",
    ]
    assert done.flag_id is None
    assert (await sg.scalars(select(Flag).where(Flag.profile_id == owner.profile_id))).all() == []


async def test_when_every_dose_is_taken_the_card_says_rest(sg: AsyncSession) -> None:
    owner, *_ = await _household(sg)
    from app.medicines.service import active_lines
    from tests.medicines_support import REGISTRY as R

    line = (await active_lines(sg, context=owner, registry=R))[0].line
    await record_dose_taken(sg, context=owner, line_id=line.id, anchor="breakfast", amount=1)
    done = await _press(sg, owner, words="tired today")
    assert done.kind is WhatToDoKind.REST
    assert [line.text for line in done.lines] == [
        "Sit down and rest.",
        "Drink water.",
        "Mei will call you.",
        "Nura will ask you again in 2 hours.",
    ]
    _verified(done.lines)


async def test_a_voice_note_nobody_could_hear_still_tells_the_family(sg: AsyncSession) -> None:
    owner, mei, *_ = await _household(sg)
    done = await _press(sg, owner, audio=placeholder_voice(UNHEARD), content_type=CONTENT_TYPE)
    assert not done.heard and done.transcript_confidence == 0.0
    texts = [line.text for line in done.lines]
    assert texts[:2] == ["Nura could not hear you.", "Please say it again, or type it."]
    # The water pill was not tapped, so the row is still the dose not taken — after saying so.
    assert done.kind is WhatToDoKind.MISSED_DOSE
    assert texts[2:4] == ["You have not taken the water pill today.", "Ask Mei before you take it."]
    assert mei.person_id in done.notified_person_ids
    told = next(n for n in done.notices if n.to_person_id == mei.person_id)
    assert notice_lines(told, patient="Pa")[:2] == [
        "Pa is not feeling well.",
        "Nura could not hear the words.",
    ]
    fact = await sg.get(Fact, done.fact_id)
    assert fact is not None and fact.value["heard"] is False
    assert fact.value["symptoms"] == ["not_well"]


async def test_malaysia_is_told_999(my: AsyncSession) -> None:
    owner, *_ = await _household(my, region=Region.MY)

    class Store(_Store):
        region = Region.MY

    done = await not_feeling_well(
        my,
        context=owner,
        store=Store(),
        transcriber=TRANSCRIBER,
        registry=REGISTRY,
        words="dada saya sakit",
    )
    assert [line.text for line in done.lines][:2] == ["Call Mei now.", "Call 999 now."]


async def test_with_nobody_to_call_the_first_line_is_the_ambulance(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110049")
    done = await _press(sg, owner, words="chest pain")
    assert [line.text for line in done.lines] == ["Call 995 now."]
    assert done.notified_person_ids == []
    rest = await _press(sg, owner, words="tired")
    assert [line.text for line in rest.lines] == [
        "Sit down and rest.",
        "Drink water.",
        "Nura will ask you again in 2 hours.",
    ]


async def test_shaky_and_sweaty_is_suppressed_and_named_until_the_medicines_are_known(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591110048")
    unknown = await _press(sg, owner, words="shaky and sweaty")
    assert unknown.red_flags == [] and unknown.suppressed == [RedFlag.SHAKY_SWEATY]
    assert unknown.kind is WhatToDoKind.REST
    fact = await sg.get(Fact, unknown.fact_id)
    assert fact is not None and fact.value["suppressed"] == ["shaky_sweaty"]
    await sugar_tablet(sg, owner)
    known = await _press(sg, owner, words="shaky and sweaty")
    assert known.red_flags == [RedFlag.SHAKY_SWEATY] and known.kind is WhatToDoKind.RED_FLAG


async def test_the_button_takes_one_of_voice_or_words(sg: AsyncSession) -> None:
    owner, *_ = await _household(sg)
    with pytest.raises(NothingSaid):
        await _press(sg, owner)
    with pytest.raises(SaidTwice):
        await _press(sg, owner, words="tired", audio=placeholder_voice(TIRED_TODAY), content_type=CONTENT_TYPE)


async def test_a_key_without_the_record_cannot_press_it_and_is_written_down(
    sg: AsyncSession,
) -> None:
    owner, _mei, _lin, siti, _kit = await _household(sg)
    with pytest.raises(OutOfScope):
        await _press(sg, siti, words="Pa says chest pain")
    refused = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.outcome is Outcome.REFUSED and line.actor_person_id == siti.person_id
    ]
    assert refused and refused[-1].target == WhatToDoCard.__tablename__
    assert (await sg.scalars(select(Notice).where(Notice.profile_id == owner.profile_id))).all() == []
