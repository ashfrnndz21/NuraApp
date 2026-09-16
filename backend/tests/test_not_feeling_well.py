"""E13-02: the not-feeling-well button.

    Three steps; guidance is rest, call clinic or go now; family notified.

A red-flag word writes the Flag before anything else (structurally: it is the first allowed
write on the trail after the artefact that holds his words), the ladder asks the right people,
the posture is ACT and the card's first line is the call line. A non-red-flag with a dose not
taken says to ask before he takes it and never says how much. Voice goes through the fixture
transcriber; every line is verified; a Malaysian profile is told 999.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, Channel
from app.channels.api.safety_schemas import WhatToDoOut
from app.channels.whatsapp.opt_in import record_opt_in
from app.clock import FrozenClock
from app.consent.opt_in_words import OPT_IN_VERSION
from app.db import utcnow
from app.delivery.triggers.models import Delivery, DeliveryChannel, DeliveryOutcome, Ladder
from app.family.roster import add_slot
from app.keys.scopes import KeyRole, Scope
from app.medicines.models import MedicationLine
from app.medicines.service import record_dose_taken
from app.memory.models import Artifact, ArtifactKind, Event, EventKind, Fact
from app.regions import OutOfRegion, Region
from app.safety.models import Notice, NoticeKind, WhatToDoCard, WhatToDoKind
from app.safety.not_feeling_well import (
    NothingSaid,
    SaidTwice,
    not_feeling_well,
    notice_lines,
)
from app.safety.red_flags import Feeling, Flag
from app.safety.symptoms import Symptom
from app.state.models import Posture
from app.state.service import StaleState, current_state
from tests.delivery_support import via_for
from tests.safety_support import (
    REGISTRY,
    assert_plain,
    fact,
    first_write_of,
    gliclazide,
    let_in,
    pa,
    trail,
    transcriber_for,
    water_pill,
)
from tests.support import refused_unit
from tests.voice import CHEST_PAIN, CONTENT_TYPE, TIRED_TODAY, UNHEARD, placeholder_voice

CLOSING = (
    "Nura wrote down how you feel.",
    "This is not a doctor's advice.",
    "Ask your doctor.",
    "Nura does not decide what is wrong.",
)
"""The not-feeling-well boundary's last four lines (`app.safety.boundary`), no doctor named:
every card, whatever its row, ends saying Nura does not decide what is wrong (E13-02)."""

URGENT = ("Nura does not decide what is wrong.",)
"""The one closing line of a red flag's urgent card: never "Ask your doctor." after 995."""

FORBIDDEN = ("mg", "tablet", "stop", "start", "double", "half", "skip", "drink")
"""Words no what-to-do card may carry: a dose, or advice about a medicine."""


async def _household(session: AsyncSession, *, region: Region = Region.SG):
    """Pa on the water pill (breakfast, not yet tapped), Mei chief, Lin emergency-only, Siti
    helper (holds EMERGENCY), Kit a viewer narrowed to visits (does not)."""
    sg = region is Region.SG
    owner = await pa(session, region=region, phone="+6591110041" if sg else "+60121110041")
    await water_pill(session, owner)
    mei = await let_in(
        session,
        owner,
        phone="+6592220041" if sg else "+60122220041",
        name="Mei",
        role=KeyRole.CHIEF,
    )
    lin = await let_in(
        session,
        owner,
        phone="+6594440041" if sg else "+60124440041",
        name="Lin",
        role=KeyRole.EMERGENCY,
    )
    siti = await let_in(
        session,
        owner,
        phone="+6596660041" if sg else "+60126660041",
        name="Siti",
        role=KeyRole.HELPER,
        language="ms",
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
        transcriber=transcriber_for(context.region),
        registry=REGISTRY,
        via=via_for(context.region),
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
    assert done.red_flags == [Feeling.CHEST_TIGHTNESS] and done.posture is Posture.ACT
    assert [line.text for line in done.lines] == [
        "Mei knows now.",
        "Call the ambulance now on 995.",
        "After that, call Mei.",
        *URGENT,
    ]
    _verified(done.lines)

    # The flag comes before anything else about the moment: after the artefact that holds his
    # words, the only write is the SYMPTOM event the flag rests on (`record_the_moment`), and
    # the ladder (E11), every fact and the card come after the flag.
    lines = await trail(sg, owner.profile_id)
    flag_at = first_write_of(lines, "red_flag")
    assert flag_at > 0
    writes_before = [
        line
        for line in lines[:flag_at]
        if line.action.value == "write" and line.outcome.value == "allowed"
    ]
    assert writes_before[-1].target == "event" and writes_before[-1].target_id == done.event_id
    assert (
        writes_before[-2].target == "artifact" and writes_before[-2].target_id == done.artifact_id
    )
    for later in ("delivery_ladder", "fact", "what_to_do_card"):
        at = first_write_of(lines, later, after=flag_at)
        assert at > flag_at, (later, at, flag_at)
    flag = await sg.get(Flag, done.flag_id)
    assert flag is not None and flag.feeling is Feeling.CHEST_TIGHTNESS
    assert flag.event_id == done.event_id and flag.suppressed_because is None
    assert str(mei.person_id) in flag.told
    # The ladder (E11-06) is the one record of who is told: straight to the roster, never his
    # own rung. Nobody is on duty, so the chief at once; five minutes on, if nobody has
    # answered, everyone else holding his emergency card. Not Kit, whose key does not hold it.
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == flag.id))).one()
    assert [(step["person_id"], step["after_minutes"]) for step in ladder.rungs] == [
        (str(mei.person_id), 0),
        (str(lin.person_id), 5),
        (str(siti.person_id), 5),
    ]
    assert done.notified_person_ids == [mei.person_id]
    assert kit.person_id not in done.notified_person_ids
    # His WhatsApp agreement is for messages to him (#143): Mei is told on her own WhatsApp,
    # under the key his agreement to let her in rests on, though he never agreed to WhatsApp.
    rows = (await sg.scalars(select(Delivery).where(Delivery.ladder_id == ladder.id))).all()
    names = {mei.person_id: "mei", lin.person_id: "lin", siti.person_id: "siti"}
    for row in rows:
        print("DBGROW", names.get(row.to_person_id, row.to_person_id), row.via, row.outcome, row.rung, row.template_name)
    # Every way she can be reached, and the notice on her family page besides (#162).
    assert {(row.to_person_id, row.via) for row in rows if row.via is DeliveryChannel.IN_APP} == {
        (mei.person_id, DeliveryChannel.IN_APP)
    }
    first = [row for row in rows if row.via is not DeliveryChannel.IN_APP]
    assert [(row.to_person_id, row.outcome) for row in first] == [
        (mei.person_id, DeliveryOutcome.SENT)
    ]
    assert first[0].via is DeliveryChannel.WHATSAPP and first[0].passed_over == []
    assert [n for n in done.notices if n.kind is NoticeKind.FAMILY_ALERT] == []
    assert done.check_in_at is None  # a red flag is the call, not a check-in later

    # The moment is on the record: a SYMPTOM event, the fact on the artefact, the posture.
    facts = (await sg.scalars(select(Fact).where(Fact.profile_id == owner.profile_id))).all()
    reported = next(f for f in facts if f.subject == "symptom")
    assert reported.artifact_id == done.artifact_id and reported.event_id == done.event_id
    assert reported.value["red_flags"] == ["chest_tightness"] and reported.value["via"] == "typed"
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
    assert (
        done.kind is WhatToDoKind.RED_FLAG
        and done.lines[1].text == "Call the ambulance now on 995."
    )
    artifact = await sg.get(Artifact, done.artifact_id)
    assert artifact is not None and artifact.kind is ArtifactKind.VOICE
    assert artifact.content_type == "audio/m4a"
    fact = await sg.get(Fact, done.fact_id)
    assert fact is not None and fact.confidence == 0.94 and fact.value["via"] == "voice"


async def test_a_dose_not_taken_says_ask_before_you_take_it_and_never_how_much(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner, mei, *_ = await _household(sg)
    # 08:00 UTC is 16:00 in Singapore: the breakfast window closed at 08:30 on his day and
    # the water pill was not tapped.
    assert utcnow().hour == 8
    done = await _press(sg, owner, words="tired today")

    assert done.kind is WhatToDoKind.MISSED_DOSE and done.missed_medicine == "the water pill"
    assert done.red_flags == [] and done.symptoms == [Symptom.TIRED]
    texts = [line.text for line in done.lines]
    # The doctor on the label is asked, not the family: a medicine question goes to the doctor.
    assert texts[0] == "Mei knows now."
    assert texts[1:3] == [
        "Nura has no note that you took the water pill today.",
        "Ask Dr Tan before you take the water pill.",
    ]
    assert texts[-5] == "Nura will ask you again in 2 hours."
    assert texts[-4:] == [*CLOSING[:2], "Ask Dr Tan.", CLOSING[3]]  # the doctor on the label
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
        "Nura heard this: tired.",
        "Nura has no note that Pa took the water pill today.",
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
        "Mei knows now.",
        "Sit down and rest now.",
        "Mei will call you today.",
        "Nura will ask you again in 2 hours.",
        *CLOSING,
    ]
    _verified(done.lines)


async def test_a_voice_note_nobody_could_hear_still_tells_the_family(sg: AsyncSession) -> None:
    owner, mei, *_ = await _household(sg)
    done = await _press(sg, owner, audio=placeholder_voice(UNHEARD), content_type=CONTENT_TYPE)
    assert not done.heard and done.transcript_confidence == 0.0
    texts = [line.text for line in done.lines]
    assert texts[1:4] == [
        "Nura could not hear you.",
        "Please tell Nura again.",
        "You can type it to Nura instead.",
    ]
    # The water pill was not tapped, so the row is still the dose not taken — after saying so.
    assert done.kind is WhatToDoKind.MISSED_DOSE
    assert texts[4] == "Nura has no note that you took the water pill today."
    assert mei.person_id in done.notified_person_ids
    told = next(n for n in done.notices if n.to_person_id == mei.person_id)
    assert notice_lines(told, patient="Pa")[:2] == [
        "Pa is not feeling well.",
        "Nura could not hear what Pa said.",
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
        transcriber=transcriber_for(Region.MY),
        registry=REGISTRY,
        via=via_for(Region.MY),
        words="dada saya sakit",
    )
    assert [line.text for line in done.lines][:2] == [
        "Mei knows now.",
        "Call the ambulance now on 999.",
    ]


async def test_with_nobody_to_call_the_first_line_is_the_ambulance(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110049")
    done = await _press(sg, owner, words="chest pain")
    assert [line.text for line in done.lines] == [
        "You did right to say so.",
        "Call the ambulance now on 995.",
        *URGENT,
    ]
    assert done.notified_person_ids == []
    rest = await _press(sg, owner, words="tired")
    assert [line.text for line in rest.lines] == [
        "You did right to say so.",
        "Sit down and rest now.",
        "Nura will ask you again in 2 hours.",
        *CLOSING,
    ]


async def test_shaky_and_sweaty_is_written_suppressed_until_a_sugar_condition_is_on_record(
    sg: AsyncSession,
) -> None:
    """E21's rule, one rule for every channel: shaky-and-sweaty is a red flag on a sugar
    condition. Without one on the record the flag is written with why, tells nobody, and the
    button takes the ordinary path; the caregiver sees it was considered."""
    owner = await pa(sg, phone="+6591110048")
    unknown = await _press(sg, owner, words="shaky and sweaty")
    assert unknown.red_flags == [] and unknown.suppressed == [Feeling.SHAKY_SWEATY]
    assert unknown.kind is WhatToDoKind.REST and unknown.flag_id is None
    reported = await sg.get(Fact, unknown.fact_id)
    assert reported is not None and reported.value["suppressed"] == ["shaky_sweaty"]
    held = (await sg.scalars(select(Flag).where(Flag.profile_id == owner.profile_id))).all()
    assert [one.suppressed_because for one in held] == ["no_sugar_condition_on_record"]
    assert held[0].told == []
    await fact(sg, owner, subject="diabetes", attribute="control", value="watch")
    known = await _press(sg, owner, words="shaky and sweaty")
    assert known.red_flags == [Feeling.SHAKY_SWEATY] and known.kind is WhatToDoKind.RED_FLAG


async def test_the_button_takes_one_of_voice_or_words(sg: AsyncSession) -> None:
    owner, *_ = await _household(sg)
    with pytest.raises(NothingSaid):
        await _press(sg, owner)
    with pytest.raises(SaidTwice):
        await _press(
            sg,
            owner,
            words="tired",
            audio=placeholder_voice(TIRED_TODAY),
            content_type=CONTENT_TYPE,
        )


async def test_a_helper_pressing_for_him_escalates_without_the_record(
    sg: AsyncSession,
) -> None:
    """Spec section 8: the helper's word about him is a red flag that escalates immediately.
    Her key holds no record, so nothing of the record is written — no artefact, no fact, no
    card — but the moment is a SYMPTOM event under the emergency scope (as E19 writes it for
    her on WhatsApp), the flag is raised on it, the family is told, and she is shown what to do."""
    owner, mei, _lin, siti, _kit = await _household(sg)
    done = await _press(sg, siti, words="Pa says chest pain")
    assert done.kind is WhatToDoKind.RED_FLAG and done.posture is Posture.ACT
    assert done.flag_id is not None
    assert [line.text for line in done.lines] == [
        "Mei knows now.",
        "Call the ambulance now on 995.",
        "After that, call Mei.",
        *URGENT,
    ]
    assert done.notified_person_ids == [mei.person_id]
    assert done.artifact_id is None and done.fact_id is None and done.event_id is not None
    assert done.card_id is None and done.state_id is None
    flag = await sg.get(Flag, done.flag_id)
    assert flag is not None and flag.event_id == done.event_id
    assert flag.raised_by_person_id == siti.person_id
    assert (await sg.scalars(select(Fact).where(Fact.subject == "symptom"))).all() == []
    # Every write is on the trail under the emergency scope, in her name.
    hers = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.actor_person_id == siti.person_id and line.action.value == "write"
    ]
    assert {line.target for line in hers} == {"event", "red_flag"}
    assert all(line.scope is Scope.EMERGENCY for line in hers)


async def test_a_caregiver_pressing_for_him_escalates_and_writes_the_record(
    sg: AsyncSession,
) -> None:
    """A caregiver holds the record but not FAMILY: the flag and the notices no longer need
    it. She writes the moment to the record; she cannot compute State, so no card row."""
    owner, mei, _lin, _siti, _kit = await _household(sg)
    ana = await let_in(sg, owner, phone="+6595550041", name="Ana", role=KeyRole.CAREGIVER)
    assert Scope.RECORDS in ana.scopes and Scope.FAMILY not in ana.scopes
    done = await _press(sg, ana, words="Pa has chest pain")
    assert done.kind is WhatToDoKind.RED_FLAG and done.flag_id is not None
    # The ladder asks the chief first (nobody is on duty); the caregiver pressed.
    assert done.notified_person_ids == [mei.person_id]
    assert done.artifact_id is not None and done.event_id is not None and done.fact_id is not None
    assert done.card_id is None and done.posture is Posture.ACT
    # The owner, who can compute State, sees the day as ACT from the fact she wrote.
    assert (await current_state(sg, context=owner)).posture is Posture.ACT


async def test_the_flag_and_the_notices_survive_a_refusal_later_in_the_same_request(
    sg: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A template that fails, a State that is stale, a door that refuses further on: the
    unit of work is rolled back, and the flag, the event it rests on and the ladder are
    written again by their keepers. Nothing else of the press survives."""
    owner, mei, *_ = await _household(sg)

    async def stale(*args: object, **kwargs: object) -> object:
        raise StaleState("the record moved")

    monkeypatch.setattr("app.safety.not_feeling_well.render_from_state", stale)
    async with refused_unit(sg, StaleState):
        await _press(sg, owner, words="chest pain")

    flags = (await sg.scalars(select(Flag).where(Flag.profile_id == owner.profile_id))).all()
    assert len(flags) == 1 and flags[0].feeling is Feeling.CHEST_TIGHTNESS
    moment = await sg.get(Event, flags[0].event_id)
    assert moment is not None and moment.kind is EventKind.SYMPTOM
    ladders = (await sg.scalars(select(Ladder).where(Ladder.profile_id == owner.profile_id))).all()
    assert [one.flag_id for one in ladders] == [flags[0].id]
    assert str(mei.person_id) in {step["person_id"] for step in ladders[0].rungs}
    notices = (await sg.scalars(select(Notice).where(Notice.profile_id == owner.profile_id))).all()
    assert [n for n in notices if n.kind is NoticeKind.FAMILY_ALERT] == []
    assert (await sg.scalars(select(Fact).where(Fact.subject == "symptom"))).all() == []
    lines = await trail(sg, owner.profile_id)
    assert any(line.target == "red_flag" and line.action.value == "write" for line in lines)


async def test_a_voice_note_is_the_senders_own_words_and_asks_no_recording_consent(
    sg: AsyncSession,
) -> None:
    """ADR 0003: the RECORDING consent is for other people's voices (a consult). His voice
    note, or Mei's about him, is the sender's own words, kept like typed text — no recording
    consent is asked, and nothing on the trail says one was."""
    owner, mei, *_ = await _household(sg)
    his = await _press(sg, owner, audio=placeholder_voice(TIRED_TODAY), content_type=CONTENT_TYPE)
    hers = await _press(sg, mei, audio=placeholder_voice(CHEST_PAIN), content_type=CONTENT_TYPE)
    assert his.by_voice and hers.by_voice and hers.kind is WhatToDoKind.RED_FLAG
    kept = await sg.get(Artifact, hers.artifact_id)
    assert kept is not None and kept.kind is ArtifactKind.VOICE
    asked = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.target == "consent" and line.scope is Scope.VISITS
    ]
    assert asked == []


async def test_a_voice_note_never_reaches_a_transcriber_in_another_region(
    sg: AsyncSession,
) -> None:
    owner, *_ = await _household(sg)
    with pytest.raises(OutOfRegion):
        await not_feeling_well(
            sg,
            context=owner,
            store=_Store(),
            transcriber=transcriber_for(Region.MY),
            registry=REGISTRY,
            via=via_for(Region.SG),
            audio=placeholder_voice(CHEST_PAIN),
            content_type=CONTENT_TYPE,
        )
    voice_notes = select(Artifact).where(
        Artifact.profile_id == owner.profile_id, Artifact.kind == ArtifactKind.VOICE
    )
    assert (await sg.scalars(voice_notes)).all() == []


async def test_the_roster_names_who_is_on_duty_and_a_red_flag_goes_to_them_first(
    sg: AsyncSession,
) -> None:
    """With a roster (E12), whoever is on duty now is named on his card and gets the ordinary
    notice; a red flag goes up the ladder (E11-06) — on duty at once, the chief five minutes
    on, then everyone else holding his emergency card — and the card names who it asked
    first. The ladder reads the roster as the system, so a caregiver pressing gets the same."""
    owner, _mei, lin, _siti, _kit = await _household(sg)
    await add_slot(
        sg,
        context=owner,
        person_id=lin.person_id,
        role=KeyRole.EMERGENCY,
        from_time=time(0, 0),
        to_time=time(23, 59),
        weekdays=list(range(7)),
    )
    tired = await _press(sg, owner, words="tired today")
    assert tired.notified_person_ids == [lin.person_id]
    assert "Lin will call you today." in [line.text for line in tired.lines]
    chest = await _press(sg, owner, words="chest pain")
    assert chest.notified_person_ids == [lin.person_id]
    ladder = (await sg.scalars(select(Ladder).where(Ladder.flag_id == chest.flag_id))).one()
    assert [(step["standing"], step["after_minutes"]) for step in ladder.rungs] == [
        ("on_duty", 0),
        ("chief", 5),
        ("key_holder", 10),
    ]
    assert [line.text for line in chest.lines] == [
        "Lin knows now.",
        "Call the ambulance now on 995.",
        "After that, call Lin.",
        *URGENT,
    ]
    ana = await let_in(sg, owner, phone="+6595550042", name="Ana", role=KeyRole.CAREGIVER)
    theirs = await _press(sg, ana, words="chest pain")
    assert theirs.lines[0].text == "Lin knows now."
    assert theirs.notified_person_ids == [lin.person_id]


async def test_a_red_flag_card_closes_on_one_line_and_never_sends_him_to_his_doctor(
    sg: AsyncSession,
) -> None:
    """After "Call the ambulance now on 995." the card never says "Ask your doctor.": it
    closes on "Nura does not decide what is wrong.", and the row carries that urgent boundary.
    An ordinary card keeps the standard closing."""
    owner, *_ = await _household(sg)
    done = await _press(sg, owner, words="chest pain")
    texts = [line.text for line in done.lines]
    assert texts[0] == "Mei knows now." and texts[-1] == "Nura does not decide what is wrong."
    assert not any(text.startswith("Ask ") for text in texts)
    card = await sg.get(WhatToDoCard, done.card_id)
    assert card is not None
    assert card.boundary == "Mei knows now.\nNura does not decide what is wrong."
    ordinary = [line.text for line in (await _press(sg, owner, words="tired today")).lines]
    assert ordinary[-4:-2] == list(CLOSING[:2]) and ordinary[-2].startswith("Ask ")
    assert ordinary[-1] == "Nura does not decide what is wrong."


async def test_the_rule_reads_the_record_as_the_system_whoever_pressed(
    sg: AsyncSession,
) -> None:
    """Shaky-and-sweaty from the helper, whose key does not open the record: the rule reads
    it as the system. With no sugar condition and nothing that lowers his sugar the flag is
    written suppressed and she sees the ordinary card; on gliclazide (the register's class, a
    sulfonylurea) it escalates. What the rule read never reaches her."""
    owner, mei, _lin, siti, _kit = await _household(sg)
    assert Scope.RECORDS not in siti.scopes
    held = await _press(sg, siti, words="Pa is shaky and sweaty")
    assert held.kind is not WhatToDoKind.RED_FLAG and held.flag_id is None
    assert held.red_flags == [] and held.suppressed == []
    flags = (await sg.scalars(select(Flag).where(Flag.profile_id == owner.profile_id))).all()
    assert [one.suppressed_because for one in flags] == ["no_sugar_condition_on_record"]

    await gliclazide(sg, owner)
    done = await _press(sg, siti, words="Pa is shaky and sweaty")
    assert done.kind is WhatToDoKind.RED_FLAG and done.flag_id is not None
    assert done.notified_person_ids == [mei.person_id]
    assert done.lines[0].text == "Mei knows now."
    assert done.lines[-1].text == "Nura does not decide what is wrong."

    # What she is sent back names no condition and no medicine, pressed either way.
    for answer in (held, done):
        sent = WhatToDoOut.of(answer).model_dump_json().lower()
        for word in ("gliclazide", "diamicron", "sulfonylurea", "diabetes", "sugar", "insulin"):
            assert word not in sent, word

    # The reads were the system's, written down as such, in her name.
    system = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.actor_person_id == siti.person_id
        and line.channel is Channel.SYSTEM
        and line.action is Action.READ
    ]
    assert {Fact.__tablename__, MedicationLine.__tablename__} <= {line.target for line in system}


async def test_the_card_names_whose_phone_was_reached_not_someone_only_the_app_told(
    sg: AsyncSession,
) -> None:
    """#162: Lin is on duty but said no to WhatsApp and has no device, so the ladder reaches
    her only by the notice on her family page — and moves on at once to Mei, his chief, whose
    WhatsApp it reaches. "Knows now" is Mei: Lin does not know yet."""
    owner, mei, lin, _siti, _kit = await _household(sg)
    await add_slot(
        sg,
        context=owner,
        person_id=lin.person_id,
        role=KeyRole.EMERGENCY,
        from_time=time(0, 0),
        to_time=time(23, 59),
        weekdays=list(range(7)),
    )
    await record_opt_in(
        sg,
        context=lin,
        messages=False,
        joins_group=False,
        wording_version=OPT_IN_VERSION,
        language="en",
    )
    chest = await _press(sg, owner, words="chest pain")
    assert chest.notified_person_ids == [mei.person_id]
    assert [line.text for line in chest.lines][:1] == ["Mei knows now."]
