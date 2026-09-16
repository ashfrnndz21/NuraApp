"""E19-02, E19-03: the thread. A forwarded photo files itself and replies; a health event
becomes a proposal that needs the poster's yes; a stranger gets one line and leaves nothing;
nothing goes out without consent; a template outside the window and free text inside it;
every message, in and out, on the trail; a MY number never reaches an SG profile."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import Action, AuditEntry, Channel, Outcome
from app.audit.trail import read_audit
from app.channels.whatsapp.classifier import Classification, Kind, RuleClassifier
from app.channels.whatsapp.inbound import handle_inbound
from app.channels.whatsapp.models import (
    Direction,
    MessageKind,
    Proposal,
    ProposalStatus,
    WhatsAppMessage,
    WhatsAppThread,
)
from app.channels.whatsapp.outbound.level0 import run_feeling_check_in, run_morning
from app.channels.whatsapp.outbound.send import OutsideTheWindow, send
from app.channels.whatsapp.provider import DevInbound
from app.clock import FrozenClock
from app.consent.models import ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import ConsentWithheld, grant_consent
from app.db import utcnow
from app.identity.service import create_own_profile, register_person
from app.ingestion.models import ReviewCard, ReviewField
from app.keys.confirm import Confirmation
from app.keys.scopes import KeyRole, Scope
from app.memory.episodic import record_event
from app.memory.models import Artifact, ArtifactKind, Event, EventKind, Fact, SourceChannel
from app.memory.semantic import assert_fact, current_facts
from app.reasoning.feelings.strings import PROMPT
from app.regions import Region
from app.state.service import current_state
from tests.support import OPENING_CONSENT, refused_unit
from tests.whatsapp_support import KIT, MEI, PA, deployment, family

# --- documents --------------------------------------------------------------------------------


async def test_a_forwarded_photo_files_itself_as_a_review_card_and_replies(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, media_id="lipid-panel-photo", content_type="image/png")
    assert handled.outcome == "document"
    assert handled.artifact_id is not None and handled.review_card_id is not None

    kept = await sg.get(Artifact, handled.artifact_id)
    assert kept is not None
    assert kept.kind is ArtifactKind.PHOTO and kept.source_channel is SourceChannel.WHATSAPP
    assert kept.region is Region.SG and kept.profile_id == home.profile.id
    # The bytes are in the SG store, under the profile, by digest.
    assert home.providers.object_store.path_of(kept.storage_key).is_file()  # type: ignore[attr-defined]

    card = await sg.get(ReviewCard, handled.review_card_id)
    assert card is not None and card.is_open and card.artifact_id == kept.id
    fields = (await sg.scalars(select(ReviewField).where(ReviewField.card_id == card.id))).all()
    assert len(fields) == 7  # the lipid report, read by the fixture extractor
    assert list(await current_facts(sg, context=home.owner)) == []  # a card, not facts

    # The reply, from the catalogue, in Mei's thread.
    assert [r.text for r in handled.replies] == ["I kept the photo.\nYou can check it in the app."]
    assert home.whatsapp.sent[-1].to_e164 == MEI and home.whatsapp.sent[-1].kind == "text"

    # And the thread has the message by reference, never the bytes.
    rows = (await sg.scalars(select(WhatsAppMessage))).all()
    inbound = [r for r in rows if r.direction is Direction.INBOUND]
    assert len(inbound) == 1 and inbound[0].kind is MessageKind.DOCUMENT
    assert inbound[0].artifact_id == kept.id and inbound[0].person_id == home.mei.id


async def test_the_patient_forwarding_a_photo_is_told_his_chief_will_check(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, PA, media_id="lipid-panel-photo", content_type="image/png")
    assert handled.replies[0].text == "I kept the photo.\nMei can check it in the app."


async def test_a_pdf_is_kept_as_a_letter(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(
        sg, MEI, media_id="clinic-letter-pdf", content_type="application/pdf"
    )
    assert handled.outcome == "document" and handled.review_card_id is None
    kept = await sg.get(Artifact, handled.artifact_id)
    assert kept is not None and kept.kind is ArtifactKind.PDF
    assert handled.replies[0].text.startswith("I kept the letter.")


async def test_media_the_provider_has_lost_is_refused_and_written_down(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, media_id="gone", content_type="image/jpeg")
    assert handled.outcome == "refused" and handled.refused == "NoSuchMedia"
    assert list(await sg.scalars(select(Artifact))) == []
    trail = await read_audit(sg, context=home.owner)
    assert any(e.refused_because == "NoSuchMedia" and e.channel is Channel.WHATSAPP for e in trail)


# --- health events: proposals ------------------------------------------------------------------


async def test_a_health_event_becomes_a_proposal_that_needs_the_posters_yes(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    heard = await home.inbound(sg, MEI, "BP 150/90 this morning")
    assert heard.outcome == "proposal" and heard.proposal_id is not None
    proposal = await sg.get(Proposal, heard.proposal_id)
    assert proposal is not None and proposal.is_open
    assert proposal.poster_person_id == home.mei.id
    assert proposal.subject == "blood_pressure" and proposal.value == {
        "systolic": 150,
        "diastolic": 90,
    }
    assert heard.replies[0].text == (
        "Did I get this right?\nPa's blood pressure was 150 over 90.\nAnswer yes or no."
    )
    # Nothing is written before the yes: no event, no fact, no confirmation.
    assert list(await sg.scalars(select(Fact))) == []
    assert list(await sg.scalars(select(Event))) == []
    assert list(await sg.scalars(select(Confirmation))) == []
    before = await current_state(sg, context=home.owner)

    # Someone else's yes finds nothing open, and writes nothing.
    his = await home.inbound(sg, PA, "yes")
    assert his.outcome == "nothing_open" and his.fact_id is None
    assert his.replies[0].text == "I have no question open for you."
    await sg.refresh(proposal)
    assert proposal.is_open and list(await sg.scalars(select(Fact))) == []

    # The poster's yes, from the same number, mints and spends the yes and writes the fact.
    yes = await home.inbound(sg, MEI, "yes")
    assert yes.outcome == "confirmed" and yes.fact_id is not None
    assert yes.replies[0].text == "Thank you for telling me.\nI wrote it down."
    fact = await sg.get(Fact, yes.fact_id)
    assert fact is not None
    assert fact.subject == "blood_pressure" and fact.attribute == "reading"
    assert fact.value == {"systolic": 150, "diastolic": 90} and fact.unit == "mmHg"
    assert fact.confirmed_by_person_id == home.mei.id
    # Provenance: the event of the reading, resting on the message it was heard in.
    assert fact.event_id is not None and fact.artifact_id == heard.artifact_id
    event = await sg.get(Event, fact.event_id)
    assert event is not None and event.kind is EventKind.READING
    assert event.artifact_id == heard.artifact_id
    assert event.source_channel is SourceChannel.WHATSAPP
    spent = (await sg.scalars(select(Confirmation))).all()
    assert len(spent) == 1 and spent[0].consumed_at is not None
    assert spent[0].via_channel is Channel.WHATSAPP and spent[0].person_id == home.mei.id
    await sg.refresh(proposal)
    assert proposal.status is ProposalStatus.CONFIRMED and proposal.fact_id == fact.id

    # State recomputed as the fact landed, naming it.
    after = await current_state(sg, context=home.owner)
    assert after.sequence > before.sequence and after.trigger_fact_id == fact.id
    folded = after.dimension("clinical")  # type: ignore[arg-type]
    assert folded is not None
    assert folded["facts"]["blood_pressure"]["reading"]["value"] == {
        "systolic": 150,
        "diastolic": 90,
    }

    # A second yes has nothing left to confirm.
    again = await home.inbound(sg, MEI, "yes")
    assert again.outcome == "nothing_open"
    assert len((await sg.scalars(select(Fact))).all()) == 1


async def test_no_closes_the_proposal_and_writes_nothing(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    heard = await home.inbound(sg, MEI, "sugar 7.2 before breakfast")
    assert heard.replies[0].text == "Did I get this right?\nPa's sugar was 7.2.\nAnswer yes or no."
    no = await home.inbound(sg, MEI, "no")
    assert no.outcome == "declined" and no.replies[0].text == "OK, I did not write it down."
    proposal = await sg.get(Proposal, heard.proposal_id)
    assert proposal is not None and proposal.status is ProposalStatus.DECLINED
    assert list(await sg.scalars(select(Fact))) == []


async def test_a_proposal_older_than_a_day_is_closed_as_expired(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home = await family(sg, tmp_path)
    heard = await home.inbound(sg, MEI, "he weighed 62 kg today")
    assert heard.replies[0].text == "Did I get this right?\nPa weighed 62 kg.\nAnswer yes or no."
    clock.step(timedelta(hours=25))
    late = await home.inbound(sg, MEI, "yes")
    assert late.outcome == "too_old"
    assert late.replies[0].text == "That question is too old.\nSend the message again."
    proposal = await sg.get(Proposal, heard.proposal_id)
    assert proposal is not None and proposal.status is ProposalStatus.EXPIRED
    assert list(await sg.scalars(select(Fact))) == []


async def test_a_caregiver_outside_scope_gets_the_same_refusal_as_in_the_app(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """E19-02's acceptance line. Mei's key opens the medicines; a blood pressure is under
    the readings scope, so proposing it is OutOfScope — on the trail, and told in-thread."""
    home = await family(
        sg,
        tmp_path,
        mei_scopes=frozenset({Scope.MEDICINES, Scope.RECORDS, Scope.SEND}),
        mei_role=KeyRole.CAREGIVER,
    )
    handled = await home.inbound(sg, MEI, "BP 150/90 this morning")
    assert handled.outcome == "refused" and handled.refused == "OutOfScope"
    assert handled.replies[0].text == (
        "That part of Pa's papers is not open to you.\nPa can change that in the app."
    )
    assert list(await sg.scalars(select(Proposal))) == []
    assert list(await sg.scalars(select(Artifact))) == []  # the unit rolled back
    trail = await read_audit(sg, context=home.owner)
    assert any(
        e.outcome is Outcome.REFUSED
        and e.refused_because == "OutOfScope"
        and e.scope is Scope.READINGS
        and e.actor_person_id == home.mei.id
        and e.channel is Channel.WHATSAPP
        for e in trail
    )


# --- the patient's own words --------------------------------------------------------------------


async def test_the_patients_feeling_word_is_written_down_without_a_second_yes(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, PA, "tired")
    assert handled.outcome == "check_in_answer" and handled.proposal_id is None
    assert handled.fact_id is not None
    fact = await sg.get(Fact, handled.fact_id)
    assert fact is not None and fact.subject == "feeling" and fact.value == "tired"
    assert fact.confirmed_by_person_id == home.pa.id and fact.event_id is not None
    event = await sg.get(Event, fact.event_id)
    assert event is not None and event.kind is EventKind.SYMPTOM
    assert handled.replies[0].text == "Thank you for telling me.\nI wrote it down."
    state = await current_state(sg, context=home.owner)
    situational = state.dimension("situational")  # type: ignore[arg-type]
    assert (
        situational is not None and situational["facts"]["feeling"]["reported"]["value"] == "tired"
    )


async def test_a_third_partys_feeling_word_is_a_proposal(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "Pa is very tired today")
    assert handled.outcome == "proposal"
    assert (
        handled.replies[0].text == "Did I get this right?\nPa is feeling tired.\nAnswer yes or no."
    )


# --- his "OK" after whatever asked him the feeling question (#205) -------------------------------


async def test_the_days_nudge_opens_his_answer_the_same_way_the_plain_check_in_does(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """#205: on a day the plain check-in stands down because the day's smart nudge already
    asked the feeling question (W7, E17-03), his "OK" back is read as its answer — because
    `WhatsAppMessage.asks_feeling` is set from what the nudge actually said, not from its
    template's name, `nudge`, which is not `feeling_check_in`."""
    home = await family(sg, tmp_path)
    state = await current_state(sg, context=home.owner)
    sent = await send(
        sg,
        context=home.owner,
        to_person=home.pa,
        kind="nudge",
        params={"message": f"You told Nura about tired last week.\n{PROMPT['en']}"},
        provider=home.providers.whatsapp,
        number=home.number,
        language="en",
        state=state,
    )
    assert sent.template_name == "nudge"
    row = await sg.get(WhatsAppMessage, sent.message_id)
    assert row is not None and row.asks_feeling is True

    handled = await home.inbound(sg, PA, "ok")
    assert handled.outcome == "check_in_answer" and handled.fact_id is not None
    fact = await sg.get(Fact, handled.fact_id)
    assert fact is not None and fact.subject == "feeling" and fact.value == "ok"
    assert handled.replies[0].text == "Thank you for telling me.\nI wrote it down."


async def test_a_nudge_that_does_not_ask_the_feeling_question_never_opens_the_check_in(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The care in #205: the marker follows the words he was actually sent, so it must not
    widen to every nudge. One that says something else — the number that only goes up, a
    week of taps kept — never opens his answer window; his "OK" to it still gets the general
    refusal, exactly as an unrelated "OK" to a dose ask or a proposal still would."""
    home = await family(sg, tmp_path)
    state = await current_state(sg, context=home.owner)
    sent = await send(
        sg,
        context=home.owner,
        to_person=home.pa,
        kind="nudge",
        params={"message": "You have taken your morning tablet every day this week."},
        provider=home.providers.whatsapp,
        number=home.number,
        language="en",
        state=state,
    )
    row = await sg.get(WhatsAppMessage, sent.message_id)
    assert row is not None and row.asks_feeling is False

    handled = await home.inbound(sg, PA, "ok")
    assert handled.outcome == "nothing_open"
    assert list(await sg.scalars(select(Fact))) == []


async def test_both_askers_on_one_day_cannot_double_count_his_one_answer(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """A day the plain check-in and the day's nudge both ask him — which the engine's own
    stand-down rule (`app.delivery.triggers.day._the_nudge_asked_today`) exists to prevent,
    but a delivery is never the only way a row could come to exist — still writes down
    exactly the one feeling his one reply carries, never one for each asker."""
    home = await family(sg, tmp_path)
    await run_feeling_check_in(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    state = await current_state(sg, context=home.owner)
    await send(
        sg,
        context=home.owner,
        to_person=home.pa,
        kind="nudge",
        params={"message": PROMPT["en"]},
        provider=home.providers.whatsapp,
        number=home.number,
        language="en",
        state=state,
    )
    asking = [
        row for row in (await sg.scalars(select(WhatsAppMessage))).all() if row.asks_feeling
    ]
    assert len(asking) == 2  # both askers reached him

    handled = await home.inbound(sg, PA, "ok")
    assert handled.outcome == "check_in_answer"
    feelings = [f for f in (await sg.scalars(select(Fact))).all() if f.subject == "feeling"]
    assert len(feelings) == 1


async def test_his_answer_to_yesterdays_nudge_does_not_land_on_todays_feeling(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    """The day boundary is unchanged by this fix: a question asked yesterday, on his wall
    clock, stays yesterday's — his "OK" today answers nothing of it."""
    home = await family(sg, tmp_path)
    state = await current_state(sg, context=home.owner)
    await send(
        sg,
        context=home.owner,
        to_person=home.pa,
        kind="nudge",
        params={"message": PROMPT["en"]},
        provider=home.providers.whatsapp,
        number=home.number,
        language="en",
        state=state,
    )
    # SGT is UTC+8; nine hours on from the frozen 08:00 UTC start crosses into his next day.
    clock.step(timedelta(hours=9))
    handled = await home.inbound(sg, PA, "ok")
    assert handled.outcome == "nothing_open"
    assert list(await sg.scalars(select(Fact))) == []


@pytest.mark.parametrize(("language", "his_word"), (("en", "ok"), ("ms", "ok"), ("zh", "好")))
async def test_his_ok_to_the_nudge_is_read_in_every_language_the_check_in_speaks(
    sg: AsyncSession, tmp_path: Path, language: str, his_word: str
) -> None:
    """The feeling question and the word offered back for it are the nudge's own words in
    en/ms/zh alike (#205): "OK" is kept as itself even in the Malay template, and "好" is the
    Chinese template's own word for it. Whichever language asked, his one word back opens
    and answers the same way the plain check-in's does."""
    home = await family(sg, tmp_path)
    state = await current_state(sg, context=home.owner)
    sent = await send(
        sg,
        context=home.owner,
        to_person=home.pa,
        kind="nudge",
        params={"message": PROMPT[language]},
        provider=home.providers.whatsapp,
        number=home.number,
        language=language,
        state=state,
    )
    row = await sg.get(WhatsAppMessage, sent.message_id)
    assert row is not None and row.asks_feeling is True

    handled = await home.inbound(sg, PA, his_word)
    assert handled.outcome == "check_in_answer" and handled.fact_id is not None
    fact = await sg.get(Fact, handled.fact_id)
    assert fact is not None and fact.subject == "feeling" and fact.value == "ok"


# --- coordination, other, ignore ----------------------------------------------------------------


async def test_coordination_is_kept_for_the_family_with_nothing_extracted(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "who is taking him on Thursday?")
    assert handled.outcome == "coordination"
    assert handled.replies[0].text == "I kept this for the family."
    kept = await sg.get(Artifact, handled.artifact_id)
    assert kept is not None and kept.kind is ArtifactKind.MESSAGE
    events = (await sg.scalars(select(Event))).all()
    assert len(events) == 1 and events[0].kind is EventKind.MESSAGE
    assert events[0].artifact_id == kept.id and events[0].label == "family message"
    assert list(await sg.scalars(select(Fact))) == []
    trail = await read_audit(sg, context=home.owner)
    assert any(e.target == "artifact" and e.scope is Scope.FAMILY for e in trail)


async def test_everything_else_is_not_kept(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "haha look at this 😂")
    assert handled.outcome == "other" and handled.artifact_id is None
    assert handled.replies[0].text.startswith("I did not understand that.")
    assert list(await sg.scalars(select(Artifact))) == []
    assert [r.kind for r in await sg.scalars(select(WhatsAppMessage))] == [MessageKind.REPLY]
    # In a group this number does not keep, silence (the family's own group: E11-01).
    quiet = await home.inbound(sg, MEI, "haha", group_id="pas-health")
    assert quiet.outcome == "ignored" and quiet.replies == ()


async def test_ignore_is_honoured_absolutely(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, MEI, "ignore: BP 150/90 was the neighbour's")
    assert handled.outcome == "ignored" and handled.replies == ()
    assert list(await sg.scalars(select(Artifact))) == []
    assert list(await sg.scalars(select(WhatsAppThread))) == []
    assert home.whatsapp.sent == []


# --- strangers and regions -----------------------------------------------------------------------


async def test_an_unknown_number_gets_one_fixed_reply_and_nothing_is_stored(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    handled = await home.inbound(sg, KIT, "BP 150/90, this is Pa's son")
    assert handled.outcome == "unknown_number" and handled.profile_id is None
    assert handled.stranger_reply == (
        "Hello, this is Nura.\nNura keeps health papers for families.\n"
        "This number is not on a family list yet.\nAsk your family to add you in the app.\n"
        "Nura is not a doctor."
    )
    assert len(home.whatsapp.sent) == 1 and home.whatsapp.sent[0].to_e164 == KIT
    assert list(await sg.scalars(select(Artifact))) == []
    assert list(await sg.scalars(select(WhatsAppThread))) == []
    assert list(await sg.scalars(select(WhatsAppMessage))) == []
    assert (
        list(await sg.scalars(select(AuditEntry).where(AuditEntry.channel == Channel.WHATSAPP)))
        == []
    )
    # A registered account with no profile and no key is a stranger too, in the same words.
    await register_person(sg, region=Region.SG, display_name="Kit", phone_e164=KIT)
    again = await home.inbound(sg, KIT, "hello?")
    assert again.outcome == "unknown_number" and again.stranger_reply == handled.stranger_reply


async def test_a_my_number_never_reaches_an_sg_profile(
    sg: AsyncSession, my: AsyncSession, tmp_path: Path
) -> None:
    """A person pinned to Malaysia is, to the Singapore deployment, a stranger: the same one
    line, nothing about the profile, nothing stored — even when a row for the number sits in
    this database."""
    home = await family(sg, tmp_path)
    # A MY person, present in the SG database (the thing the region pin guards against).
    await register_person(sg, region=Region.MY, display_name="Kit", phone_e164=KIT)
    handled = await home.inbound(sg, KIT, "BP 150/90")
    assert handled.outcome == "unknown_number" and handled.profile_id is None
    assert list(await sg.scalars(select(Artifact))) == []
    assert list(await sg.scalars(select(WhatsAppThread))) == []
    # And the MY deployment, with its own database, knows no SG profile to reach.
    settings, providers = deployment(tmp_path / "my", Region.MY)
    kit = await register_person(my, region=Region.MY, display_name="Kit", phone_e164=KIT)
    await create_own_profile(my, region=Region.MY, owner=kit, consent=OPENING_CONSENT)
    reached = await handle_inbound(
        my,
        settings=settings,
        providers=providers,
        number=home.number,
        classifier=RuleClassifier(),
        message=DevInbound(from_e164=KIT, text="BP 150/90").as_message(utcnow()),
    )
    assert reached.profile_id != home.profile.id


# --- consent and the window ----------------------------------------------------------------------


async def test_without_whatsapp_consent_nothing_is_kept_and_nothing_is_sent_through_the_door(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path, whatsapp_consent=False)
    handled = await home.inbound(sg, MEI, "BP 150/90 this morning")
    assert handled.outcome == "refused" and handled.refused == "ConsentWithheld"
    assert list(await sg.scalars(select(Artifact))) == []
    assert list(await sg.scalars(select(Proposal))) == []
    # The one line the poster gets is a refusal notice, and it is written down as one.
    assert home.whatsapp.sent[-1].text == (
        "Nura does not send WhatsApp messages for Pa yet.\nPa can turn that on in the app."
    )
    trail = await read_audit(sg, context=home.owner)
    assert any(
        e.refused_because == "ConsentWithheld" and e.channel is Channel.WHATSAPP for e in trail
    )
    assert any(e.action is Action.SHARE and e.target == "refusal_notice" for e in trail)
    # And a send through the door is refused outright.
    async with refused_unit(sg, ConsentWithheld):
        await send(
            sg,
            context=home.owner,
            to_person=home.pa,
            kind="written_down",
            params={},
            provider=home.providers.whatsapp,
            number=home.number,
        )


async def test_a_template_goes_outside_the_window_and_free_text_inside_it(
    sg: AsyncSession, tmp_path: Path, clock: FrozenClock
) -> None:
    home = await family(sg, tmp_path)
    # Nobody has written yet: the morning card goes as a template.
    first = await run_morning(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    assert first.kind == "template" and first.template_name == "morning_card"
    assert home.whatsapp.sent[-1].kind == "template"
    assert home.whatsapp.sent[-1].template_name == "morning_card"
    assert home.whatsapp.sent[-1].params == {
        "name": "Pa",
        "day": "Thursday 3 September",
        "doses": "You have no tablets written down for today.",
    }
    # A reply outside the window cannot go as free text.
    async with refused_unit(sg, OutsideTheWindow):
        await send(
            sg,
            context=home.owner,
            to_person=home.pa,
            kind="written_down",
            params={},
            provider=home.providers.whatsapp,
            number=home.number,
        )
    # Pa writes; the window opens; the same card goes as text now.
    await home.inbound(sg, PA, "ok")
    second = await run_feeling_check_in(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    assert second.kind == "text" and second.template_name == "feeling_check_in"
    assert (
        second.text
        == "Hello Pa, this is Nura.\nHow are you feeling today?\nAnswer OK, tired or pain."
    )
    # Twenty-five hours on, the window has closed again.
    clock.step(timedelta(hours=25))
    third = await run_morning(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    assert third.kind == "template"


async def test_the_morning_card_says_what_his_feed_leads_with(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """The morning card is the thread's twin of the top of his feed: the now card (no
    tablets written down here), then today's cards under the feed's caps — a number he
    took this morning, said the way the feed card says it."""
    home = await family(sg, tmp_path)
    taken = await record_event(
        sg,
        context=home.owner,
        kind=EventKind.READING,
        occurred_at=utcnow(),
        label="blood pressure",
        source_channel=SourceChannel.APP,
    )
    await assert_fact(
        sg,
        context=home.owner,
        subject="blood_pressure",
        attribute="reading",
        value={"systolic": 138, "diastolic": 84},
        unit="mmHg",
        confidence=1.0,
        event_id=taken.id,
    )
    await run_morning(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    assert home.whatsapp.sent[-1].params["doses"].splitlines() == [
        "You have no tablets written down for today.",
        "Your blood pressure today was 138 over 84.",
        "It is in your blood pressure book.",
        "Mei can see it too.",
    ]


async def test_every_template_send_names_the_state_it_was_composed_from(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path)
    sent = await run_morning(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    row = await sg.get(WhatsAppMessage, sent.message_id)
    assert row is not None and row.direction is Direction.OUTBOUND
    assert row.kind is MessageKind.TEMPLATE and row.template_name == "morning_card"
    state = await current_state(sg, context=home.owner)
    assert row.state_id == state.id


# --- the trail -----------------------------------------------------------------------------------


async def test_every_inbound_and_outbound_is_on_the_trail(sg: AsyncSession, tmp_path: Path) -> None:
    home = await family(sg, tmp_path)
    heard = await home.inbound(sg, MEI, "BP 150/90 this morning")
    await home.inbound(sg, MEI, "yes")
    await run_morning(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        profile_id=home.profile.id,
    )
    trail = await read_audit(sg, context=home.owner, limit=500)
    on_whatsapp = [e for e in trail if e.channel is Channel.WHATSAPP]
    writes = {(e.action, e.target) for e in on_whatsapp if e.outcome is Outcome.ALLOWED}
    assert (Action.WRITE, "whatsapp_message") in writes
    assert (Action.WRITE, "whatsapp_proposal") in writes
    assert (Action.WRITE, "whatsapp_thread") in writes
    assert (Action.WRITE, "artifact") in writes
    assert (Action.WRITE, "confirmation") in writes
    # Every send is a SHARE line on the WhatsApp channel naming who it went to.
    shares = [e for e in on_whatsapp if e.action is Action.SHARE]
    assert len(shares) == 3  # the read-back, the thank-you, the morning card
    assert {e.shared_with_person_id for e in shares} == {home.mei.id, home.pa.id}
    assert all(e.scope is Scope.SEND and e.target == "whatsapp_message" for e in shares)
    assert heard.message_id in {e.target_id for e in on_whatsapp if e.target == "whatsapp_message"}


async def test_the_classifier_is_replaceable_and_the_thread_follows_it(
    sg: AsyncSession, tmp_path: Path
) -> None:
    """A model behind the same protocol: the thread does what the classification says."""

    class Model:
        def classify(self, *, text: str | None, content_type: str | None) -> Classification:
            if text and text.startswith("ignore"):
                return Classification(Kind.IGNORE)
            return Classification(Kind.COORDINATION, matched="model")

    home = await family(sg, tmp_path)
    handled = await handle_inbound(
        sg,
        settings=home.settings,
        providers=home.providers,
        number=home.number,
        classifier=Model(),
        message=DevInbound(from_e164=MEI, text="BP 150/90 this morning").as_message(utcnow()),
    )
    assert handled.outcome == "coordination" and handled.proposal_id is None


async def test_a_stewarded_profile_has_no_patient_to_send_the_morning_card_to(
    sg: AsyncSession, tmp_path: Path
) -> None:
    from app.channels.whatsapp.outbound.level0 import NoPatientYet

    home = await family(sg, tmp_path)
    with pytest.raises(NoPatientYet):
        await run_morning(
            sg,
            settings=home.settings,
            providers=home.providers,
            number=home.number,
            profile_id=home.mei.id,  # not a profile here
        )


async def test_whatsapp_consent_is_the_gate_for_the_thread_too(
    sg: AsyncSession, tmp_path: Path
) -> None:
    home = await family(sg, tmp_path, whatsapp_consent=False)
    await grant_consent(
        sg,
        context=home.owner,
        purpose=ConsentPurpose.WHATSAPP,
        captured_via=ConsentChannel.WHATSAPP,
        basis=ConsentBasis.OWNER,
        language="en",
    )
    handled = await home.inbound(sg, MEI, "BP 150/90 this morning")
    assert handled.outcome == "proposal"
