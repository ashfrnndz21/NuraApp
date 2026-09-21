"""Checkpoint 3, "What it means for you" (`docs/design/experience-blueprint.html`, scene
`insight`): the moment a paper is confirmed, Nura connects it to the person's own record —
his medicines, his other results of the same analytes, his next visit — and offers back
questions for the doctor, never advice.

This reuses the Health Analyst's own machinery start to finish, the same gate every weekly
candidate already passes: `app.reasoning.analyst.pipeline.Candidate`/`finalize` is the one
safety check every candidate here goes through too, and a candidate that would touch a
medicine and fails it is rerouted through `app.reasoning.analyst.rule.ask_the_doctor` — the
same reroute the weekly report uses, never a second safety path. The Claude path (`app.
channels.api.analyst`) reuses `app.reasoning.analyst.claude_adapter.ClaudeAnalyst`'s own
`_ask_claude`/`_rebuild` unchanged: this module only builds a `Report`-shaped pool of
already rule-finalised candidates for that adapter to choose and rephrase from, so the cite
check and the `EXTERNAL_MODEL_PROCESSOR` audit line stay the analyst's own.

Values are compared only with the range printed on the paper itself (`_printed_range`),
never a guideline table: a fact's own embedded `range` where a sibling builder's shape has
landed, else the legacy sibling fact `{attribute}_reference_range` this backend writes today
(`app.llm.prompts.extract_document.txt`) — both shapes are read, so this module does not
care which one is on a given profile.

`read_phase` is the one half of this module that touches the database; it never calls a
model. The caller (`app.channels.api.analyst`) is the one that structures the three short
units of work a stream needs — reads, then the model call with no session open at all, then
the rebuild and the save — so no database transaction is ever open while a model call is in
flight (the defect `app.delivery.feed.background`'s own docstring describes: a synchronous
model call blocking the one event loop, and by extension a connection, for as long as it
takes).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.access import audited_read
from app.channels.about_him import Reader
from app.db import as_utc, utcnow
from app.delivery import analyst_strings as words
from app.drugs.registry import DrugRegistry, UnknownDrug
from app.errors import Refusal
from app.ingestion.models import ReviewCard, ReviewField
from app.ingestion.review import card_fields
from app.keys.context import KeyContext
from app.keys.scopes import Scope, scope_for_subject
from app.medicines.models import LineStatus, MedicationLine
from app.medicines.strings import PLAIN_NAME
from app.memory.models import Appointment
from app.memory.semantic import current_facts
from app.memory.spine import upcoming_appointments
from app.reasoning.analyst.pipeline import Candidate, finalize
from app.reasoning.analyst.port import AskWho, Confidence, Evidence, Insight, InsightKind
from app.reasoning.analyst.rule import ask_the_doctor
from app.safety.boundary import Surface, boundary_lines

REPORT_KEY = "questions_for_the_doctor"
"""The one section name a *saved* paper-scoped insight carries (`app.reasoning.analyst.
paper_service._section_json`) — cosmetic, read back by `questions_of` alone."""

CANDIDATE_SECTION_KEY = "paper_candidates"
"""The section key `app.channels.api.analyst._paper_events` puts the rule-finalised
candidates under before handing them to `ClaudeAnalyst`'s own `_ask_claude`/`_rebuild`
(`app.reasoning.analyst.claude_adapter`) — deliberately never
`app.reasoning.analyst.rule.QUESTIONS_KEY`: `_rebuild` treats that one key as the weekly
report's own rollup and always skips it, rebuilding it instead from what its other five
sections kept (its own docstring). A paper-scoped run has no other sections to roll up from,
so its own candidates must sit under an ordinary key `_rebuild` actually rebuilds."""


class NotAConfirmedPaper(Refusal):
    """No confirmed paper by this id on this profile — an unconfirmed card and another
    profile's artifact both refuse in these same words (404), the same standing `NoKey`
    already holds to (`app.keys.context`): neither should be told apart by what comes back.
    A key without RECORDS is turned away earlier and differently: `audited_read` requires
    the scope before it ever runs the query, so that case is `OutOfScope` (403), from
    `app.keys.context.KeyContext.require`, never this refusal."""


class PaperStepKey(StrEnum):
    """One real read behind a paper-scoped insight, in the order it happens."""

    PAPER = "paper"
    MEDICINES = "medicines"
    HISTORY = "history"
    VISIT = "visit"


@dataclass(frozen=True, slots=True)
class PaperStep:
    key: PaperStepKey
    label: str


@dataclass(frozen=True, slots=True)
class LookedAt:
    kind: str
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class ReadResult:
    """Everything the read phase produced: finalised candidates (`pipeline.finalize` and,
    where a medicine one failed, `ask_the_doctor` already ran), ready either to become the
    insight as-is (rule mode) or to be shown to Claude to choose and rephrase from."""

    paper_label: str
    questions: tuple[Insight, ...]
    looked_at: tuple[LookedAt, ...]
    withheld: tuple[str, ...]


PaperReadEvent = PaperStep | ReadResult


@dataclass(frozen=True, slots=True)
class PaperInsight:
    """The finished, paper-scoped insight: a headline, what was actually read, and 1-4
    questions for the doctor — never a diagnosis, never advice."""

    report_id: str
    generated_at: datetime
    language: str
    source: str
    boundary: tuple[str, ...]
    headline: str
    looked_at: tuple[LookedAt, ...]
    questions: tuple[Insight, ...]
    withheld: tuple[str, ...]


_RANGE_RE = re.compile(
    r"^\s*(?:"
    r"(?P<le><=|<)\s*(?P<hi1>-?\d+(?:\.\d+)?)"
    r"|(?P<ge>>=|>)\s*(?P<lo1>-?\d+(?:\.\d+)?)"
    r"|(?P<lo2>-?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(?P<hi2>-?\d+(?:\.\d+)?)"
    r")\s*$"
)
"""A printed lab range, as a lab prints it: "<130", ">=40", "3.5-5.5", "3.5 to 5.5". Whatever
does not match this small, literal set is read as no range at all — never guessed at."""


def _parse_printed_range(text: str) -> tuple[float | None, float | None] | None:
    match = _RANGE_RE.match(text)
    if match is None:
        return None
    if match.group("hi1") is not None:
        return (None, float(match.group("hi1")))
    if match.group("lo1") is not None:
        return (float(match.group("lo1")), None)
    if match.group("lo2") is not None and match.group("hi2") is not None:
        return (float(match.group("lo2")), float(match.group("hi2")))
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _printed_range(
    value: Any, sibling: Any, *, field_range: Mapping[str, Any] | None = None
) -> tuple[float | None, float | None] | None:
    """The range printed beside one value on the paper, in whichever shape this profile's own
    rows carry it — read in this order, the first that answers wins:

    1. `field_range` — `app.ingestion.models.ReviewField.range` (defect #3, #292): `{"low":
       number|null, "high": number|null, "text": string}`, already parsed by the confirm
       flow itself (`app.ingestion.extract.fold_legacy_reference_ranges`), the shape every
       confirm from here on carries. Bounds are read straight off it — never reparsed —
       *unless* neither bound parsed there either (both `None`, an unambiguous or compound
       range the extractor itself could not reduce to numbers); then `text` is tried here
       too, on the chance it is one of this module's own literal shapes after all.
    2. A `range` already embedded on the fact's own `value` (a sibling shape no confirm here
       writes yet, kept for forward compatibness — `{"value": 140, "range": "<130"}`).
    3. The legacy sibling fact this backend wrote before #292 (`{attribute}_reference_range`,
       a plain string) — a card confirmed on an older build, still on someone's record.

    None of the three needs to have landed for the others to work.
    """
    if field_range is not None:
        low, high = field_range.get("low"), field_range.get("high")
        if isinstance(low, int | float) or isinstance(high, int | float):
            return (
                float(low) if isinstance(low, int | float) else None,
                float(high) if isinstance(high, int | float) else None,
            )
        text = field_range.get("text")
        if isinstance(text, str):
            parsed = _parse_printed_range(text)
            if parsed is not None:
                return parsed
    if isinstance(value, Mapping) and "range" in value:
        embedded = value.get("range")
        if isinstance(embedded, str):
            return _parse_printed_range(embedded)
        return None
    if isinstance(sibling, str):
        return _parse_printed_range(sibling)
    return None


def _band(value: float, bounds: tuple[float | None, float | None]) -> str | None:
    low, high = bounds
    if low is not None and value < low:
        return "below"
    if high is not None and value > high:
        return "above"
    return None


ANALYTE_DRUG_CLASS_HINTS: dict[str, tuple[str, ...]] = {
    "ldl": ("statin",),
    "cholesterol": ("statin",),
    "hdl": ("statin",),
    "triglycerides": ("statin", "fibrate"),
    "hba1c": ("biguanide", "sulfonylurea", "insulin"),
    "glucose": ("biguanide", "sulfonylurea", "insulin"),
    "potassium": ("ace_inhibitor", "arb", "diuretic"),
    "tsh": ("thyroid",),
}
"""A small heuristic, not a clinical claim, the same standing `app.reasoning.analyst.rule.
SUPPLEMENT_INDICATIONS` already holds: which drug classes are commonly relevant to a lab
analyte, used only to decide whether a value worth asking about is also worth citing a
medicine beside — never to say the medicine is right or wrong."""


def _plain_name(registry: DrugRegistry | None, generic: str, language: str) -> str:
    if registry is not None:
        try:
            return PLAIN_NAME[language][registry.monograph(generic).plain_name_id]
        except (UnknownDrug, KeyError):
            pass
    return generic


_DETERMINER_PREFIX: dict[str, tuple[str, ...]] = {"en": ("your ", "the "), "zh": ("您的",)}
_DETERMINER_SUFFIX: dict[str, tuple[str, ...]] = {"ms": (" anda",)}


def _bare_word(plain: str, language: str) -> str:
    """`plain` with whatever determiner it already carries stripped off — a medicine's plain
    name (`app.medicines.strings.PLAIN_NAME`, "your insulin") or a lab value's plain label
    (`words.ANALYTE_PLAIN_LABEL`, mirrored word for word from the web's own report table
    catalogue, "the bad cholesterol", "your body salt") — so a caller's own "my"/"{patient}'s"
    (or the Malay/Chinese equivalent) is never doubled onto it ("my the bad cholesterol", "my
    your insulin"). Every caller here (`PAPER_SINGLE_VALUE_*`, `PAPER_AGGREGATE_VALUE`,
    `PAPER_MEDICINE_QUESTION`) puts its own determiner around the bare word instead."""
    for prefix in _DETERMINER_PREFIX.get(language, ()):
        if plain.startswith(prefix):
            return plain[len(prefix) :]
    for suffix in _DETERMINER_SUFFIX.get(language, ()):
        if plain.endswith(suffix):
            return plain[: -len(suffix)]
    return plain


def _analyte_label(
    subject: str, attribute: str, *, label_on_paper: str | None, language: str
) -> str | None:
    """The plain word for one line of a lab paper — the same word the report table itself
    already shows for it (`words.ANALYTE_PLAIN_LABEL`, mirrored from the web's own report
    table catalogue), never the raw subject/attribute code, and never carrying that
    catalogue's own determiner into a question that supplies its own (`_bare_word`). Falls
    back to the paper's own printed label (`ReviewField.label_on_paper`) when this surface has
    no plain word for the code yet; `None` — never a code — when neither is there, so a caller
    can leave that one value out of a question rather than name it by its code."""
    table = words.ANALYTE_PLAIN_LABEL.get(language, words.ANALYTE_PLAIN_LABEL["en"])
    plain = table.get((subject, attribute))
    if plain:
        return _bare_word(plain, language)
    printed = (label_on_paper or "").strip()
    return _bare_word(printed, language) if printed else None


def _render(
    self_template: Mapping[str, str],
    theirs_template: Mapping[str, str],
    *,
    reader: Reader,
    language: str,
    **slots: object,
) -> str:
    """One of the card's own first-person questions, in the voice this key actually reads in
    — his own key gets `self_template` unchanged ("my", "I", "me"); anyone else's gets
    `theirs_template` with his name in `{patient}` — chosen here, explicitly, rather than left
    to `app.channels.about_him`'s generic pass: that pass only ever swaps a line that already
    says "you"/"your" (`TO_HIM`), which a first-person line never does (module docstring)."""
    if reader.his:
        return words.fill(self_template[language], **slots)
    return words.fill(theirs_template[language], patient=reader.name, **slots)


async def _confirmed_paper(
    session: AsyncSession, *, context: KeyContext, artifact_id: uuid.UUID
) -> ReviewCard:
    """The confirmed review card for this artifact, on this profile — or `NotAConfirmedPaper`
    for an unconfirmed card, another profile's artifact, or a key without RECORDS: all three
    read the same way an `audited_read` under RECORDS scoped to this profile already reads
    them, so none is told apart from another (`NoKey`'s own reasoning)."""
    found = await audited_read(
        session,
        ReviewCard,
        context,
        Scope.RECORDS,
        where=(ReviewCard.artifact_id == artifact_id,),
    )
    confirmed = [card for card in found if not card.is_open]
    if not confirmed:
        raise NotAConfirmedPaper(
            f"no confirmed paper {artifact_id} on profile {context.profile_id}"
        )
    return confirmed[0]


def _page_of(fields: Sequence[ReviewField], *, subject: str, attribute: str) -> int | None:
    for field in fields:
        if field.subject == subject and field.attribute == attribute:
            span = field.span
            if isinstance(span, Mapping):
                page = span.get("page")
                if isinstance(page, int):
                    return page
    return None


def _field_range_of(
    fields: Sequence[ReviewField], *, subject: str, attribute: str
) -> Mapping[str, Any] | None:
    """The matching `ReviewField.range` (defect #3, #292: `{"low", "high", "text"}`), the
    range as the confirm flow itself already parsed it off the paper — read here rather than
    reparsed, the current, primary shape `_printed_range` prefers."""
    for field in fields:
        if field.subject == subject and field.attribute == attribute and isinstance(field.range, Mapping):
            return field.range
    return None


def _evidence_label(paper_label: str, page: int | None) -> str:
    return f"{paper_label} (page {page})" if page is not None else paper_label


@dataclass(frozen=True, slots=True)
class _FlaggedValue:
    """One value on this paper found outside its own printed range — never compared with a
    guideline table, only the range printed on this paper itself."""

    fact_id: uuid.UUID
    subject: str
    attribute: str
    band: str
    """`"above"` or `"below"` — `_band`'s own two words."""
    label: str | None
    """The plain word for this line (`_analyte_label`), or `None` when this surface has
    neither a plain word for the code nor a label printed on the paper for it — a value this
    still counts toward "how many are outside range", but is never named by its raw code."""
    page: int | None


def _value_evidence(
    paper_label: str, artifact_id: uuid.UUID, flagged: _FlaggedValue
) -> tuple[Evidence, ...]:
    return (
        Evidence(
            kind="fact",
            id=str(flagged.fact_id),
            label=flagged.label or paper_label,
            scope=Scope.RECORDS,
        ),
        Evidence(
            kind="artifact",
            id=str(artifact_id),
            label=_evidence_label(paper_label, flagged.page),
            scope=Scope.RECORDS,
        ),
    )


async def _flagged_values(
    session: AsyncSession,
    *,
    context: KeyContext,
    card: ReviewCard,
    moment: datetime,
    language: str,
) -> list[_FlaggedValue]:
    """Every value on this paper found outside its own printed range, in the order the paper
    prints its fields.

    A paper can carry more than one kind of fact — a lab row under RECORDS beside a vital
    the confirm route turned into a READINGS reading (`app.ingestion.review`, the module
    doc's own example) — so each subject is read only where this key holds the scope it
    sits under (`scope_for_subject`); a subject outside the key's scopes is skipped, never a
    reason to refuse the whole insight."""
    fields = await card_fields(session, context=context, card_id=card.id)
    subjects = sorted(
        {
            field.subject
            for field in fields
            if context.allows(scope_for_subject(field.subject))
        }
    )
    flagged: list[_FlaggedValue] = []
    seen_facts: set[uuid.UUID] = set()
    for subject in subjects:
        facts = await current_facts(session, context=context, subject=subject, at=moment)
        by_attribute = {fact.attribute: fact for fact in facts if fact.artifact_id == card.artifact_id}
        for attribute, fact in by_attribute.items():
            if attribute.endswith(("_reference_range", "_flagged", "_date")):
                continue
            number = _number(fact.value)
            if number is None or fact.id in seen_facts:
                continue
            sibling = by_attribute.get(f"{attribute}_reference_range")
            field_range = _field_range_of(fields, subject=subject, attribute=attribute)
            bounds = _printed_range(
                fact.value,
                sibling.value if sibling is not None else None,
                field_range=field_range,
            )
            if bounds is None or (bounds[0] is None and bounds[1] is None):
                continue
            band = _band(number, bounds)
            if band is None:
                continue
            seen_facts.add(fact.id)
            page = _page_of(fields, subject=subject, attribute=attribute)
            label_on_paper = next(
                (
                    field.label_on_paper
                    for field in fields
                    if field.subject == subject and field.attribute == attribute
                ),
                None,
            )
            label = _analyte_label(subject, attribute, label_on_paper=label_on_paper, language=language)
            flagged.append(
                _FlaggedValue(
                    fact_id=fact.id, subject=subject, attribute=attribute, band=band, label=label, page=page
                )
            )
    return flagged


def _value_candidate(
    flagged: Sequence[_FlaggedValue],
    *,
    artifact_id: uuid.UUID,
    paper_label: str,
    reader: Reader,
    language: str,
) -> Candidate | None:
    """The card's own first question: one out-of-range value asks about that value by name;
    several ask, once, how many — never a question per value (the blueprint's own card asks
    about "four of my numbers", not four separate lines)."""
    if not flagged:
        return None
    why = _render(words.PAPER_VALUE_WHY, words.PAPER_VALUE_WHY_THEIRS, reader=reader, language=language)
    if len(flagged) == 1:
        only = flagged[0]
        if only.label is None:
            return None
        above = only.band == "above"
        template = words.PAPER_SINGLE_VALUE_ABOVE if above else words.PAPER_SINGLE_VALUE_BELOW
        template_theirs = (
            words.PAPER_SINGLE_VALUE_ABOVE_THEIRS if above else words.PAPER_SINGLE_VALUE_BELOW_THEIRS
        )
        text = _render(template, template_theirs, reader=reader, language=language, label=only.label)
        evidence = _value_evidence(paper_label, artifact_id, only)
        insight_id = f"paper_value:{only.fact_id}"
    else:
        text = _render(
            words.PAPER_AGGREGATE_VALUE, words.PAPER_AGGREGATE_VALUE_THEIRS,
            reader=reader, language=language, n=len(flagged),
        )
        evidence = tuple(e for one in flagged for e in _value_evidence(paper_label, artifact_id, one))
        insight_id = f"paper_values:{artifact_id}"
    return Candidate(
        insight_id=insight_id,
        kind=InsightKind.CHECK,
        text=text,
        ask_who=AskWho.DOCTOR,
        evidence=evidence,
        why_plain=why,
        confidence=Confidence.WORTH_A_LOOK,
    )


def _medicine_candidate(
    flagged: Sequence[_FlaggedValue],
    *,
    medicines: Sequence[MedicationLine],
    registry: DrugRegistry | None,
    artifact_id: uuid.UUID,
    paper_label: str,
    reader: Reader,
    language: str,
) -> Candidate | None:
    """The card's own second question, only when the engine already has the link
    (`ANALYTE_DRUG_CLASS_HINTS`) between one of the flagged values and a medicine he already
    takes — the first such pairing, in the order the paper prints its fields, never one
    question per medicine (so there is never a second one this line would need to be told
    apart from — `PAPER_MEDICINE_QUESTION` never names when it is taken)."""
    for value in flagged:
        hints = ANALYTE_DRUG_CLASS_HINTS.get(value.attribute, ())
        match = next(
            (line for line in medicines if line.drug_class in hints or line.generic.lower() in hints),
            None,
        )
        if match is None:
            continue
        plain = _plain_name(registry, match.generic, language)
        bare = _bare_word(plain, language)
        text = _render(
            words.PAPER_MEDICINE_QUESTION, words.PAPER_MEDICINE_QUESTION_THEIRS,
            reader=reader, language=language, medicine=bare,
        )
        fact_evidence = Evidence(
            kind="fact", id=str(value.fact_id), label=value.label or paper_label, scope=Scope.RECORDS
        )
        artifact_evidence = Evidence(
            kind="artifact",
            id=str(artifact_id),
            label=_evidence_label(paper_label, value.page),
            scope=Scope.RECORDS,
        )
        medicine_evidence = Evidence(kind="medication_line", id=str(match.id), label=plain)
        return Candidate(
            insight_id=f"paper_medicine:{match.id}",
            kind=InsightKind.MEDICINE,
            text=text,
            ask_who=AskWho.DOCTOR,
            evidence=(fact_evidence, artifact_evidence, medicine_evidence),
            why_plain=words.PAPER_MEDICINE_WHY[language],
            confidence=Confidence.WORTH_A_LOOK,
        )
    return None


def _retest_candidate(
    flagged: Sequence[_FlaggedValue], *, artifact_id: uuid.UUID, paper_label: str, language: str
) -> Candidate | None:
    """The card's own closing question — always, once anything at all is outside range. Names
    no person, so the same line serves either voice (`PAPER_RETEST_QUESTION` carries no
    `_THEIRS` twin)."""
    if not flagged:
        return None
    evidence = tuple(
        Evidence(kind="fact", id=str(one.fact_id), label=one.label or paper_label, scope=Scope.RECORDS)
        for one in flagged
    )
    return Candidate(
        insight_id=f"paper_retest:{artifact_id}",
        kind=InsightKind.CHECK,
        text=words.PAPER_RETEST_QUESTION[language],
        ask_who=AskWho.DOCTOR,
        evidence=evidence,
        why_plain=words.PAPER_REPEAT_WHY[language],
        confidence=Confidence.WORTH_A_LOOK,
    )


async def read_phase(
    session: AsyncSession,
    *,
    context: KeyContext,
    artifact_id: uuid.UUID,
    language: str,
    reader: Reader,
    registry: DrugRegistry | None = None,
    now: datetime | None = None,
) -> Any:
    """An async generator: a `PaperStep` the instant each real read finishes, then one
    `ReadResult`, last. Never calls a model — see the module docstring. `reader` is the same
    one the caller already resolved (`app.channels.about_him.reader_of`) to say a step's own
    label about him or not; the card's own first-person questions need it too, to choose
    between "my"/"I" and his name explicitly rather than leaving it to the generic pass that
    resolves everything else here (`_render`'s own docstring)."""
    moment = now if now is not None else utcnow()
    card = await _confirmed_paper(session, context=context, artifact_id=artifact_id)
    paper_label = words.LOOKED_AT_LABEL[language]["paper"]
    yield PaperStep(PaperStepKey.PAPER, words.PAPER_STEP_LABEL[language]["paper"])

    looked_at = [LookedAt(kind="artifact", id=str(artifact_id), label=paper_label)]
    withheld: list[str] = []

    medicines: list[MedicationLine] = []
    if context.allows(Scope.MEDICINES):
        medicines = list(
            await audited_read(
                session,
                MedicationLine,
                context,
                Scope.MEDICINES,
                where=(
                    MedicationLine.superseded_at.is_(None),
                    MedicationLine.status == LineStatus.ACTIVE,
                ),
            )
        )
        yield PaperStep(PaperStepKey.MEDICINES, words.PAPER_STEP_LABEL[language]["medicines"])
        if medicines:
            looked_at.append(
                LookedAt(
                    kind="medicines",
                    id=",".join(str(line.id) for line in medicines),
                    label=words.fill(
                        words.LOOKED_AT_LABEL[language]["medicines"], count=len(medicines)
                    ),
                )
            )
    else:
        withheld.append("medicines_and_supplements")

    flagged = await _flagged_values(session, context=context, card=card, moment=moment, language=language)
    yield PaperStep(PaperStepKey.HISTORY, words.PAPER_STEP_LABEL[language]["history"])

    next_visit: Appointment | None = None
    if context.allows(Scope.VISITS):
        upcoming = await upcoming_appointments(session, context=context, at=moment)
        ordered = sorted(upcoming, key=lambda visit: (as_utc(visit.scheduled_at), str(visit.id)))
        next_visit = ordered[0] if ordered else None
        yield PaperStep(PaperStepKey.VISIT, words.PAPER_STEP_LABEL[language]["visit"])
        if next_visit is not None:
            looked_at.append(
                LookedAt(
                    kind="appointment",
                    id=str(next_visit.id),
                    label=words.LOOKED_AT_LABEL[language]["visit"],
                )
            )

    candidates: list[Candidate] = []
    value_candidate = _value_candidate(
        flagged, artifact_id=artifact_id, paper_label=paper_label, reader=reader, language=language
    )
    if value_candidate is not None:
        candidates.append(value_candidate)
    medicine_candidate = _medicine_candidate(
        flagged,
        medicines=medicines,
        registry=registry,
        artifact_id=artifact_id,
        paper_label=paper_label,
        reader=reader,
        language=language,
    )
    if medicine_candidate is not None:
        candidates.append(medicine_candidate)
    retest_candidate = _retest_candidate(
        flagged, artifact_id=artifact_id, paper_label=paper_label, language=language
    )
    if retest_candidate is not None:
        candidates.append(retest_candidate)

    async def reroute(candidate: Candidate) -> Insight | None:
        return await ask_the_doctor(session, context, language, candidate)

    questions = [
        insight
        for candidate in candidates
        if (insight := await finalize(candidate, language=language, reroute=reroute)) is not None
    ]

    yield ReadResult(
        paper_label=paper_label,
        questions=tuple(questions),
        looked_at=tuple(looked_at),
        withheld=tuple(withheld),
    )


def build_insight(
    *,
    language: str,
    source: str,
    questions: Sequence[Insight],
    looked_at: Sequence[LookedAt],
    withheld: Sequence[str],
    now: datetime,
) -> PaperInsight:
    headline = (
        words.PAPER_HEADLINE[language] if questions else words.PAPER_NOTHING_LINE[language]
    )
    return PaperInsight(
        report_id=str(uuid.uuid4()),
        generated_at=now,
        language=language,
        source=source,
        boundary=boundary_lines(Surface.INSIGHT, language, doctor=None),
        headline=headline,
        looked_at=tuple(looked_at),
        questions=tuple(questions[:4]),
        withheld=tuple(withheld),
    )


__all__ = [
    "ANALYTE_DRUG_CLASS_HINTS",
    "CANDIDATE_SECTION_KEY",
    "REPORT_KEY",
    "LookedAt",
    "NotAConfirmedPaper",
    "PaperInsight",
    "PaperReadEvent",
    "PaperStep",
    "PaperStepKey",
    "ReadResult",
    "build_insight",
    "read_phase",
]
