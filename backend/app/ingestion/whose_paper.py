"""D-2, "whose paper is it" — the safety half of package 7a (`docs/design/build-spec.md`,
"Owner requirement added 2026-09-22"): before any fact is written from a review card, the
card's own identity fields are compared against the profile's own. Deterministic rules only,
exactly as the requirement demands ("the model never decides identity") — nothing here reads
an extraction confidence or calls a model; a name is a string, a year is a number, a sex is
one of two words, and every comparison is plain code a person could read and check.

The comparison this module runs is narrower than the full owner requirement (national ID,
the facility's own patient number across visits, impossible dates) — see the module's own
`IdentitySignal` for exactly the four fields it checks: name, patient id, birth year, sex.
Extending it to the fuller set is future work, tracked in the audit (D-2) and the build spec;
this module's job is the part every downstream reasoning path already depends on being right
— `person.birth_year` and `person.sex` must never be written from a paper that was not
compared first (`review.py:_write_paper`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.extract import ExtractedField
from app.keys.context import KeyContext
from app.memory.models import ConfidenceState
from app.memory.semantic import current_facts

PERSON = "person"
LAB_REPORT = "lab_report"

_WHITESPACE = re.compile(r"\s+")
_SPLIT = re.compile(r"[\s,]+")


class IdentityOutcome(StrEnum):
    """The four outcomes the build spec names. `MATCH`/`LIKELY_MATCH` file without a
    question; `MISMATCH` asks; `CANNOT_TELL` — no identifying line on the paper at all —
    files, saying so once (not this module's job; the caller decides what "saying so" means).
    This module only ever returns `MATCH` or `MISMATCH`: a paper with nothing to compare has
    nothing to mismatch on, so it is `MATCH` by default, and the finer `LIKELY_MATCH`/
    `CANNOT_TELL` distinction is left to a later pass (see the module docstring)."""

    MATCH = "match"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class IdentitySignal:
    """One field the card and the profile disagree on."""

    kind: str
    """`"name"`, `"patient_id"`, `"birth_year"` or `"sex"`."""
    paper_value: Any
    profile_value: Any


@dataclass(frozen=True, slots=True)
class IdentityCheck:
    outcome: IdentityOutcome
    mismatches: tuple[IdentitySignal, ...]
    paper_name: str | None
    paper_birth_year: int | None
    paper_sex: str | None


def _normalise_name(name: str) -> str:
    return _WHITESPACE.sub(" ", name.strip().lower())


def _name_tokens(name: str) -> list[str]:
    return [tok for tok in _SPLIT.split(_normalise_name(name)) if tok]


def names_match(paper_name: str, profile_name: str) -> bool:
    """Tolerant to case, spacing and an initial standing in for a full given name — "M Lim"
    for "Mary Lim", "mary   lim" for "Mary Lim" — never tolerant to a different surname: every
    token of the shorter name must appear in the longer name, as itself or as the other's
    leading initial, or this is a mismatch. No edit-distance or phonetic fuzzing — a genuinely
    different name must never pass as "close enough"."""
    paper_tokens, profile_tokens = _name_tokens(paper_name), _name_tokens(profile_name)
    if not paper_tokens or not profile_tokens:
        return False
    if paper_tokens == profile_tokens:
        return True
    shorter, longer = (
        (paper_tokens, profile_tokens)
        if len(paper_tokens) <= len(profile_tokens)
        else (profile_tokens, paper_tokens)
    )

    def _one_matches(a: str, b: str) -> bool:
        return a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))

    remaining = list(longer)
    for token in shorter:
        hit = next((other for other in remaining if _one_matches(token, other)), None)
        if hit is None:
            return False
        remaining.remove(hit)
    return True


def _field(fields: Sequence[ExtractedField], subject: str, attribute: str) -> ExtractedField | None:
    return next((f for f in fields if f.subject == subject and f.attribute == attribute), None)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _birth_year_on_paper(fields: Sequence[ExtractedField], *, document_date: date | None) -> int | None:
    """The paper's own year of birth, read directly if it printed one, else worked out from a
    printed age and the paper's own date — the same "age on the date of that paper" logic
    `app.reasoning.trends.birth_decade` already uses for the record's own facts."""
    born = _field(fields, PERSON, "birth_year")
    if born is not None:
        return _int_or_none(born.value)
    aged = _field(fields, PERSON, "age")
    years = _int_or_none(aged.value) if aged is not None else None
    if years is not None and document_date is not None and 0 < years < 130:
        return document_date.year - years
    return None


async def check_whose_paper(
    session: AsyncSession,
    *,
    context: KeyContext,
    fields: Sequence[ExtractedField],
    document_date: date | None,
    profile_display_name: str,
) -> IdentityCheck:
    """Compare the card's own identity fields against the profile's: its display name, and
    whatever `person.birth_year`/`person.sex` and `lab_report.patient_id` the record already
    holds, confirmed by a person before (`ConfidenceState.CONFIRMED_BY_PERSON` facts only —
    never a earlier paper's own unconfirmed guess). A field the profile has nothing on file
    for cannot mismatch: there is nothing to compare it to, so it is skipped, exactly as the
    build spec's `cannot_tell` reasons about a paper with nothing identifying at all, applied
    field by field instead of paper by paper."""
    mismatches: list[IdentitySignal] = []

    paper_name_field = _field(fields, LAB_REPORT, "patient_name")
    paper_name = paper_name_field.value if isinstance(getattr(paper_name_field, "value", None), str) else None
    if paper_name and profile_display_name:
        if not names_match(paper_name, profile_display_name):
            mismatches.append(IdentitySignal("name", paper_name, profile_display_name))

    paper_id_field = _field(fields, LAB_REPORT, "patient_id")
    paper_patient_id = paper_id_field.value if isinstance(getattr(paper_id_field, "value", None), str) else None
    if paper_patient_id:
        known_ids = await current_facts(session, context=context, subject=LAB_REPORT, attribute="patient_id")
        confirmed_ids = {
            str(f.value).strip().lower()
            for f in known_ids
            if isinstance(f.value, str) and f.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
        }
        if confirmed_ids and paper_patient_id.strip().lower() not in confirmed_ids:
            mismatches.append(IdentitySignal("patient_id", paper_patient_id, sorted(confirmed_ids)[0]))

    paper_birth_year = _birth_year_on_paper(fields, document_date=document_date)
    if paper_birth_year is not None:
        known_years = await current_facts(session, context=context, subject=PERSON, attribute="birth_year")
        confirmed_years = [
            _int_or_none(f.value)
            for f in known_years
            if f.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
        ]
        confirmed_years = [y for y in confirmed_years if y is not None]
        if confirmed_years:
            # A year or two of slack: a lab's printed age is often rounded, and a birthday
            # inside the gap between two papers moves the computed year by exactly one.
            known_year = confirmed_years[-1]
            if abs(paper_birth_year - known_year) > 2:
                mismatches.append(IdentitySignal("birth_year", paper_birth_year, known_year))

    paper_sex_field = _field(fields, PERSON, "sex")
    paper_sex = (
        paper_sex_field.value.strip().lower()
        if isinstance(getattr(paper_sex_field, "value", None), str)
        else None
    )
    if paper_sex in {"male", "female"}:
        known_sexes = await current_facts(session, context=context, subject=PERSON, attribute="sex")
        confirmed_sexes = {
            f.value.strip().lower()
            for f in known_sexes
            if isinstance(f.value, str) and f.confidence_state is ConfidenceState.CONFIRMED_BY_PERSON
        }
        confirmed_sexes = {s for s in confirmed_sexes if s in {"male", "female"}}
        if confirmed_sexes and paper_sex not in confirmed_sexes:
            mismatches.append(IdentitySignal("sex", paper_sex, sorted(confirmed_sexes)[0]))

    outcome = IdentityOutcome.MISMATCH if mismatches else IdentityOutcome.MATCH
    return IdentityCheck(
        outcome=outcome,
        mismatches=tuple(mismatches),
        paper_name=paper_name,
        paper_birth_year=paper_birth_year,
        paper_sex=paper_sex,
    )


__all__ = [
    "IdentityCheck",
    "IdentityOutcome",
    "IdentitySignal",
    "check_whose_paper",
    "names_match",
]
