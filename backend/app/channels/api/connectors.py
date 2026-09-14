"""The calendar connector over HTTP (E18-02). Read-only: nothing here writes to a calendar.

    POST /profiles/{id}/connectors/calendar            connect, on the calendar consent
    POST /profiles/{id}/connectors/{c}/scan            read an uploaded .ics; propose visits
    GET  /profiles/{id}/proposals?status=              the proposals, soonest first
    POST /profiles/{id}/proposals/{p}/accept           his yes → a PLANNED appointment
    POST /profiles/{id}/proposals/{p}/dismiss          a no; nothing is booked

The yes for a proposal is minted at `POST /profiles/{id}/confirmations` with subject
`appointment_proposal`. The .ics file comes with the scan, is read in memory, and is not kept;
an event that is not a visit is not written anywhere.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read
from app.channels.api.daily_schemas import (
    AcceptedOut,
    AcceptIn,
    ConnectIn,
    ConnectorOut,
    ProposalOut,
    ScanIn,
    ScanOut,
)
from app.channels.api.deps import Context, Db
from app.ingestion.connectors.calendar import IcsFileCalendar
from app.ingestion.connectors.models import AppointmentProposal, ProposalStatus
from app.ingestion.connectors.service import (
    accept_proposal,
    connect_calendar,
    dismiss_proposal,
    list_proposals,
    proposal_lines,
    scan,
    zone_of,
)
from app.keys.context import KeyContext

router = APIRouter(prefix="/profiles", tags=["connectors"])

Language = Query(default=None, min_length=2, max_length=16)


async def _out(
    session: AsyncSession,
    context: KeyContext,
    rows: list[AppointmentProposal],
    language: str | None,
) -> list[ProposalOut]:
    lang = language or (await audited_profile_read(session, context)).language
    zone = zone_of(context)
    return [ProposalOut.of(row, proposal_lines(row, zone=zone, language=lang)) for row in rows]


@router.post("/{profile_id}/connectors/calendar", status_code=status.HTTP_201_CREATED)
async def connect(body: ConnectIn, context: Context, session: Db) -> ConnectorOut:
    """Connect a calendar. Refused without the calendar consent in force
    (`ConsentWithheld`, 403); the owner may agree to it here with `consent`."""
    row = await connect_calendar(
        session,
        context=context,
        source=body.source,
        consent=None if body.consent is None else body.consent.as_record(),
    )
    return ConnectorOut.of(row)


@router.post("/{profile_id}/connectors/{connector_id}/scan")
async def scan_calendar(
    body: ScanIn,
    connector_id: uuid.UUID,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> ScanOut:
    """Read the uploaded calendar from now on and propose what looks like a visit."""
    done = await scan(
        session,
        context=context,
        connector_id=connector_id,
        calendar=IcsFileCalendar(body.data, zone=zone_of(context)),
    )
    return ScanOut(
        read=done.read,
        proposed=await _out(session, context, list(done.proposed), language),
        dropped=done.dropped,
        already=done.already,
    )


@router.get("/{profile_id}/proposals")
async def proposals(
    context: Context,
    session: Db,
    status: ProposalStatus | None = None,
    language: str | None = Language,
) -> list[ProposalOut]:
    rows = await list_proposals(session, context=context, status=status)
    return await _out(session, context, list(rows), language)


@router.post("/{profile_id}/proposals/{proposal_id}/accept")
async def accept(
    body: AcceptIn,
    proposal_id: uuid.UUID,
    context: Context,
    session: Db,
    language: str | None = Language,
) -> AcceptedOut:
    """His yes, minted for exactly this proposal: the visit is booked as PLANNED."""
    proposal, appointment = await accept_proposal(
        session, context=context, proposal_id=proposal_id, confirmation_id=body.confirmation_id
    )
    (shown,) = await _out(session, context, [proposal], language)
    return AcceptedOut.of(shown, appointment)


@router.post("/{profile_id}/proposals/{proposal_id}/dismiss")
async def dismiss(
    proposal_id: uuid.UUID, context: Context, session: Db, language: str | None = Language
) -> ProposalOut:
    proposal = await dismiss_proposal(session, context=context, proposal_id=proposal_id)
    (shown,) = await _out(session, context, [proposal], language)
    return shown
