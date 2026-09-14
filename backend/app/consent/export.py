"""The consent record a person can hold: the PDPA export.

`export_consent_record` builds a structured document — every consent ever given on the
profile, with its words, its version, who gave it, how, on what basis, when, and when it
was withdrawn — and hands it to a renderer. The document carries no health content and
names people and the profile by display name, never by id; the only identifiers in it are
the consent rows' own ids, so a line in it can be pointed at if it is ever disputed.

Rendering sits behind `ConsentRenderer`. `PlainTextRenderer` is the one implementation
here, producing Markdown a person can read as it is. A PDF renderer is a later adapter
with the same one method; nothing above it changes when it arrives. Whatever renders it
receives the whole document, names included.
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

PURPOSE_TITLES: Mapping[ConsentPurpose, str] = {
    ConsentPurpose.HOLD_HEALTH_RECORD: "Keeping your papers",
    ConsentPurpose.SHARE_WITH_FAMILY: "Sharing with your family",
    ConsentPurpose.RECORDING: "Recording your visits",
    ConsentPurpose.WHATSAPP: "WhatsApp",
}
CHANNEL_WORDS: Mapping[ConsentChannel, str] = {
    ConsentChannel.APP: "in the app",
    ConsentChannel.WHATSAPP: "on WhatsApp",
    ConsentChannel.PAPER: "on paper",
    ConsentChannel.VERBAL_WITNESSED: "out loud, with a witness",
}
BASIS_WORDS: Mapping[ConsentBasis, str] = {
    ConsentBasis.OWNER: "on their own behalf",
    ConsentBasis.LPA: "with a lasting power of attorney",
    ConsentBasis.MEDICAL_LETTER: "with a doctor's letter",
    ConsentBasis.VERBAL_RECORDED: "on a recorded spoken agreement",
}
REGION_NAMES: Mapping[Region, str] = {Region.SG: "Singapore", Region.MY: "Malaysia"}
LANGUAGE_NAMES: Mapping[str, str] = {"en": "English", "zh": "Chinese", "ms": "Malay", "ta": "Tamil"}


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
    return as_utc(moment).isoformat()


def _plain(moment: datetime) -> str:
    """The day and the date, as `docs/plain-words.md` asks; the clock time kept for the record."""
    utc = as_utc(moment)
    return f"{utc:%A} {utc.day} {utc:%B %Y} at {utc:%H:%M} UTC"


def _status(consent: Consent, now: datetime) -> str:
    if not consent.is_active(now):
        return "withdrawn"
    if consent.text_version != current_version(consent.purpose):
        return "out_of_date"
    return "in_force"


class PlainTextRenderer:
    """Markdown, readable as plain text. The default until the PDF adapter arrives."""

    media_type = "text/markdown"

    def render(self, document: dict[str, Any]) -> bytes:
        profile = document["profile"]
        lines = [
            "# Consent record",
            "",
            f"This record is for {profile['name']}. It is kept in {profile['region_name']}.",
            (
                f"Nura prepared it on {document['prepared_at_plain']} "
                f"for {document['prepared_for']}."
            ),
            "",
        ]
        by_purpose: dict[str, list[dict[str, Any]]] = {}
        for entry in document["consents"]:
            by_purpose.setdefault(entry["title"], []).append(entry)
        if not by_purpose:
            lines.append("Nothing has been agreed to on this record yet.")
        for title, entries in by_purpose.items():
            lines.append(f"## {title}")
            lines.append("")
            for entry in entries:
                lines.append(
                    f"- {entry['given_by']} agreed {entry['basis_words']}, "
                    f"{entry['captured_via_words']}, on {entry['given_at_plain']}."
                )
                words = entry["wording"] or "not on file"
                lines.append(
                    f"  The words (version {entry['version']}, in {entry['language_name']}): "
                    f"\"{words}\""
                )
                if entry["status"] == "withdrawn":
                    who = entry["withdrawn_by"] or "someone"
                    lines.append(f"  {who} withdrew this on {entry['withdrawn_at_plain']}.")
                elif entry["status"] == "out_of_date":
                    lines.append("  These words have since changed.")
                    lines.append(f"  Nura will ask {profile['name']} to agree again.")
                else:
                    lines.append("  This is still in force.")
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
    profile = await session.get(Profile, context.profile_id)
    if profile is None:  # the context was resolved against it, so this is not reachable
        raise NoKey(person_id=context.person_id, profile_id=context.profile_id)

    names: dict[uuid.UUID, str] = {}

    async def name_of(person_id: uuid.UUID) -> str:
        if person_id not in names:
            person = await session.get(Person, person_id)
            names[person_id] = person.display_name if person is not None else "someone"
        return names[person_id]

    entries: list[dict[str, Any]] = []
    for consent in consents:
        entry: dict[str, Any] = {
            "id": str(consent.id),
            "purpose": consent.purpose.value,
            "title": PURPOSE_TITLES[consent.purpose],
            "version": consent.text_version,
            "wording": wording(consent.purpose, consent.text_version, consent.language),
            "language": consent.language,
            "language_name": LANGUAGE_NAMES.get(consent.language, consent.language),
            "captured_via": consent.captured_via.value,
            "captured_via_words": CHANNEL_WORDS[consent.captured_via],
            "basis": consent.basis.value,
            "basis_words": BASIS_WORDS[consent.basis],
            "given_by": await name_of(consent.person_id),
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
            "name": profile.display_name,
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
