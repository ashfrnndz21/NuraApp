"""The consent record a person can hold: the PDPA export.

`export_consent_record` builds a structured document — every consent ever given on the
profile, with the words as they were read, who gave it, for whom, how, on what basis, when,
and when it was withdrawn — and hands it to a renderer. The document carries no health
content and names people and the profile by display name, never by id; the only
identifiers in it are the consent rows' own ids, so a line can be pointed at if disputed.
The words come from the row, never re-derived from the catalogue.

Rendering sits behind `ConsentRenderer`. `PlainTextRenderer` is the one implementation
here: Markdown a person can read as it is, in plain words, addressed to whoever it was
made for — "you" when that is the patient, his name when it is someone he let in. A PDF
renderer is a later adapter with the same one method; nothing above it changes when it
arrives. Whatever renders it receives the whole document, names included.

The `status` codes and raw enum values in the document are for the caregiver's app and the
PDF adapter to put words to; the plain words for the patient are the `*_words` fields and
the rendered page. Every read here goes through the doors: the consents under `FAMILY`,
the profile under `PROFILE`, the names under `FAMILY` and only for people the record names.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_profile_read, person_display_name, record_share
from app.audit.models import Channel
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import all_consents
from app.consent.texts import LANGUAGES, current_version, what_words
from app.db import as_utc, utcnow
from app.keys.context import KeyContext
from app.keys.scopes import Scope
from app.regions import REGION_TZ, Region

EXPORT_TARGET = "consent_record"
"""What the trail calls the document that leaves."""

# @patient
PURPOSE_TITLES: Mapping[ConsentPurpose, str] = {
    ConsentPurpose.HOLD_HEALTH_RECORD: "Keeping your papers",
    ConsentPurpose.SHARE_WITH_PERSON: "Who can see your papers",
    ConsentPurpose.RECORDING: "Recording when you see the doctor",
    ConsentPurpose.WHATSAPP: "Sending your Today page on WhatsApp",
}
# @patient
CHANNEL_WORDS: Mapping[ConsentChannel, str] = {
    ConsentChannel.APP: "in the app",
    ConsentChannel.WHATSAPP: "on WhatsApp",
    ConsentChannel.PAPER: "on paper",
    ConsentChannel.VERBAL_WITNESSED: "out loud",
}
# @patient
REGION_NAMES: Mapping[Region, str] = {Region.SG: "Singapore", Region.MY: "Malaysia"}

_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s*")


# @patient
def basis_lines(basis: ConsentBasis, giver: str, patient: str) -> list[str]:
    """The lines that say why `giver` could agree for `patient`. None when he agreed himself.

    `giver` and `patient` arrive already in the reader's voice ("you", or a name).
    """
    match basis:
        case ConsentBasis.OWNER:
            return []
        case ConsentBasis.LPA:
            return [
                f"{giver} holds the paper that says {giver} may decide for {patient}.",
                "Lawyers call that paper a lasting power of attorney.",
            ]
        case ConsentBasis.MEDICAL_LETTER:
            return [f"A doctor's letter says {giver} may decide for {patient}."]
        case ConsentBasis.VERBAL_RECORDED:
            return [
                f"{patient} said yes out loud.",
                f"{giver} wrote it down here.",
                f"Nura kept what {patient} said.",
            ]


@dataclass(frozen=True, slots=True)
class Rendered:
    media_type: str
    body: bytes


class ConsentRenderer(Protocol):
    """Turns the structured document into bytes of one media type."""

    @property
    def media_type(self) -> str: ...

    def render(self, document: dict[str, Any]) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ConsentRecord:
    document: dict[str, Any]
    rendered: Rendered
    region: Region
    """The region the record belongs to. The bytes do not leave it."""


def _stamp(moment: datetime) -> str:
    """The exact instant, in UTC, for the structured half. The page says his own day."""
    return as_utc(moment).isoformat()


# @patient
def _plain(moment: datetime, region: Region) -> str:
    """The day and the date on the patient's own clock: "Monday 14 September 2026"."""
    local = as_utc(moment).astimezone(REGION_TZ[region])
    return f"{local:%A} {local.day} {local:%B %Y}"


def _status(consent: Consent, now: datetime) -> str:
    if not consent.is_active(now):
        return "withdrawn"
    if consent.text_version != current_version(consent.purpose):
        return "out_of_date"
    return "in_force"


class _Voice:
    """How the page names each person: "you" for the reader, a name for everyone else."""

    def __init__(self, reader_is_patient: bool, patient: str) -> None:
        self.reader_is_patient = reader_is_patient
        self.patient = patient

    def who(self, name: str) -> str:
        return "you" if self.reader_is_patient and name == self.patient else name

    def whose(self, name: str) -> str:
        return "your" if self.reader_is_patient and name == self.patient else f"{name}'s"

    @staticmethod
    def cap(line: str) -> str:
        """Capitalise the first letter, past any bullet or indent: "- you" becomes "- You"."""
        for index, char in enumerate(line):
            if char.isalpha():
                return line[:index] + char.upper() + line[index + 1 :]
        return line


class PlainTextRenderer:
    """Markdown, readable as plain text. The default until the PDF adapter arrives."""

    media_type = "text/markdown"

    # @patient
    def render(self, document: dict[str, Any]) -> bytes:
        patient = document["profile"]["name"]
        voice = _Voice(document["prepared_for_patient"], patient)
        me, mine = voice.who(patient), voice.whose(patient)
        cap = voice.cap
        lines = [
            cap(f"# What {me} said yes to"),
            "",
            cap(f"{me} said yes to the things on this page."),
            cap(f"{mine} papers never leave {document['profile']['region_name']}."),
            (
                f"Nura made this page for {voice.who(document['prepared_for'])} "
                f"on {document['prepared_at_plain']}."
            ),
            "",
        ]
        by_title: dict[str, list[dict[str, Any]]] = {}
        for entry in document["consents"]:
            by_title.setdefault(entry["title"], []).append(entry)
        if not by_title:
            lines.append("There is nothing on this page yet.")
        for title, entries in by_title.items():
            lines.append(f"## {title}")
            lines.append("")
            for entry in entries:
                giver = voice.who(entry["given_by"])
                lines.append(
                    cap(
                        f"- {giver} said yes {entry['captured_via_words']} "
                        f"on {entry['given_at_plain']}."
                    )
                )
                if entry["holder"]:
                    holder = voice.who(entry["holder"])
                    can = "can no longer see" if entry["status"] == "withdrawn" else "can see"
                    lines.append(cap(f"  {holder} {can} {mine} {entry['what_words']}."))
                basis = ConsentBasis(entry["basis"])
                if basis not in (ConsentBasis.OWNER, ConsentBasis.VERBAL_RECORDED):
                    lines.append(cap(f"  {giver} said yes for {me}."))
                for line in basis_lines(basis, giver, me):
                    lines.append(f"  {cap(line)}")
                if entry["wording"]:
                    if entry["language_name"]:
                        lines.append(f"  These are the words {giver} read in {entry['language_name']}:")
                    else:
                        lines.append(f"  These are the words {giver} read:")
                    for sentence in _SENTENCE_END.split(entry["wording"]):
                        if sentence:
                            lines.append(f"  {sentence}")
                else:
                    lines.append(f"  Nura does not have the words {giver} read that day.")
                if entry["status"] == "withdrawn":
                    if entry["withdrawn_by"]:
                        who = voice.who(entry["withdrawn_by"])
                        lines.append(
                            cap(f"  {who} stopped this one on {entry['withdrawn_at_plain']}.")
                        )
                    else:
                        lines.append(f"  This one stopped on {entry['withdrawn_at_plain']}.")
                        lines.append("  Nura does not have who stopped it.")
                elif entry["status"] == "out_of_date":
                    lines.append(f"  Nura has changed these words since {giver} said yes.")
                    lines.append(cap(f"  Nura will ask {me} to say yes again."))
                else:
                    lines.append("  This one is still on.")
            lines.append("")
        return "\n".join(lines).encode()


async def export_consent_record(
    session: AsyncSession,
    *,
    context: KeyContext,
    renderer: ConsentRenderer | None = None,
    now: datetime | None = None,
) -> ConsentRecord:
    """Every consent ever given on this profile, as a document the person can keep.

    Reading the consents goes through the family door like any other read, the profile
    through the profile door and every name through the family door; the document leaving
    is written down as a share, to the person who asked for it. Every person named on the
    page is named by a consent row, so no name can refuse the page.
    """
    moment = now or utcnow()
    consents = await all_consents(session, context=context, now=moment)
    profile = await audited_profile_read(session, context, now=moment)
    region = profile.region

    names: dict[uuid.UUID, str] = {}

    async def name_of(person_id: uuid.UUID) -> str:
        if person_id not in names:
            names[person_id] = await person_display_name(session, context, person_id, now=moment)
        return names[person_id]

    patient = profile.display_name
    entries: list[dict[str, Any]] = []
    for consent in consents:
        giver = await name_of(consent.person_id)
        scopes = [Scope(name) for name in consent.scopes] if consent.scopes is not None else None
        entry: dict[str, Any] = {
            "id": str(consent.id),
            "purpose": consent.purpose.value,
            "title": PURPOSE_TITLES[consent.purpose],
            "holder": (
                await name_of(consent.holder_person_id)
                if consent.holder_person_id is not None
                else None
            ),
            "scopes": sorted(scope.value for scope in scopes) if scopes is not None else None,
            "what_words": what_words(scopes, "en") if scopes is not None else what_words((), "en"),
            "version": consent.text_version,
            "wording": consent.wording_text,
            "language": consent.language,
            "language_name": LANGUAGES.get(consent.language),
            "captured_via": consent.captured_via.value,
            "captured_via_words": CHANNEL_WORDS[consent.captured_via],
            "basis": consent.basis.value,
            "given_by": giver,
            "given_at": _stamp(consent.granted_at),
            "given_at_plain": _plain(consent.granted_at, region),
            "status": _status(consent, moment),
            "withdrawn_at": None,
            "withdrawn_at_plain": None,
            "withdrawn_by": None,
        }
        if consent.revoked_at is not None:
            entry["withdrawn_at"] = _stamp(consent.revoked_at)
            entry["withdrawn_at_plain"] = _plain(consent.revoked_at, region)
            if consent.revoked_by_person_id is not None:
                entry["withdrawn_by"] = await name_of(consent.revoked_by_person_id)
        entries.append(entry)

    document: dict[str, Any] = {
        "kind": EXPORT_TARGET,
        "profile": {
            "name": patient,
            "region": region.value,
            "region_name": REGION_NAMES[region],
        },
        "prepared_at": _stamp(moment),
        "prepared_at_plain": _plain(moment, region),
        "prepared_for": await name_of(context.person_id),
        # Decided by who asked, never by comparing names: the owner reads "you".
        "prepared_for_patient": context.person_id == profile.owner_person_id,
        "consents": entries,
    }
    chosen: ConsentRenderer = renderer or PlainTextRenderer()
    rendered = Rendered(media_type=chosen.media_type, body=chosen.render(document))

    await record_share(
        session,
        context=context,
        scope=Scope.FAMILY,
        target=EXPORT_TARGET,
        channel=Channel.APP,
        shared_with_person_id=context.person_id,
        now=moment,
    )
    return ConsentRecord(document=document, rendered=rendered, region=region)
