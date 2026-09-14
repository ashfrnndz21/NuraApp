"""E14-01: the symptom log by voice, with severity and duration.

    Logged in his words; appears in the pre-visit brief.

A voice note is heard through the fixture transcriber and becomes a SYMPTOM event and a
`symptom.reported` fact with a window, resting on the artefact; the log is read back in plain
words with the day's name; a viewer's key is refused and written down; a red-flag word in a
symptom escalates exactly as the button does.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Outcome
from app.clock import FrozenClock
from app.db import as_utc, utcnow
from app.keys.context import OutOfScope
from app.keys.scopes import KeyRole, Scope
from app.memory.models import Artifact, ArtifactKind, ConfidenceState, Event, EventKind, Fact
from app.regions import Region
from app.safety.models import Flag
from app.safety.red_flags import RedFlag
from app.safety.symptom_log import log_symptom, nothing_since_line, symptoms_since
from app.safety.symptoms import Duration, Symptom
from app.state.models import Posture
from app.state.service import current_state
from tests.safety_support import REGISTRY, TRANSCRIBER, assert_plain, let_in, pa, trail
from tests.voice import CONTENT_TYPE, DIZZY, SAKIT_DADA, placeholder_voice


class _Store:
    region = Region.SG

    def __init__(self) -> None:
        self.kept: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.kept[key] = data

    async def get(self, key: str) -> bytes:
        return self.kept[key]


async def _log(session: AsyncSession, context, **said):
    return await log_symptom(
        session, context=context, store=_Store(), transcriber=TRANSCRIBER, registry=REGISTRY, **said
    )


_verified = assert_plain


async def test_a_symptom_by_voice_is_logged_in_his_words_with_how_much_and_since_when(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg, phone="+6591110051")
    logged = await _log(sg, owner, audio=placeholder_voice(DIZZY), content_type=CONTENT_TYPE)
    entry = logged.entry

    assert entry.symptoms == [Symptom.DIZZY] and entry.severity == 2
    assert entry.duration is Duration.THIS_MORNING and entry.by_voice and entry.heard
    assert entry.confidence == 0.9
    # Thursday 3 September 2026, 16:00 in Singapore.
    assert [line.text for line in entry.lines] == [
        "Pa felt dizzy on Thursday 3 September.",
        "It was quite a lot.",
        "It started this morning.",
        "Pa said this by voice.",
    ]
    _verified(entry.lines)
    assert logged.flag_id is None and logged.posture is None and logged.notified_person_ids == []

    fact = await sg.get(Fact, entry.fact_id)
    assert fact is not None and fact.subject == "symptom" and fact.attribute == "reported"
    assert fact.confidence_state is ConfidenceState.EXTRACTED
    assert as_utc(fact.valid_to) == utcnow() + timedelta(days=7)
    assert fact.artifact_id == entry.artifact_id and fact.event_id == entry.event_id
    artifact = await sg.get(Artifact, entry.artifact_id)
    assert artifact is not None and artifact.kind is ArtifactKind.VOICE
    event = await sg.get(Event, entry.event_id)
    assert event is not None and event.kind is EventKind.SYMPTOM and event.label == "symptom"
    # His words are in the store, not in any row.
    assert fact.value == {
        "symptoms": ["dizzy"],
        "red_flags": [],
        "suppressed": [],
        "severity": 2,
        "duration": "this_morning",
        "heard": True,
        "via": "voice",
    }


async def test_typed_words_are_his_own_word_and_severity_maps_both_ways(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110052")
    logged = await _log(sg, owner, words="very tired since yesterday")
    entry = logged.entry
    assert entry.symptoms == [Symptom.TIRED] and entry.severity == 3
    assert entry.duration is Duration.SINCE_YESTERDAY and not entry.by_voice
    assert [line.text for line in entry.lines] == [
        "Pa felt tired on Thursday 3 September.",
        "It was very bad.",
        "It started yesterday.",
        "Pa typed this.",
    ]
    fact = await sg.get(Fact, entry.fact_id)
    assert fact is not None and fact.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
    assert fact.confirmed_by_person_id == owner.person_id
    little = await _log(sg, owner, words="a little dizzy")
    assert little.entry.severity == 1
    assert little.entry.lines[1].text == "It was a little."


async def test_the_chief_reads_the_log_in_plain_words_and_a_viewer_is_refused(
    sg: AsyncSession, clock: FrozenClock
) -> None:
    owner = await pa(sg, phone="+6591110053")
    mei = await let_in(sg, owner, phone="+6592220053", name="Mei", role=KeyRole.CHIEF)
    kit = await let_in(sg, owner, phone="+6593330053", name="Kit", role=KeyRole.VIEWER)
    assert Scope.RECORDS not in kit.scopes and Scope.READINGS in kit.scopes

    before = await symptoms_since(sg, context=mei)
    assert before.entries == []
    empty = nothing_since_line(before.since, language="en", region=Region.SG)
    assert empty == "Nothing was written down since Thursday 27 August."

    await _log(sg, owner, audio=placeholder_voice(DIZZY), content_type=CONTENT_TYPE)
    clock.step(timedelta(minutes=5))
    await _log(sg, owner, words="no appetite")
    log = await symptoms_since(sg, context=mei, since=utcnow() - timedelta(days=1))
    assert [e.symptoms for e in log.entries] == [[Symptom.DIZZY], [Symptom.POOR_APPETITE]]
    assert log.entries[1].lines[0].text == "Pa felt no appetite on Thursday 3 September."
    for entry in log.entries:
        _verified(entry.lines)
    malay = await symptoms_since(sg, context=mei, language="ms")
    assert malay.entries[0].lines[0].text == "Pa rasa pening pada Khamis 3 September."
    _verified(malay.entries[0].lines, "ms")

    with pytest.raises(OutOfScope):
        await symptoms_since(sg, context=kit)
    refused = [
        line
        for line in await trail(sg, owner.profile_id)
        if line.outcome is Outcome.REFUSED and line.actor_person_id == kit.person_id
    ]
    assert refused and refused[-1].scope is Scope.RECORDS and refused[-1].target == "fact"


async def test_a_red_flag_word_in_a_symptom_escalates_like_the_button(sg: AsyncSession) -> None:
    owner = await pa(sg, phone="+6591110054")
    mei = await let_in(sg, owner, phone="+6592220054", name="Mei", role=KeyRole.CHIEF)
    logged = await _log(sg, owner, audio=placeholder_voice(SAKIT_DADA), content_type=CONTENT_TYPE)
    assert logged.entry.red_flags == [RedFlag.CHEST_PAIN]
    assert logged.posture is Posture.ACT and logged.flag_id is not None
    assert logged.notified_person_ids == [mei.person_id]
    assert logged.entry.lines[0].text == "Pa felt chest pain on Thursday 3 September."
    flag = await sg.get(Flag, logged.flag_id)
    assert flag is not None and flag.code == "chest_pain"
    assert (await current_state(sg, context=owner)).posture is Posture.ACT
    flags = (await sg.scalars(select(Flag).where(Flag.profile_id == owner.profile_id))).all()
    assert len(flags) == 1
