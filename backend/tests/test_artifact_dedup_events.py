"""D-4a's other half: the bytes may be deduped, but the event built on them never is.

The unique index on `artifact(profile_id, sha256)` (migration `0055`) means the exact same
bytes offered twice for one profile can never become two `Artifact` rows — every writer that
can plausibly be handed the same bytes twice checks first
(`app.ingestion.duplicates.find_own_artifact_by_digest`) and reuses what is already on file
rather than raising the integrity error. That is D-4a's first half, and it is settled.

This file is the second half, the one the bytes-level fix must never quietly break: the
*event* a caller is on its way to record when it happens to offer the same bytes again is a
real, distinct thing that happened a second time — a second question, a second inbound
message, a second symptom report, a second photo of the screen, a second turn on a thread —
and none of the five writers that now dedupe artefact bytes may let that reuse swallow the
event along with the row. One test per writer, each proving both halves: exactly one
`Artifact` survives the second write, and the second event is genuinely there, pointing at
that one shared artefact wherever the schema carries such a reference.

    app.search.ask._keep_question             -- asking the same question twice (recall)
    app.ingestion.voice.store_words            -- saying the same symptom words twice (E13-02)
    app.channels.whatsapp.inbound._keep_text   -- the same WhatsApp text sent twice
    app.ingestion.photos.store_photo           -- the same device-screen photo posted twice
    app.search.conversation._keep_answer       -- the same conversation answer kept twice (W2)

Four of the five run at the service layer, on `sg`, the way `test_recall.py`,
`test_not_feeling_well.py` and `test_conversation_w2.py` already do; the photo case runs over
HTTP, the way `test_device_screens.py` already does, because that is where the review card the
second event rests on is minted.

The independent safety review's B5 widened two more writers the same way, after the unique
index (`0055`) turned a resend into a raw `IntegrityError` instead of a reuse:

    app.ingestion.voice.store_voice                    -- the same voice note said twice
    app.channels.whatsapp.inbound._document (PDF branch) -- the same PDF letter sent twice

Both get their own test here, on the same proof: one artefact, but the second message or
event is genuinely there.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action
from app.audit.trail import read_audit
from app.channels.whatsapp.models import MessageKind, WhatsAppMessage
from app.clock import FrozenClock
from app.ingestion.models import ReviewCard
from app.ingestion.objects import LocalObjectStore, sha256_of
from app.keys.scopes import Scope
from app.memory.models import Artifact, ArtifactKind, Event, EventKind, Fact
from app.regions import Region
from app.safety.models import WhatToDoKind
from app.safety.not_feeling_well import WhatToDoNow, not_feeling_well
from app.search.ask import ASK_TARGET, Answer, AnswerLine, Cite, Mode, _keep_question, recall
from app.search.conversation import current_conversation, record_turn, turns_of
from app.search.retrieve import KeywordRetriever
from tests.api import bearer, own_profile, register_by_phone
from tests.capture_support import confirm, decide, photo
from tests.conftest import Deployment
from tests.delivery_support import via_for
from tests.medicines_support import REGISTRY as ASK_REGISTRY
from tests.paper import BP_CUFF
from tests.safety_support import REGISTRY as SAFETY_REGISTRY
from tests.safety_support import pa as safety_pa
from tests.safety_support import transcriber_for
from tests.timeline_support import record as arranged_record
from tests.voice_notes import AFTER_THE_WALK, placeholder_voice
from tests.voice_notes import CONTENT_TYPE as VOICE_NOTE_CONTENT_TYPE
from tests.whatsapp_support import MEI, family


async def _ask(
    session: AsyncSession, context, question: str, tmp_path: Path, *, mode: Mode = Mode.TEXT
):
    """`recall`, the same way `test_recall.py`'s own `ask` helper drives it: the fixture
    keyword retriever, a fresh local store per test."""
    return await recall(
        session,
        context=context,
        question=question,
        mode=mode,
        retriever=KeywordRetriever(),
        store=LocalObjectStore(tmp_path, Region.SG),
        registry=ASK_REGISTRY,
    )


async def test_the_same_question_asked_twice_still_produces_two_audited_reads(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`_keep_question` (`app.search.ask`) keeps the question's words as a MESSAGE artefact by
    digest and reuses the one already on file for the exact same words. But asking again is a
    real second ask: it must be answered again, not silently skipped, and the trail must show
    two reads, not one folded into the first."""
    rec = await arranged_record(sg)
    question = "what was my blood pressure"

    first = await _ask(sg, rec.owner, question, tmp_path)
    second = await _ask(sg, rec.owner, question, tmp_path)

    # Both asks were genuinely answered -- the second is not a silent no-op.
    assert first.answered and second.answered
    assert first.lines and second.lines

    # The bytes are the one artefact D-4a promises: both answers cite it, and only one row of
    # it exists on this profile.
    assert first.question_artifact_id is not None
    assert first.question_artifact_id == second.question_artifact_id
    digest = sha256_of(question.encode("utf-8"))
    kept = (
        await sg.scalars(
            select(Artifact).where(
                Artifact.profile_id == rec.owner.profile_id,
                Artifact.kind == ArtifactKind.MESSAGE,
                Artifact.sha256 == digest,
            )
        )
    ).all()
    assert len(kept) == 1 and kept[0].id == first.question_artifact_id

    # Two separate reads on the trail, both naming the one kept question -- an ask is never
    # merged into an earlier one just because its words were seen before.
    asks = [
        entry
        for entry in await read_audit(sg, context=rec.owner, action=Action.READ, scope=Scope.ASK)
        if entry.target == ASK_TARGET and entry.target_id == first.question_artifact_id
    ]
    assert len(asks) == 2


def _turn_answer(lines: tuple[AnswerLine, ...] = (), honest: tuple[str, ...] = ()) -> Answer:
    """A minimal `Answer` for `record_turn`, the same shape `test_conversation_w2.py`'s own
    `_answer` helper builds. `_keep_answer` never reads `question_artifact_id` -- it only
    serialises `lines`/`honest`/`clarify` -- so a fresh one per call changes nothing about the
    answer artefact's own bytes."""
    return Answer(
        question_artifact_id=uuid.uuid4(),
        mode=Mode.TEXT,
        language="en",
        lines=lines,
        honest=honest,
        boundary=("Ask Dr Tan.",),
        withheld=(),
        dropped=0,
    )


async def test_the_same_answer_kept_twice_on_a_conversation_still_writes_two_turns(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`_keep_answer` (`app.search.conversation`), the answer's own half of the question's
    `_keep_question`: a turn's answer is kept as a MESSAGE artefact by digest, and a repeated
    question -- itself already deduped -- naturally composes the identical answer, so the
    second turn's answer is the same bytes and reuses the one artefact already on file
    (`find_own_artifact_by_digest`, `Scope.ASK`, `ArtifactKind.MESSAGE`). But each is still its
    own turn on the thread -- its own question, its own read of the record -- and `record_turn`
    must write both, never collapse the second into the first because its answer matched."""
    rec = await arranged_record(sg)
    store = LocalObjectStore(tmp_path, Region.SG)
    conversation = await current_conversation(sg, context=rec.owner)
    answer = _turn_answer(
        lines=(
            AnswerLine(
                text="Your medicine is on your list.", cites=(Cite(kind="fact", id=uuid.uuid4()),)
            ),
        )
    )

    first_question = await _keep_question(sg, rec.owner, store, "what is my medicine")
    first_turn = await record_turn(
        sg,
        context=rec.owner,
        store=store,
        conversation=conversation,
        question_artifact_id=first_question.id,
        answer=answer,
    )
    second_question = await _keep_question(sg, rec.owner, store, "what is my medicine, again")
    second_turn = await record_turn(
        sg,
        context=rec.owner,
        store=store,
        conversation=conversation,
        question_artifact_id=second_question.id,
        answer=answer,
    )

    # Two distinct turns -- each its own question -- sharing the one answer artefact.
    assert first_turn.id != second_turn.id
    assert first_turn.question_artifact_id != second_turn.question_artifact_id
    assert first_turn.answer_artifact_id is not None
    assert first_turn.answer_artifact_id == second_turn.answer_artifact_id

    # Exactly one Artifact row for that answer's digest -- the reuse, not a duplicate row.
    kept_answer = await sg.get(Artifact, first_turn.answer_artifact_id)
    assert kept_answer is not None and kept_answer.kind is ArtifactKind.MESSAGE
    same_digest = (
        await sg.scalars(
            select(Artifact).where(
                Artifact.profile_id == rec.owner.profile_id,
                Artifact.kind == ArtifactKind.MESSAGE,
                Artifact.sha256 == kept_answer.sha256,
            )
        )
    ).all()
    assert len(same_digest) == 1 and same_digest[0].id == first_turn.answer_artifact_id

    # Both turns are genuinely on the thread, not one silently skipped.
    turns = await turns_of(sg, context=rec.owner, conversation=conversation)
    assert {t.id for t in turns} == {first_turn.id, second_turn.id}


async def test_the_same_symptom_words_said_twice_still_write_two_symptom_events(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`store_words` (`app.ingestion.voice`), the way `not_feeling_well`'s `capture` step
    calls it, keeps his typed words as a MESSAGE artefact by digest. Pressing the button again
    with the exact same words is the same bytes -- one artefact -- but he is still not feeling
    well the second time, whatever he said the first: the SYMPTOM event and the
    `symptom.reported` fact it rests on must each be their own press's, never dropped because
    the words matched an earlier one."""
    owner = await safety_pa(sg)
    store = LocalObjectStore(tmp_path, owner.region)
    via = via_for(owner.region)

    async def press() -> WhatToDoNow:
        return await not_feeling_well(
            sg,
            context=owner,
            store=store,
            transcriber=transcriber_for(owner.region),
            registry=SAFETY_REGISTRY,
            via=via,
            words="tired today",
        )

    first = await press()
    second = await press()

    # Nothing red here, no medicine on record to be missed: both presses land on the ordinary
    # rest row, and each is its own event and fact, not two names for the first.
    assert first.kind is WhatToDoKind.REST and second.kind is WhatToDoKind.REST
    assert first.event_id is not None and second.event_id is not None
    assert first.event_id != second.event_id
    assert first.fact_id is not None and second.fact_id is not None
    assert first.fact_id != second.fact_id

    # One artefact for the words, reused the second time.
    assert first.artifact_id is not None
    assert first.artifact_id == second.artifact_id
    artifacts = (
        await sg.scalars(
            select(Artifact).where(
                Artifact.profile_id == owner.profile_id, Artifact.kind == ArtifactKind.MESSAGE
            )
        )
    ).all()
    assert len(artifacts) == 1 and artifacts[0].id == first.artifact_id

    # Two SYMPTOM events, each naming that one artefact.
    events = (
        await sg.scalars(
            select(Event).where(
                Event.profile_id == owner.profile_id, Event.kind == EventKind.SYMPTOM
            )
        )
    ).all()
    assert {e.id for e in events} == {first.event_id, second.event_id}
    assert {e.artifact_id for e in events} == {first.artifact_id}

    # Two `symptom.reported` facts, one per press.
    facts = (
        await sg.scalars(
            select(Fact).where(
                Fact.profile_id == owner.profile_id,
                Fact.subject == "symptom",
                Fact.attribute == "reported",
            )
        )
    ).all()
    assert {f.id for f in facts} == {first.fact_id, second.fact_id}


async def test_the_same_whatsapp_text_sent_twice_still_keeps_two_inbound_messages(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`_keep_text` (`app.channels.whatsapp.inbound`), plain coordination in the private
    thread -- "who is taking him on Thursday?" -- never tangled in a feeling word's own
    business logic: Mei's exact words sent twice are the same bytes, one artefact, but each
    message she actually sent must still land in the thread as its own `WhatsAppMessage` row,
    naming that one artefact -- never silently absorbed into the first."""
    home = await family(sg, tmp_path)
    text = "who is taking him on Thursday?"

    first = await home.inbound(sg, MEI, text)
    second = await home.inbound(sg, MEI, text)

    assert first.outcome == "coordination" and second.outcome == "coordination"
    assert first.message_id is not None and second.message_id is not None
    assert first.message_id != second.message_id

    # One artefact for the words, reused the second time.
    assert first.artifact_id is not None
    assert first.artifact_id == second.artifact_id
    artifacts = (
        await sg.scalars(
            select(Artifact).where(
                Artifact.profile_id == home.profile.id, Artifact.kind == ArtifactKind.MESSAGE
            )
        )
    ).all()
    assert len(artifacts) == 1 and artifacts[0].id == first.artifact_id

    # Two inbound WhatsAppMessage rows, each naming that one artefact.
    messages = (
        await sg.scalars(
            select(WhatsAppMessage).where(WhatsAppMessage.kind == MessageKind.COORDINATION)
        )
    ).all()
    assert {m.id for m in messages} == {first.message_id, second.message_id}
    assert {m.artifact_id for m in messages} == {first.artifact_id}


LATER_THAT_DAY = datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
"""The same moment `test_device_screens.py` sets the clock to before posting a BP_CUFF screen
photo: the fixture's screen reads a time on its own clock that only sits before "now" once the
frozen clock is moved there."""


async def _pa(deployment: Deployment) -> tuple[dict[str, str], str]:
    person = await register_by_phone(deployment, "+6591200099", "Pa")
    return person, await own_profile(deployment, person, language="en")


async def _screen(deployment: Deployment, pa: dict[str, str], profile_id: str) -> dict:
    posted = await deployment.client.post(
        f"/profiles/{profile_id}/readings/photo", json=photo(BP_CUFF), headers=bearer(pa["token"])
    )
    assert posted.status_code == 201, posted.text
    card: dict = posted.json()
    return card


async def test_a_retaken_device_screen_photo_reuses_the_artifact_but_gets_its_own_review_card(
    deployment: Deployment, clock: FrozenClock
) -> None:
    """`store_photo` (`app.ingestion.photos`), through `POST .../readings/photo`
    (`add_screen_photo`, `app.channels.api.capture`): that route never pre-checks the digest
    the way the paper routes' `find_artifact_by_digest` does, so it always calls
    `review_artifact` and always mints a fresh `ReviewCard` -- a re-taken photo of the same
    screen is a genuinely new reading event, even though the bytes underneath it, once
    dedup(e)d, are the one artefact `store_photo` already has on file."""
    clock.set(LATER_THAT_DAY)
    pa, profile_id = await _pa(deployment)

    first_card = await _screen(deployment, pa, profile_id)
    second_card = await _screen(deployment, pa, profile_id)

    assert first_card["artifact_id"] == second_card["artifact_id"]
    assert first_card["card_id"] != second_card["card_id"]

    async with deployment.sessions() as session:
        artifacts = (
            await session.scalars(
                select(Artifact).where(
                    Artifact.profile_id == uuid.UUID(profile_id),
                    Artifact.kind == ArtifactKind.PHOTO,
                )
            )
        ).all()
        assert len(artifacts) == 1 and str(artifacts[0].id) == first_card["artifact_id"]

        cards = (
            await session.scalars(
                select(ReviewCard).where(
                    ReviewCard.artifact_id == uuid.UUID(first_card["artifact_id"])
                )
            )
        ).all()
        assert {str(c.id) for c in cards} == {first_card["card_id"], second_card["card_id"]}

    # Each retake still confirms into its own reading: two READING events, not one.
    first_done = await confirm(deployment, pa["token"], profile_id, first_card, decide(first_card))
    assert first_done.status_code == 200, first_done.text
    second_done = await confirm(
        deployment, pa["token"], profile_id, second_card, decide(second_card)
    )
    assert second_done.status_code == 200, second_done.text
    first_event_id = first_done.json()["event_id"]
    second_event_id = second_done.json()["event_id"]
    assert first_event_id is not None and second_event_id is not None
    assert first_event_id != second_event_id


async def test_the_same_voice_note_said_twice_still_writes_two_symptom_events(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """`store_voice` (`app.ingestion.voice`), through `not_feeling_well`'s own audio path
    (B5, the independent safety review): the exact same recording pressed again is the same
    bytes -- migration `0055`'s unique index makes a second `Artifact` row of them impossible,
    so this reuses the one already on file rather than raising `IntegrityError` out of the
    button. But he is still not feeling well the second time he presses it, whatever the note
    said the first time: its own SYMPTOM event and `symptom.reported` fact must each be their
    own press's, exactly as the typed-words case above already proves for `store_words`."""
    owner = await safety_pa(sg)
    store = LocalObjectStore(tmp_path, owner.region)
    via = via_for(owner.region)
    audio = placeholder_voice(AFTER_THE_WALK)

    async def press() -> WhatToDoNow:
        return await not_feeling_well(
            sg,
            context=owner,
            store=store,
            transcriber=transcriber_for(owner.region),
            registry=SAFETY_REGISTRY,
            via=via,
            audio=audio,
            content_type=VOICE_NOTE_CONTENT_TYPE,
        )

    first = await press()
    second = await press()

    assert first.kind is WhatToDoKind.REST and second.kind is WhatToDoKind.REST
    assert first.event_id is not None and second.event_id is not None
    assert first.event_id != second.event_id
    assert first.fact_id is not None and second.fact_id is not None
    assert first.fact_id != second.fact_id

    # One artefact for the recording, reused the second time.
    assert first.artifact_id is not None
    assert first.artifact_id == second.artifact_id
    artifacts = (
        await sg.scalars(
            select(Artifact).where(
                Artifact.profile_id == owner.profile_id, Artifact.kind == ArtifactKind.VOICE
            )
        )
    ).all()
    assert len(artifacts) == 1 and artifacts[0].id == first.artifact_id

    # Two SYMPTOM events, each naming that one artefact.
    events = (
        await sg.scalars(
            select(Event).where(
                Event.profile_id == owner.profile_id, Event.kind == EventKind.SYMPTOM
            )
        )
    ).all()
    assert {e.id for e in events} == {first.event_id, second.event_id}
    assert {e.artifact_id for e in events} == {first.artifact_id}

    # Two `symptom.reported` facts, one per press.
    facts = (
        await sg.scalars(
            select(Fact).where(
                Fact.profile_id == owner.profile_id,
                Fact.subject == "symptom",
                Fact.attribute == "reported",
            )
        )
    ).all()
    assert {f.id for f in facts} == {first.fact_id, second.fact_id}


async def test_the_same_pdf_letter_sent_twice_on_whatsapp_still_keeps_two_inbound_messages(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The `_document` PDF branch (`app.channels.whatsapp.inbound`, B5): the exact same letter
    forwarded a second time -- Mei resending the one Nura already asked her for -- is the same
    bytes, so this reuses the one `Artifact` already on file instead of a raw `IntegrityError`
    out of the webhook (a 500, and silence, for resending exactly the letter she was asked to).
    But each send is still its own inbound message on the thread, never folded into the
    first."""
    home = await family(sg, tmp_path)

    first = await home.inbound(sg, MEI, media_id="clinic-letter-pdf", content_type="application/pdf")
    second = await home.inbound(sg, MEI, media_id="clinic-letter-pdf", content_type="application/pdf")

    assert first.outcome == "document" and second.outcome == "document"
    assert first.message_id is not None and second.message_id is not None
    assert first.message_id != second.message_id

    # One artefact for the letter, reused the second time.
    assert first.artifact_id is not None
    assert first.artifact_id == second.artifact_id
    artifacts = (
        await sg.scalars(
            select(Artifact).where(
                Artifact.profile_id == home.profile.id, Artifact.kind == ArtifactKind.PDF
            )
        )
    ).all()
    assert len(artifacts) == 1 and artifacts[0].id == first.artifact_id

    # Two inbound WhatsAppMessage rows, each naming that one artefact.
    messages = (
        await sg.scalars(select(WhatsAppMessage).where(WhatsAppMessage.kind == MessageKind.DOCUMENT))
    ).all()
    assert {m.id for m in messages} == {first.message_id, second.message_id}
    assert {m.artifact_id for m in messages} == {first.artifact_id}
