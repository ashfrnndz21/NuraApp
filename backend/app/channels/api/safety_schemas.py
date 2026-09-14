"""The wire shapes of the safety routes (E13, E14): what comes in and what goes out.

Kept beside `schemas.py` rather than in it so the parallel epics do not collide on one file;
the conventions are the same. Nothing here carries a person's words: the answer to a voice
note or typed words is codes and verified lines, and the artefact id where the words are.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.ingestion.voice import MAX_VOICE_BYTES
from app.safety.emergency_card import Card
from app.safety.models import WhatToDoKind
from app.safety.not_feeling_well import OfflineCards, WhatToDoNow
from app.safety.symptom_log import Entry, Logged
from app.state.models import Posture


class SaidIn(BaseModel):
    """What he said: a voice note (base64 bytes and their content type) or typed words, one
    of the two. `language` asks for the card in another language than the profile's."""

    audio: str | None = Field(default=None, min_length=1, max_length=MAX_VOICE_BYTES * 4 // 3 + 4)
    content_type: str | None = Field(default=None, min_length=1, max_length=128)
    words: str | None = Field(default=None, min_length=1, max_length=2000)
    language: str | None = Field(default=None, min_length=2, max_length=16)

    @field_validator("audio")
    @classmethod
    def _base64(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as not_base64:
            raise ValueError("audio is base64") from not_base64
        return value

    @model_validator(mode="after")
    def _one_of_the_two(self) -> SaidIn:
        if (self.audio is None) == (self.words is None):
            raise ValueError("send a voice note or typed words, one of the two")
        if self.audio is not None and self.content_type is None:
            raise ValueError("a voice note names its content type")
        return self

    def audio_bytes(self) -> bytes | None:
        return None if self.audio is None else base64.b64decode(self.audio, validate=True)


class LineOut(BaseModel):
    id: str
    text: str


class MedicineOut(BaseModel):
    line_id: uuid.UUID
    generic: str
    brand: str | None
    strength: str
    form: str
    plain_name: str
    amount: str
    when: str
    high_risk: bool
    high_risk_class: str | None


class ContactOut(BaseModel):
    person_id: uuid.UUID
    name: str
    phone_e164: str | None
    role: str


class ClinicOut(BaseModel):
    provider_id: uuid.UUID
    name: str
    kind: str
    phone_e164: str | None


class InsurerOut(BaseModel):
    """His insurer: the name, said in a line of the card, and the policy reference, as data."""

    name: str
    policy_reference: str | None


class InsurerIn(BaseModel):
    """The insurer as typed, on the typer's yes for exactly these words
    (`POST /confirmations`, subject `insurer`). No name takes the insurer off the card."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    policy_reference: str | None = Field(default=None, min_length=1, max_length=40)
    confirmation_id: uuid.UUID


class InsurerSetOut(BaseModel):
    insurer_id: uuid.UUID
    name: str | None
    policy_reference: str | None
    set_by_person_id: uuid.UUID
    set_at: datetime


class NamedOut(BaseModel):
    code: str
    words: str
    fact_id: uuid.UUID


class EmergencyCardOut(BaseModel):
    """The card: the data a stranger needs, and the verified lines that say it in his
    language. `state_id` is the snapshot it was rendered from; `card_id` the render."""

    card_id: uuid.UUID
    profile_id: uuid.UUID
    state_id: uuid.UUID
    rendered_at: datetime
    name: str
    language: str
    spoken_language: str
    age_band: str | None
    conditions: list[NamedOut]
    medicines: list[MedicineOut]
    allergies: list[NamedOut]
    blood_type: str | None
    high_risk: list[str]
    contacts: list[ContactOut]
    clinic: ClinicOut | None
    last_reading_at: datetime | None
    emergency_number: str
    lines: list[LineOut]
    insurer: InsurerOut | None = None
    english_lines: list[LineOut] = []
    """The same lines in English when `language` is not English (E13-01): one card in two
    languages, so the ambulance crew reads what he reads. Empty when the card is English."""

    @classmethod
    def of(cls, card: Card) -> EmergencyCardOut:
        return cls(
            card_id=card.card_id,
            profile_id=card.profile_id,
            state_id=card.state_id,
            rendered_at=card.rendered_at,
            name=card.name,
            language=card.language,
            spoken_language=card.spoken_language,
            age_band=card.age_band,
            conditions=[
                NamedOut(code=c.code, words=c.words, fact_id=c.fact_id) for c in card.conditions
            ],
            medicines=[
                MedicineOut(
                    line_id=m.line_id,
                    generic=m.generic,
                    brand=m.brand,
                    strength=m.strength,
                    form=m.form,
                    plain_name=m.plain_name,
                    amount=m.amount,
                    when=m.when,
                    high_risk=m.high_risk,
                    high_risk_class=m.high_risk_class,
                )
                for m in card.medicines
            ],
            allergies=[
                NamedOut(code=a.code, words=a.words, fact_id=a.fact_id) for a in card.allergies
            ],
            blood_type=card.blood_type,
            high_risk=card.high_risk,
            contacts=[
                ContactOut(person_id=c.person_id, name=c.name, phone_e164=c.phone_e164, role=c.role)
                for c in card.contacts
            ],
            clinic=None
            if card.clinic is None
            else ClinicOut(
                provider_id=card.clinic.provider_id,
                name=card.clinic.name,
                kind=card.clinic.kind,
                phone_e164=card.clinic.phone_e164,
            ),
            last_reading_at=card.last_reading_at,
            emergency_number=card.emergency_number,
            lines=[LineOut(id=line.id, text=line.text) for line in card.lines],
            insurer=None
            if card.insurer is None
            else InsurerOut(name=card.insurer.name, policy_reference=card.insurer.policy_reference),
            english_lines=[LineOut(id=line.id, text=line.text) for line in card.english_lines],
        )


class WhatToDoOut(BaseModel):
    """The what-to-do-now card and what was written on the way to it. `lines[0]` is the
    first thing he reads or hears. `card_id`/`state_id` are null when the key could not
    compute State (no card row was written); `artifact_id`/`event_id`/`fact_id` are null
    when the key holds no record to write the moment into. The flag and the notices are
    there whoever pressed."""

    card_id: uuid.UUID | None
    state_id: uuid.UUID | None
    kind: WhatToDoKind
    posture: Posture | None
    language: str
    lines: list[LineOut]
    artifact_id: uuid.UUID | None
    event_id: uuid.UUID | None
    fact_id: uuid.UUID | None
    heard: bool
    by_voice: bool
    transcript_confidence: float
    red_flags: list[str]
    suppressed: list[str]
    symptoms: list[str]
    flag_id: uuid.UUID | None
    notified_person_ids: list[uuid.UUID]
    check_in_at: datetime | None
    missed_medicine: str | None

    @classmethod
    def of(cls, done: WhatToDoNow) -> WhatToDoOut:
        return cls(
            card_id=done.card_id,
            state_id=done.state_id,
            kind=done.kind,
            posture=done.posture,
            language=done.language,
            lines=[LineOut(id=line.id, text=line.text) for line in done.lines],
            artifact_id=done.artifact_id,
            event_id=done.event_id,
            fact_id=done.fact_id,
            heard=done.heard,
            by_voice=done.by_voice,
            transcript_confidence=done.transcript_confidence,
            red_flags=[one.value for one in done.red_flags],
            suppressed=[one.value for one in done.suppressed],
            symptoms=[one.value for one in done.symptoms],
            flag_id=done.flag_id,
            notified_person_ids=done.notified_person_ids,
            check_in_at=done.check_in_at,
            missed_medicine=done.missed_medicine,
        )


class SymptomEntryOut(BaseModel):
    fact_id: uuid.UUID
    event_id: uuid.UUID | None
    artifact_id: uuid.UUID | None
    at: datetime
    symptoms: list[str]
    red_flags: list[str]
    severity: int | None
    severity_words: str | None
    duration: str | None
    by_voice: bool
    heard: bool
    confidence: float
    lines: list[LineOut]

    @classmethod
    def of(cls, entry: Entry, severity_words: str | None) -> SymptomEntryOut:
        return cls(
            fact_id=entry.fact_id,
            event_id=entry.event_id,
            artifact_id=entry.artifact_id,
            at=entry.at,
            symptoms=[one.value for one in entry.symptoms],
            red_flags=[one.value for one in entry.red_flags],
            severity=entry.severity,
            severity_words=severity_words,
            duration=None if entry.duration is None else entry.duration.value,
            by_voice=entry.by_voice,
            heard=entry.heard,
            confidence=entry.confidence,
            lines=[LineOut(id=line.id, text=line.text) for line in entry.lines],
        )


class SymptomLoggedOut(BaseModel):
    entry: SymptomEntryOut
    posture: Posture | None
    flag_id: uuid.UUID | None
    notified_person_ids: list[uuid.UUID]
    suppressed: list[str]
    card: list[LineOut] | None = None
    """What he is shown next, in order: a red flag's urgent card (the button's), or the table's
    call-the-clinic card when what he said was "quite a lot", a day or more, or a new medicine's
    watch-out (E13-02). None otherwise."""

    @classmethod
    def of(cls, logged: Logged, severity_words: str | None) -> SymptomLoggedOut:
        return cls(
            entry=SymptomEntryOut.of(logged.entry, severity_words),
            posture=logged.posture,
            flag_id=logged.flag_id,
            notified_person_ids=logged.notified_person_ids,
            suppressed=[one.value for one in logged.suppressed],
            card=None
            if logged.card is None
            else [LineOut(id=line.id, text=line.text) for line in logged.card],
        )


class SymptomLogOut(BaseModel):
    since: datetime
    entries: list[SymptomEntryOut]
    lines: list[LineOut]
    """Every entry's lines in order, or the one line for an empty log."""

    @classmethod
    def of(
        cls, since: datetime, entries: list[SymptomEntryOut], empty_line: str | None
    ) -> SymptomLogOut:
        lines = [line for entry in entries for line in entry.lines]
        if not lines and empty_line is not None:
            lines = [LineOut(id="sym.none", text=empty_line)]
        return cls(since=since, entries=entries, lines=lines)


class OfflineCardsOut(BaseModel):
    """What the phone keeps for when it cannot reach Nura: two fixed cards, each its verified
    lines in order. `red_flag` for a red word tapped with no network; `unknown` for the button
    pressed with no network. Nothing was written and nobody was told when either is shown."""

    language: str
    emergency_number: str
    red_flag: list[LineOut]
    unknown: list[LineOut]

    @classmethod
    def of(cls, cards: OfflineCards) -> OfflineCardsOut:
        return cls(
            language=cards.language,
            emergency_number=cards.emergency_number,
            red_flag=[LineOut(id=line.id, text=line.text) for line in cards.red_flag],
            unknown=[LineOut(id=line.id, text=line.text) for line in cards.unknown],
        )


__all__: list[str] = [
    "EmergencyCardOut",
    "OfflineCardsOut",
    "SaidIn",
    "SymptomLogOut",
    "SymptomLoggedOut",
    "WhatToDoOut",
]

_ = Any
