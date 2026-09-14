"""The consent record a person can hold: the PDPA export.

`export_consent_record` builds a structured document — every consent ever given on the
profile, with its words, its version, who gave it, how, on what basis, when, and when it
was withdrawn — and hands it to a renderer. The document carries no health content and
names people and the profile by display name, never by id; the only identifiers in it are
the consent rows' own ids, so a line in it can be pointed at if it is ever disputed.

Rendering sits behind `ConsentRenderer`. `PlainTextRenderer` is the one implementation
here: Markdown a person can read as it is, in plain words, because the patient is who
holds this page. A PDF renderer is a later adapter with the same one method; nothing above
it changes when it arrives. Whatever renders it receives the whole document, names included.

The `status` codes and raw enum values in the document are for the caregiver's app and the
PDF adapter to put words to; the plain words for the patient are the `*_words` fields and
the rendered page.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import record_share
from app.audit.models import Channel
from app.consent.models import Consent, ConsentBasis, ConsentChannel, ConsentPurpose
from app.consent.service import all_consents
from app.consent.texts import current_version, wording
from app.db import as_utc, utcnow
from app.identity.models import Person, Profile
from app.keys.context import KeyContext, NoKey
from app.keys.scopes import Scope
from app.regions import Region

EXPORT_TARGET = "consent_record"
"""What the trail calls the document that leaves."""

# @patient
PURPOSE_TITLES: Mapping[ConsentPurpose, str] = {
    ConsentPurpose.HOLD_HEALTH_RECORD: "Keeping your papers",
    ConsentPurpose.SHARE_WITH_FAMILY: "Sharing with your family",
    ConsentPurpose.RECORDING: "Recording your visits",
    ConsentPurpose.WHATSAPP: "Sending your Today page on WhatsApp",
}
# @patient
CHANNEL_WORDS: Mapping[ConsentChannel, str] = {
    ConsentChannel.APP: "in the app",
    ConsentChannel.WHATSAPP: "on WhatsApp",
    ConsentChannel.PAPER: "on paper",
    ConsentChannel.VERBAL_WITNESSED: "out loud",
}
REGION_NAMES: Mapping[Region, str] = {Region.SG: "Singapore", Region.MY: "Malaysia"}
LANGUAGE_NAMES: Mapping[str, str] = {"en": "English", "zh": "Chinese", "ms": "Malay", "ta": "Tamil"}


# @patient
def basis_words(basis: ConsentBasis, giver: str, patient: str) -> str | None:
    """The line that says why `giver` could agree for `patient`. None when he agreed himself."""
    match basis:
        case ConsentBasis.OWNER:
            return None
        case ConsentBasis.LPA:
            return (
                f"{giver} holds the paper that says {giver} may decide for {patient}. "
                "Lawyers call it a lasting power of attorney."
            )
        case ConsentBasis.MEDICAL_LETTER:
            return f"A doctor's letter says {giver} may decide for {patient}."
        case ConsentBasis.VERBAL_RECORDED:
            return f"{patient} said yes out loud, and Nura kept the recording."


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


def _stamp(moment: datetime) -> str:
    """The exact instant, for the structured half. The page says the day and the date."""
    return as_utc(moment).isoformat()


def _plain(moment: datetime) -> str:
    """The day and the date, as `docs/plain-words.md` asks: "Monday 14 September 2026"."""
    utc = as_utc(moment)
    return f"{utc:%A} {utc.day} {utc:%B %Y}"


def _status(consent: Consent, now: datetime) -> str:
    if not consent.is_active(now):
        return "withdrawn"
    if consent.text_version != current_version(consent.purpose):
        return "out_of_date"
    return "in_force"


class PlainTextRenderer:
    """Markdown, readable as plain text. The default until the PDF adapter arrives."""

    media_type = "text/markdown"

    # @patient
    def render(self, document: dict[str, Any]) -> bytes:
        patient = document["profile"]["name"]
        lines = [
            "# What you agreed to",
            "",
            f"This page shows what {patient} agreed to.",
            f"{patient}'s papers are kept in {document['profile']['region_name']}.",
            (
                f"Nura made this page for {document['prepared_for']} "
                f"on {document['prepared_at_plain']}."
            ),
            "",
        ]
        by_title: dict[str, list[dict[str, Any]]] = {}
        for entry in document["consents"]:
            by_title.setdefault(entry["title"], []).append(entry)
        if not by_title:
            lines.append(f"{patient} has not agreed to anything yet.")
        for title, entries in by_title.items():
            lines.append(f"## {title}")
            lines.append("")
            for entry in entries:
                giver = entry["given_by"]
                for_whom = "" if giver == patient else f" for {patient}"
                lines.append(
                    f"- {giver} agreed to this{for_whom} {entry['captured_via_words']} "
                    f"on {entry['given_at_plain']}."
                )
                if entry["basis_words"]:
                    lines.append(f"  {entry['basis_words']}")
                if entry["wording"]:
                    lines.append(
                        f"  These are the words {giver} read, in {entry['language_name']}:"
                    )
                    lines.append(f"  \"{entry['wording']}\"")
                else:
                    lines.append(f"  We do not have the exact words {giver} read that day.")
                if entry["status"] == "withdrawn":
                    who = entry["withdrawn_by"]
                    stopped = f"{who} stopped this" if who else "This was stopped"
                    lines.append(f"  {stopped} on {entry['withdrawn_at_plain']}.")
                elif entry["status"] == "out_of_date":
                    lines.append(f"  Nura has changed these words since {giver} agreed.")
                    lines.append(f"  Nura will ask {patient} to agree again.")
                else:
                    lines.append("  This is still on today.")
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

    Reading the consents goes through the family door like any other read; the document
    leaving is written down as a share, to the person who asked for it.
    """
    moment = now or utcnow()
    consents = await all_consents(session, context=context, now=moment)
    # The profile and person rows below are identity, not profile data: a name and a
    # region, read after the family door above has let this context through. The names
    # are the only thing in the document that is not on the consent rows themselves.
    profile = await session.get(Profile, context.profile_id)
    if profile is None:  # the context was resolved against it, so this is not reachable
        raise NoKey(person_id=context.person_id, profile_id=context.profile_id)

    names: dict[uuid.UUID, str] = {}

    async def name_of(person_id: uuid.UUID) -> str:
        if person_id not in names:
            person = await session.get(Person, person_id)
            names[person_id] = person.display_name if person is not None else "someone"
        return names[person_id]

    patient = profile.display_name
    entries: list[dict[str, Any]] = []
    for consent in consents:
        giver = await name_of(consent.person_id)
        entry: dict[str, Any] = {
            "id": str(consent.id),
            "purpose": consent.purpose.value,
            "title": PURPOSE_TITLES[consent.purpose],
            "version": consent.text_version,
            "wording": wording(
                consent.purpose, consent.text_version, consent.language, profile.region
            ),
            "language": consent.language,
            "language_name": LANGUAGE_NAMES.get(consent.language, consent.language),
            "captured_via": consent.captured_via.value,
            "captured_via_words": CHANNEL_WORDS[consent.captured_via],
            "basis": consent.basis.value,
            "basis_words": basis_words(consent.basis, giver, patient),
            "given_by": giver,
            "given_at": _stamp(consent.granted_at),
            "given_at_plain": _plain(consent.granted_at),
            "status": _status(consent, moment),
            "withdrawn_at": None,
            "withdrawn_at_plain": None,
            "withdrawn_by": None,
        }
        if consent.revoked_at is not None:
            entry["withdrawn_at"] = _stamp(consent.revoked_at)
            entry["withdrawn_at_plain"] = _plain(consent.revoked_at)
            if consent.revoked_by_person_id is not None:
                entry["withdrawn_by"] = await name_of(consent.revoked_by_person_id)
        entries.append(entry)

    document: dict[str, Any] = {
        "kind": EXPORT_TARGET,
        "profile": {
            "name": patient,
            "region": profile.region.value,
            "region_name": REGION_NAMES[profile.region],
        },
        "prepared_at": _stamp(moment),
        "prepared_at_plain": _plain(moment),
        "prepared_for": await name_of(context.person_id),
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
    return ConsentRecord(document=document, rendered=rendered)
