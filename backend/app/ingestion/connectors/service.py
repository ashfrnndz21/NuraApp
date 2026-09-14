"""The calendar connector (E18-02): connect, scan, and a person's yes or no.

    Acceptance: candidates suggested, never auto-added.

`connect_calendar` records one connector on the profile, resting on the consent for the
calendar (`ConsentPurpose.CALENDAR`), which the owner may give in the same step. Connected by
the owner, the steward or a chief, in the owner's name (docs/read-only-connectors.md §2).

`scan` reads the calendar through the `CalendarSource` port — read-only; there is no call
that writes back — for events from now on. An event that names a provider in his directory,
or carries a word on the health list (`KEYWORDS`), becomes an `AppointmentProposal`; any
other event is dropped in memory and never written anywhere, not even as a count on a row.
A second scan does not propose the same event twice (a digest of its UID).

`accept_proposal` is the one path from a calendar to the spine: a person's yes, minted for
exactly this proposal as shown (`ProposalDraft`), and then — in the same unit of work, from
the same person — the provider found or added to his directory and a PLANNED appointment
booked on its own yes, the way the review card writes each fact. `dismiss_proposal` is a no;
it books nothing. Every refusal on the way is written to the trail by the doors.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write
from app.audit.models import Action
from app.audit.trail import record
from app.consent.models import ConsentBasis, ConsentPurpose
from app.consent.service import RecordConsent, grant_consent, require_consent
from app.db import as_utc, utcnow
from app.delivery import calendar_strings as words
from app.delivery.when_words import say_clock, say_day
from app.drafts import AppointmentDraft, ProposalDraft
from app.errors import Refusal
from app.ingestion.connectors.calendar import CalendarEvent, CalendarSource
from app.ingestion.connectors.models import (
    AppointmentProposal,
    Connector,
    ConnectorKind,
    ConnectorSource,
    MatchedBy,
    ProposalStatus,
)
from app.keys.confirm import confirm, consume_confirmation
from app.keys.context import KeyContext
from app.keys.scopes import KeyRole, Scope
from app.memory.models import LABEL_LENGTH, Appointment, Provider, ProviderKind
from app.memory.spine import add_provider, book_appointment, list_providers
from app.regions import REGION_TZ
from app.safety.boundary import language_of
from app.safety.plain_words import verify

CONNECTOR = Connector.__tablename__
PROPOSAL = AppointmentProposal.__tablename__

HORIZON = timedelta(days=366)
"""How far ahead a scan looks. Events before now are not proposed."""

CONNECTORS: frozenset[KeyRole] = frozenset({KeyRole.CHIEF})
"""Who may connect a calendar, beside the owner and the steward (§2: the owner or the chief)."""
DECIDERS: frozenset[KeyRole] = frozenset({KeyRole.CHIEF, KeyRole.CAREGIVER})
"""Who may scan and say yes or no to a proposal, beside the owner and the steward."""

HOSPITALS = ("sgh", "nuh", "ttsh", "kkh", "cgh", "ktph", "ntfgh", "skh", "hkl", "ummc", "ppum")
"""Hospitals families write by their initials, in Singapore and Malaysia."""

_LATIN_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("doctor", r"doctor|doktor|dr\.?"),
    ("clinic", r"clinic|klinik|polyclinic|poliklinik"),
    ("hospital", r"hospital|" + "|".join(HOSPITALS)),
    ("dialysis", r"dialysis|dialisis"),
    ("follow_up", r"follow[- ]?up|rawatan susulan"),
    ("check_up", r"check[- ]?up|pemeriksaan kesihatan|health screening"),
    ("specialist", r"specialist|pakar"),
    ("physio", r"physio(?:therapy)?|fisioterapi"),
    ("dentist", r"dentist|doktor gigi|dental"),
    ("scan", r"x[- ]?ray|mri|ct scan|ultrasound"),
    ("blood_test", r"blood test|ujian darah"),
    ("pharmacy", r"pharmacy|farmasi"),
    ("eye", r"eye doctor|ophthalm\w*"),
)
_CJK_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("doctor", "医生"),
    ("doctor", "看病"),
    ("clinic", "诊所"),
    ("hospital", "医院"),
    ("follow_up", "复诊"),
    ("dialysis", "洗肾"),
    ("check_up", "体检"),
    ("blood_test", "验血"),
    ("pharmacy", "药房"),
)
KEYWORDS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (code, re.compile(rf"(?<![\w-])(?:{pattern})(?![\w-])", re.IGNORECASE))
    for code, pattern in _LATIN_KEYWORDS
) + tuple((code, re.compile(re.escape(word))) for code, word in _CJK_KEYWORDS)
"""The health list: an event carrying one of these is a candidate visit. In the order they
are tried, so the code kept is the most specific the event carries."""

_DOCTOR_NAMED = re.compile(r"\b(?:Dr|Doctor|Doktor)\.?\s+([A-Z][\w'’-]+)")
_HOSPITAL_WORDS = re.compile(
    r"(?<![\w-])(?:hospital|" + "|".join(HOSPITALS) + r")(?![\w-])|医院", re.IGNORECASE
)
_CLINIC_WORDS = re.compile(r"(?<![\w-])(?:clinic|klinik|polyclinic|poliklinik)(?![\w-])|诊所", re.IGNORECASE)


class NoSuchConnector(Refusal):
    """No connector by that id on this profile."""


class NoSuchProposal(Refusal):
    """No proposal by that id on this profile."""


class AlreadyDecided(Refusal):
    """This proposal has had its yes or its no. A visit booked from it is on the spine now."""


class NotTheirsToConnect(Refusal):
    """A calendar is connected by the owner, the steward or a chief, in the owner's name."""


class NotTheirsToDecide(Refusal):
    """A key to read the visits is not a key to say yes or no to one."""


@dataclass(frozen=True, slots=True)
class Match:
    matched_by: MatchedBy
    keyword: str | None
    provider_id: uuid.UUID | None
    provider_name: str
    provider_kind: ProviderKind


@dataclass(frozen=True, slots=True)
class Scan:
    """What one scan did: how many events it read, the proposals it made, how many it
    dropped unread-for-good, and how many it had proposed before."""

    read: int
    proposed: tuple[AppointmentProposal, ...]
    dropped: int
    already: int


def _label(text: str | None) -> str | None:
    if text is None:
        return None
    one = " ".join(text.split())
    return one[:LABEL_LENGTH] or None


def _names_provider(provider: Provider, text: str) -> bool:
    name = provider.name.strip()
    if len(name) < 3:
        return False
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.IGNORECASE) is not None


def match_event(event: CalendarEvent, providers: Sequence[Provider]) -> Match | None:
    """Whether an event looks like a visit, and to whom. A provider in his directory first;
    then the health list. None for anything else — lunch with a friend is not a visit."""
    text = " ".join(part for part in (event.summary, event.location or "") if part)
    for provider in providers:
        if _names_provider(provider, text):
            return Match(MatchedBy.PROVIDER, None, provider.id, provider.name, provider.kind)
    keyword = next((code for code, pattern in KEYWORDS if pattern.search(text)), None)
    if keyword is None:
        return None
    named = _DOCTOR_NAMED.search(event.summary) or _DOCTOR_NAMED.search(event.location or "")
    location = _label(event.location)
    if named is not None:
        return Match(MatchedBy.KEYWORD, keyword, None, f"Dr {named.group(1)}", ProviderKind.DOCTOR)
    if _HOSPITAL_WORDS.search(text):
        found = _HOSPITAL_WORDS.search(text)
        name = location or (found.group(0).upper() if found else event.summary)
        return Match(MatchedBy.KEYWORD, keyword, None, name[:120], ProviderKind.HOSPITAL)
    if _CLINIC_WORDS.search(text):
        return Match(MatchedBy.KEYWORD, keyword, None, (location or event.summary)[:120], ProviderKind.CLINIC)
    return Match(MatchedBy.KEYWORD, keyword, None, (location or event.summary)[:120], ProviderKind.OTHER)


def event_digest(event: CalendarEvent) -> str:
    """The same event on a second scan: its UID, or its summary and start when it has none."""
    key = event.uid or f"{event.summary}|{event.starts_at.isoformat()}"
    return hashlib.sha256(key.encode()).hexdigest()


def may_connect(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role in CONNECTORS:
        return
    raise NotTheirsToConnect(f"a {context.role} key does not connect a calendar")


def may_decide(context: KeyContext) -> None:
    if context.is_owner or context.is_steward or context.role in DECIDERS:
        return
    raise NotTheirsToDecide(f"a {context.role} key reads the visits; it does not decide them")


@audited(Action.WRITE, Scope.VISITS, CONNECTOR)
async def connect_calendar(
    session: AsyncSession,
    *,
    context: KeyContext,
    source: ConnectorSource,
    consent: RecordConsent | None = None,
) -> Connector:
    """Connect a calendar to this profile. The consent for the calendar must be in force; the
    owner may agree to it here, in the words at `consent.text_version` in his language."""
    may_connect(context)
    if consent is not None:
        await grant_consent(
            session,
            context=context,
            purpose=ConsentPurpose.CALENDAR,
            captured_via=consent.captured_via,
            basis=ConsentBasis.OWNER,
            language=consent.language,
            text_version=consent.text_version,
        )
    agreed = await require_consent(
        session, context=context, purpose=ConsentPurpose.CALENDAR, scope=Scope.VISITS
    )
    return await audited_write(
        session,
        Connector,
        context,
        Scope.VISITS,
        kind=ConnectorKind.CALENDAR,
        source=source,
        consent_id=agreed.consent_id,
        connected_by_person_id=context.person_id,
        connected_at=utcnow(),
    )


async def _connector(session: AsyncSession, context: KeyContext, connector_id: uuid.UUID) -> Connector:
    found = await audited_read(
        session, Connector, context, Scope.VISITS, where=(Connector.id == connector_id,)
    )
    if not found:
        raise NoSuchConnector(f"no connector {connector_id} on profile {context.profile_id}")
    return found[0]


@audited(Action.WRITE, Scope.VISITS, PROPOSAL)
async def scan(
    session: AsyncSession,
    *,
    context: KeyContext,
    connector_id: uuid.UUID,
    calendar: CalendarSource,
) -> Scan:
    """Read the calendar from now on; keep only what looks like a visit, as proposals."""
    may_decide(context)
    connector = await _connector(session, context, connector_id)
    await require_consent(
        session, context=context, purpose=ConsentPurpose.CALENDAR, scope=Scope.VISITS
    )
    moment = utcnow()
    events = await calendar.events(since=moment, until=moment + HORIZON)
    providers = await list_providers(session, context=context)
    seen = {
        row.event_digest
        for row in await audited_read(
            session,
            AppointmentProposal,
            context,
            Scope.VISITS,
            where=(AppointmentProposal.connector_id == connector.id,),
        )
    }
    proposed: list[AppointmentProposal] = []
    dropped = already = 0
    for event in events:
        if event.cancelled:
            dropped += 1
            continue
        found = match_event(event, providers)
        if found is None:
            # Not a visit: nothing of it is written, anywhere.
            dropped += 1
            continue
        digest = event_digest(event)
        if digest in seen:
            already += 1
            continue
        seen.add(digest)
        proposed.append(
            await audited_write(
                session,
                AppointmentProposal,
                context,
                Scope.VISITS,
                connector_id=connector.id,
                event_digest=digest,
                title=_label(event.summary) or "",
                location=_label(event.location),
                starts_at=event.starts_at,
                all_day=event.all_day,
                matched_by=found.matched_by,
                keyword=found.keyword,
                provider_id=found.provider_id,
                provider_name=found.provider_name,
                provider_kind=found.provider_kind,
                status=ProposalStatus.PROPOSED,
                found_at=moment,
            )
        )
    return Scan(read=len(events), proposed=tuple(proposed), dropped=dropped, already=already)


@audited(Action.READ, Scope.VISITS, PROPOSAL)
async def list_proposals(
    session: AsyncSession, *, context: KeyContext, status: ProposalStatus | None = None
) -> Sequence[AppointmentProposal]:
    """The proposals on this profile, soonest first; `status` narrows."""
    where = [] if status is None else [AppointmentProposal.status == status]
    found = await audited_read(session, AppointmentProposal, context, Scope.VISITS, where=where)
    return sorted(found, key=lambda row: (as_utc(row.starts_at), str(row.id)))


async def _open(session: AsyncSession, context: KeyContext, proposal_id: uuid.UUID) -> AppointmentProposal:
    found = await audited_read(
        session,
        AppointmentProposal,
        context,
        Scope.VISITS,
        where=(AppointmentProposal.id == proposal_id,),
    )
    if not found:
        raise NoSuchProposal(f"no proposal {proposal_id} on profile {context.profile_id}")
    proposal = found[0]
    if proposal.status is not ProposalStatus.PROPOSED:
        raise AlreadyDecided(f"proposal {proposal_id} is {proposal.status}")
    return proposal


def draft_of(proposal: AppointmentProposal) -> ProposalDraft:
    return ProposalDraft(
        proposal_id=proposal.id,
        provider_name=proposal.provider_name,
        scheduled_at=as_utc(proposal.starts_at),
        purpose=proposal.title,
    )


@audited(Action.READ, Scope.VISITS, PROPOSAL)
async def proposal_draft_for(
    session: AsyncSession, *, context: KeyContext, proposal_id: uuid.UUID
) -> ProposalDraft:
    """What the person is saying yes to: this visit, with this provider, at this time."""
    may_decide(context)
    return draft_of(await _open(session, context, proposal_id))


async def _provider_for(
    session: AsyncSession, context: KeyContext, proposal: AppointmentProposal
) -> uuid.UUID:
    if proposal.provider_id is not None:
        return proposal.provider_id
    for provider in await list_providers(session, context=context):
        if provider.name.strip().lower() == proposal.provider_name.strip().lower():
            return provider.id
    added = await add_provider(
        session,
        context=context,
        name=proposal.provider_name,
        kind=proposal.provider_kind,
        region=context.region,
    )
    return added.id


@audited(Action.WRITE, Scope.VISITS, PROPOSAL)
async def accept_proposal(
    session: AsyncSession,
    *,
    context: KeyContext,
    proposal_id: uuid.UUID,
    confirmation_id: uuid.UUID,
) -> tuple[AppointmentProposal, Appointment]:
    """His yes: the visit goes on the spine as PLANNED, and the proposal names it."""
    may_decide(context)
    proposal = await _open(session, context, proposal_id)
    yes = await consume_confirmation(session, context, confirmation_id, draft_of(proposal))
    provider_id = await _provider_for(session, context, proposal)
    when = as_utc(proposal.starts_at)
    booking = AppointmentDraft(provider_id=provider_id, scheduled_at=when, purpose=proposal.title)
    # The proposal's yes is the evidence; the booking's own yes is how the spine records who
    # gave it — the same person, in the same unit of work (the review card's pattern).
    booked = await confirm(session, context, booking)
    appointment = await book_appointment(
        session,
        context=context,
        provider_id=provider_id,
        scheduled_at=when,
        purpose=proposal.title,
        confirmation_id=booked.id,
    )
    proposal.status = ProposalStatus.ACCEPTED
    proposal.decided_at = utcnow()
    proposal.decided_by_person_id = yes.person_id
    proposal.appointment_id = appointment.id
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.VISITS,
        target=PROPOSAL,
        target_id=proposal.id,
        rows=1,
    )
    return proposal, appointment


@audited(Action.WRITE, Scope.VISITS, PROPOSAL)
async def dismiss_proposal(
    session: AsyncSession, *, context: KeyContext, proposal_id: uuid.UUID
) -> AppointmentProposal:
    """A no: nothing is booked, and the proposal says who said no and when."""
    may_decide(context)
    proposal = await _open(session, context, proposal_id)
    proposal.status = ProposalStatus.DISMISSED
    proposal.decided_at = utcnow()
    proposal.decided_by_person_id = context.person_id
    await session.flush()
    await record(
        session,
        context=context,
        action=Action.WRITE,
        scope=Scope.VISITS,
        target=PROPOSAL,
        target_id=proposal.id,
        rows=1,
    )
    return proposal


def _passes(lines: Sequence[str], language: str) -> bool:
    return not any(
        finding.severity == "fail" for line in lines for finding in verify(line, language)
    )


def proposal_lines(proposal: AppointmentProposal, *, zone: ZoneInfo, language: str | None) -> list[str]:
    """What he reads about a proposal, in his language, verified. A name the calendar gave
    that is not a word he can read ("SGH") becomes "your doctor"; nothing unverified leaves.
    A dismissed proposal says nothing to him."""
    lang = language_of(language)
    if proposal.status is ProposalStatus.DISMISSED:
        return []
    local = as_utc(proposal.starts_at).astimezone(zone)
    this_year = utcnow().astimezone(zone).year
    day = say_day(local.date(), lang, with_year=local.year != this_year)
    when = (
        words.ON_DAY[lang].format(day=day)
        if proposal.all_day
        else words.ON_DAY_AT[lang].format(day=day, clock=say_clock(local.time(), lang))
    )
    closing = words.ADDED[lang] if proposal.status is ProposalStatus.ACCEPTED else words.SAY_YES[lang]
    for provider in (proposal.provider_name, words.THE_DOCTOR[lang]):
        lines = [words.FOUND[lang].format(provider=provider), when, closing]
        if _passes(lines, lang):
            return lines
    from app.family.common import NotPlainWords

    raise NotPlainWords([f"a proposal's lines do not pass plain words in {lang}"])


def zone_of(context: KeyContext) -> ZoneInfo:
    return REGION_TZ[context.region]
