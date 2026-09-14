"""What changed since you last looked (E03-04): the chief's home screen.

A look is the reader's own act and a row of its own (`LastLooked`): who, when, and the spine
as it stood — each visit's id and status, nothing of what the visits were — so the next look
can tell a visit whose status moved from one that did not (a status change leaves no moment
of its own on the visit). `what_changed` counts from the reader's last look, or from the
beginning on a first look, and says what is new, part by part, each under its own scope and
withheld by name where the key does not reach:

- the visits: booked since, and moved since — confirmed, happened, did not happen, cancelled;
- the medicines: a line added, or a new pack that says a different amount — told as a
  question for the doctor and never as the amount (E04) — and a new interaction question;
- the facts, by State dimension: new ones, and corrections old → new with the provenance of
  both;
- the papers: new photos and papers, new episodes, papers put with a visit or an illness;
- the things we do not wait for, raised since;
- the family: keys cut and closed, agreements given and withdrawn, and the chief's notes
  about a place (only for the owner and his chief).

Beside the changes, what is still waiting — cards waiting for a yes, today's tablets not
taken yet — said at every look, because it is a to-do and not a change. Every line is a
whole sentence from `app.delivery.timeline_strings`, with the day said in full, and passes the
plain-words verifier before it leaves; each carries the ids it is about, and the structured
payload beside it says the same by part.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited, audited_read, audited_write, person_display_name
from app.audit.models import Action
from app.consent.models import Consent
from app.db import as_utc, utcnow
from app.delivery import timeline_strings as words
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.ingestion.models import ReviewCard, ReviewField
from app.keys.context import KeyContext
from app.keys.models import Key
from app.keys.scopes import Scope
from app.medicines.models import ChangeKind, InteractionFlag, MedicationLine
from app.medicines.service import today
from app.medicines.strings import PLAIN_NAME
from app.memory.episodic import fact_cites_only_what_is_held_here, held_here
from app.memory.models import (
    Appointment,
    AppointmentStatus,
    Artifact,
    ArtifactKind,
    Attachment,
    ConfidenceState,
    Episode,
    Fact,
    LastLooked,
    Provider,
    ProviderNote,
)
from app.memory.providers import is_chief
from app.memory.semantic import fact_is_under
from app.memory.timeline import FACT_SCOPES, language_for
from app.safety.red_flags import Flag
from app.state.dimensions import dimension_of

LOOK_TARGET = LastLooked.__tablename__

SECTIONS = ("visits", "medicines", "facts", "papers", "flags", "family")
"""The parts of what changed, in the order they are said."""

MEDICATION = "medication"
"""The fact a medicine line is the typed view of: told as the line, not twice."""


@dataclass(frozen=True, slots=True)
class ChangeLine:
    """One line of what changed, in his words, and the ids it is about."""

    section: str
    key: str
    text: str
    refs: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class Changes:
    language: str
    since: datetime | None
    first_look: bool
    lines: tuple[ChangeLine, ...]
    waiting: tuple[ChangeLine, ...]
    sections: Mapping[str, Any]
    withheld: tuple[Scope, ...]
    dropped: int
    """Lines that did not pass the plain-words verifier and were not said. Zero, always, for
    the templates here; counted so a name that breaks a line is seen, not hidden."""


def _ids(*values: uuid.UUID | None) -> tuple[str, ...]:
    return tuple(str(value) for value in values if value is not None)


@dataclass
class _Said:
    language: str
    context: KeyContext
    lines: dict[str, list[ChangeLine]] = field(default_factory=lambda: {s: [] for s in SECTIONS})
    waiting: list[ChangeLine] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
    withheld: list[Scope] = field(default_factory=list)
    dropped: int = 0

    def day(self, moment: datetime) -> str:
        return words.said_date(moment, self.context.region, self.language)

    def _keep(self, line: ChangeLine, into: list[ChangeLine]) -> None:
        if words.verified(line.text, self.language):
            into.append(line)
        else:
            self.dropped += 1

    def say(
        self, section: str, key: str, refs: Mapping[str, tuple[str, ...]], **slots: str
    ) -> None:
        text = words.changed_line(key, self.language, **slots)
        self._keep(ChangeLine(section, key, text, dict(refs)), self.lines[section])

    def still(self, key: str, refs: Mapping[str, tuple[str, ...]], **slots: str) -> None:
        text = words.waiting_line(key, self.language, **slots)
        self._keep(ChangeLine("waiting", key, text, dict(refs)), self.waiting)

    def withhold(self, scope: Scope) -> None:
        if scope not in self.withheld:
            self.withheld.append(scope)


@audited(Action.READ, Scope.PROFILE, LOOK_TARGET)
async def last_look(session: AsyncSession, *, context: KeyContext) -> LastLooked | None:
    """The reader's own last look at this profile, or None before the first."""
    found = await audited_read(
        session,
        LastLooked,
        context,
        Scope.PROFILE,
        where=(LastLooked.person_id == context.person_id,),
        order_by=(LastLooked.looked_at.desc(),),
        limit=1,
    )
    return found[0] if found else None


@audited(Action.WRITE, Scope.PROFILE, LOOK_TARGET)
async def mark_looked(session: AsyncSession, *, context: KeyContext) -> LastLooked:
    """Write down that the reader looked, now, and the spine as it stood — ids and statuses
    only, and only as far as the key reaches the visits."""
    seen: dict[str, str] = {}
    if context.allows(Scope.VISITS):
        visits = await audited_read(session, Appointment, context, Scope.VISITS)
        seen = {str(visit.id): visit.status.value for visit in visits}
    return await audited_write(
        session,
        LastLooked,
        context,
        Scope.PROFILE,
        person_id=context.person_id,
        looked_at=utcnow(),
        appointments=seen,
    )


def _name(registry: DrugRegistry | None, generic: str, language: str) -> str:
    """His name for a medicine, from the licensed monograph; "medicine" when there is none."""
    if registry is not None:
        try:
            return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]
        except (UnknownDrug, KeyError):
            pass
    return words.what_word(MEDICATION, language)


async def _visits(
    session: AsyncSession,
    said: _Said,
    newer: Callable[[Any], tuple[ColumnElement[bool], ...]],
    after: datetime | None,
    seen: Mapping[str, str] | None,
) -> dict[uuid.UUID, Provider]:
    context = said.context
    if not context.allows(Scope.VISITS):
        said.withhold(Scope.VISITS)
        return {}
    visits = await audited_read(session, Appointment, context, Scope.VISITS)
    providers = {p.id: p for p in await audited_read(session, Provider, context, Scope.VISITS)}
    moved: list[dict[str, Any]] = []
    for visit in sorted(visits, key=lambda v: as_utc(v.scheduled_at)):
        booked = after is None or as_utc(visit.booked_at) > after
        before = None if seen is None else seen.get(str(visit.id))
        status_moved = visit.status != AppointmentStatus.PLANNED and (
            (before is None and booked) or (before is not None and before != visit.status.value)
        )
        if not (booked or status_moved):
            continue
        provider = providers.get(visit.provider_id)
        doctor = "" if provider is None else provider.name
        refs = {"appointment_ids": _ids(visit.id), "provider_ids": _ids(visit.provider_id)}
        when = said.day(visit.scheduled_at)
        if booked:
            said.say("visits", "visit_booked", refs, doctor=doctor, date=when)
        if status_moved:
            said.say("visits", f"visit_{visit.status.value}", refs, doctor=doctor, date=when)
        moved.append(
            {
                "appointment_id": str(visit.id),
                "provider_id": str(visit.provider_id),
                "booked_since": booked,
                "status": visit.status.value,
                "was": before,
            }
        )
    said.sections["visits"] = moved
    return providers


async def _medicines(
    session: AsyncSession,
    said: _Said,
    newer: Callable[[Any], tuple[ColumnElement[bool], ...]],
    registry: DrugRegistry | None,
) -> None:
    context = said.context
    if not context.allows(Scope.MEDICINES):
        said.withhold(Scope.MEDICINES)
        return
    lines = await audited_read(
        session, MedicationLine, context, Scope.MEDICINES, where=newer(MedicationLine.asserted_at)
    )
    changed: list[dict[str, Any]] = []
    for line in sorted(lines, key=lambda each: as_utc(each.asserted_at)):
        name = _name(registry, line.generic, said.language)
        refs = {
            "medication_line_ids": _ids(line.id, line.supersedes_id),
            "fact_ids": _ids(line.fact_id),
            "artifact_ids": _ids(line.source_artifact_id),
            "event_ids": _ids(line.source_event_id),
        }
        if line.change_kind == ChangeKind.DOSE_CHANGE:
            said.say("medicines", "medicine_changed", refs, name=name)
            said.say("medicines", "medicine_ask", refs, doctor=line.prescriber or "")
        else:
            said.say(
                "medicines", "medicine_added", refs, name=name, date=said.day(line.asserted_at)
            )
        changed.append(
            {
                "line_id": str(line.id),
                "supersedes_id": None if line.supersedes_id is None else str(line.supersedes_id),
                "change_kind": line.change_kind.value,
                "fact_id": str(line.fact_id),
                "source_artifact_id": _ids(line.source_artifact_id)[0]
                if line.source_artifact_id
                else None,
            }
        )
    flags = await audited_read(
        session, InteractionFlag, context, Scope.MEDICINES, where=newer(InteractionFlag.flagged_at)
    )
    if flags:
        by_id = {line.id: line for line in lines}
        doctor = next(
            (
                by_id[f.line_id].prescriber
                for f in flags
                if f.line_id in by_id and by_id[f.line_id].prescriber
            ),
            None,
        )
        said.say(
            "medicines",
            "interaction",
            {"interaction_flag_ids": _ids(*(f.id for f in flags))},
            doctor=doctor or "",
        )
    said.sections["medicines"] = {
        "lines": changed,
        "interaction_flag_ids": [str(f.id) for f in flags],
    }
    if registry is not None:
        slots = await today(session, context=context, registry=registry, language=said.language)
        open_slots = [slot for slot in slots if not slot.taken]
        if open_slots:
            said.still(
                "one_not_taken" if len(open_slots) == 1 else "not_taken",
                {"medication_line_ids": _ids(*(slot.line.id for slot in open_slots))},
                count=str(len(open_slots)),
            )


def _provenance(fact: Fact) -> dict[str, str | None]:
    return {
        "fact_id": str(fact.id),
        "artifact_id": None if fact.artifact_id is None else str(fact.artifact_id),
        "event_id": None if fact.event_id is None else str(fact.event_id),
    }


async def _facts(
    session: AsyncSession,
    said: _Said,
    newer: Callable[[Any], tuple[ColumnElement[bool], ...]],
) -> None:
    context = said.context
    by_dimension: dict[str, dict[str, list[str]]] = {}
    corrected: list[dict[str, Any]] = []
    for scope in FACT_SCOPES:
        if not context.allows(scope):
            said.withhold(scope)
            continue
        rows = await audited_read(
            session,
            Fact,
            context,
            scope,
            where=(
                fact_is_under(scope),
                Fact.confidence_state != ConfidenceState.DISPUTED,
                fact_cites_only_what_is_held_here(context, scope),
                *newer(Fact.asserted_at),
            ),
        )
        replaced = [fact.supersedes_id for fact in rows if fact.supersedes_id is not None]
        olds: dict[uuid.UUID, Fact] = {}
        if replaced:
            found = await audited_read(
                session, Fact, context, scope, where=(Fact.id.in_(replaced), fact_is_under(scope))
            )
            olds = {old.id: old for old in found}
        new_groups: dict[tuple[str, str], list[Fact]] = {}
        fixed_groups: dict[tuple[str, str], list[tuple[Fact, Fact]]] = {}
        for fact in sorted(rows, key=lambda each: as_utc(each.asserted_at)):
            old = None if fact.supersedes_id is None else olds.get(fact.supersedes_id)
            if old is not None:
                corrected.append(
                    {
                        "subject": fact.subject,
                        "attribute": fact.attribute,
                        "old": _provenance(old),
                        "new": _provenance(fact),
                    }
                )
                if fact.subject != MEDICATION:
                    key = (fact.subject, said.day(old.valid_from))
                    fixed_groups.setdefault(key, []).append((old, fact))
                continue
            dimension = dimension_of(fact.subject).value
            by_dimension.setdefault(dimension, {}).setdefault(fact.subject, []).append(str(fact.id))
            if fact.subject != MEDICATION:
                new_groups.setdefault((fact.subject, said.day(fact.asserted_at)), []).append(fact)
        for (subject, day), facts in new_groups.items():
            refs = {
                "fact_ids": _ids(*(f.id for f in facts)),
                "artifact_ids": _ids(
                    *sorted({f.artifact_id for f in facts if f.artifact_id}, key=str)
                ),
                "event_ids": _ids(*sorted({f.event_id for f in facts if f.event_id}, key=str)),
            }
            said.say(
                "facts", "new_fact", refs, what=words.what_word(subject, said.language), date=day
            )
        for (subject, day), pairs in fixed_groups.items():
            refs = {"fact_ids": _ids(*(f.id for pair in pairs for f in pair))}
            said.say(
                "facts", "superseded", refs, what=words.what_word(subject, said.language), date=day
            )
    said.sections["facts"] = {"new_by_dimension": by_dimension, "corrected": corrected}


async def _papers(
    session: AsyncSession,
    said: _Said,
    newer: Callable[[Any], tuple[ColumnElement[bool], ...]],
) -> None:
    context = said.context
    if not context.allows(Scope.RECORDS):
        said.withhold(Scope.RECORDS)
        return
    arrived = await audited_read(
        session,
        Artifact,
        context,
        Scope.RECORDS,
        where=(
            held_here(context),
            # A question asked of Nura is kept as a message; it is the asker's, not a paper.
            Artifact.kind != ArtifactKind.MESSAGE,
            *newer(Artifact.stored_at),
        ),
    )
    by_day: dict[tuple[str, str], list[Artifact]] = {}
    for artifact in sorted(arrived, key=lambda a: as_utc(a.stored_at)):
        key = "new_photo" if artifact.kind == ArtifactKind.PHOTO else "new_paper"
        by_day.setdefault((key, said.day(artifact.stored_at)), []).append(artifact)
    for (key, day), artifacts in by_day.items():
        said.say("papers", key, {"artifact_ids": _ids(*(a.id for a in artifacts))}, date=day)
    episodes = await audited_read(
        session, Episode, context, Scope.RECORDS, where=newer(Episode.opened_at)
    )
    for episode in episodes:
        said.say(
            "papers",
            "episode_opened",
            {"episode_ids": _ids(episode.id)},
            date=said.day(episode.opened_at),
        )
    hung = await audited_read(
        session, Attachment, context, Scope.RECORDS, where=newer(Attachment.attached_at)
    )
    for each in hung:
        said.say(
            "papers",
            "attached",
            {
                "attachment_ids": _ids(each.id),
                "artifact_ids": _ids(each.artifact_id),
                "episode_ids": _ids(each.episode_id),
                "appointment_ids": _ids(each.appointment_id),
            },
        )
    said.sections["papers"] = {
        "artifact_ids": [str(a.id) for a in arrived],
        "episode_ids": [str(e.id) for e in episodes],
        "attachment_ids": [str(a.id) for a in hung],
    }
    # Waiting: a card with something on it to say yes to. A photo the reader found nothing
    # on makes an empty card; that is not waiting for anyone.
    cards = await audited_read(
        session, ReviewCard, context, Scope.RECORDS, where=(ReviewCard.confirmed_at.is_(None),)
    )
    if cards:
        fields = await audited_read(
            session,
            ReviewField,
            context,
            Scope.RECORDS,
            where=(ReviewField.card_id.in_([card.id for card in cards]),),
        )
        with_fields = {each.card_id for each in fields}
        open_cards = [card for card in cards if card.id in with_fields]
        refs = {"review_card_ids": _ids(*(card.id for card in open_cards))}
        if len(open_cards) == 1:
            said.still("one_card", refs)
        elif open_cards:
            said.still("cards", refs, count=str(len(open_cards)))


async def _flags(
    session: AsyncSession,
    said: _Said,
    newer: Callable[[Any], tuple[ColumnElement[bool], ...]],
) -> None:
    context = said.context
    if not context.allows(Scope.EMERGENCY):
        said.withhold(Scope.EMERGENCY)
        return
    raised = await audited_read(
        session, Flag, context, Scope.EMERGENCY, where=newer(Flag.raised_at)
    )
    for flag in sorted(raised, key=lambda f: as_utc(f.raised_at)):
        said.say(
            "flags",
            "red_flag",
            {"flag_ids": _ids(flag.id), "event_ids": _ids(flag.event_id)},
            date=said.day(flag.raised_at),
        )
    said.sections["flags"] = [
        {
            "flag_id": str(f.id),
            "event_id": str(f.event_id),
            "suppressed_because": f.suppressed_because,
        }
        for f in raised
    ]


async def _family(
    session: AsyncSession,
    said: _Said,
    newer: Callable[[Any], tuple[ColumnElement[bool], ...]],
    after: datetime | None,
    providers: Mapping[uuid.UUID, Provider],
) -> None:
    context = said.context
    if not context.allows(Scope.FAMILY):
        said.withhold(Scope.FAMILY)
        return

    def since(moment: datetime | None) -> bool:
        return moment is not None and (after is None or as_utc(moment) > after)

    names: dict[uuid.UUID, str] = {}

    async def name_of(person_id: uuid.UUID) -> str:
        if person_id not in names:
            names[person_id] = await person_display_name(session, context, person_id)
        return names[person_id]

    keys = await audited_read(session, Key, context, Scope.FAMILY)
    for key in sorted(keys, key=lambda k: as_utc(k.granted_at)):
        refs = {"key_ids": _ids(key.id)}
        if since(key.granted_at):
            who = await name_of(key.holder_person_id)
            said.say("family", "key_cut", refs, who=who, date=said.day(key.granted_at))
        if key.revoked_at is not None and since(key.revoked_at):
            who = await name_of(key.holder_person_id)
            said.say("family", "key_closed", refs, who=who, date=said.day(key.revoked_at))
    consents = await audited_read(session, Consent, context, Scope.FAMILY)
    for consent in sorted(consents, key=lambda c: as_utc(c.granted_at)):
        refs = {"consent_ids": _ids(consent.id)}
        if since(consent.granted_at):
            said.say("family", "consent_given", refs, date=said.day(consent.granted_at))
        if consent.revoked_at is not None and since(consent.revoked_at):
            said.say("family", "consent_withdrawn", refs, date=said.day(consent.revoked_at))
    notes: Sequence[ProviderNote] = ()
    if is_chief(context):
        notes = await audited_read(
            session, ProviderNote, context, Scope.FAMILY, where=newer(ProviderNote.written_at)
        )
        for note in sorted(notes, key=lambda n: as_utc(n.written_at)):
            provider = providers.get(note.provider_id)
            said.say(
                "family",
                "note_added",
                {"provider_note_ids": _ids(note.id), "provider_ids": _ids(note.provider_id)},
                who=await name_of(note.written_by_person_id),
                doctor="" if provider is None else provider.name,
                date=said.day(note.written_at),
            )
    said.sections["family"] = {
        "key_ids": [str(k.id) for k in keys if since(k.granted_at) or since(k.revoked_at)],
        "consent_ids": [str(c.id) for c in consents if since(c.granted_at) or since(c.revoked_at)],
        "provider_note_ids": [str(n.id) for n in notes],
    }


@audited(Action.READ, Scope.PROFILE, LOOK_TARGET)
async def what_changed(
    session: AsyncSession,
    *,
    context: KeyContext,
    since: datetime | None,
    seen: Mapping[str, str] | None = None,
    registry: DrugRegistry | None = None,
    language: str | None = None,
) -> Changes:
    """What changed on this profile after `since` (from the beginning when None), part by
    part as far as the key reaches, in his words with the ids beside each line.

    `seen` is the spine as the reader last saw it (`LastLooked.appointments`); with it a
    visit whose status moved is told apart from one that did not. Nothing is marked here:
    the surface marks the look (`mark_looked`) once the reader has it.
    """
    lang = await language_for(session, context, language)
    said = _Said(language=lang, context=context)
    after = None if since is None else as_utc(since)

    def newer(column: Any) -> tuple[ColumnElement[bool], ...]:
        return () if after is None else (column > after,)

    providers = await _visits(session, said, newer, after, seen)
    await _medicines(session, said, newer, registry)
    await _facts(session, said, newer)
    await _papers(session, said, newer)
    await _flags(session, said, newer)
    await _family(session, said, newer, after, providers)

    lines = [line for section in SECTIONS for line in said.lines[section]]
    if after is None:
        head = ChangeLine("look", "first_look", words.changed_line("first_look", lang), {})
        lines.insert(0, head)
    elif not lines:
        nothing = words.changed_line("nothing", lang, date=said.day(after))
        lines.append(ChangeLine("look", "nothing", nothing, {}))
    return Changes(
        language=lang,
        since=after,
        first_look=after is None,
        lines=tuple(lines),
        waiting=tuple(said.waiting),
        sections=said.sections,
        withheld=tuple(said.withheld),
        dropped=said.dropped,
    )


__all__ = [
    "ChangeLine",
    "Changes",
    "last_look",
    "mark_looked",
    "what_changed",
]
