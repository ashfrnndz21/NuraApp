"""E18-02: the calendar, a read-only connector.

    Acceptance: candidates suggested, never auto-added.

The calendar is read through a port with no way to write. Events that name a provider in his
directory or carry a health word become proposals — never appointments — and everything
else is dropped in memory and written nowhere. A proposal becomes a PLANNED visit only on a
person's yes for exactly it; a no books nothing. No other person's name is kept.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.consent.models import ConsentChannel
from app.consent.service import ConsentWithheld, RecordConsent
from app.ingestion.connectors.calendar import (
    CalendarEvent,
    CalendarSource,
    FixtureCalendar,
    IcsFileCalendar,
    NotACalendar,
    parse_ics,
)
from app.ingestion.connectors.models import (
    AppointmentProposal,
    ConnectorSource,
    MatchedBy,
    ProposalStatus,
)
from app.ingestion.connectors.service import (
    AlreadyDecided,
    NotTheirsToConnect,
    NotTheirsToDecide,
    accept_proposal,
    connect_calendar,
    dismiss_proposal,
    match_event,
    proposal_draft_for,
    proposal_lines,
    scan,
)
from app.keys.confirm import NotAConfirmerHere, confirm
from app.keys.scopes import KeyRole, Scope
from app.memory.models import Appointment, AppointmentStatus, ProviderKind
from app.memory.spine import add_provider
from app.regions import Region
from tests.medicines_support import let_in, pa
from tests.trio_support import every_value, refusals

ICS = Path(__file__).resolve().parent / "fixtures" / "calendar" / "three-events.ics"
SG = ZoneInfo("Asia/Singapore")
CALENDAR_CONSENT = RecordConsent(text_version="1", language="en", captured_via=ConsentChannel.APP)


def _file() -> IcsFileCalendar:
    return IcsFileCalendar(ICS.read_bytes(), zone=SG)


# --- the reader --------------------------------------------------------------------------


def test_the_file_is_read_for_events_and_never_for_people() -> None:
    events = parse_ics(ICS.read_bytes(), zone=SG)
    assert [e.summary for e in events] == ["Dr Tan follow-up", "Dialysis SGH", "Lunch with Ah Kow"]
    visit = events[0]
    assert visit.starts_at == datetime(2026, 9, 24, 2, 0, tzinfo=UTC)  # 10 in the morning, SGT
    assert visit.location == "Tan Family Clinic, Bishan"  # unescaped
    assert visit.uid == "dr-tan-2026-09-24@nura.test"
    assert events[1].starts_at == datetime(2026, 9, 18, 2, 0, tzinfo=UTC)
    # Nothing but summary, start, place, UID and status: no attendee, organiser, description
    # or alarm reaches an event, so no other person's name can be kept downstream.
    assert set(CalendarEvent.__dataclass_fields__) == {
        "uid",
        "summary",
        "starts_at",
        "all_day",
        "location",
        "cancelled",
    }
    flat = repr(events)
    for name in ("Mei Lim", "Kit Lim", "ahkow@example.com", "mei@example.com", "knee", "refill"):
        assert name not in flat


def test_an_all_day_event_a_cancelled_one_and_a_file_that_is_not_a_calendar() -> None:
    data = (
        b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Eye doctor\r\nDTSTART;VALUE=DATE:20261001\r\n"
        b"END:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:Clinic\r\nSTATUS:CANCELLED\r\n"
        b"DTSTART:20261002T010000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    day, cancelled = parse_ics(data, zone=SG)
    assert day.all_day and day.starts_at == datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
    assert cancelled.cancelled
    with pytest.raises(NotACalendar):
        parse_ics(b"not a calendar", zone=SG)
    with pytest.raises(NotACalendar):
        parse_ics(b"BEGIN:VCALENDAR\r\n" + b"X" * 300_000, zone=SG)


def test_the_port_reads_and_has_no_way_to_write() -> None:
    public = {name for name in dir(CalendarSource) if not name.startswith("_")}
    assert public == {"events"}
    for reader in (FixtureCalendar, IcsFileCalendar):
        assert {name for name in dir(reader) if not name.startswith("_")} == {"events"}


def test_what_looks_like_a_visit() -> None:
    at = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)
    lunch = match_event(CalendarEvent(None, "Lunch with Ah Kow", at), [])
    assert lunch is None
    doctor = match_event(CalendarEvent(None, "Dr Tan follow-up", at), [])
    assert doctor is not None and (doctor.provider_name, doctor.provider_kind) == (
        "Dr Tan",
        ProviderKind.DOCTOR,
    )
    hospital = match_event(
        CalendarEvent(None, "Dialysis SGH", at, location="Singapore General Hospital"), []
    )
    assert hospital is not None and hospital.provider_kind is ProviderKind.HOSPITAL
    assert hospital.provider_name == "Singapore General Hospital"
    assert match_event(CalendarEvent(None, "复诊", at), []) is not None
    assert match_event(CalendarEvent(None, "Temujanji di klinik", at), []) is not None
    # A word that merely contains a keyword is not one: "drive" is not "dr".
    assert match_event(CalendarEvent(None, "Drive Ah Kow home", at), []) is None


# --- the connector -----------------------------------------------------------------------


async def test_connecting_rests_on_the_calendar_consent(sg: AsyncSession) -> None:
    owner = await pa(sg)
    with pytest.raises(ConsentWithheld):
        await connect_calendar(sg, context=owner, source=ConnectorSource.ICS_FILE)
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.ICS_FILE, consent=CALENDAR_CONSENT
    )
    assert connector.consent_id is not None and connector.connected_by_person_id == owner.person_id
    mei = await let_in(
        sg, owner, phone="+6591110002", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.VISITS}
    )
    with pytest.raises(NotTheirsToConnect):
        await connect_calendar(sg, context=mei, source=ConnectorSource.ICS_FILE)
    assert await refusals(sg, owner, "NotTheirsToConnect")


async def test_three_events_two_proposals_and_the_lunch_is_stored_nowhere(sg: AsyncSession) -> None:
    owner = await pa(sg)
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.ICS_FILE, consent=CALENDAR_CONSENT
    )
    mei = await let_in(
        sg, owner, phone="+6591110002", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.VISITS}
    )
    done = await scan(sg, context=mei, connector_id=connector.id, calendar=_file())
    assert (done.read, done.dropped, done.already) == (3, 1, 0)
    assert sorted(p.title for p in done.proposed) == ["Dialysis SGH", "Dr Tan follow-up"]
    assert all(p.status is ProposalStatus.PROPOSED for p in done.proposed)
    assert {p.matched_by for p in done.proposed} == {MatchedBy.KEYWORD}
    # Candidates, never visits: nothing is on the spine.
    assert (await sg.scalars(select(Appointment))).all() == []
    # Not the lunch, not the friend, not anyone in any event: in no column of any table.
    kept = " ".join(str(value) for value in await every_value(sg))
    for word in ("Ah Kow", "Lunch", "Maxwell", "Mei Lim", "Kit Lim", "example.com", "knee"):
        assert word not in kept, word
    # A second scan of the same file proposes nothing new.
    again = await scan(sg, context=mei, connector_id=connector.id, calendar=_file())
    assert (again.proposed, again.already) == ((), 2)


async def test_a_provider_in_his_directory_is_matched_by_name(sg: AsyncSession) -> None:
    owner = await pa(sg)
    tan = await add_provider(
        sg, context=owner, name="Tan Family Clinic", kind=ProviderKind.CLINIC, region=Region.SG
    )
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.ICS_FILE, consent=CALENDAR_CONSENT
    )
    done = await scan(sg, context=owner, connector_id=connector.id, calendar=_file())
    by_title = {p.title: p for p in done.proposed}
    assert by_title["Dr Tan follow-up"].matched_by is MatchedBy.PROVIDER
    assert by_title["Dr Tan follow-up"].provider_id == tan.id


async def test_his_yes_books_a_planned_visit_and_a_no_books_nothing(sg: AsyncSession) -> None:
    owner = await pa(sg)
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.ICS_FILE, consent=CALENDAR_CONSENT
    )
    done = await scan(sg, context=owner, connector_id=connector.id, calendar=_file())
    by_title = {p.title: p for p in done.proposed}
    visit, dialysis = by_title["Dr Tan follow-up"], by_title["Dialysis SGH"]

    dismissed = await dismiss_proposal(sg, context=owner, proposal_id=dialysis.id)
    assert dismissed.status is ProposalStatus.DISMISSED and dismissed.appointment_id is None
    with pytest.raises(AlreadyDecided):
        await proposal_draft_for(sg, context=owner, proposal_id=dialysis.id)

    # A yes for the other proposal does not book this one.
    wrong = await confirm(
        sg, owner, await proposal_draft_for(sg, context=owner, proposal_id=visit.id)
    )
    with pytest.raises(AlreadyDecided):
        await accept_proposal(sg, context=owner, proposal_id=dialysis.id, confirmation_id=wrong.id)
    assert (await sg.scalars(select(Appointment))).all() == []

    accepted, appointment = await accept_proposal(
        sg, context=owner, proposal_id=visit.id, confirmation_id=wrong.id
    )
    assert appointment.status is AppointmentStatus.PLANNED
    assert appointment.confirmed_by_person_id == owner.person_id
    assert appointment.scheduled_at.replace(tzinfo=UTC) == datetime(2026, 9, 24, 2, 0, tzinfo=UTC)
    assert (accepted.status, accepted.appointment_id) == (ProposalStatus.ACCEPTED, appointment.id)
    assert (await sg.scalars(select(Appointment))).all() == [appointment]
    with pytest.raises(AlreadyDecided):
        await accept_proposal(sg, context=owner, proposal_id=visit.id, confirmation_id=wrong.id)


async def test_a_yes_must_be_the_persons_own_and_a_viewer_decides_nothing(sg: AsyncSession) -> None:
    owner = await pa(sg)
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.ICS_FILE, consent=CALENDAR_CONSENT
    )
    done = await scan(sg, context=owner, connector_id=connector.id, calendar=_file())
    proposal = done.proposed[0]
    mei = await let_in(
        sg, owner, phone="+6591110002", name="Mei", role=KeyRole.CAREGIVER, scopes={Scope.VISITS}
    )
    his_yes = await confirm(
        sg, owner, await proposal_draft_for(sg, context=owner, proposal_id=proposal.id)
    )
    with pytest.raises(NotAConfirmerHere):
        await accept_proposal(sg, context=mei, proposal_id=proposal.id, confirmation_id=his_yes.id)
    aunt = await let_in(
        sg, owner, phone="+6591110005", name="Aunt", role=KeyRole.VIEWER, scopes={Scope.VISITS}
    )
    with pytest.raises(NotTheirsToDecide):
        await dismiss_proposal(sg, context=aunt, proposal_id=proposal.id)
    assert await refusals(sg, owner, "NotTheirsToDecide")
    assert await refusals(sg, owner, "NotAConfirmerHere")
    rows = (await sg.scalars(select(AppointmentProposal))).all()
    assert all(row.status is ProposalStatus.PROPOSED for row in rows)


async def test_a_scan_needs_the_consent_in_force_and_a_bad_file_is_refused_on_the_trail(
    sg: AsyncSession,
) -> None:
    owner = await pa(sg)
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.ICS_FILE, consent=CALENDAR_CONSENT
    )
    with pytest.raises(NotACalendar):
        await scan(
            sg,
            context=owner,
            connector_id=connector.id,
            calendar=IcsFileCalendar(b"hello", zone=SG),
        )
    assert await refusals(sg, owner, "NotACalendar")


def test_his_words_for_a_proposal_name_the_doctor_or_say_your_doctor() -> None:
    at = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)
    row = AppointmentProposal(
        title="Dr Tan follow-up",
        starts_at=at,
        all_day=False,
        provider_name="Dr Tan",
        status=ProposalStatus.PROPOSED,
    )
    assert proposal_lines(row, zone=SG, language="en") == [
        "Nura found a visit to Dr Tan in the calendar.",
        "It is on Thursday 24 September at 10 in the morning.",
        "Tap Yes to add it to your visits.",
    ]
    initials = AppointmentProposal(
        title="Dialysis SGH",
        starts_at=at,
        all_day=False,
        provider_name="SGH",
        status=ProposalStatus.PROPOSED,
    )
    assert proposal_lines(initials, zone=SG, language="en")[0] == (
        "Nura found a visit to your doctor in the calendar."
    )
    assert (
        proposal_lines(row, zone=SG, language="ms")[1]
        == "Ia pada Khamis 24 September, pukul 10 pagi."
    )
    row.status = ProposalStatus.DISMISSED
    assert proposal_lines(row, zone=SG, language="en") == []


async def test_a_fixture_calendar_behind_the_same_port(sg: AsyncSession) -> None:
    owner = await pa(sg)
    connector = await connect_calendar(
        sg, context=owner, source=ConnectorSource.FIXTURE, consent=CALENDAR_CONSENT
    )
    past = CalendarEvent("old", "Dr Lim review", datetime(2026, 8, 1, tzinfo=UTC))
    soon = CalendarEvent("soon", "Klinik Kesihatan", datetime(2026, 9, 10, 1, 0, tzinfo=UTC))
    done = await scan(
        sg, context=owner, connector_id=connector.id, calendar=FixtureCalendar([past, soon])
    )
    # Events before now are not proposed.
    assert [p.title for p in done.proposed] == ["Klinik Kesihatan"]
    assert done.proposed[0].provider_kind is ProviderKind.CLINIC
